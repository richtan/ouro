"""Standalone MCP server for Ouro HPC compute with browser payment."""

from __future__ import annotations

import os
import sys

import httpx
import uvicorn
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _get_api_url() -> str:
    url = os.environ.get("OURO_API_URL")
    if not url:
        print("Error: OURO_API_URL environment variable is required.", file=sys.stderr)
        sys.exit(1)
    return url


def _get_dashboard_url() -> str:
    return os.environ.get(
        "DASHBOARD_URL",
        "https://dashboard-production-80cd.up.railway.app",
    )


# ---------------------------------------------------------------------------
# Price quotes and job status (plain HTTP, no wallet needed)
# ---------------------------------------------------------------------------


async def _get_quote(nodes: int, time_limit_min: int) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_get_api_url()}/api/compute/submit",
            json={"script": "echo hi", "nodes": nodes, "time_limit_min": time_limit_min},
        )
        if resp.status_code == 402:
            data = resp.json()
            return {
                "price": data.get("price", "unknown"),
                "breakdown": data.get("breakdown", {}),
                "guaranteed_profitable": True,
            }
    return {"price": "unknown", "breakdown": {}}


async def _fetch_job(job_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{_get_api_url()}/api/jobs/{job_id}")
        if resp.status_code == 404:
            return {"error": "not_found", "message": f"Job {job_id} not found"}
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Payment sessions (stored in agent DB via API; survives restarts and replicas)
# ---------------------------------------------------------------------------


def _payment_url(session_id: str) -> str:
    return f"{_get_dashboard_url()}/pay/{session_id}"


async def _create_session_via_api(
    script: str, nodes: int, time_limit_min: int, price: str
) -> dict:
    """Create a payment session via the agent API (persisted in DB)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_get_api_url()}/api/sessions",
            json={
                "script": script,
                "nodes": nodes,
                "time_limit_min": time_limit_min,
                "price": price,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def _get_session_from_api(session_id: str) -> dict | None:
    """Fetch a payment session from the agent API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{_get_api_url()}/api/sessions/{session_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "Ouro Compute",
    instructions=(
        "Ouro is a Proof-of-Compute Oracle that runs verifiable HPC jobs "
        "on a real Slurm cluster. Payment is in USDC via the x402 protocol "
        "and results include on-chain proofs on Base.\n\n"
        "Workflow: call run_compute_job -> show the payment_url to the user -> "
        "user pays in browser -> call get_job_status with the session_id to get results.\n\n"
        "Use get_price_quote to check pricing before committing."
    ),
)


@mcp.tool()
async def get_job_status(job_id: str) -> dict:
    """Check the status of a compute job or payment session.

    Accepts either a job_id (from a completed payment) or a session_id
    (from submit_compute_job / run_compute_job). Returns full job details
    including output and on-chain proof hash when completed.

    Args:
        job_id: The job ID or session ID to check
    """
    session = await _get_session_from_api(job_id)
    if session:
        if session.get("status") == "pending":
            return {
                "status": "awaiting_payment",
                "payment_url": _payment_url(session["id"]),
                "message": "User has not completed payment yet.",
            }
        real_job_id = session.get("job_id")
        if not real_job_id:
            return {"error": "session_error", "message": "Session marked paid but no job_id"}
        job_id = real_job_id

    return await _fetch_job(job_id)


@mcp.tool()
async def run_compute_job(
    script: str,
    nodes: int = 1,
    time_limit_min: int = 1,
) -> dict:
    """Submit a shell script to run on Ouro's HPC cluster.

    Returns a one-time payment link. The user must open it in their browser,
    connect their wallet, and pay with USDC on Base. After paying, call
    get_job_status with the returned session_id to get the result.

    IMPORTANT: Always show the payment_url to the user so they can open it.

    Args:
        script: Shell script to execute (e.g. "echo hello" or "python3 -c 'print(42)'")
        nodes: Number of compute nodes (default 1)
        time_limit_min: Maximum runtime in minutes (default 1)
    """
    quote = await _get_quote(nodes, time_limit_min)
    session = await _create_session_via_api(script, nodes, time_limit_min, quote["price"])
    url = _payment_url(session["id"])

    return {
        "status": "awaiting_payment",
        "payment_url": url,
        "session_id": session["id"],
        "price": quote["price"],
        "message": (
            f"Payment of {quote['price']} USDC required. "
            f"Please open this link to pay with your wallet: {url}\n"
            f"After paying, call get_job_status with session_id '{session['id']}' to get the result."
        ),
    }


@mcp.tool()
async def get_price_quote(
    nodes: int = 1,
    time_limit_min: int = 1,
) -> dict:
    """Get a price quote for a compute job without submitting or paying.

    Use this to check pricing before committing to a job.

    Args:
        nodes: Number of compute nodes (default 1)
        time_limit_min: Maximum runtime in minutes (default 1)
    """
    return await _get_quote(nodes, time_limit_min)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main():
    port = int(os.environ.get("PORT", "8080"))

    app = mcp.http_app(
        middleware=[
            Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
        ]
    )
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
