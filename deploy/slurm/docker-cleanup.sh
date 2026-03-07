#!/bin/bash
# Periodic Docker cleanup for Ouro Slurm worker nodes.
# Installed via setup-slurm-cluster.sh (persistent workers) and
# build-golden-image.sh (spot workers). Runs every 6 hours via cron.

# Remove stopped containers
docker container prune -f >/dev/null 2>&1
# Remove ALL unused images (not just dangling) older than 24h
docker image prune -a -f --filter until=24h >/dev/null 2>&1
# Remove build cache older than 24h
docker builder prune -f --filter until=24h >/dev/null 2>&1

# Emergency: if disk > 85% used, prune aggressively (no age filter)
USAGE=$(df /var/lib/docker --output=pcent 2>/dev/null | tail -1 | tr -d ' %')
if [ "${USAGE:-0}" -gt 85 ]; then
    docker image prune -a -f >/dev/null 2>&1
    docker builder prune -a -f >/dev/null 2>&1
fi

# Re-pull prebuilt images to keep them cached
docker pull -q ubuntu:22.04 >/dev/null 2>&1 || true
docker pull -q python:3.12-slim >/dev/null 2>&1 || true
docker pull -q node:20-slim >/dev/null 2>&1 || true
