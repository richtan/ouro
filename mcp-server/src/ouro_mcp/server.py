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
        "https://ourocompute.com",
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


async def _get_payment_requirements(
    script: str,
    nodes: int,
    time_limit_min: int,
    submitter_address: str | None = None,
    builder_code: str | None = None,
) -> dict:
    """Hit the agent submit endpoint without payment to get the 402 response
    including the raw PAYMENT-REQUIRED header that an x402 client needs to
    construct and sign a payment."""
    body: dict = {"script": script, "nodes": nodes, "time_limit_min": time_limit_min}
    if submitter_address:
        body["submitter_address"] = submitter_address

    headers: dict[str, str] = {}
    if builder_code:
        headers["X-BUILDER-CODE"] = builder_code

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_get_api_url()}/api/compute/submit",
            json=body,
            headers=headers,
        )
        if resp.status_code == 402:
            data = resp.json()
            payment_header = resp.headers.get("payment-required", "")
            return {
                "price": data.get("price", "unknown"),
                "breakdown": data.get("breakdown", {}),
                "payment_required_header": payment_header,
            }
        # Unexpected non-402 (e.g. validation error)
        return {"error": f"Expected 402, got {resp.status_code}", "body": resp.text}


async def _submit_with_payment(
    script: str,
    nodes: int,
    time_limit_min: int,
    payment_signature: str,
    submitter_address: str | None = None,
    builder_code: str | None = None,
) -> dict:
    """Forward a job payload with a pre-signed x402 payment to the agent API."""
    body: dict = {"script": script, "nodes": nodes, "time_limit_min": time_limit_min}
    if submitter_address:
        body["submitter_address"] = submitter_address

    headers: dict[str, str] = {"payment-signature": payment_signature}
    if builder_code:
        headers["X-BUILDER-CODE"] = builder_code

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_get_api_url()}/api/compute/submit",
            json=body,
            headers=headers,
        )
        return {"status_code": resp.status_code, "body": resp.json()}


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
        "Ouro runs HPC compute jobs on a real Slurm cluster, paid in USDC via x402 on Base.\n\n"
        "Two payment flows are available:\n\n"
        "BROWSER FLOW (human pays):\n"
        "  run_compute_job -> show payment_url to user -> user pays in browser -> "
        "get_job_status with session_id\n\n"
        "AUTONOMOUS FLOW (agent pays with own wallet):\n"
        "  get_payment_requirements -> decode header, sign payment locally -> "
        "submit_and_pay with signature -> get_job_status with job_id\n\n"
        "Use get_price_quote to check pricing before committing.\n"
        "Use get_api_endpoint for direct HTTP access without MCP."
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


@mcp.tool()
async def get_payment_requirements(
    script: str,
    nodes: int = 1,
    time_limit_min: int = 1,
    submitter_address: str | None = None,
    builder_code: str | None = None,
) -> dict:
    """Get x402 payment requirements for a compute job.

    Returns the price breakdown and the raw PAYMENT-REQUIRED header that your
    x402 library needs to construct and sign a USDC payment on Base.

    This is step 1 of the autonomous payment flow:
      1. Call get_payment_requirements to get the payment header
      2. Decode the header, sign the payment locally with your wallet
      3. Call submit_and_pay with the signed payment-signature

    The price is valid for ~30 seconds. Complete both steps within that window.

    Args:
        script: Shell script to execute
        nodes: Number of compute nodes (default 1)
        time_limit_min: Maximum runtime in minutes (default 1)
        submitter_address: Your wallet address (optional, for job tracking)
        builder_code: Builder code for 10% discount (optional)
    """
    result = await _get_payment_requirements(
        script, nodes, time_limit_min, submitter_address, builder_code,
    )
    if "error" in result:
        return result
    return {
        **result,
        "message": (
            f"Payment of {result['price']} USDC required on Base. "
            "Decode the payment_required_header with your x402 library, "
            "sign the payment with your wallet, then call submit_and_pay "
            "with the resulting payment-signature. Complete within 30 seconds."
        ),
    }


@mcp.tool()
async def submit_and_pay(
    script: str,
    payment_signature: str,
    nodes: int = 1,
    time_limit_min: int = 1,
    submitter_address: str | None = None,
    builder_code: str | None = None,
) -> dict:
    """Submit a compute job with a pre-signed x402 payment.

    This is step 2 of the autonomous payment flow. You must first call
    get_payment_requirements to get the payment header, sign it locally
    with your wallet, then pass the signature here.

    No private keys are sent — only the opaque payment-signature string.

    After a successful submission, call get_job_status with the returned
    job_id to poll for results.

    Args:
        script: Shell script to execute (must match get_payment_requirements call)
        payment_signature: The signed x402 payment string from your wallet
        nodes: Number of compute nodes (must match get_payment_requirements call)
        time_limit_min: Maximum runtime in minutes (must match)
        submitter_address: Your wallet address (optional, for job tracking)
        builder_code: Builder code for 10% discount (must match if used in step 1)
    """
    result = await _submit_with_payment(
        script, nodes, time_limit_min, payment_signature,
        submitter_address, builder_code,
    )
    status = result["status_code"]
    body = result["body"]

    if status == 200:
        return {
            "job_id": body.get("job_id"),
            "status": body.get("status", "pending"),
            "price": body.get("price"),
            "message": (
                f"Job {body.get('job_id')} submitted successfully. "
                "Call get_job_status to poll for results."
            ),
        }
    if status == 402:
        return {
            "error": "payment_not_recognized",
            "message": "Payment signature not accepted. Re-run get_payment_requirements and sign again.",
            "details": body,
        }
    if status == 403:
        reason = body.get("error", "verification_failed")
        detail = body.get("detail", "")
        payer = body.get("payer")
        msg = f"Payment verification failed: {reason}."
        if reason == "insufficient_funds":
            msg = f"Insufficient USDC balance for payer {payer}. {detail}"
        elif reason == "invalid_payload":
            msg = "Payment payload structure is invalid. Ensure you're using the latest x402 signing format."
        return {
            "error": f"payment_{reason}",
            "message": msg,
            "details": body,
        }
    if status == 429:
        return {
            "error": "rate_limited",
            "message": "Too many requests. Wait and retry.",
            "details": body,
        }
    if status == 503:
        return {
            "error": "facilitator_unavailable",
            "message": "Payment facilitator is temporarily unavailable. Retry shortly.",
            "details": body,
        }
    return {
        "error": f"unexpected_status_{status}",
        "message": f"Agent API returned {status}.",
        "details": body,
    }


@mcp.tool()
async def get_api_endpoint() -> dict:
    """Get the direct API endpoint for programmatic compute submission.

    Returns the URL, method, expected body schema, and an example.
    The endpoint uses the x402 protocol: POST without payment returns 402
    with price details; POST with a valid payment-signature header creates the job.
    """
    return {
        "url": f"{_get_api_url()}/api/compute/submit",
        "method": "POST",
        "payment_protocol": "x402",
        "network": "eip155:8453",
        "currency": "USDC",
        "body_schema": {
            "script": "string (required) - shell script to execute",
            "nodes": "int (default 1) - number of compute nodes",
            "time_limit_min": "int (default 1) - max runtime in minutes",
            "submitter_address": "string (optional) - your wallet address for job tracking",
        },
        "example_body": {
            "script": "echo hello world",
            "nodes": 1,
            "time_limit_min": 1,
        },
    }


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
