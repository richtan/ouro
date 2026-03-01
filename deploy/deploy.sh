#!/usr/bin/env bash
# Deploy all Ouro services to Railway.
# Fetches Slurm controller IP from GCP, sets SLURMREST_URL, then deploys
# agent, mcp-server, and dashboard in parallel.
#
# Secrets: Managed by Doppler → Railway integration (auto-synced).
# Only SLURMREST_URL is set here because it's dynamically fetched from GCP.
#
# Usage:
#   ./deploy/deploy.sh              # Deploy all services
#   ./deploy/deploy.sh agent mcp    # Deploy only agent and mcp-server
#
# Prerequisites: gcloud configured, railway CLI logged in and linked.
set -euo pipefail

PROJECT="${GCP_PROJECT:-ouro-hpc-2026}"
ZONE="${GCP_ZONE:-us-central1-a}"
CONTROLLER="${SLURM_CONTROLLER:-ouro-slurm}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

ALL_SERVICES=(agent mcp-server dashboard)

if [ $# -gt 0 ]; then
  SERVICES=()
  for arg in "$@"; do
    case "$arg" in
      agent)      SERVICES+=(agent) ;;
      mcp|mcp-server) SERVICES+=(mcp-server) ;;
      dash|dashboard) SERVICES+=(dashboard) ;;
      *) echo "Unknown service: $arg (valid: agent, mcp-server, dashboard)"; exit 1 ;;
    esac
  done
else
  SERVICES=("${ALL_SERVICES[@]}")
fi

echo "Services to deploy: ${SERVICES[*]}"

# Fetch Slurm controller IP if deploying agent
for svc in "${SERVICES[@]}"; do
  if [ "$svc" = "agent" ]; then
    echo ""
    echo "Fetching Slurm controller external IP..."
    CONTROLLER_IP=$(gcloud compute instances describe "$CONTROLLER" \
      --project="$PROJECT" \
      --zone="$ZONE" \
      --format="get(networkInterfaces[0].accessConfigs[0].natIP)" 2>/dev/null) || true

    if [ -z "$CONTROLLER_IP" ]; then
      echo "ERROR: Could not get IP for $CONTROLLER. Is the instance running?"
      echo "  gcloud compute instances list --project=$PROJECT --filter=name=$CONTROLLER"
      exit 1
    else
      SLURM_URL="http://${CONTROLLER_IP}:6820"
      echo "  Controller: $CONTROLLER_IP -> $SLURM_URL"
      echo "Setting SLURMREST_URL in Railway..."
      railway variable set "SLURMREST_URL=$SLURM_URL" -s agent
    fi
    break
  fi
done

# Deploy services (using -s flag to target correct service)
PIDS=()
for svc in "${SERVICES[@]}"; do
  echo ""
  echo "Deploying $svc..."
  railway up "$svc" --path-as-root --detach -s "$svc" &
  PIDS+=($!)
done

# Wait for all deploys
FAILED=0
for i in "${!PIDS[@]}"; do
  if ! wait "${PIDS[$i]}"; then
    echo "FAILED: ${SERVICES[$i]}"
    FAILED=1
  else
    echo "OK: ${SERVICES[$i]}"
  fi
done

echo ""
if [ $FAILED -eq 0 ]; then
  echo "All services deployed successfully."
else
  echo "Some services failed to deploy. Check railway logs."
  exit 1
fi
