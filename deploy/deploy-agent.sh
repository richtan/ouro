#!/usr/bin/env bash
# Deploy the Ouro agent with Slurm URL auto-injected from GCP.
# Run from project root. Fetches controller IP, sets SLURMREST_URL, deploys.
#
# Prerequisites: gcloud configured, railway CLI logged in and linked.
set -euo pipefail

PROJECT="${GCP_PROJECT:-ouro-hpc-2026}"
ZONE="${GCP_ZONE:-us-central1-a}"
CONTROLLER="${SLURM_CONTROLLER:-ouro-slurm}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "Fetching Slurm controller external IP..."
CONTROLLER_IP=$(gcloud compute instances describe "$CONTROLLER" \
  --project="$PROJECT" \
  --zone="$ZONE" \
  --format="get(networkInterfaces[0].accessConfigs[0].natIP)" 2>/dev/null) || true

if [ -z "$CONTROLLER_IP" ]; then
  echo "ERROR: Could not get IP for $CONTROLLER. Is the instance running?"
  echo "  gcloud compute instances list --project=$PROJECT --filter=name=$CONTROLLER"
  exit 1
fi

SLURM_URL="http://${CONTROLLER_IP}:6820"
echo "  Controller: $CONTROLLER_IP -> $SLURM_URL"

echo "Setting SLURMREST_URL in Railway (agent service)..."
railway variable set "SLURMREST_URL=$SLURM_URL" -s agent

echo "Deploying agent..."
railway up agent --path-as-root --detach

echo "Done. Agent will use $SLURM_URL for Slurm."
