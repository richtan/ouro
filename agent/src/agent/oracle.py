from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

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
    script: str
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


class JobResult(BaseModel):
    job_id: str
    status: str
    output_hash: str | None = None
    proof_tx: str | None = None


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
    deps = ctx.deps
    deps.event_bus.emit("agent", f"Validating request for job {deps.job_id}")

    if not deps.script or not deps.script.strip():
        return "INVALID: script is empty"
    if deps.nodes < 1 or deps.nodes > 16:
        return "INVALID: nodes must be between 1 and 16"
    if deps.time_limit_min < 1 or deps.time_limit_min > 60:
        return "INVALID: time_limit_min must be between 1 and 60"

    return f"VALID: script={len(deps.script)} chars, nodes={deps.nodes}, time={deps.time_limit_min}min"


@oracle_agent.tool
async def submit_to_slurm(ctx: RunContext[OracleDeps]) -> str:
    deps = ctx.deps
    deps.event_bus.emit("slurm", f"Submitting job {deps.job_id} to Slurm")

    try:
        from sqlalchemy import update as sql_update
        from src.db.models import ActiveJob

        slurm_job_id = await deps.slurm_client.submit_job(
            script=deps.script,
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


@oracle_agent.tool
async def poll_slurm_status(ctx: RunContext[OracleDeps], slurm_job_id: int) -> str:
    deps = ctx.deps
    import asyncio

    for attempt in range(60):
        status = await deps.slurm_client.get_job_status(slurm_job_id)
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


@oracle_agent.tool
async def submit_onchain_proof(ctx: RunContext[OracleDeps], output_data: str) -> str:
    deps = ctx.deps
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
