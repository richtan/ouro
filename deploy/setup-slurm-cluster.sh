#!/usr/bin/env bash
set -euo pipefail

PROJECT="${GCP_PROJECT:-ouro-hpc-2026}"
ZONE="${GCP_ZONE:-us-central1-a}"
CONTROLLER="${SLURM_CONTROLLER:-ouro-slurm}"
WORKERS=("ouro-worker-1" "ouro-worker-2")
# Controller (ouro-slurm) should be e2-small; provision separately.
MACHINE_TYPE="e2-medium"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SLURM_DIR="$SCRIPT_DIR/slurm"

ssh_cmd() {
    local host="$1"; shift
    gcloud compute ssh "$host" --project="$PROJECT" --zone="$ZONE" --command="$*" 2>&1
}

scp_to() {
    local src="$1" host="$2" dest="$3"
    gcloud compute scp "$src" "$host:$dest" --project="$PROJECT" --zone="$ZONE" 2>&1
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

echo "============================================"
echo " Ouro HPC Cluster Setup"
echo " Controller: $CONTROLLER"
echo " Workers:    ${WORKERS[*]}"
echo "============================================"

# ------------------------------------------------------------------
# Phase 1: Create worker VMs
# ------------------------------------------------------------------
echo ""
echo "[Phase 1] Creating worker VMs..."

for w in "${WORKERS[@]}"; do
    if gcloud compute instances describe "$w" --project="$PROJECT" --zone="$ZONE" &>/dev/null; then
        echo "  $w already exists, skipping creation"
    else
        echo "  Creating $w ($MACHINE_TYPE)..."
        gcloud compute instances create "$w" \
            --project="$PROJECT" \
            --zone="$ZONE" \
            --machine-type="$MACHINE_TYPE" \
            --image-family="$IMAGE_FAMILY" \
            --image-project="$IMAGE_PROJECT" \
            --boot-disk-size=20GB \
            --tags=slurm-worker \
            --metadata=startup-script='#!/bin/bash
                apt-get update -qq
                apt-get install -y -qq munge slurmd slurm-client nfs-common software-properties-common
                add-apt-repository -y ppa:apptainer/ppa
                apt-get update -qq
                apt-get install -y -qq apptainer'
    fi
done

echo "  Waiting for VMs to accept SSH..."
for w in "${WORKERS[@]}"; do
    wait_for_ssh "$w" 30
done

# ------------------------------------------------------------------
# Phase 2: Collect internal IPs and build /etc/hosts
# ------------------------------------------------------------------
echo ""
echo "[Phase 2] Collecting internal IPs..."

echo "  Verifying controller SSH..."
wait_for_ssh "$CONTROLLER" 30

CONTROLLER_IP=$(gcloud compute instances describe "$CONTROLLER" \
    --project="$PROJECT" --zone="$ZONE" \
    --format="get(networkInterfaces[0].networkIP)")
echo "  $CONTROLLER -> $CONTROLLER_IP"

declare -A WORKER_IPS
for w in "${WORKERS[@]}"; do
    ip=$(gcloud compute instances describe "$w" \
        --project="$PROJECT" --zone="$ZONE" \
        --format="get(networkInterfaces[0].networkIP)")
    WORKER_IPS[$w]=$ip
    echo "  $w -> $ip"
done

HOSTS_BLOCK="
# Ouro HPC cluster
$CONTROLLER_IP  $CONTROLLER
"
for w in "${WORKERS[@]}"; do
    HOSTS_BLOCK+="${WORKER_IPS[$w]}  $w
"
done

ALL_NODES=("$CONTROLLER" "${WORKERS[@]}")

echo ""
echo "[Phase 2b] Distributing /etc/hosts entries..."
for node in "${ALL_NODES[@]}"; do
    ssh_cmd "$node" "sudo bash -c 'grep -q \"Ouro HPC cluster\" /etc/hosts || echo \"$HOSTS_BLOCK\" >> /etc/hosts'"
    echo "  $node done"
done

# ------------------------------------------------------------------
# Phase 3: Install packages on controller (Apptainer if missing)
# ------------------------------------------------------------------
echo ""
echo "[Phase 3] Ensuring packages on controller..."

ssh_cmd "$CONTROLLER" "
    if ! command -v apptainer &>/dev/null; then
        echo 'Installing Apptainer on controller...'
        sudo add-apt-repository -y ppa:apptainer/ppa
        sudo apt-get update -qq
        sudo apt-get install -y -qq apptainer
    else
        echo 'Apptainer already installed'
    fi
    sudo apt-get install -y -qq nfs-kernel-server
"

# ------------------------------------------------------------------
# Phase 4: Wait for worker startup scripts to finish, verify packages
# ------------------------------------------------------------------
echo ""
echo "[Phase 4] Verifying worker packages..."

for w in "${WORKERS[@]}"; do
    echo "  Waiting for $w packages..."
    for attempt in $(seq 1 30); do
        if ssh_cmd "$w" "dpkg -l | grep -q slurmd && command -v apptainer" &>/dev/null; then
            echo "  $w ready"
            break
        fi
        if [ "$attempt" -eq 30 ]; then
            echo "  $w: retrying manual install..."
            ssh_cmd "$w" "
                sudo apt-get update -qq
                sudo apt-get install -y -qq munge slurmd slurm-client nfs-common
                sudo add-apt-repository -y ppa:apptainer/ppa
                sudo apt-get update -qq
                sudo apt-get install -y -qq apptainer
            "
        fi
        sleep 10
    done
done

# ------------------------------------------------------------------
# Phase 5: Set up NFS shared filesystem
# ------------------------------------------------------------------
echo ""
echo "[Phase 5] Setting up NFS shared filesystem..."

ssh_cmd "$CONTROLLER" "
    sudo mkdir -p /ouro-jobs/output /ouro-jobs/scripts /ouro-jobs/images
    sudo chown -R nobody:nogroup /ouro-jobs
    sudo chmod -R 777 /ouro-jobs

    if ! grep -q '/ouro-jobs' /etc/exports 2>/dev/null; then
        echo '/ouro-jobs *(rw,sync,no_subtree_check,no_root_squash)' | sudo tee -a /etc/exports
        sudo exportfs -ra
    fi
    sudo systemctl restart nfs-kernel-server
"

for w in "${WORKERS[@]}"; do
    ssh_cmd "$w" "
        sudo mkdir -p /ouro-jobs
        if ! grep -q '/ouro-jobs' /etc/fstab; then
            echo '$CONTROLLER_IP:/ouro-jobs /ouro-jobs nfs defaults 0 0' | sudo tee -a /etc/fstab
        fi
        sudo mount -a || sudo mount $CONTROLLER_IP:/ouro-jobs /ouro-jobs
    "
    echo "  $w NFS mounted"
done

# ------------------------------------------------------------------
# Phase 6: Distribute munge key
# ------------------------------------------------------------------
echo ""
echo "[Phase 6] Distributing munge key..."

MUNGE_TMP=$(mktemp)
gcloud compute ssh "$CONTROLLER" --project="$PROJECT" --zone="$ZONE" \
    --command="sudo cat /etc/munge/munge.key" 2>/dev/null > "$MUNGE_TMP"

for w in "${WORKERS[@]}"; do
    scp_to "$MUNGE_TMP" "$w" "/tmp/munge.key"
    ssh_cmd "$w" "
        sudo cp /tmp/munge.key /etc/munge/munge.key
        sudo chown munge:munge /etc/munge/munge.key
        sudo chmod 400 /etc/munge/munge.key
        sudo systemctl restart munge
        sudo systemctl enable munge
    "
    echo "  $w munge configured"
done
rm -f "$MUNGE_TMP"

# ------------------------------------------------------------------
# Phase 7: Distribute Slurm configuration
# ------------------------------------------------------------------
echo ""
echo "[Phase 7] Distributing Slurm configuration..."

for node in "${ALL_NODES[@]}"; do
    scp_to "$SLURM_DIR/slurm.conf" "$node" "/tmp/slurm.conf"
    scp_to "$SLURM_DIR/cgroup.conf" "$node" "/tmp/cgroup.conf"
    ssh_cmd "$node" "
        sudo cp /tmp/slurm.conf /etc/slurm/slurm.conf
        sudo cp /tmp/cgroup.conf /etc/slurm/cgroup.conf
        sudo chown slurm:slurm /etc/slurm/slurm.conf /etc/slurm/cgroup.conf
    "
    echo "  $node config updated"
done

# Copy JWT key to workers
JWT_TMP=$(mktemp)
gcloud compute ssh "$CONTROLLER" --project="$PROJECT" --zone="$ZONE" \
    --command="sudo cat /etc/slurm/jwt_hs256.key" 2>/dev/null > "$JWT_TMP"

for w in "${WORKERS[@]}"; do
    scp_to "$JWT_TMP" "$w" "/tmp/jwt_hs256.key"
    ssh_cmd "$w" "
        sudo cp /tmp/jwt_hs256.key /etc/slurm/jwt_hs256.key
        sudo chown slurm:slurm /etc/slurm/jwt_hs256.key
        sudo chmod 600 /etc/slurm/jwt_hs256.key
    "
    echo "  $w JWT key distributed"
done
rm -f "$JWT_TMP"

# ------------------------------------------------------------------
# Phase 8: Create Slurm spool directories on workers
# ------------------------------------------------------------------
echo ""
echo "[Phase 8] Setting up Slurm directories on workers..."

for w in "${WORKERS[@]}"; do
    ssh_cmd "$w" "
        sudo mkdir -p /var/spool/slurmd /var/log/slurm /run
        sudo chown slurm:slurm /var/spool/slurmd /var/log/slurm
    "
done

# ------------------------------------------------------------------
# Phase 9: Build Apptainer base image
# ------------------------------------------------------------------
echo ""
echo "[Phase 9] Building Apptainer base image..."

ssh_cmd "$CONTROLLER" "
    if [ ! -f /ouro-jobs/images/base.sif ]; then
        echo 'Building base.sif from ubuntu:22.04...'
        sudo apptainer build /ouro-jobs/images/base.sif docker://ubuntu:22.04
        sudo chmod 644 /ouro-jobs/images/base.sif
    else
        echo 'base.sif already exists'
    fi
"

# ------------------------------------------------------------------
# Phase 9b: Custom image cache dir + sudoers for apptainer build
# ------------------------------------------------------------------
echo ""
echo "[Phase 9b] Setting up custom image cache and build permissions..."

ssh_cmd "$CONTROLLER" "
    sudo mkdir -p /ouro-jobs/images/custom
    sudo chmod 755 /ouro-jobs/images/custom

    # Allow the proxy service user to run apptainer build without a password
    if [ ! -f /etc/sudoers.d/ouro-apptainer ]; then
        echo 'ALL ALL=(root) NOPASSWD: /usr/bin/apptainer build *' | sudo tee /etc/sudoers.d/ouro-apptainer > /dev/null
        sudo chmod 440 /etc/sudoers.d/ouro-apptainer
        echo 'sudoers entry for apptainer build added'
    else
        echo 'sudoers entry already exists'
    fi
"

# ------------------------------------------------------------------
# Phase 10: Update proxy on controller
# ------------------------------------------------------------------
echo ""
echo "[Phase 10] Deploying updated Slurm proxy..."

scp_to "$SLURM_DIR/slurm_proxy.py" "$CONTROLLER" "/tmp/slurm_proxy.py"
ssh_cmd "$CONTROLLER" "
    sudo cp /tmp/slurm_proxy.py /opt/slurmrest/slurm_proxy.py
"

# ------------------------------------------------------------------
# Phase 11: Restart all services
# ------------------------------------------------------------------
echo ""
echo "[Phase 11] Restarting services..."

ssh_cmd "$CONTROLLER" "
    sudo systemctl restart munge
    sudo systemctl restart slurmctld
    sudo systemctl restart slurmd
    sudo systemctl restart slurm-proxy
"
echo "  Controller services restarted"

for w in "${WORKERS[@]}"; do
    ssh_cmd "$w" "
        sudo systemctl restart munge
        sudo systemctl enable slurmd
        sudo systemctl restart slurmd
    "
    echo "  $w slurmd restarted"
done

sleep 5

# ------------------------------------------------------------------
# Phase 12: Clear stale state and undrain nodes
# ------------------------------------------------------------------
echo ""
echo "[Phase 12] Clearing stale Slurm state..."

ssh_cmd "$CONTROLLER" "
    sudo scancel --state=PENDING --full 2>/dev/null || true

    for node in $CONTROLLER ${WORKERS[*]}; do
        state=\$(sinfo -n \"\$node\" -h -o '%T' 2>/dev/null || echo 'unknown')
        if echo \"\$state\" | grep -qiE 'drain|down'; then
            echo \"  Undrain \$node (was \$state)\"
            sudo scontrol update NodeName=\"\$node\" State=IDLE Reason='setup-script-reset'
        fi
    done
"

echo "  Waiting for nodes to settle..."
for attempt in $(seq 1 12); do
    idle_count=$(ssh_cmd "$CONTROLLER" "sinfo -h -o '%T' | grep -c 'idle'" 2>/dev/null || echo 0)
    if [ "$idle_count" -ge "${#ALL_NODES[@]}" ]; then
        echo "  All ${#ALL_NODES[@]} nodes idle"
        break
    fi
    if [ "$attempt" -eq 12 ]; then
        echo "  WARNING: Not all nodes reached idle state after 60s"
        ssh_cmd "$CONTROLLER" "sinfo"
    fi
    sleep 5
done

# ------------------------------------------------------------------
# Phase 13: Verify cluster
# ------------------------------------------------------------------
echo ""
echo "[Phase 13] Verifying cluster..."
echo ""
echo "--- sinfo ---"
ssh_cmd "$CONTROLLER" "sinfo"
echo ""
echo "--- scontrol show nodes ---"
ssh_cmd "$CONTROLLER" "scontrol show nodes | grep -E 'NodeName|State|CPUs|RealMemory'"
echo ""
echo "--- Test job ---"
ssh_cmd "$CONTROLLER" "timeout 30 srun --nodes=1 hostname" || echo "  WARNING: test job did not complete within 30s"
echo ""
echo "--- Apptainer test ---"
ssh_cmd "$CONTROLLER" "timeout 30 apptainer exec /ouro-jobs/images/base.sif echo 'Container isolation working'" || echo "  WARNING: apptainer test did not complete within 30s"
echo ""

echo "============================================"
echo " Cluster setup complete!"
echo " Controller: $CONTROLLER ($CONTROLLER_IP)"
for w in "${WORKERS[@]}"; do
    echo " Worker:     $w (${WORKER_IPS[$w]})"
done
echo " Nodes:      ${#ALL_NODES[@]}"
echo " Isolation:  Apptainer containers"
echo " Shared FS:  /ouro-jobs (NFS)"
echo "============================================"
