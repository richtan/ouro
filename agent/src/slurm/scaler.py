"""Elastic auto-scaler for GCP spot Slurm workers.

Monitors cluster utilization and pending job queue depth.
Boots spot instances when demand exceeds capacity.
Drains and terminates idle spot instances to save cost.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import ActiveJob

logger = logging.getLogger(__name__)

# Lazy import to avoid requiring google-cloud-compute when scaling is disabled
_gcp_client = None


def _get_gcp_client():
    global _gcp_client
    if _gcp_client is None:
        import json
        from google.cloud import compute_v1
        if settings.GCP_CREDENTIALS_JSON:
            from google.oauth2 import service_account
            info = json.loads(settings.GCP_CREDENTIALS_JSON)
            credentials = service_account.Credentials.from_service_account_info(info)
            _gcp_client = compute_v1.InstancesClient(credentials=credentials)
        else:
            _gcp_client = compute_v1.InstancesClient()  # ADC fallback
    return _gcp_client


@dataclass
class ScalingEvent:
    action: str          # "scale_out" | "scale_down" | "boot_failed" | "preempted"
    node_name: str
    reason: str


class AutoScaler:
    """Decides when to boot/terminate GCP spot instances based on demand."""

    # Tier definitions: (prefix, max_cpus, template_name)
    TIERS = [
        ("ouro-spot-sm-", 2, "ouro-spot-sm-template"),
        ("ouro-spot-md-", 4, "ouro-spot-md-template"),
        ("ouro-spot-lg-", 8, "ouro-spot-lg-template"),
    ]

    def __init__(self) -> None:
        self.last_scale_time: datetime | None = None
        self._idle_since: dict[str, datetime] = {}  # node_name -> first idle timestamp
        self._booting: dict[str, datetime] = {}     # node_name -> boot started

    async def evaluate_and_act(
        self,
        cluster_info: dict,
        db: AsyncSession,
    ) -> ScalingEvent | None:
        """Called every 60s from autonomous loop. Returns event if action taken."""
        now = datetime.now(timezone.utc)

        # Respect cooldown between scaling actions
        if self.last_scale_time:
            elapsed = (now - self.last_scale_time).total_seconds()
            if elapsed < settings.SCALING_COOLDOWN_SECONDS:
                return None

        pending_jobs = await self._get_pending_jobs_with_cpus(db)
        available_cpus = cluster_info.get("available_cpus", 0)
        spot_idle = self._get_idle_spot_nodes(cluster_info)
        cloud_nodes = cluster_info.get("nodes_detail", [])

        # Clear booting nodes that have been booting > 3 min (stale)
        for name in list(self._booting):
            if (now - self._booting[name]).total_seconds() > 180:
                self._booting.pop(name)

        # --- Scale OUT ---
        # Enforce max spot nodes cap
        active_spot = sum(
            1 for n in cloud_nodes
            if n["name"].startswith("ouro-spot-")
            and "CLOUD" not in n.get("state", [])
            and "DOWN" not in n.get("state", [])
        ) + len(self._booting)
        if active_spot >= settings.SCALING_MAX_SPOT_NODES:
            return None

        # If there are pending jobs that can't fit in available CPUs
        booting_cpus = sum(
            self._cpus_for_node(name) for name in self._booting
        )
        if pending_jobs and (available_cpus + booting_cpus) < sum(j["cpus"] for j in pending_jobs):
            max_cpus_needed = max(j["cpus"] for j in pending_jobs)
            node_name, template = self._pick_node_for_cpus(max_cpus_needed, cloud_nodes)
            if node_name and node_name not in self._booting:
                event = await self._boot_spot_instance(node_name, template)
                if event and event.action == "scale_out":
                    self._booting[node_name] = now
                    self.last_scale_time = now
                return event

        # --- Scale DOWN ---
        # If spot nodes have been idle for longer than the drain threshold
        for node_name in spot_idle:
            idle_start = self._idle_since.setdefault(node_name, now)
            idle_minutes = (now - idle_start).total_seconds() / 60
            if idle_minutes >= settings.SCALING_IDLE_DRAIN_MINUTES:
                event = await self._terminate_spot_instance(node_name)
                if event:
                    self.last_scale_time = now
                    self._idle_since.pop(node_name, None)
                return event

        # Clean up tracking for nodes that are no longer idle
        active_idle_names = set(spot_idle)
        for name in list(self._idle_since.keys()):
            if name not in active_idle_names:
                self._idle_since.pop(name, None)

        return None

    async def _get_pending_jobs_with_cpus(self, db: AsyncSession) -> list[dict]:
        """Return pending jobs with their CPU requirements."""
        result = await db.execute(
            select(ActiveJob.id, ActiveJob.payload).where(ActiveJob.status == "pending")
        )
        jobs = []
        for row in result.all():
            cpus = (row.payload or {}).get("cpus", 1)
            jobs.append({"id": str(row.id), "cpus": cpus})
        return jobs

    def _pick_node_for_cpus(
        self, cpus_needed: int, all_nodes: list[dict]
    ) -> tuple[str | None, str | None]:
        """Find the smallest CLOUD node that fits the CPU request."""
        for prefix, max_cpus, template in self.TIERS:
            if cpus_needed <= max_cpus:
                candidates = [
                    n["name"] for n in all_nodes
                    if n["name"].startswith(prefix)
                    and "CLOUD" in n.get("state", [])
                ]
                candidates.sort(key=lambda n: int(re.search(r"\d+$", n).group()))
                if candidates:
                    return candidates[0], template
        return None, None

    def _cpus_for_node(self, node_name: str) -> int:
        """Return expected CPU count for a node based on its tier prefix."""
        for prefix, max_cpus, _ in self.TIERS:
            if node_name.startswith(prefix):
                return max_cpus
        return 2

    def _get_idle_spot_nodes(self, cluster_info: dict) -> list[str]:
        """Return names of spot nodes currently in IDLE state."""
        nodes = cluster_info.get("nodes_detail", [])
        return [
            n["name"] for n in nodes
            if n["name"].startswith("ouro-spot-")
            and "IDLE" in n.get("state", [])
        ]

    async def _boot_spot_instance(self, node_name: str, template: str) -> ScalingEvent | None:
        """Create a GCP spot instance from the appropriate instance template."""
        try:
            client = _get_gcp_client()
            from google.cloud import compute_v1

            instance = compute_v1.Instance()
            instance.name = node_name
            instance.zone = f"projects/{settings.GCP_PROJECT}/zones/{settings.GCP_ZONE}"

            request = compute_v1.InsertInstanceRequest(
                project=settings.GCP_PROJECT,
                zone=settings.GCP_ZONE,
                instance_resource=instance,
                source_instance_template=(
                    f"projects/{settings.GCP_PROJECT}/global/"
                    f"instanceTemplates/{template}"
                ),
            )

            operation = client.insert(request=request)
            await asyncio.to_thread(operation.result)

            logger.info("spot_instance_booted node=%s", node_name)
            return ScalingEvent("scale_out", node_name, "pending jobs, no idle capacity")

        except Exception as e:
            logger.error("spot_boot_failed node=%s error=%s", node_name, e)
            return ScalingEvent("boot_failed", node_name, str(e))

    async def _terminate_spot_instance(self, node_name: str) -> ScalingEvent | None:
        """Drain and delete a spot instance."""
        try:
            client = _get_gcp_client()
            from google.cloud import compute_v1

            request = compute_v1.DeleteInstanceRequest(
                project=settings.GCP_PROJECT,
                zone=settings.GCP_ZONE,
                instance=node_name,
            )
            operation = client.delete(request=request)
            await asyncio.to_thread(operation.result)

            logger.info("spot_instance_terminated node=%s", node_name)
            return ScalingEvent(
                "scale_down", node_name,
                f"idle for >{settings.SCALING_IDLE_DRAIN_MINUTES} min",
            )

        except Exception as e:
            logger.error("spot_terminate_failed node=%s error=%s", node_name, e)
            return None
