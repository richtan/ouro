#!/usr/bin/env bash
# One-time setup for elastic auto-scaling infrastructure.
# Run after initial cluster setup, before enabling AUTO_SCALING_ENABLED.
set -euo pipefail

PROJECT="${GCP_PROJECT:-ouro-hpc-2026}"
ZONE="${GCP_ZONE:-us-central1-a}"
CONTROLLER="${SLURM_CONTROLLER:-ouro-slurm}"
REGION="${ZONE%-*}"  # us-central1

echo "Setting up elastic scaling infrastructure..."

# 1. Store secrets in Secret Manager
echo "[1/6] Storing secrets..."
CONTROLLER_IP=$(gcloud compute instances describe "$CONTROLLER" \
  --project="$PROJECT" --zone="$ZONE" \
  --format="get(networkInterfaces[0].networkIP)")

# Munge key (fetch from controller)
gcloud compute ssh "$CONTROLLER" --project="$PROJECT" --zone="$ZONE" \
  --command="sudo cat /etc/munge/munge.key" > /tmp/munge.key
gcloud secrets create ouro-munge-key --data-file=/tmp/munge.key \
  --project="$PROJECT" 2>/dev/null || \
gcloud secrets versions add ouro-munge-key --data-file=/tmp/munge.key \
  --project="$PROJECT"
rm /tmp/munge.key

# JWT key (fetch from controller)
gcloud compute ssh "$CONTROLLER" --project="$PROJECT" --zone="$ZONE" \
  --command="sudo cat /etc/slurm/jwt_hs256.key" > /tmp/jwt.key
gcloud secrets create ouro-jwt-key --data-file=/tmp/jwt.key \
  --project="$PROJECT" 2>/dev/null || \
gcloud secrets versions add ouro-jwt-key --data-file=/tmp/jwt.key \
  --project="$PROJECT"
rm /tmp/jwt.key

# 2. Store controller IP in project metadata
echo "[2/6] Setting project metadata..."
gcloud compute project-info add-metadata \
  --metadata=ouro-controller-ip="$CONTROLLER_IP" \
  --project="$PROJECT"

# 3. Create service account for spot instances
echo "[3/6] Creating service account..."
SA_NAME="ouro-spot-worker"
SA_EMAIL="$SA_NAME@$PROJECT.iam.gserviceaccount.com"

gcloud iam service-accounts create "$SA_NAME" \
  --display-name="Ouro Spot Worker" \
  --project="$PROJECT" 2>/dev/null || true

# Grant Secret Manager access
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor" --quiet

# Grant Compute metadata read
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/compute.viewer" --quiet

# 4. Create instance templates (one per size tier)
echo "[4/6] Creating instance templates..."
for tier in sm:e2-medium md:e2-standard-4 lg:e2-standard-8; do
  name="${tier%%:*}"
  machine="${tier##*:}"
  gcloud compute instance-templates create "ouro-spot-${name}-template" \
    --project="$PROJECT" \
    --machine-type="$machine" \
    --image-family=ouro-worker \
    --image-project="$PROJECT" \
    --boot-disk-size=20GB \
    --provisioning-model=SPOT \
    --instance-termination-action=STOP \
    --service-account="$SA_EMAIL" \
    --scopes=cloud-platform \
    --network-tags=slurm-worker \
    --no-address  # Internal IP only
done

# 5. Update NFS exports to allow VPC subnet (instead of per-IP)
echo "[5/6] Updating NFS exports..."
gcloud compute ssh "$CONTROLLER" --project="$PROJECT" --zone="$ZONE" --command="
  # Replace per-IP exports with subnet-based export
  sudo sed -i '/^\/ouro-jobs/d' /etc/exports
  echo '/ouro-jobs 10.128.0.0/20(rw,sync,no_subtree_check,root_squash)' | sudo tee -a /etc/exports
  sudo exportfs -ra
"

# 6. Copy slurm.conf to NFS for spot instances (avoids needing SSH keys)
echo "[6/6] Sharing slurm.conf via NFS..."
gcloud compute ssh "$CONTROLLER" --project="$PROJECT" --zone="$ZONE" --command="
  sudo mkdir -p /ouro-jobs/.cluster
  sudo cp /etc/slurm/slurm.conf /ouro-jobs/.cluster/slurm.conf
  sudo chmod 644 /ouro-jobs/.cluster/slurm.conf
  echo 'NOTE: Re-run this step after any slurm.conf changes'
"

echo ""
echo "Elastic infrastructure ready!"
echo "  Secrets: ouro-munge-key, ouro-jwt-key"
echo "  Metadata: ouro-controller-ip=$CONTROLLER_IP"
echo "  Templates: ouro-spot-sm-template, ouro-spot-md-template, ouro-spot-lg-template"
echo "  Service account: $SA_EMAIL"
echo ""
echo "Next: set AUTO_SCALING_ENABLED=true in the agent config"
