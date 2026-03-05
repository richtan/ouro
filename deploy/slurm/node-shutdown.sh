#!/usr/bin/env bash
# Graceful shutdown: drain this node so Slurm doesn't schedule new jobs to it.
# Running jobs will be requeued by Slurm if RequeueExit is configured,
# otherwise the agent's retry logic handles re-submission.
set -euo pipefail

NODE_NAME=$(curl -sf -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/name 2>/dev/null || hostname)
logger -t "ouro-node-shutdown" "Draining $NODE_NAME (preemption or shutdown)"
scontrol update NodeName="$NODE_NAME" State=DRAIN Reason="preempted" 2>/dev/null || true
