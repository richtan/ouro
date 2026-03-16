#!/usr/bin/env bash
set -euo pipefail

# ── Ouro local dev launcher ──────────────────────────────────────────
# Usage: ./dev.sh [--fresh] [--down] [compose args...]
#   --fresh    Drop DB volume and re-init from 01-init.sql + 02-seed.sql
#   --down     Stop and remove containers (add -v to also remove volumes)
#   --detach   Run in background (passed through to docker compose)
#   agent      Start only agent + postgres (passed through to docker compose)

GCP_PROJECT="${GCP_PROJECT:-ouro-hpc-2026}"
GCP_ZONE="${GCP_ZONE:-us-central1-a}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ────────────────────────────────────────────────────────────
red()    { printf '\033[0;31m%s\033[0m\n' "$*"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }
green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
bold()   { printf '\033[1m%s\033[0m\n' "$*"; }

# ── Parse args ────────────────────────────────────────────────────────
FRESH=false
DOWN=false
COMPOSE_ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--fresh" ]; then
    FRESH=true
  elif [ "$arg" = "--down" ]; then
    DOWN=true
  else
    COMPOSE_ARGS+=("$arg")
  fi
done

if [ "$DOWN" = true ]; then
  bold "Stopping Ouro containers..."
  docker compose down "${COMPOSE_ARGS[@]}"
  green "Done"
  exit 0
fi

# ── 1. Prerequisites ─────────────────────────────────────────────────
bold "Checking prerequisites..."

if ! command -v docker &>/dev/null; then
  red "Docker is not installed. Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
  exit 1
fi

if ! docker info &>/dev/null; then
  red "Docker daemon is not running. Start Docker Desktop and try again."
  exit 1
fi

if ! command -v doppler &>/dev/null; then
  red "Doppler CLI is not installed."
  echo "  Install: https://docs.doppler.com/docs/install-cli"
  exit 1
fi

if ! doppler me --json &>/dev/null; then
  red "Doppler is not authenticated."
  echo "  Run: doppler login && doppler setup"
  exit 1
fi

green "Prerequisites OK"

# ── 2. Slurm IP sync (best-effort) ───────────────────────────────────
if command -v gcloud &>/dev/null; then
  SLURM_IP=$(gcloud compute instances describe ouro-slurm \
    --project="$GCP_PROJECT" --zone="$GCP_ZONE" \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null || true)

  if [ -n "$SLURM_IP" ]; then
    export SLURMREST_URL="http://${SLURM_IP}:6820"
    green "Slurm IP synced: $SLURM_IP"

    # Persist to .env if it exists
    if [ -f .env ]; then
      if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s|^SLURMREST_URL=.*|SLURMREST_URL=$SLURMREST_URL|" .env
      else
        sed -i "s|^SLURMREST_URL=.*|SLURMREST_URL=$SLURMREST_URL|" .env
      fi
    fi
  else
    yellow "Warning: ouro-slurm instance appears stopped. Slurm won't be available."
  fi
else
  if [ -f .env ] && grep -q '^SLURMREST_URL=.' .env; then
    yellow "No gcloud CLI — using SLURMREST_URL from .env"
  else
    yellow "No gcloud CLI and no SLURMREST_URL in .env. Slurm won't be available."
  fi
fi

# ── 3. Port conflict detection ────────────────────────────────────────
find_free_port() {
  local port=$1 max=$2
  while [ "$port" -le "$max" ]; do
    if ! lsof -i :"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "$port"
      return 0
    fi
    port=$((port + 1))
  done
  return 1
}

# Check if a port has a non-Docker listener
port_has_conflict() {
  local port=$1
  # Get PIDs listening on the port
  local pids
  pids=$(lsof -i :"$port" -sTCP:LISTEN -F p 2>/dev/null | grep '^p' | sed 's/^p//' || true)
  [ -z "$pids" ] && return 1  # Nothing listening — no conflict

  # Check if all listeners are Docker
  for pid in $pids; do
    local cmd
    cmd=$(lsof -i :"$port" -sTCP:LISTEN -F pc 2>/dev/null | grep -A1 "^p${pid}$" | grep '^c' | sed 's/^c//' || true)
    if [[ "$cmd" != "com.docke"* ]]; then
      return 0  # Non-Docker process found — conflict
    fi
  done
  return 1  # All Docker — no conflict
}

# Check if Ouro compose containers are already running
OURO_RUNNING=$(docker compose ps --format '{{.Name}}' 2>/dev/null || true)
if [ -n "$OURO_RUNNING" ]; then
  yellow "Replacing existing Ouro containers..."
fi

check_and_resolve_port() {
  local name=$1 default=$2 range_start=$3 range_end=$4 env_var=$5

  if port_has_conflict "$default"; then
    local free
    if free=$(find_free_port "$range_start" "$range_end"); then
      yellow "Port $default in use — $name will use port $free"
      export "$env_var=$free"
    else
      red "Ports ${default}-${range_end} all in use. Free a port and retry."
      exit 1
    fi
  fi
}

check_and_resolve_port "Dashboard"  3000 3001 3010 DASHBOARD_PORT
check_and_resolve_port "Agent API"  8000 8001 8010 AGENT_PORT
check_and_resolve_port "Postgres"   5432 5433 5442 DB_EXPOSE_PORT

# ── 4. Handle --fresh ────────────────────────────────────────────────
if [ "$FRESH" = true ]; then
  yellow "Dropping DB volume for fresh init..."
  docker compose down -v
fi

# ── 5. Build MCP server ────────────────────────────────────────────
bold "Building MCP server..."
(cd mcp && npm install --silent && npm run build --silent)
green "MCP server ready → mcp/dist/index.js"

# ── 6. Launch ─────────────────────────────────────────────────────────
echo ""
bold "Starting Ouro..."
echo "  Dashboard:  http://localhost:${DASHBOARD_PORT:-3000}"
echo "  Agent API:  http://localhost:${AGENT_PORT:-8000}"
echo "  Postgres:   localhost:${DB_EXPOSE_PORT:-5432}"
echo ""

exec doppler run -- docker compose up --build "${COMPOSE_ARGS[@]}"
