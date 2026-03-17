#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-ouro-hpc-2026}"
ZONE="${GCP_ZONE:-us-central1-a}"
CONTROLLER="${SLURM_CONTROLLER:-ouro-slurm}"
WORKERS=("ouro-worker-1" "ouro-worker-2")
ALL_NODES=("$CONTROLLER" "${WORKERS[@]}")

ssh_cmd() {
    local host="$1"; shift
    gcloud compute ssh "$host" --project="$PROJECT" --zone="$ZONE" --command="$*" 2>&1
}

wait_for_ssh() {
    local host="$1" max_attempts="${2:-30}"
    for attempt in $(seq 1 "$max_attempts"); do
        if gcloud compute ssh "$host" --project="$PROJECT" --zone="$ZONE" \
            --command="true" --ssh-flag="-o ConnectTimeout=5" &>/dev/null; then
            return 0
        fi
        echo "  Waiting for $host SSH... (attempt $attempt/$max_attempts)"
        sleep 10
    done
    echo "  ERROR: $host SSH not reachable after $max_attempts attempts"
    return 1
}

cmd_status() {
    echo "=== GCP Instances ==="
    gcloud compute instances list --project="$PROJECT" \
        --filter="name~ouro" \
        --format="table(name,status,zone,networkInterfaces[0].networkIP,networkInterfaces[0].accessConfigs[0].natIP)"
    echo ""

    # Check if controller is running before SSHing
    CTRL_STATUS=$(gcloud compute instances describe "$CONTROLLER" \
        --project="$PROJECT" --zone="$ZONE" \
        --format="get(status)" 2>/dev/null || echo "NOT_FOUND")

    if [ "$CTRL_STATUS" != "RUNNING" ]; then
        echo "Controller is $CTRL_STATUS — cannot query Slurm state"
        return
    fi

    echo "=== Slurm Nodes ==="
    ssh_cmd "$CONTROLLER" "sinfo -N -l 2>/dev/null" || echo "  slurmctld not responding"
    echo ""

    echo "=== Running Jobs ==="
    ssh_cmd "$CONTROLLER" "squeue 2>/dev/null" || echo "  slurmctld not responding"
    echo ""

    echo "=== Proxy Health ==="
    ssh_cmd "$CONTROLLER" "curl -s http://localhost:6820/health 2>/dev/null" || echo "  slurm-proxy not responding"
    echo ""

    CTRL_IP=$(gcloud compute instances describe "$CONTROLLER" \
        --project="$PROJECT" --zone="$ZONE" \
        --format="get(networkInterfaces[0].accessConfigs[0].natIP)")
    echo "SLURMREST_URL: http://${CTRL_IP}:6820"
}

cmd_start() {
    echo "=== Starting Slurm Cluster ==="

    # 1. Start all instances in parallel
    echo ""
    echo "[1/5] Starting GCP instances..."
    for node in "${ALL_NODES[@]}"; do
        STATUS=$(gcloud compute instances describe "$node" \
            --project="$PROJECT" --zone="$ZONE" \
            --format="get(status)" 2>/dev/null || echo "NOT_FOUND")
        if [ "$STATUS" = "RUNNING" ]; then
            echo "  $node already running"
        else
            echo "  Starting $node..."
            gcloud compute instances start "$node" --project="$PROJECT" --zone="$ZONE" --quiet &
        fi
    done
    wait
    echo "  All start commands issued"

    # 2. Wait for SSH on all nodes
    echo ""
    echo "[2/5] Waiting for SSH..."
    for node in "${ALL_NODES[@]}"; do
        wait_for_ssh "$node" 30
        echo "  $node ready"
    done

    # 3. Start services on controller (restart munge to pick up any key changes)
    echo ""
    echo "[3/6] Starting controller services..."
    ssh_cmd "$CONTROLLER" "
        sudo systemctl start nfs-kernel-server
        sudo systemctl restart munge
        sudo systemctl restart slurmctld
        sudo systemctl restart slurmd
        sudo systemctl restart slurm-proxy
    "
    echo "  Controller services started"

    # 4. Sync slurm.conf and munge key from controller to workers via NFS
    echo ""
    echo "[4/6] Syncing config to workers..."
    ssh_cmd "$CONTROLLER" "
        sudo cp /etc/slurm/slurm.conf /ouro-jobs/_slurm.conf.sync
        sudo cp /etc/munge/munge.key /ouro-jobs/_munge.key.sync
        sudo chmod 644 /ouro-jobs/_slurm.conf.sync /ouro-jobs/_munge.key.sync
    "

    # 5. Mount NFS, apply synced config, and start services on workers
    echo ""
    echo "[5/6] Starting worker services..."
    for w in "${WORKERS[@]}"; do
        ssh_cmd "$w" "
            # Remount NFS (handles stale mounts from previous session)
            sudo umount -l /ouro-jobs 2>/dev/null || true
            sudo umount -l /ouro-storage 2>/dev/null || true
            sudo mount -a 2>/dev/null || true

            # Sync slurm.conf and munge key from controller
            sudo cp /ouro-jobs/_slurm.conf.sync /etc/slurm/slurm.conf
            sudo chown slurm:slurm /etc/slurm/slurm.conf
            sudo cp /ouro-jobs/_munge.key.sync /etc/munge/munge.key
            sudo chown munge:munge /etc/munge/munge.key
            sudo chmod 400 /etc/munge/munge.key

            sudo systemctl restart munge
            sudo systemctl restart slurmd
        "
        echo "  $w synced and started"
    done

    # Clean up sync files
    ssh_cmd "$CONTROLLER" "sudo rm -f /ouro-jobs/_slurm.conf.sync /ouro-jobs/_munge.key.sync"

    # 6. Undrain nodes and verify
    echo ""
    echo "[6/6] Bringing nodes online..."
    ssh_cmd "$CONTROLLER" "
        for node in $CONTROLLER ${WORKERS[*]}; do
            state=\$(sinfo -n \"\$node\" -h -o '%T' 2>/dev/null || echo 'unknown')
            if echo \"\$state\" | grep -qiE 'drain|down'; then
                echo \"  Undrain \$node (was \$state)\"
                sudo scontrol update NodeName=\"\$node\" State=IDLE Reason='slurm.sh-start'
            fi
        done
    "

    # Wait for nodes to become idle (sinfo -N gives one line per node)
    for attempt in $(seq 1 12); do
        idle_count=$(ssh_cmd "$CONTROLLER" "sinfo -N -h -o '%T' | grep -ci 'idle'" 2>/dev/null || echo 0)
        # Strip any non-numeric chars (SSH warnings)
        idle_count=$(echo "$idle_count" | grep -oE '[0-9]+' | tail -1 || echo 0)
        idle_count="${idle_count:-0}"
        if [ "$idle_count" -ge "${#ALL_NODES[@]}" ]; then
            echo "  All ${#ALL_NODES[@]} nodes idle"
            break
        fi
        if [ "$attempt" -eq 12 ]; then
            echo "  WARNING: Not all nodes reached idle state after 60s"
            ssh_cmd "$CONTROLLER" "sinfo -N -l"
        fi
        sleep 5
    done

    # Report IP and update Railway if needed
    CTRL_IP=$(gcloud compute instances describe "$CONTROLLER" \
        --project="$PROJECT" --zone="$ZONE" \
        --format="get(networkInterfaces[0].accessConfigs[0].natIP)")
    echo ""
    echo "  Controller external IP: $CTRL_IP"
    echo "  SLURMREST_URL: http://${CTRL_IP}:6820"

    if command -v railway &>/dev/null; then
        echo "  Updating SLURMREST_URL in Railway..."
        railway variable set "SLURMREST_URL=http://${CTRL_IP}:6820" -s agent 2>/dev/null && \
            echo "  Railway SLURMREST_URL updated" || \
            echo "  WARNING: Failed to update Railway variable (are you logged in?)"
    else
        echo "  NOTE: Install railway CLI to auto-update SLURMREST_URL"
    fi

    # Quick health check
    echo ""
    echo "=== Health Check ==="
    ssh_cmd "$CONTROLLER" "curl -s http://localhost:6820/health" || echo "  WARNING: proxy health check failed"
    echo ""
    ssh_cmd "$CONTROLLER" "timeout 15 srun --nodes=1 hostname" && echo "  Test job: OK" || echo "  WARNING: test job failed"

    echo ""
    echo "=== Cluster Started ==="
}

cmd_stop() {
    echo "=== Stopping Slurm Cluster ==="

    # Check controller is running
    CTRL_STATUS=$(gcloud compute instances describe "$CONTROLLER" \
        --project="$PROJECT" --zone="$ZONE" \
        --format="get(status)" 2>/dev/null || echo "NOT_FOUND")

    if [ "$CTRL_STATUS" = "RUNNING" ]; then
        # 1. Drain nodes to prevent new jobs
        echo ""
        echo "[1/4] Draining nodes..."
        ssh_cmd "$CONTROLLER" "
            for node in $CONTROLLER ${WORKERS[*]}; do
                sudo scontrol update NodeName=\"\$node\" State=DRAIN Reason='slurm.sh-stop' 2>/dev/null || true
            done
        "
        echo "  Nodes drained"

        # 2. Wait for running jobs to finish (up to 60s)
        echo ""
        echo "[2/4] Waiting for running jobs to finish..."
        for attempt in $(seq 1 12); do
            job_count=$(ssh_cmd "$CONTROLLER" "squeue -h -t RUNNING 2>/dev/null | wc -l" 2>/dev/null || echo 0)
            job_count=$(echo "$job_count" | grep -oE '[0-9]+' | tail -1 || echo 0)
            job_count="${job_count:-0}"
            if [ "$job_count" -eq 0 ]; then
                echo "  No running jobs"
                break
            fi
            if [ "$attempt" -eq 12 ]; then
                echo "  WARNING: $job_count jobs still running after 60s — they will be recovered as failed on next start"
                ssh_cmd "$CONTROLLER" "squeue" 2>/dev/null || true
            else
                echo "  $job_count jobs still running (waiting ${attempt}/12)..."
                sleep 5
            fi
        done

        # 3. Stop services
        echo ""
        echo "[3/4] Stopping services..."
        ssh_cmd "$CONTROLLER" "
            sudo systemctl stop slurm-proxy 2>/dev/null || true
            sudo systemctl stop slurmctld 2>/dev/null || true
            sudo systemctl stop slurmd 2>/dev/null || true
            sudo systemctl stop munge 2>/dev/null || true
        "
        echo "  Controller services stopped"

        for w in "${WORKERS[@]}"; do
            ssh_cmd "$w" "
                sudo systemctl stop slurmd 2>/dev/null || true
                sudo systemctl stop munge 2>/dev/null || true
            " 2>/dev/null || true
            echo "  $w services stopped"
        done
    else
        echo "  Controller is $CTRL_STATUS — skipping service shutdown"
    fi

    # 4. Stop all instances
    echo ""
    echo "[4/4] Stopping GCP instances..."
    for node in "${ALL_NODES[@]}"; do
        STATUS=$(gcloud compute instances describe "$node" \
            --project="$PROJECT" --zone="$ZONE" \
            --format="get(status)" 2>/dev/null || echo "NOT_FOUND")
        if [ "$STATUS" = "TERMINATED" ] || [ "$STATUS" = "STOPPED" ]; then
            echo "  $node already stopped"
        else
            echo "  Stopping $node..."
            gcloud compute instances stop "$node" --project="$PROJECT" --zone="$ZONE" --quiet &
        fi
    done
    wait
    echo ""
    echo "=== Cluster Stopped ==="
    echo "  Running jobs (if any) will be recovered as failed with credit on next start."
}

cmd_ssh() {
    exec gcloud compute ssh "$CONTROLLER" --project="$PROJECT" --zone="$ZONE"
}

# --- Main ---
case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_stop; echo ""; cmd_start ;;
    status)  cmd_status ;;
    ssh)     cmd_ssh ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|ssh}"
        echo ""
        echo "Commands:"
        echo "  start    Start instances, services, undrain nodes, update SLURMREST_URL"
        echo "  stop     Drain nodes, wait for jobs, stop services, stop instances"
        echo "  restart  Stop then start"
        echo "  status   Show instance status, Slurm state, proxy health"
        echo "  ssh      SSH into controller"
        exit 1
        ;;
esac
