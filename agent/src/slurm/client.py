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
        submission_mode: str = "script",
        script: str = "",
        workspace_path: str | None = None,
        entrypoint: str | None = None,
        image: str | None = None,
        partition: str = "compute",
        nodes: int = 1,
        time_limit_min: int = 1,
    ) -> int:
        body: dict = {
            "submission_mode": submission_mode,
            "image": image,
            "job": {
                "environment": ["PATH=/usr/bin:/bin"],
                "name": f"ouro-{uuid4().hex[:8]}",
                "partition": partition,
                "nodes": str(nodes),
                "tasks": 1,
                "time_limit": {"set": True, "number": time_limit_min * 60},
                "current_working_directory": "/tmp",
            },
        }

        if submission_mode == "script":
            body["script"] = f"#!/bin/bash\n{script}"
        elif submission_mode == "multi_file":
            body["workspace_path"] = workspace_path
            body["entrypoint"] = entrypoint

        resp = await self.client.post("/slurm/v0.0.38/job/submit", json=body)
        resp.raise_for_status()
        data = resp.json()
        job_id = data.get("job_id") or data.get("result", [{}])[0].get("job_id")
        logger.info("slurm_job_submitted job_id=%s mode=%s", job_id, submission_mode)
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
            return {"state": "UNKNOWN"}
        job = jobs[0]
        return {
            "state": job.get("job_state", "UNKNOWN"),
            "exit_code": job.get("exit_code", {}).get("return_code"),
            "start_time": job.get("start_time"),
            "end_time": job.get("end_time"),
        }

    async def get_job_output(self, job_id: int) -> str:
        try:
            resp = await self.client.get(f"/slurm/v0.0.38/job/{job_id}/output")
            resp.raise_for_status()
            return resp.text
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
            return {
                "total_nodes": total,
                "idle_nodes": idle,
                "allocated_nodes": allocated,
                "status": "healthy" if total > 0 else "offline",
            }
        except Exception as e:
            logger.warning("slurm_cluster_info_failed: %s", e)
            return {"total_nodes": 0, "idle_nodes": 0, "allocated_nodes": 0, "status": "unreachable"}

    async def close(self) -> None:
        await self.client.aclose()
