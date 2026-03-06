from __future__ import annotations

import logging
from uuid import uuid4

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class SlurmClient:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            base_url=settings.SLURMREST_URL,
            headers={
                "X-SLURM-USER-TOKEN": settings.SLURMREST_JWT,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def submit_job(
        self,
        *,
        workspace_path: str,
        entrypoint: str = "",
        image: str | None = None,
        docker_image: str | None = None,
        entrypoint_cmd: list[str] | None = None,
        dockerfile_content: str | None = None,
        partition: str = "compute",
        cpus: int = 1,
        time_limit_min: int = 1,
    ) -> int:
        body: dict = {
            "workspace_path": workspace_path,
            "entrypoint": entrypoint,
            "image": image,
            "job": {
                "environment": ["PATH=/usr/bin:/bin"],
                "name": f"ouro-{uuid4().hex[:8]}",
                "partition": partition,
                "cpus": cpus,
                "tasks": 1,
                "time_limit": {"set": True, "number": time_limit_min * 60},
                "current_working_directory": "/tmp",
            },
        }
        if docker_image:
            body["docker_image"] = docker_image
        if entrypoint_cmd:
            body["entrypoint_cmd"] = entrypoint_cmd
        if dockerfile_content:
            body["dockerfile_content"] = dockerfile_content

        resp = await self.client.post("/slurm/v0.0.38/job/submit", json=body)
        resp.raise_for_status()
        data = resp.json()
        job_id = data.get("job_id") or data.get("result", [{}])[0].get("job_id")
        logger.info("slurm_job_submitted job_id=%s", job_id)
        return int(job_id)

    async def create_workspace(self, workspace_id: str, files: list[dict]) -> str:
        """Send files to proxy, which writes them to NFS. Returns workspace_path."""
        resp = await self.client.post(
            "/slurm/v0.0.38/workspace",
            json={
                "workspace_id": workspace_id,
                "mode": "multi_file",
                "files": files,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()["workspace_path"]

    async def delete_workspace(self, workspace_id: str) -> bool:
        """Delete workspace from NFS after job completion."""
        try:
            resp = await self.client.delete(
                f"/slurm/v0.0.38/workspace/{workspace_id}",
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json().get("deleted", False)
        except Exception as e:
            logger.warning("delete_workspace failed for %s: %s", workspace_id, e)
            return False

    async def get_job_status(self, job_id: int) -> dict:
        resp = await self.client.get(f"/slurm/v0.0.38/job/{job_id}")
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
        if not jobs:
            return {"state": "UNKNOWN", "reason": ""}
        job = jobs[0]
        return {
            "state": job.get("job_state", "UNKNOWN"),
            "exit_code": job.get("exit_code", {}).get("return_code"),
            "start_time": job.get("start_time"),
            "end_time": job.get("end_time"),
            "reason": job.get("reason", ""),
        }

    async def cancel_job(self, job_id: int) -> bool:
        """Cancel a Slurm job via scancel."""
        resp = await self.client.delete(f"/slurm/v0.0.38/job/{job_id}")
        resp.raise_for_status()
        return resp.json().get("cancelled", False)

    async def get_job_output(self, job_id: int) -> str:
        try:
            resp = await self.client.get(f"/slurm/v0.0.38/job/{job_id}/output")
            resp.raise_for_status()
            data = resp.json()
            return data.get("output", "")
        except Exception:
            return ""

    async def get_cluster_info(self) -> dict:
        try:
            resp = await self.client.get("/slurm/v0.0.38/nodes")
            resp.raise_for_status()
            nodes = resp.json().get("nodes", [])

            total = len(nodes)
            idle = sum(1 for n in nodes if "IDLE" in n.get("state", []))
            allocated = sum(1 for n in nodes if "ALLOCATED" in n.get("state", []))

            # CPU-level capacity (only count non-DOWN nodes; FUTURE nodes are invisible)
            total_cpus = sum(
                n.get("cpus", 0) for n in nodes
                if "DOWN" not in n.get("state", [])
            )
            available_cpus = sum(
                n.get("cpus", 0) for n in nodes if "IDLE" in n.get("state", [])
            )
            available_cpus += sum(
                n.get("free_cpus", 0) for n in nodes if "MIXED" in n.get("state", [])
            )

            return {
                "total_nodes": total,
                "idle_nodes": idle,
                "allocated_nodes": allocated,
                "total_cpus": total_cpus,
                "available_cpus": available_cpus,
                "nodes_detail": nodes,
                "status": "healthy" if total > 0 else "offline",
            }
        except Exception as e:
            logger.warning("slurm_cluster_info_failed: %s", e)
            return {
                "total_nodes": 0, "idle_nodes": 0, "allocated_nodes": 0,
                "total_cpus": 0, "available_cpus": 0,
                "nodes_detail": [], "status": "unreachable",
            }

    async def close(self) -> None:
        await self.client.aclose()
