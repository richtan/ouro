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
from src.slurm.scaler import AutoScaler

logger = logging.getLogger(__name__)

# Shared scaler instance for reactive capacity checks
_scaler = AutoScaler()


@dataclass
class OracleDeps:
    job_id: str
    workspace_path: str
    entrypoint: str
    image: str  # default "base"
    partition: str
    cpus: int
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

    if deps.cpus < 1 or deps.cpus > 8:
        return "INVALID: cpus must be between 1 and 8"
    if deps.time_limit_min < 1 or deps.time_limit_min > 60:
        return "INVALID: time_limit_min must be between 1 and 60"

    return f"VALID: cpus={deps.cpus}, time={deps.time_limit_min}min"


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
            cpus=deps.cpus,
            time_limit_min=deps.time_limit_min,
        )

        await deps.db.execute(
            sql_update(ActiveJob)
            .where(ActiveJob.id == deps.job_id)
            .values(slurm_job_id=slurm_job_id)
        )
        await deps.db.commit()

        deps.event_bus.emit(
            "slurm",
            f"Job {deps.job_id} submitted as Slurm job {slurm_job_id} "
            f"(partition={deps.partition}, cpus={deps.cpus})",
        )
        return f"SUBMITTED: slurm_job_id={slurm_job_id}"
    except Exception as e:
        deps.event_bus.emit("slurm_error", f"Slurm submit failed: {e}")
        return f"ERROR: {e}"


async def poll_slurm_status_impl(deps: OracleDeps, slurm_job_id: int) -> str:
    from sqlalchemy import update as sql_update
    from src.db.models import ActiveJob

    marked_running = False
    pending_count = 0  # consecutive PENDING polls with resource reason

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
        reason = status.get("reason", "")

        if state == "COMPLETED":
            output = await deps.slurm_client.get_job_output(slurm_job_id)
            deps.captured_output = output
            deps.event_bus.emit("slurm", f"Job {slurm_job_id} completed")
            return f"COMPLETED: output_length={len(output)}, output_preview={output[:200]}"

        if state in ("FAILED", "CANCELLED", "TIMEOUT"):
            deps.event_bus.emit("slurm", f"Job {slurm_job_id} {state}")
            return f"FAILED: state={state}, exit_code={status.get('exit_code')}"

        # Track transition to RUNNING
        if state in ("RUNNING", "COMPLETING") and not marked_running:
            await deps.db.execute(
                sql_update(ActiveJob)
                .where(ActiveJob.id == deps.job_id)
                .values(status="running")
            )
            await deps.db.commit()
            marked_running = True
            pending_count = 0

        # Detect stuck PENDING (no node available)
        if state == "PENDING" and "ReqNodeNotAvail" in reason:
            pending_count += 1
            if pending_count >= 6:
                deps.event_bus.emit(
                    "slurm",
                    f"Job {slurm_job_id} stuck PENDING: {reason} — cancelling",
                )
                try:
                    await deps.slurm_client.cancel_job(slurm_job_id)
                except Exception:
                    pass
                return f"FAILED: state=PENDING, reason={reason} (no suitable node, cancelled)"
        elif state != "PENDING":
            pending_count = 0

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

    has_external_entrypoint = bool(deps.entrypoint)
    parsed = parse_dockerfile(deps.dockerfile_content, require_entrypoint=not has_external_entrypoint)
    deps.entrypoint_cmd = parsed.entrypoint_cmd or None

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


async def _ensure_capacity(deps: OracleDeps) -> None:
    """Check cluster capacity for this job's CPU needs. Boot a spot node if needed.

    Raises RuntimeError if capacity cannot be ensured.
    """
    cpus_needed = deps.cpus
    cluster_info = await deps.slurm_client.get_cluster_info()
    nodes = cluster_info.get("nodes_detail", [])

    # Find max CPUs available on any single IDLE or MIXED node
    max_node_cpus = 0
    for node in nodes:
        states = node.get("state", [])
        if "DOWN" in states:
            continue
        if "IDLE" in states:
            max_node_cpus = max(max_node_cpus, node.get("cpus", 0))
        elif "MIXED" in states:
            max_node_cpus = max(max_node_cpus, node.get("free_cpus", 0))

    if max_node_cpus >= cpus_needed:
        return  # Cluster has capacity

    if not settings.AUTO_SCALING_ENABLED:
        raise RuntimeError(
            f"No node has {cpus_needed} CPUs (max available: {max_node_cpus}). "
            f"Enable auto-scaling for larger jobs."
        )

    # Boot a spot node
    deps.event_bus.emit(
        "scaler",
        f"No node has {cpus_needed} CPUs (max: {max_node_cpus}), scaling out...",
    )
    node_name, template = _scaler._pick_node_for_cpus(cpus_needed, nodes)
    if not node_name:
        raise RuntimeError(
            f"No spot node tier supports {cpus_needed} CPUs"
        )

    event = await _scaler._boot_spot_instance(node_name, template)
    if not event or event.action != "scale_out":
        raise RuntimeError(f"Failed to boot spot node {node_name}: {event.reason if event else 'unknown'}")

    deps.event_bus.emit("scaler", f"Booted {node_name}, waiting for it to become IDLE...")

    # Poll until node appears as IDLE (timeout 180s)
    for _ in range(18):
        await asyncio.sleep(10)
        info = await deps.slurm_client.get_cluster_info()
        for node in info.get("nodes_detail", []):
            if node["name"] == node_name and "IDLE" in node.get("state", []):
                deps.event_bus.emit("scaler", f"{node_name} is IDLE — proceeding")
                return

    raise RuntimeError(f"Spot node {node_name} did not become IDLE within 180s")


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

    # Ensure cluster has capacity for this job's CPU needs
    try:
        await _ensure_capacity(deps)
    except RuntimeError as e:
        deps.event_bus.emit("agent_error", f"Capacity check failed: {e}")
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
