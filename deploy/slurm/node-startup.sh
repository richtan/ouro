#!/usr/bin/env bash
# Runs on each spot instance boot. Joins the Slurm cluster automatically.
set -euo pipefail

LOG_TAG="ouro-node-init"
log() { logger -t "$LOG_TAG" "$*"; echo "$*"; }

# 1. Get our hostname (matches the GCP instance name, which is the Slurm node name)
NODE_NAME=$(curl -sf -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/name)
log "Node: $NODE_NAME"

# 2. Get controller IP from project metadata
CONTROLLER_IP=$(curl -sf -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/project/attributes/ouro-controller-ip)
log "Controller: $CONTROLLER_IP"

# 3. Update /etc/hosts
grep -q "ouro-slurm" /etc/hosts || echo "$CONTROLLER_IP ouro-slurm" >> /etc/hosts

# 4. Mount NFS (needed for keys and config)
mkdir -p /ouro-jobs
if ! mountpoint -q /ouro-jobs; then
  mount -t nfs -o timeo=10,retrans=3 ouro-slurm:/ouro-jobs /ouro-jobs
fi
log "NFS mounted"

# 5. Install Docker if not present
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker slurm
    cat > /etc/docker/daemon.json << 'EOF'
{
  "userns-remap": "default",
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
    systemctl enable docker && systemctl start docker
fi

# Block metadata server from Docker containers
iptables -I DOCKER-USER -d 169.254.169.254/32 -j DROP

# Pre-pull base images (in background for fast startup)
for img in ubuntu:22.04 python:3.12-slim node:20-slim; do
    docker pull -q "$img" &
done
wait
log "Docker ready, base images pulled"

# 6. Copy auth keys from NFS (placed there by setup-elastic-infra.sh)
cp /ouro-jobs/.cluster/munge.key /etc/munge/munge.key
chown munge:munge /etc/munge/munge.key
chmod 400 /etc/munge/munge.key

cp /ouro-jobs/.cluster/jwt_hs256.key /etc/slurm/jwt_hs256.key
chown slurm:slurm /etc/slurm/jwt_hs256.key
chmod 600 /etc/slurm/jwt_hs256.key
log "Auth keys copied from NFS"

# 7. Fetch latest slurm.conf from NFS
if [ -f /ouro-jobs/.cluster/slurm.conf ]; then
  cp /ouro-jobs/.cluster/slurm.conf /etc/slurm/slurm.conf
  log "Copied fresh slurm.conf from NFS"
else
  log "WARN: No slurm.conf on NFS, using baked-in copy"
fi

# 8. Start services
systemctl restart munge
systemctl restart slurmd
sleep 2

# 9. Tell Slurm we're ready (must run as root for auth)
scontrol update NodeName="$NODE_NAME" State=IDLE Reason="spot-booted"
log "Node $NODE_NAME is IDLE and ready for jobs"
