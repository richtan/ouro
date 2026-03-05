"""Ouro Python SDK — submit and poll compute jobs.

Does NOT handle payment itself. Expects the caller to provide an httpx.AsyncClient.
If the client has x402 payment handling configured, the 402→sign→retry flow
is transparent — the SDK just POSTs normally.
"""

from __future__ import annotations

import asyncio

import httpx

from ouro_sdk.models import JobResult, Quote

DEFAULT_API_URL = "https://api.ourocompute.com"


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

    async def quote(
        self,
        cpus: int = 1,
        time_limit_min: int = 1,
        submission_mode: str = "script",
    ) -> Quote:
        """Get a price quote without submitting."""
        resp = await self._client.get(
            f"{self._api_url}/api/price",
            params={"cpus": cpus, "time_limit_min": time_limit_min, "submission_mode": submission_mode},
        )
        resp.raise_for_status()
        data = resp.json()
        return Quote(
            price=data.get("price", "unknown"),
            breakdown=data.get("breakdown", {}),
            guaranteed_profitable=True,
        )

    async def submit(
        self,
        *,
        script: str | None = None,
        files: list[dict] | None = None,
        entrypoint: str | None = None,
        image: str = "base",
        cpus: int = 1,
        time_limit_min: int = 1,
        submitter_address: str | None = None,
        builder_code: str | None = None,
    ) -> str:
        """Submit a compute job. Returns the job_id.

        Provide ONE of: script or files.
        - script: shell script string
        - files: list of {path, content} dicts + entrypoint

        With a plain httpx client this will raise on 402.
        With an x402-wrapped client, payment is handled automatically.
        """
        body: dict = {"cpus": cpus, "time_limit_min": time_limit_min}
        if script:
            body["script"] = script
        elif files:
            body["files"] = files
            body["entrypoint"] = entrypoint
        if image and image != "base":
            body["image"] = image
        if submitter_address:
            body["submitter_address"] = submitter_address

        headers: dict[str, str] = {}
        if builder_code:
            headers["X-BUILDER-CODE"] = builder_code

        resp = await self._client.post(
            f"{self._api_url}/api/compute/submit",
            json=body,
            headers=headers,
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
        *,
        script: str | None = None,
        files: list[dict] | None = None,
        entrypoint: str | None = None,
        image: str = "base",
        cpus: int = 1,
        time_limit_min: int = 1,
        submitter_address: str | None = None,
        builder_code: str | None = None,
    ) -> JobResult:
        """Submit and wait for completion in one call."""
        job_id = await self.submit(
            script=script, files=files, entrypoint=entrypoint,
            image=image, cpus=cpus, time_limit_min=time_limit_min,
            submitter_address=submitter_address, builder_code=builder_code,
        )
        return await self.wait(job_id)

    async def capabilities(self) -> dict:
        """Fetch the server capability manifest."""
        resp = await self._client.get(f"{self._api_url}/api/capabilities")
        resp.raise_for_status()
        return resp.json()
