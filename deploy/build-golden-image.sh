#!/usr/bin/env bash
# Build a GCP custom image ("golden image") for Ouro Slurm worker nodes.
# This image has all packages pre-installed so spot instances boot fast.
#
# Usage: ./deploy/build-golden-image.sh [--image-name ouro-worker-v2]
#
# The image is used by the auto-scaler when creating new spot instances.
# Rebuild when: Slurm version changes, Docker updates, or slurm.conf changes.
set -euo pipefail

PROJECT="${GCP_PROJECT:-ouro-hpc-2026}"
ZONE="${GCP_ZONE:-us-central1-a}"
IMAGE_NAME="${1:-ouro-worker-v1}"
TEMP_VM="golden-image-builder"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Building golden image: $IMAGE_NAME"

# 1. Create temporary VM
gcloud compute instances create "$TEMP_VM" \
  --project="$PROJECT" --zone="$ZONE" \
  --machine-type=e2-medium \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB

# Wait for SSH
for i in $(seq 1 30); do
  gcloud compute ssh "$TEMP_VM" --project="$PROJECT" --zone="$ZONE" \
    --command="true" --ssh-flag="-o ConnectTimeout=5" &>/dev/null && break
  sleep 10
done

# 2. Install all packages
gcloud compute ssh "$TEMP_VM" --project="$PROJECT" --zone="$ZONE" --command="
  # Fix corrupted apt sources and enable universe/multiverse repos
  sudo sed -i '/^[a-z]-/d' /etc/apt/sources.list
  sudo add-apt-repository -y universe
  sudo add-apt-repository -y multiverse
  sudo apt-get update -qq
  sudo apt-get install -y -qq munge slurmd slurm-client nfs-common
  # Install Docker
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker slurm
  sudo cat > /etc/docker/daemon.json << 'DOCKEREOF'
{
  "userns-remap": "default",
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
DOCKEREOF
  sudo systemctl enable docker

  # Pre-pull base images into golden image so spot instances skip the pull
  sudo systemctl start docker
  sudo docker pull ubuntu:22.04
  sudo docker pull python:3.12-slim
  sudo docker pull node:20-slim
  sudo systemctl stop docker

  # Install gcloud CLI (needed by startup script to fetch secrets)
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
  echo 'deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main' | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
  sudo apt-get update -qq
  sudo apt-get install -y -qq google-cloud-cli

  # Create required directories
  sudo mkdir -p /var/spool/slurmd /var/log/slurm /ouro-jobs
  sudo chown slurm:slurm /var/spool/slurmd /var/log/slurm
"

# 3. Copy Slurm config files
gcloud compute scp "$SCRIPT_DIR/slurm/slurm.conf" "$TEMP_VM:/tmp/slurm.conf" \
  --project="$PROJECT" --zone="$ZONE"
gcloud compute scp "$SCRIPT_DIR/slurm/cgroup.conf" "$TEMP_VM:/tmp/cgroup.conf" \
  --project="$PROJECT" --zone="$ZONE"
gcloud compute scp "$SCRIPT_DIR/slurm/node-startup.sh" "$TEMP_VM:/tmp/node-startup.sh" \
  --project="$PROJECT" --zone="$ZONE"
gcloud compute scp "$SCRIPT_DIR/slurm/node-shutdown.sh" "$TEMP_VM:/tmp/node-shutdown.sh" \
  --project="$PROJECT" --zone="$ZONE"
gcloud compute scp "$SCRIPT_DIR/slurm/docker-cleanup.sh" "$TEMP_VM:/tmp/docker-cleanup.sh" \
  --project="$PROJECT" --zone="$ZONE"

gcloud compute ssh "$TEMP_VM" --project="$PROJECT" --zone="$ZONE" --command="
  sudo cp /tmp/slurm.conf /etc/slurm/slurm.conf
  sudo cp /tmp/cgroup.conf /etc/slurm/cgroup.conf
  sudo cp /tmp/node-startup.sh /opt/ouro-node-startup.sh
  sudo cp /tmp/node-shutdown.sh /opt/ouro-node-shutdown.sh
  sudo cp /tmp/docker-cleanup.sh /opt/ouro-docker-cleanup.sh
  sudo chmod +x /opt/ouro-node-startup.sh /opt/ouro-node-shutdown.sh /opt/ouro-docker-cleanup.sh

  # Docker cleanup cron (every 6 hours)
  echo '0 */6 * * * /opt/ouro-docker-cleanup.sh 2>/dev/null' | sudo crontab -

  # Systemd service to run startup script on boot
  sudo tee /etc/systemd/system/ouro-node-init.service > /dev/null <<'UNIT'
[Unit]
Description=Ouro Slurm Node Initialization
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/ouro-node-startup.sh
RemainAfterExit=yes
StandardOutput=journal

[Install]
WantedBy=multi-user.target
UNIT
  sudo systemctl enable ouro-node-init.service

  # Shutdown hook for spot preemption
  sudo tee /etc/systemd/system/ouro-node-shutdown.service > /dev/null <<'UNIT'
[Unit]
Description=Ouro Slurm Node Graceful Shutdown
DefaultDependencies=no
Before=shutdown.target

[Service]
Type=oneshot
ExecStart=/opt/ouro-node-shutdown.sh

[Install]
WantedBy=shutdown.target
UNIT
  sudo systemctl enable ouro-node-shutdown.service

  # Clean up for image
  sudo apt-get clean
  sudo rm -rf /tmp/*
  sudo truncate -s 0 /var/log/*.log
"

# 4. Stop VM and create image
gcloud compute instances stop "$TEMP_VM" --project="$PROJECT" --zone="$ZONE"
gcloud compute images create "$IMAGE_NAME" \
  --project="$PROJECT" \
  --source-disk="$TEMP_VM" \
  --source-disk-zone="$ZONE" \
  --family=ouro-worker

# 5. Clean up temporary VM
gcloud compute instances delete "$TEMP_VM" --project="$PROJECT" --zone="$ZONE" --quiet

echo "Golden image created: $IMAGE_NAME"
