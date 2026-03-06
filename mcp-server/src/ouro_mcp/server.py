"""Standalone MCP server for Ouro HPC compute with browser payment."""

from __future__ import annotations

import logging
import os
import sys

import httpx

logger = logging.getLogger("ouro_mcp")
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
# Helpers: build request bodies for all submission modes
# ---------------------------------------------------------------------------


def _has_dockerfile(files: list[dict] | None) -> bool:
    """Check if files include a Dockerfile."""
    if not files:
        return False
    return any(f.get("path", "").lower() == "dockerfile" for f in files)


def _build_submit_body(
    *,
    script: str | None = None,
    files: list[dict] | None = None,
    entrypoint: str | None = None,
    image: str = "base",
    cpus: int = 1,
    time_limit_min: int = 1,
    submitter_address: str | None = None,
) -> dict:
    """Centralizes body construction for all modes."""
    body: dict = {"cpus": cpus, "time_limit_min": time_limit_min}
    if image and image != "base":
        body["image"] = image
    if submitter_address:
        body["submitter_address"] = submitter_address
    if script:
        body["script"] = script
    elif files:
        body["files"] = files
        if entrypoint:
            body["entrypoint"] = entrypoint
        # When no entrypoint, the agent extracts it from the Dockerfile
    return body


def _submission_mode(script: str | None, files: list[dict] | None) -> str:
    if files:
        return "multi_file"
    return "script"


# ---------------------------------------------------------------------------
# Price quotes and job status (plain HTTP, no wallet needed)
# ---------------------------------------------------------------------------


async def _get_quote(cpus: int, time_limit_min: int, submission_mode: str = "script") -> dict:
    """Get price quote using the dedicated /api/price endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_get_api_url()}/api/price",
            params={"cpus": cpus, "time_limit_min": time_limit_min, "submission_mode": submission_mode},
        )
        resp.raise_for_status()
        return resp.json()


async def _get_payment_requirements(
    body: dict,
    builder_code: str | None = None,
) -> dict:
    """Hit the agent submit endpoint without payment to get the 402 response
    including the raw PAYMENT-REQUIRED header that an x402 client needs to
    construct and sign a payment."""
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
        logger.error("get_payment_requirements: expected 402, got %d: %s", resp.status_code, resp.text[:500])
        return {"error": f"Unexpected response (status {resp.status_code})"}


async def _submit_with_payment(
    body: dict,
    payment_signature: str,
    builder_code: str | None = None,
) -> dict:
    """Forward a job payload with a pre-signed x402 payment to the agent API."""
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
    *,
    script: str | None = None,
    job_payload: dict | None = None,
    cpus: int,
    time_limit_min: int,
    price: str,
) -> dict:
    """Create a payment session via the agent API (persisted in DB)."""
    body: dict = {"cpus": cpus, "time_limit_min": time_limit_min, "price": price}
    if script:
        body["script"] = script
    if job_payload:
        body["job_payload"] = job_payload
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_get_api_url()}/api/sessions",
            json=body,
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
        "SUBMISSION MODES:\n"
        "  - script: single shell script string (simplest)\n"
        "  - files: list of {path, content} dicts (multi-file workspaces)\n\n"
        "ENVIRONMENT CONFIGURATION:\n"
        "  Include a file named 'Dockerfile' in files to configure the environment.\n"
        "  Without a Dockerfile, use 'image' and 'entrypoint' params directly.\n"
        "  Prebuilt aliases (instant): base, python312, node20, pytorch, r-base.\n"
        "  Any Docker Hub image also works via Dockerfile (e.g. FROM python:3.12-slim).\n\n"
        "  Supported Dockerfile instructions:\n"
        "    FROM — select base image (required first line)\n"
        "    RUN — install dependencies / run build commands\n"
        "    ENV — set environment variables\n"
        "    WORKDIR — set working directory\n"
        "    ENTRYPOINT — define the main command (exec form recommended)\n"
        "    CMD — default arguments for ENTRYPOINT\n"
        "    COPY — copy workspace files into the image (local paths only, no glob patterns)\n"
        "    ADD — like COPY but no URLs allowed (local files only, no globs)\n"
        "    ARG — build-time variables (substituted in RUN, ENV, WORKDIR, COPY)\n"
        "    LABEL — image metadata (no runtime effect)\n"
        "    EXPOSE — document ports (no runtime effect)\n"
        "    SHELL — set shell for RUN commands (JSON exec form, e.g. [\"/bin/bash\", \"-c\"])\n\n"
        "  Not supported (returns clear error):\n"
        "    USER, VOLUME, HEALTHCHECK, STOPSIGNAL, ONBUILD\n"
        "    These are rejected because Apptainer containers run as the host user\n"
        "    and don't support Docker-style volumes or signal handling.\n\n"
        "  Note: COPY/ADD disables image caching since copied files may change between builds.\n\n"
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
    script: str | None = None,
    files: list[dict] | None = None,
    entrypoint: str | None = None,
    image: str = "base",
    cpus: int = 1,
    time_limit_min: int = 1,
) -> dict:
    """Submit a compute job to run on Ouro's HPC cluster (browser payment flow).

    Returns a one-time payment link. The user must open it in their browser,
    connect their wallet, and pay with USDC on Base. After paying, call
    get_job_status with the returned session_id to get the result.

    Provide ONE of: script or files.
    - script: shell script string (simplest)
    - files: list of {path, content} dicts for multi-file workspaces

    Include a Dockerfile in files to configure the environment. Supported instructions:
    FROM, RUN, ENV, WORKDIR, ENTRYPOINT, CMD, COPY, ADD, ARG, LABEL, EXPOSE, SHELL.
    Not supported (returns error): USER, VOLUME, HEALTHCHECK, STOPSIGNAL, ONBUILD.
    Without a Dockerfile, provide entrypoint and image params.

    IMPORTANT: Always show the payment_url to the user so they can open it.

    Args:
        script: Shell script to execute (e.g. "echo hello" or "python3 -c 'print(42)'")
        files: List of {path, content} file dicts for multi-file workspace
        entrypoint: File to execute (required with files unless a Dockerfile is included)
        image: Container image (default "base"). Options: base, python312, node20, pytorch, r-base
        cpus: Number of CPU cores (default 1, max 8)
        time_limit_min: Maximum runtime in minutes (default 1)
    """
    if not script and not files:
        return {"error": "Provide one of: script or files"}
    if files and not entrypoint and not _has_dockerfile(files):
        return {"error": "entrypoint required when using files (or include a Dockerfile)"}
    if not (1 <= cpus <= 8):
        return {"error": "cpus must be between 1 and 8"}
    if not (1 <= time_limit_min <= 60):
        return {"error": "time_limit_min must be between 1 and 60"}

    mode = _submission_mode(script, files)
    quote = await _get_quote(cpus, time_limit_min, mode)

    if script:
        session = await _create_session_via_api(script=script, cpus=cpus, time_limit_min=time_limit_min, price=quote["price"])
    else:
        job_payload = {
            "submission_mode": "multi_file",
            "files": files,
            "entrypoint": entrypoint,
            "image": image,
            "cpus": cpus,
            "time_limit_min": time_limit_min,
        }
        session = await _create_session_via_api(job_payload=job_payload, cpus=cpus, time_limit_min=time_limit_min, price=quote["price"])

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
    cpus: int = 1,
    time_limit_min: int = 1,
    submission_mode: str = "script",
) -> dict:
    """Get a price quote for a compute job without submitting or paying.

    Use this to check pricing before committing to a job.

    Args:
        cpus: Number of CPU cores (default 1, max 8)
        time_limit_min: Maximum runtime in minutes (default 1)
        submission_mode: "script" or "multi_file" (affects setup cost)
    """
    return await _get_quote(cpus, time_limit_min, submission_mode)


@mcp.tool()
async def get_payment_requirements(
    script: str | None = None,
    files: list[dict] | None = None,
    entrypoint: str | None = None,
    image: str = "base",
    cpus: int = 1,
    time_limit_min: int = 1,
    submitter_address: str | None = None,
    builder_code: str | None = None,
) -> dict:
    """Get x402 payment requirements for a compute job.

    Returns the price breakdown and the raw PAYMENT-REQUIRED header that your
    x402 library needs to construct and sign a USDC payment on Base.

    Provide ONE of: script or files. Include a Dockerfile in files to configure
    the environment (FROM, RUN, ENV, WORKDIR, ENTRYPOINT, CMD, COPY, ADD, ARG,
    LABEL, EXPOSE, SHELL). USER/VOLUME/HEALTHCHECK/STOPSIGNAL/ONBUILD are rejected.

    This is step 1 of the autonomous payment flow:
      1. Call get_payment_requirements to get the payment header
      2. Decode the header, sign the payment locally with your wallet
      3. Call submit_and_pay with the signed payment-signature

    The price is valid for ~30 seconds.

    Args:
        script: Shell script to execute
        files: List of {path, content} file dicts for multi-file workspace
        entrypoint: File to execute (required with files unless a Dockerfile is included)
        image: Container image (default "base")
        cpus: Number of CPU cores (default 1, max 8)
        time_limit_min: Maximum runtime in minutes (default 1)
        submitter_address: Your wallet address (optional, for job tracking)
        builder_code: Builder code for ERC-8021 attribution (optional)
    """
    if not script and not files:
        return {"error": "Provide one of: script or files"}
    body = _build_submit_body(
        script=script, files=files, entrypoint=entrypoint,
        image=image, cpus=cpus, time_limit_min=time_limit_min,
        submitter_address=submitter_address,
    )
    result = await _get_payment_requirements(body, builder_code)
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
    payment_signature: str,
    script: str | None = None,
    files: list[dict] | None = None,
    entrypoint: str | None = None,
    image: str = "base",
    cpus: int = 1,
    time_limit_min: int = 1,
    submitter_address: str | None = None,
    builder_code: str | None = None,
) -> dict:
    """Submit a compute job with a pre-signed x402 payment.

    This is step 2 of the autonomous payment flow. You must first call
    get_payment_requirements to get the payment header, sign it locally
    with your wallet, then pass the signature here.

    Provide ONE of: script or files (must match get_payment_requirements call).
    Include a Dockerfile in files to configure the environment (supports FROM, RUN,
    ENV, WORKDIR, ENTRYPOINT, CMD, COPY, ADD, ARG, LABEL, EXPOSE, SHELL).

    Args:
        payment_signature: The signed x402 payment string from your wallet
        script: Shell script to execute (must match get_payment_requirements call)
        files: List of {path, content} file dicts (must match)
        entrypoint: File to execute (must match, not needed if Dockerfile included)
        image: Container image (must match, not needed if Dockerfile included)
        cpus: Number of CPU cores (must match)
        time_limit_min: Maximum runtime in minutes (must match)
        submitter_address: Your wallet address (optional)
        builder_code: Builder code (must match if used in step 1)
    """
    if not script and not files:
        return {"error": "Provide one of: script or files"}
    body = _build_submit_body(
        script=script, files=files, entrypoint=entrypoint,
        image=image, cpus=cpus, time_limit_min=time_limit_min,
        submitter_address=submitter_address,
    )
    result = await _submit_with_payment(body, payment_signature, builder_code)
    status = result["status_code"]
    resp_body = result["body"]

    if status == 200:
        return {
            "job_id": resp_body.get("job_id"),
            "status": resp_body.get("status", "pending"),
            "price": resp_body.get("price"),
            "message": (
                f"Job {resp_body.get('job_id')} submitted successfully. "
                "Call get_job_status to poll for results."
            ),
        }
    if status == 402:
        return {
            "error": "payment_not_recognized",
            "message": "Payment signature not accepted. Re-run get_payment_requirements and sign again.",
        }
    if status == 403:
        reason = resp_body.get("error", "verification_failed")
        msg = f"Payment verification failed: {reason}."
        if reason == "insufficient_funds":
            msg = "Insufficient USDC balance. Ensure your wallet has enough USDC on Base."
        elif reason == "invalid_payload":
            msg = "Payment payload structure is invalid. Ensure you're using the latest x402 signing format."
        return {
            "error": f"payment_{reason}",
            "message": msg,
        }
    if status == 429:
        return {
            "error": "rate_limited",
            "message": "Too many requests. Wait and retry.",
        }
    if status == 503:
        return {
            "error": "facilitator_unavailable",
            "message": "Payment facilitator is temporarily unavailable. Retry shortly.",
        }
    logger.error("submit_and_pay: unexpected status %d: %s", status, resp_body)
    return {
        "error": f"unexpected_status_{status}",
        "message": f"Agent API returned unexpected status {status}.",
    }


@mcp.tool()
async def get_allowed_images() -> dict:
    """Get available container images for compute jobs.

    Returns the list of image IDs that can be passed as the 'image' parameter.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{_get_api_url()}/api/capabilities")
        resp.raise_for_status()
        data = resp.json()
        images = data.get("compute", {}).get("allowed_images", [])
        return {
            "images": images,
            "default": "base",
            "message": f"Available images: {', '.join(images)}. Use 'base' (Ubuntu 22.04) if unsure.",
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
            "script": "string (optional) - shell script to execute",
            "files": "array (optional) - [{path, content}] for multi-file workspace. Include a Dockerfile to configure the environment (FROM, RUN, ENV, WORKDIR, ENTRYPOINT, CMD, COPY, ADD, ARG, LABEL, EXPOSE, SHELL; USER/VOLUME/HEALTHCHECK/STOPSIGNAL/ONBUILD rejected).",
            "entrypoint": "string (optional) - file to execute (required with files unless Dockerfile included)",
            "image": "string (optional) - container image (default: base, ignored if Dockerfile present)",
            "cpus": "int (default 1, max 8) - number of CPU cores",
            "time_limit_min": "int (default 1) - max runtime in minutes",
            "submitter_address": "string (optional) - your wallet address for job tracking",
        },
        "submission_modes": ["script", "multi_file"],
        "price_endpoint": f"{_get_api_url()}/api/price?cpus=1&time_limit_min=1&submission_mode=script",
        "example_body": {
            "script": "echo hello world",
            "cpus": 1,
            "time_limit_min": 1,
        },
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main():
    port = int(os.environ.get("PORT", "8080"))
    cors_origins_str = os.environ.get(
        "CORS_ORIGINS",
        "https://ourocompute.com,http://localhost:3000,http://localhost:3001",
    )
    cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]

    app = mcp.http_app(
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Content-Type"],
            ),
        ]
    )
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
