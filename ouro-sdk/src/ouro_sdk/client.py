"""Ouro Python SDK — submit and poll compute jobs.

Does NOT handle payment itself. Expects the caller to provide an httpx.AsyncClient.
If the client has x402 payment handling configured, the 402→sign→retry flow
is transparent — the SDK just POSTs normally.
"""

from __future__ import annotations

import asyncio

import httpx

from ouro_sdk.models import JobResult, Quote

DEFAULT_API_URL = "https://agent-production-3b3a.up.railway.app"


class OuroClient:
    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        client: httpx.AsyncClient | None = None,
        poll_interval_s: float = 3.0,
        poll_timeout_s: float = 600.0,
    ):
        self._api_url = api_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._poll_interval = poll_interval_s
        self._poll_timeout = poll_timeout_s

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def close(self):
        if self._owns_client:
            await self._client.aclose()

    async def quote(self, nodes: int = 1, time_limit_min: int = 1) -> Quote:
        """Get a price quote without submitting."""
        resp = await self._client.post(
            f"{self._api_url}/api/compute/submit",
            json={"script": "echo quote", "nodes": nodes, "time_limit_min": time_limit_min},
        )
        if resp.status_code == 402:
            data = resp.json()
            return Quote(
                price=data.get("price", "unknown"),
                breakdown=data.get("breakdown", {}),
                guaranteed_profitable=True,
            )
        resp.raise_for_status()
        return Quote(price="unknown")

    async def submit(
        self,
        script: str,
        nodes: int = 1,
        time_limit_min: int = 1,
        submitter_address: str | None = None,
    ) -> str:
        """Submit a compute job. Returns the job_id.

        With a plain httpx client this will raise on 402.
        With an x402-wrapped client, payment is handled automatically.
        """
        body: dict = {
            "script": script,
            "nodes": nodes,
            "time_limit_min": time_limit_min,
        }
        if submitter_address:
            body["submitter_address"] = submitter_address

        resp = await self._client.post(
            f"{self._api_url}/api/compute/submit",
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["job_id"]

    async def get_job(self, job_id: str) -> JobResult:
        """Fetch current job status."""
        resp = await self._client.get(f"{self._api_url}/api/jobs/{job_id}")
        resp.raise_for_status()
        data = resp.json()
        return JobResult(
            job_id=data["id"],
            status=data["status"],
            output=data.get("output", ""),
            error_output=data.get("error_output", ""),
            output_hash=data.get("output_hash"),
            proof_tx_hash=data.get("proof_tx_hash"),
            compute_duration_s=data.get("compute_duration_s"),
            price_usdc=data.get("price_usdc"),
        )

    async def wait(self, job_id: str) -> JobResult:
        """Poll until a job completes or fails. Uses exponential backoff."""
        elapsed = 0.0
        interval = self._poll_interval

        while elapsed < self._poll_timeout:
            result = await self.get_job(job_id)
            if result.status in ("completed", "failed"):
                return result
            await asyncio.sleep(interval)
            elapsed += interval
            interval = min(interval * 1.5, 30.0)

        raise TimeoutError(f"Job {job_id} did not complete within {self._poll_timeout}s")

    async def run(
        self,
        script: str,
        nodes: int = 1,
        time_limit_min: int = 1,
        submitter_address: str | None = None,
    ) -> JobResult:
        """Submit and wait for completion in one call."""
        job_id = await self.submit(script, nodes, time_limit_min, submitter_address)
        return await self.wait(job_id)

    async def capabilities(self) -> dict:
        """Fetch the server capability manifest."""
        resp = await self._client.get(f"{self._api_url}/api/capabilities")
        resp.raise_for_status()
        return resp.json()
