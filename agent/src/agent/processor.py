"""Job processor: picks up pending ActiveJobs and runs them through the oracle agent."""

from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.agent.event_bus import EventBus
from src.agent.oracle import OracleDeps, oracle_agent
from src.api.pricing import estimate_llm_cost, verify_job_profit
from src.chain.client import BaseChainClient
from src.config import settings
from src.db.models import ActiveJob
from src.db.operations import complete_job, log_cost
from src.slurm.client import SlurmClient

logger = logging.getLogger(__name__)

# Max time for oracle agent run (validate + submit + poll 5min + proof)
ORACLE_RUN_TIMEOUT_S = 900


async def recover_stuck_jobs(
    session_maker: async_sessionmaker,
    event_bus: EventBus,
) -> None:
    """Reset orphaned jobs on startup.

    - processing: reset to pending (safe retry, not yet submitted to Slurm)
    - running: mark failed (already in Slurm, we lost the in-flight context)
    """
    async with session_maker() as db:
        # Processing: safe to retry
        proc_result = await db.execute(
            update(ActiveJob)
            .where(ActiveJob.status == "processing")
            .values(status="pending")
            .returning(ActiveJob.id)
        )
        recovered = proc_result.scalars().all()

        # Running: mark failed (Slurm job may complete but we can't track it)
        run_result = await db.execute(
            update(ActiveJob)
            .where(ActiveJob.status == "running")
            .values(status="failed")
            .returning(ActiveJob.id)
        )
        failed = run_result.scalars().all()

        await db.commit()
        if recovered:
            event_bus.emit("system", f"Recovered {len(recovered)} stuck processing jobs (-> pending)")
            logger.info("Recovered processing -> pending: %s", [str(r)[:8] for r in recovered])
        if failed:
            event_bus.emit("system", f"Marked {len(failed)} orphaned running jobs as failed")
            logger.info("Orphaned running -> failed: %s", [str(r)[:8] for r in failed])


async def process_pending_jobs(
    chain_client: BaseChainClient,
    slurm_client: SlurmClient,
    session_maker: async_sessionmaker,
    event_bus: EventBus,
) -> None:
    """Background loop that picks up pending jobs and processes them via the oracle agent."""
    await recover_stuck_jobs(session_maker, event_bus)

    while True:
        job = None
        try:
            async with session_maker() as db:
                result = await db.execute(
                    select(ActiveJob)
                    .where(ActiveJob.status == "pending")
                    .order_by(ActiveJob.submitted_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                job = result.scalar_one_or_none()

                if job is None:
                    await asyncio.sleep(5)
                    continue

                await db.execute(
                    update(ActiveJob)
                    .where(ActiveJob.id == job.id)
                    .values(status="processing")
                )
                await db.commit()

            event_bus.emit("agent", f"Processing job {str(job.id)[:8]}")
            job_start = time.monotonic()

            async with session_maker() as db:
                deps = OracleDeps(
                    job_id=str(job.id),
                    script=job.payload.get("script", ""),
                    partition=job.payload.get("partition", "default"),
                    nodes=job.payload.get("nodes", 1),
                    time_limit_min=job.payload.get("time_limit_min", 1),
                    client_builder_code=job.client_builder_code,
                    slurm_client=slurm_client,
                    chain_client=chain_client,
                    db=db,
                    event_bus=event_bus,
                )

                prompt = (
                    f"Process compute job {deps.job_id}. "
                    f"Script: {deps.script[:200]}. "
                    f"Nodes: {deps.nodes}, Time limit: {deps.time_limit_min}min. "
                    f"Validate, submit to Slurm, poll until complete, then submit proof on-chain."
                )

                agent_result = await asyncio.wait_for(
                    oracle_agent.run(prompt, deps=deps),
                    timeout=ORACLE_RUN_TIMEOUT_S,
                )
                usage = agent_result.usage()

                llm_cost_usd = estimate_llm_cost(
                    settings.LLM_MODEL,
                    usage.input_tokens or 0,
                    usage.output_tokens or 0,
                )
                await log_cost(db, "llm_inference", llm_cost_usd, {
                    "model": settings.LLM_MODEL,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "job_id": str(job.id),
                })

                job_result = agent_result.output
                compute_duration_s = time.monotonic() - job_start

                if deps.captured_output:
                    await db.execute(
                        update(ActiveJob)
                        .where(ActiveJob.id == job.id)
                        .values(payload=dict(job.payload, output_text=deps.captured_output[:10000]))
                    )
                    await db.commit()

                if job_result and job_result.proof_tx:
                    output_hash = bytes.fromhex(job_result.output_hash) if job_result.output_hash else b""
                    await complete_job(
                        db=db,
                        job_id=str(job.id),
                        proof_tx=job_result.proof_tx,
                        output_hash=output_hash,
                        gas_cost_usd=deps.captured_gas_cost_usd,
                        llm_cost_usd=llm_cost_usd,
                        compute_duration_s=compute_duration_s,
                    )

                    pv = verify_job_profit(
                        job_id=str(job.id),
                        price_charged_usd=float(job.price_usdc),
                        gas_cost_usd=deps.captured_gas_cost_usd,
                        llm_cost_usd=llm_cost_usd,
                        compute_duration_s=compute_duration_s,
                        nodes=deps.nodes,
                    )
                    event_bus.emit(
                        "profit",
                        f"Job {str(job.id)[:8]} — "
                        f"charged: ${pv.price_charged_usd:.4f}, "
                        f"actual cost: ${pv.actual_cost_usd:.4f}, "
                        f"profit: ${pv.actual_profit_usd:.4f} ({pv.actual_profit_pct:.1f}%) "
                        f"{'PROFITABLE' if pv.profitable else 'LOSS'}",
                    )
                    if not pv.profitable:
                        logger.warning("Job %s completed at a LOSS: %s", job.id, pv)

                    event_bus.emit("job", f"Job {str(job.id)[:8]} completed and archived")
                else:
                    async with session_maker() as db2:
                        await db2.execute(
                            update(ActiveJob)
                            .where(ActiveJob.id == job.id)
                            .values(status="failed")
                        )
                        await db2.commit()
                    event_bus.emit("job", f"Job {str(job.id)[:8]} processing ended: {job_result.status if job_result else 'no result'}")

        except asyncio.TimeoutError as e:
            event_bus.emit("agent_error", f"Job processor timeout after {ORACLE_RUN_TIMEOUT_S}s: {e}")
            logger.error("Oracle agent run timed out for job %s", job.id if job else "?")
            if job is not None:
                try:
                    async with session_maker() as err_db:
                        await err_db.execute(
                            update(ActiveJob)
                            .where(ActiveJob.id == job.id)
                            .values(status="failed")
                        )
                        await err_db.commit()
                    event_bus.emit("job", f"Job {str(job.id)[:8]} failed: timeout")
                except Exception:
                    logger.exception("failed to mark job %s as failed (timeout)", job.id)
            await asyncio.sleep(10)
        except Exception as e:
            event_bus.emit("agent_error", f"Job processor error (recovering): {e}")
            logger.exception("job processor error")
            if job is not None:
                try:
                    async with session_maker() as err_db:
                        await err_db.execute(
                            update(ActiveJob)
                            .where(ActiveJob.id == job.id)
                            .values(status="failed")
                        )
                        await err_db.commit()
                    event_bus.emit("job", f"Job {str(job.id)[:8]} failed: {e}")
                except Exception:
                    logger.exception("failed to mark job %s as failed", job.id)
            await asyncio.sleep(10)
