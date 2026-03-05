"""Job processor: picks up pending ActiveJobs, runs them through the
deterministic fast path, and falls back to the LLM agent on failure."""

from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.agent.event_bus import EventBus
from src.agent.oracle import JobResult, OracleDeps, oracle_agent, process_job_fast
from src.api.pricing import estimate_llm_cost, verify_job_profit
from src.chain.client import BaseChainClient
from src.config import settings
from src.db.models import ActiveJob
from src.db.operations import complete_job, issue_credit, log_audit, log_cost
from src.slurm.client import SlurmClient

logger = logging.getLogger(__name__)

FAST_PATH_TIMEOUT_S = 600
LLM_FALLBACK_TIMEOUT_S = 900
MAX_RETRIES = 2
MAX_CONCURRENT_JOBS = 3

TRANSIENT_ERRORS = ("timeout", "connection", "unreachable", "slurm_error")


def _is_transient(error_msg: str) -> bool:
    lower = error_msg.lower()
    return any(tok in lower for tok in TRANSIENT_ERRORS)


async def recover_stuck_jobs(
    session_maker: async_sessionmaker,
    event_bus: EventBus,
) -> None:
    """Reset orphaned jobs on startup.

    - processing: reset to pending (safe retry, not yet submitted to Slurm)
    - running: mark failed (already in Slurm, we lost the in-flight context)
    """
    async with session_maker() as db:
        proc_result = await db.execute(
            update(ActiveJob)
            .where(ActiveJob.status == "processing")
            .values(status="pending")
            .returning(ActiveJob.id)
        )
        recovered = proc_result.scalars().all()

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


async def _mark_failed(
    session_maker: async_sessionmaker,
    event_bus: EventBus,
    job: ActiveJob,
    reason: str,
) -> None:
    """Mark a job as failed and issue a credit to the submitter."""
    try:
        async with session_maker() as db:
            await db.execute(
                update(ActiveJob)
                .where(ActiveJob.id == job.id)
                .values(status="failed")
            )
            await db.commit()

        if job.submitter_address and float(job.price_usdc) > 0:
            async with session_maker() as db:
                await issue_credit(
                    db,
                    wallet_address=job.submitter_address,
                    amount_usdc=float(job.price_usdc),
                    reason=f"job_failed:{job.id}",
                )
                await log_audit(
                    db,
                    event_type="credit_issued",
                    job_id=job.id,
                    wallet_address=job.submitter_address,
                    amount_usdc=float(job.price_usdc),
                    detail={"reason": reason},
                )

        event_bus.emit("job", f"Job {str(job.id)[:8]} failed: {reason}")
    except Exception:
        logger.exception("failed to mark job %s as failed", job.id)


async def _maybe_retry(
    session_maker: async_sessionmaker,
    event_bus: EventBus,
    job: ActiveJob,
    reason: str,
) -> bool:
    """If the failure is transient and retries remain, reset to pending. Returns True if retried."""
    retry_count = job.retry_count or 0
    if retry_count >= MAX_RETRIES or not _is_transient(reason):
        return False

    try:
        async with session_maker() as db:
            await db.execute(
                update(ActiveJob)
                .where(ActiveJob.id == job.id)
                .values(status="pending", retry_count=retry_count + 1)
            )
            await db.commit()
        event_bus.emit(
            "job",
            f"Job {str(job.id)[:8]} retrying ({retry_count + 1}/{MAX_RETRIES}): {reason}",
        )
        return True
    except Exception:
        logger.exception("failed to retry job %s", job.id)
        return False


async def _finalize_success(
    session_maker: async_sessionmaker,
    event_bus: EventBus,
    job: ActiveJob,
    job_result: JobResult,
    deps: OracleDeps,
    llm_cost_usd: float,
    compute_duration_s: float,
) -> None:
    """Archive a successful job and log profitability."""
    async with session_maker() as db:
        if deps.captured_output:
            await db.execute(
                update(ActiveJob)
                .where(ActiveJob.id == job.id)
                .values(payload=dict(job.payload, output_text=deps.captured_output[:10000]))
            )
            await db.commit()

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

        await log_audit(
            db,
            event_type="job_completed",
            job_id=job.id,
            wallet_address=job.submitter_address,
            amount_usdc=float(job.price_usdc),
            detail={
                "proof_tx": job_result.proof_tx,
                "gas_cost_usd": deps.captured_gas_cost_usd,
                "duration_s": compute_duration_s,
            },
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


async def _process_one_job(
    job: ActiveJob,
    chain_client: BaseChainClient,
    slurm_client: SlurmClient,
    session_maker: async_sessionmaker,
    event_bus: EventBus,
    semaphore: asyncio.Semaphore,
) -> None:
    """Process a single job. Runs as a concurrent task; releases semaphore when done."""
    try:
        event_bus.emit("agent", f"Processing job {str(job.id)[:8]} (fast path)")
        job_start = time.monotonic()
        llm_cost_usd = 0.0

        async with session_maker() as db:
            payload = job.payload or {}

            # Legacy normalization: old script-mode jobs have no workspace_path.
            # Create workspace at processing time so the unified path works.
            workspace_path = payload.get("workspace_path")
            entrypoint = payload.get("entrypoint")
            if not workspace_path and payload.get("script"):
                script = payload["script"]
                files = [{"path": "job.sh", "content": script}]
                workspace_path = await slurm_client.create_workspace(str(job.id), files)
                entrypoint = "job.sh"
                event_bus.emit("agent", f"Legacy job {str(job.id)[:8]}: created workspace from inline script")

            deps = OracleDeps(
                job_id=str(job.id),
                workspace_path=workspace_path or "",
                entrypoint=entrypoint or "",
                image=payload.get("image", "base"),
                partition=payload.get("partition", "default"),
                nodes=payload.get("nodes", 1),
                time_limit_min=payload.get("time_limit_min", 1),
                client_builder_code=job.client_builder_code,
                slurm_client=slurm_client,
                chain_client=chain_client,
                db=db,
                event_bus=event_bus,
                dockerfile_content=payload.get("dockerfile_content"),
            )

            job_result = await asyncio.wait_for(
                process_job_fast(deps),
                timeout=FAST_PATH_TIMEOUT_S,
            )

        compute_duration_s = time.monotonic() - job_start

        if job_result and job_result.proof_tx:
            await _finalize_success(
                session_maker, event_bus, job, job_result,
                deps, llm_cost_usd, compute_duration_s,
            )
        else:
            reason = job_result.status if job_result else "no result"
            retried = await _maybe_retry(session_maker, event_bus, job, reason)
            if not retried:
                await _mark_failed(session_maker, event_bus, job, reason)

    except asyncio.TimeoutError:
        reason = f"timeout after {FAST_PATH_TIMEOUT_S}s"
        event_bus.emit("agent_error", f"Job {str(job.id)[:8]} {reason}")
        logger.error("Fast path timed out for job %s", job.id)
        retried = await _maybe_retry(session_maker, event_bus, job, reason)
        if not retried:
            await _mark_failed(session_maker, event_bus, job, reason)
    except Exception as e:
        reason = str(e)
        event_bus.emit("agent_error", f"Job {str(job.id)[:8]} error: {reason}")
        logger.exception("job processor error for %s", job.id)
        retried = await _maybe_retry(session_maker, event_bus, job, reason)
        if not retried:
            await _mark_failed(session_maker, event_bus, job, reason)
    finally:
        semaphore.release()


async def process_pending_jobs(
    chain_client: BaseChainClient,
    slurm_client: SlurmClient,
    session_maker: async_sessionmaker,
    event_bus: EventBus,
) -> None:
    """Background loop: pick up pending jobs and process up to MAX_CONCURRENT_JOBS concurrently."""
    await recover_stuck_jobs(session_maker, event_bus)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

    while True:
        await semaphore.acquire()
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
                    semaphore.release()
                    await asyncio.sleep(5)
                    continue

                await db.execute(
                    update(ActiveJob)
                    .where(ActiveJob.id == job.id)
                    .values(status="processing")
                )
                await db.commit()

            # Spawn concurrent task — semaphore is released in _process_one_job's finally
            asyncio.create_task(_process_one_job(
                job, chain_client, slurm_client, session_maker, event_bus, semaphore,
            ))

        except Exception as e:
            semaphore.release()
            logger.exception("Error picking up job: %s", e)
            event_bus.emit("agent_error", f"Job pickup error: {e}")
            await asyncio.sleep(10)
