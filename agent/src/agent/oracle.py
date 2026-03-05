from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.event_bus import EventBus
from src.chain.client import BaseChainClient
from src.config import settings
from src.slurm.client import SlurmClient

logger = logging.getLogger(__name__)


@dataclass
class OracleDeps:
    job_id: str
    workspace_path: str
    entrypoint: str
    image: str  # default "base"
    partition: str
    nodes: int
    time_limit_min: int
    client_builder_code: str | None
    slurm_client: SlurmClient
    chain_client: BaseChainClient
    db: AsyncSession
    event_bus: EventBus
    captured_output: str = ""
    captured_gas_cost_usd: float = 0.0
    # Dockerfile-based fields
    dockerfile_content: str | None = None
    sif_path: str | None = None
    entrypoint_cmd: list[str] | None = field(default=None)


class JobResult(BaseModel):
    job_id: str
    status: str
    output_hash: str | None = None
    proof_tx: str | None = None


# ---------------------------------------------------------------------------
# Core implementation functions (used by both fast path and LLM agent)
# ---------------------------------------------------------------------------


async def validate_request_impl(deps: OracleDeps) -> str:
    deps.event_bus.emit("agent", f"Validating request for job {deps.job_id}")

    # Entrypoint comes from Dockerfile when dockerfile_content is set
    if not deps.dockerfile_content and not deps.entrypoint:
        return "INVALID: entrypoint required"
    if not deps.workspace_path:
        return "INVALID: workspace_path required"

    if deps.nodes < 1 or deps.nodes > 16:
        return "INVALID: nodes must be between 1 and 16"
    if deps.time_limit_min < 1 or deps.time_limit_min > 60:
        return "INVALID: time_limit_min must be between 1 and 60"

    return f"VALID: nodes={deps.nodes}, time={deps.time_limit_min}min"


async def submit_to_slurm_impl(deps: OracleDeps) -> str:
    deps.event_bus.emit("slurm", f"Submitting job {deps.job_id} to Slurm")

    try:
        from sqlalchemy import update as sql_update
        from src.db.models import ActiveJob

        slurm_job_id = await deps.slurm_client.submit_job(
            workspace_path=deps.workspace_path,
            entrypoint=deps.entrypoint,
            image=deps.image,
            sif_path=deps.sif_path,
            entrypoint_cmd=deps.entrypoint_cmd,
            partition=deps.partition,
            nodes=deps.nodes,
            time_limit_min=deps.time_limit_min,
        )

        await deps.db.execute(
            sql_update(ActiveJob)
            .where(ActiveJob.id == deps.job_id)
            .values(slurm_job_id=slurm_job_id, status="running")
        )
        await deps.db.commit()

        deps.event_bus.emit(
            "slurm",
            f"Job {deps.job_id} submitted as Slurm job {slurm_job_id} "
            f"(partition={deps.partition}, nodes={deps.nodes})",
        )
        return f"SUBMITTED: slurm_job_id={slurm_job_id}"
    except Exception as e:
        deps.event_bus.emit("slurm_error", f"Slurm submit failed: {e}")
        return f"ERROR: {e}"


async def poll_slurm_status_impl(deps: OracleDeps, slurm_job_id: int) -> str:
    for attempt in range(60):
        try:
            status = await deps.slurm_client.get_job_status(slurm_job_id)
        except Exception as e:
            if attempt % 5 == 0:
                deps.event_bus.emit("slurm", f"Poll error for {slurm_job_id}: {e} (retrying)")
                logger.warning("get_job_status failed (attempt %d): %s", attempt, e)
            await asyncio.sleep(5)
            continue
        state = status["state"]

        if state == "COMPLETED":
            output = await deps.slurm_client.get_job_output(slurm_job_id)
            deps.captured_output = output
            deps.event_bus.emit("slurm", f"Job {slurm_job_id} completed")
            return f"COMPLETED: output_length={len(output)}, output_preview={output[:200]}"

        if state in ("FAILED", "CANCELLED", "TIMEOUT"):
            deps.event_bus.emit("slurm", f"Job {slurm_job_id} {state}")
            return f"FAILED: state={state}, exit_code={status.get('exit_code')}"

        if attempt % 5 == 0:
            deps.event_bus.emit("slurm", f"Job {slurm_job_id} state={state} (poll {attempt})")

        await asyncio.sleep(5)

    return "TIMEOUT: polling exceeded 5 minutes"


async def submit_onchain_proof_impl(deps: OracleDeps, output_data: str) -> str:
    deps.event_bus.emit("chain", f"Computing output hash for job {deps.job_id}")

    output_hash = hashlib.sha256(output_data.encode()).digest()
    deps.event_bus.emit("chain", f"Submitting proof for job {deps.job_id} to Base")

    try:
        from src.db.operations import log_attribution, log_cost

        result = await deps.chain_client.submit_proof(
            job_id=deps.job_id,
            output_hash=output_hash,
            client_builder_code=deps.client_builder_code,
        )

        deps.captured_gas_cost_usd = result.gas_cost_usd
        await log_cost(deps.db, "gas", result.gas_cost_usd, {
            "tx_hash": result.tx_hash, "gas_wei": str(result.gas_cost_wei),
            "job_id": deps.job_id,
        })
        await log_attribution(deps.db, result.tx_hash, result.codes, result.gas_cost_wei)

        deps.event_bus.emit(
            "chain",
            f"Proof posted for job {deps.job_id}: tx={result.tx_hash} (builder codes attached)",
        )
        return f"PROOF_POSTED: tx_hash={result.tx_hash}, output_hash={output_hash.hex()}"
    except Exception as e:
        deps.event_bus.emit("chain_error", f"Proof submission failed: {e}")
        return f"ERROR: {e}"


# ---------------------------------------------------------------------------
# Dockerfile image build step
# ---------------------------------------------------------------------------


async def build_image_if_needed(deps: OracleDeps) -> None:
    """Parse Dockerfile and build image if needed. Mutates deps in place."""
    if not deps.dockerfile_content:
        return  # Legacy path — use image/entrypoint fields as-is

    from src.agent.dockerfile import (
        IMAGES_DIR,
        PREBUILT_ALIASES,
        dockerfile_to_def,
        parse_dockerfile,
    )

    parsed = parse_dockerfile(deps.dockerfile_content)
    deps.entrypoint_cmd = parsed.entrypoint_cmd

    if not parsed.needs_build:
        # Prebuilt alias, no RUN → use prebuilt .sif directly
        sif_file = PREBUILT_ALIASES[parsed.from_image]
        deps.sif_path = os.path.join(IMAGES_DIR, sif_file)
        deps.event_bus.emit("agent", f"Using prebuilt image: {parsed.from_image}")
        return

    # Needs build → convert to .def and send to proxy
    def_content = dockerfile_to_def(parsed)
    deps.event_bus.emit("agent", f"Building image from Dockerfile (FROM {parsed.from_image})...")

    result = await deps.slurm_client.build_image(def_content)
    deps.sif_path = result["sif_path"]
    if result.get("cached"):
        deps.event_bus.emit("agent", "Image found in cache")
    else:
        deps.event_bus.emit("agent", f"Image built in {result.get('build_time_s', 0):.1f}s")


# ---------------------------------------------------------------------------
# Deterministic fast path — no LLM, direct tool execution
# ---------------------------------------------------------------------------


async def _cleanup_workspace(deps: OracleDeps) -> None:
    """Clean up NFS workspace after job completion."""
    try:
        await deps.slurm_client.delete_workspace(deps.job_id)
    except Exception as e:
        logger.warning("Workspace cleanup failed for %s: %s", deps.job_id, e)


async def process_job_fast(deps: OracleDeps) -> JobResult:
    """Execute the standard validate -> submit -> poll -> prove pipeline without an LLM."""
    validation = await validate_request_impl(deps)
    if validation.startswith("INVALID"):
        await _cleanup_workspace(deps)
        return JobResult(job_id=deps.job_id, status="failed")

    # Build image from Dockerfile if present (before Slurm submit, outside time_limit)
    try:
        await build_image_if_needed(deps)
    except Exception as e:
        deps.event_bus.emit("agent_error", f"Image build failed: {e}")
        await _cleanup_workspace(deps)
        return JobResult(job_id=deps.job_id, status="failed")

    submission = await submit_to_slurm_impl(deps)
    if submission.startswith("ERROR"):
        await _cleanup_workspace(deps)
        return JobResult(job_id=deps.job_id, status="failed")

    slurm_job_id = int(submission.split("slurm_job_id=")[1])

    poll_result = await poll_slurm_status_impl(deps, slurm_job_id)

    # Cleanup workspace AFTER output is captured
    await _cleanup_workspace(deps)

    if not poll_result.startswith("COMPLETED"):
        return JobResult(job_id=deps.job_id, status="failed")

    proof_result = await submit_onchain_proof_impl(deps, deps.captured_output)
    if proof_result.startswith("ERROR"):
        return JobResult(job_id=deps.job_id, status="completed_no_proof")

    tx_hash = proof_result.split("tx_hash=")[1].split(",")[0]
    output_hash = proof_result.split("output_hash=")[1]
    return JobResult(
        job_id=deps.job_id,
        status="completed",
        output_hash=output_hash,
        proof_tx=tx_hash,
    )


# ---------------------------------------------------------------------------
# LLM agent (fallback for complex error recovery)
# ---------------------------------------------------------------------------

oracle_agent = Agent(
    settings.LLM_MODEL,
    deps_type=OracleDeps,
    output_type=JobResult,
    system_prompt=(
        "You are Ouro, a Proof-of-Compute Oracle. You receive compute requests, "
        "submit them to the HPC cluster, monitor execution, and post verifiable "
        "proofs on-chain. You MUST use the tools in order: validate -> submit_to_slurm "
        "-> poll_status -> submit_proof. Report results precisely."
    ),
)


@oracle_agent.tool
async def validate_request(ctx: RunContext[OracleDeps]) -> str:
    return await validate_request_impl(ctx.deps)


@oracle_agent.tool
async def submit_to_slurm(ctx: RunContext[OracleDeps]) -> str:
    return await submit_to_slurm_impl(ctx.deps)


@oracle_agent.tool
async def poll_slurm_status(ctx: RunContext[OracleDeps], slurm_job_id: int) -> str:
    return await poll_slurm_status_impl(ctx.deps, slurm_job_id)


@oracle_agent.tool
async def submit_onchain_proof(ctx: RunContext[OracleDeps], output_data: str) -> str:
    return await submit_onchain_proof_impl(ctx.deps, output_data)
