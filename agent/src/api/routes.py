from __future__ import annotations

import hmac
import json
import logging
import time
import uuid
from collections import OrderedDict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.event_bus import EventBus
import src.api.pricing as pricing_state
from src.api.pricing import calculate_price
from src.chain.client import BaseChainClient
from src.chain import erc8021
from src.config import settings
from src.db.models import (
    ActiveJob,
    AgentCost,
    AttributionLog,
    AuditLog,
    HistoricalData,
    PaymentSession,
    WalletSnapshot,
)
from src.db.operations import get_available_credit, log_audit, redeem_credits
from src.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ComputeSubmitRequest(BaseModel):
    script: str = Field(..., min_length=1, max_length=65_536)
    nodes: int = Field(default=1, ge=1, le=16)
    time_limit_min: int = Field(default=1, ge=1, le=60)
    submitter_address: Optional[str] = None
    builder_code: Optional[str] = None


class CreateSessionRequest(BaseModel):
    script: str = Field(..., min_length=1, max_length=65_536)
    nodes: int = Field(default=1, ge=1, le=16)
    time_limit_min: int = Field(default=1, ge=1, le=60)
    price: str = "unknown"


class CompleteSessionRequest(BaseModel):
    job_id: str = Field(..., min_length=1)

_event_bus: EventBus | None = None
_chain_client: BaseChainClient | None = None
_resource_server = None

MAX_SCRIPT_SIZE = 65_536
MAX_ACTIVE_JOBS_PER_WALLET = 20


# ---------------------------------------------------------------------------
# Price cache — ensures x402 402→retry uses the same price
# ---------------------------------------------------------------------------

class _PriceCache:
    def __init__(self, ttl: float = 30.0, max_size: int = 100):
        self._cache: OrderedDict = OrderedDict()
        self._ttl = ttl
        self._max_size = max_size

    def get(self, key: tuple):
        entry = self._cache.get(key)
        if entry and time.monotonic() - entry["ts"] < self._ttl:
            self._cache.move_to_end(key)
            return entry["quote"]
        if entry:
            del self._cache[key]
        return None

    def set(self, key: tuple, quote):
        self._cache[key] = {"quote": quote, "ts": time.monotonic()}
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)


_price_cache = _PriceCache()


def _parse_facilitator_error(error_str: str) -> dict | None:
    """Try to extract structured JSON from a facilitator error message.

    The x402 facilitator client raises ValueError with messages like:
        Facilitator verify failed (400): {"invalidMessage":"...","invalidReason":"...","isValid":false,...}

    Returns the parsed dict if the message looks like a facilitator rejection,
    or None if it's a transient/unrecognized error.
    """
    idx = error_str.find("{")
    if idx == -1:
        return None
    try:
        data = json.loads(error_str[idx:])
        if isinstance(data, dict) and "invalidReason" in data:
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


# ---------------------------------------------------------------------------
# Rate limiter — per-wallet + global sliding window
# ---------------------------------------------------------------------------

class _RateLimiter:
    def __init__(self, per_key_limit: int = 10, global_limit: int = 100, window_s: float = 60.0):
        self._per_key: dict[str, list[float]] = {}
        self._global: list[float] = []
        self._per_key_limit = per_key_limit
        self._global_limit = global_limit
        self._window = window_s
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = 300.0  # 5 minutes

    def _prune(self, timestamps: list[float], now: float) -> list[float]:
        cutoff = now - self._window
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)
        return timestamps

    def _maybe_cleanup(self, now: float) -> None:
        """Prune expired timestamps and remove empty keys to prevent unbounded growth."""
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        cutoff = now - self._window
        empty_keys = []
        for k, v in self._per_key.items():
            while v and v[0] < cutoff:
                v.pop(0)
            if not v:
                empty_keys.append(k)
        for k in empty_keys:
            del self._per_key[k]

    def check(self, key: str | None) -> bool:
        """Returns True if the request is allowed."""
        now = time.monotonic()
        self._maybe_cleanup(now)
        self._global = self._prune(self._global, now)
        if len(self._global) >= self._global_limit:
            return False
        if key:
            ts_list = self._per_key.setdefault(key, [])
            self._prune(ts_list, now)
            if len(ts_list) >= self._per_key_limit:
                return False
            ts_list.append(now)
        self._global.append(now)
        return True


_rate_limiter = _RateLimiter()


async def require_admin_key(request: Request):
    if not settings.ADMIN_API_KEY:
        return
    key = request.headers.get("x-admin-key", "")
    if not hmac.compare_digest(key, settings.ADMIN_API_KEY):
        raise HTTPException(403, "Invalid admin key")


def init_routes(event_bus: EventBus, chain_client: BaseChainClient, resource_server) -> None:
    global _event_bus, _chain_client, _resource_server
    _event_bus = event_bus
    _chain_client = chain_client
    _resource_server = resource_server


# ---------------------------------------------------------------------------
# GET /health, GET /health/ready
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(db: AsyncSession = Depends(get_db)):
    checks: dict[str, str] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    if _chain_client:
        try:
            eth_bal, usdc_bal = await _chain_client.get_balances()
            checks["wallet_eth"] = "ok" if eth_bal > 0 else "low"
            checks["wallet_usdc"] = f"{usdc_bal:.2f}"
        except Exception as e:
            checks["wallet"] = f"error: {e}"

    all_ok = all(v == "ok" for k, v in checks.items() if k not in ("wallet_usdc",))
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )


# ---------------------------------------------------------------------------
# POST /api/compute/submit — x402-gated compute endpoint
# ---------------------------------------------------------------------------

@router.post("/api/compute/submit")
async def submit_compute(request: Request, db: AsyncSession = Depends(get_db)):
    from x402 import ResourceConfig
    from x402.http.utils import (
        decode_payment_signature_header,
        encode_payment_required_header,
    )

    payment_header = request.headers.get("payment-signature")
    raw_body = await request.json()
    client_code = request.headers.get("X-BUILDER-CODE")

    try:
        body = ComputeSubmitRequest(**raw_body)
    except ValidationError as e:
        raise HTTPException(422, detail=e.errors())

    if payment_header:
        logger.debug("x402 payment-signature header received (len=%d)", len(payment_header))
        try:
            from x402.http.utils import safe_base64_decode
            decoded = safe_base64_decode(payment_header)
            logger.debug("x402 decoded payload: %s", decoded[:500])
        except Exception:
            logger.debug("x402 could not decode payment-signature header")

    script = body.script
    nodes = body.nodes
    time_limit_min = body.time_limit_min
    submitter_address = body.submitter_address

    rate_key = submitter_address.lower() if submitter_address else None
    if not _rate_limiter.check(rate_key):
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests"},
            headers={"Retry-After": "60"},
        )

    if submitter_address:
        active_count_q = await db.execute(
            select(func.count(ActiveJob.id))
            .where(func.lower(ActiveJob.submitter_address) == submitter_address.lower())
        )
        if active_count_q.scalar_one() >= MAX_ACTIVE_JOBS_PER_WALLET:
            raise HTTPException(429, f"Too many active jobs (max {MAX_ACTIVE_JOBS_PER_WALLET})")

    cache_key = (nodes, time_limit_min)
    quote = _price_cache.get(cache_key)
    if not quote:
        quote = await calculate_price(db, nodes, time_limit_min)
        _price_cache.set(cache_key, quote)

    config = ResourceConfig(
        scheme="exact",
        network=settings.CHAIN_CAIP2,
        pay_to=settings.WALLET_ADDRESS,
        price=quote.price_str,
    )
    requirements = _resource_server.build_payment_requirements(config)

    if not payment_header:
        payment_required = _resource_server.create_payment_required_response(requirements)
        encoded_header = encode_payment_required_header(payment_required)
        return JSONResponse(
            status_code=402,
            content={
                "error": "Payment required",
                "price": quote.price_str,
                "breakdown": quote.breakdown,
            },
            headers={"PAYMENT-REQUIRED": encoded_header},
        )

    try:
        payload = decode_payment_signature_header(payment_header)
        result = await _resource_server.verify_payment(payload, requirements[0])
    except Exception as e:
        error_str = str(e)
        # The facilitator client raises ValueError with the raw response for
        # non-200 statuses.  Parse it to distinguish client errors (403) from
        # genuine availability problems (503).
        facilitator_reason = _parse_facilitator_error(error_str)
        if facilitator_reason:
            logger.warning("x402 verification rejected: %s", facilitator_reason)
            return JSONResponse(
                status_code=403,
                content={
                    "error": facilitator_reason.get("invalidReason", "verification_failed"),
                    "detail": facilitator_reason.get("invalidMessage", error_str),
                    "payer": facilitator_reason.get("payer"),
                },
            )
        logger.error("x402 facilitator error: %s", e)
        return JSONResponse(
            status_code=503,
            content={"error": "Payment verification temporarily unavailable", "detail": error_str},
            headers={"Retry-After": "30"},
        )

    if not result.is_valid:
        logger.warning("x402 payment verification failed: %s", getattr(result, "error", "unknown"))
        raise HTTPException(403, "Payment verification failed")

    _event_bus.emit(
        "x402",
        f"Payment verified: {quote.price_str} from client "
        f"(cost floor: ${quote.cost_floor_usd:.4f}, guaranteed profit: {quote.profit_pct:.1f}%)",
    )

    job_id = str(uuid.uuid4())
    job = ActiveJob(
        id=job_id,
        payload=raw_body,
        price_usdc=quote.price_usd,
        client_builder_code=client_code,
        submitter_address=submitter_address,
        status="pending",
    )
    db.add(job)
    await db.commit()

    await log_audit(
        db,
        event_type="payment_received",
        job_id=uuid.UUID(job_id),
        wallet_address=submitter_address,
        amount_usdc=quote.price_usd,
        detail={"price_str": quote.price_str},
    )

    _event_bus.emit("job", f"Job {job_id[:8]} created, queued for processing")

    return {
        "job_id": job_id,
        "status": "pending",
        "price": quote.price_str,
        "profitability": {
            "guaranteed": quote.guaranteed_profitable,
            "estimated_profit_pct": round(quote.profit_pct, 1),
        },
    }


# ---------------------------------------------------------------------------
# GET /api/stream — SSE live event feed
# ---------------------------------------------------------------------------

@router.get("/api/stream")
async def event_stream(request: Request, _=Depends(require_admin_key)):
    async def generate():
        async for event in _event_bus.subscribe():
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /api/stats — aggregate P&L, job counts, revenue breakdown
# ---------------------------------------------------------------------------

@router.get("/api/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    revenue_q = await db.execute(
        select(
            func.coalesce(func.sum(HistoricalData.price_usdc), 0).label("total_revenue"),
            func.count(HistoricalData.id).label("completed_jobs"),
            func.coalesce(func.avg(HistoricalData.compute_duration_s), 0).label("avg_duration"),
        )
    )
    rev_row = revenue_q.one()

    gas_q = await db.execute(
        select(func.coalesce(func.sum(AgentCost.amount_usd), 0)).where(
            AgentCost.cost_type == "gas"
        )
    )
    gas_costs = float(gas_q.scalar_one())

    llm_q = await db.execute(
        select(func.coalesce(func.sum(AgentCost.amount_usd), 0)).where(
            AgentCost.cost_type == "llm_inference"
        )
    )
    llm_costs = float(llm_q.scalar_one())

    active_q = await db.execute(select(func.count(ActiveJob.id)))
    active_jobs = active_q.scalar_one()

    total_revenue = float(rev_row.total_revenue)
    total_costs = gas_costs + llm_costs
    net_pnl = total_revenue - total_costs
    completed = rev_row.completed_jobs

    avg_cost_per_job = total_costs / completed if completed > 0 else 0
    avg_price_per_job = total_revenue / completed if completed > 0 else 0
    avg_margin_per_job = avg_price_per_job - avg_cost_per_job

    proof_count = 0
    if _chain_client:
        try:
            proof_count = await _chain_client.get_on_chain_proof_count()
        except Exception:
            pass

    jobs_last_hour_q = await db.execute(
        select(func.count(ActiveJob.id)).where(
            ActiveJob.submitted_at >= text("now() - interval '1 hour'")
        )
    )
    jobs_last_hour = int(jobs_last_hour_q.scalar_one())

    return {
        "total_revenue_usdc": total_revenue,
        "gas_costs_usd": gas_costs,
        "llm_costs_usd": llm_costs,
        "total_costs_usd": total_costs,
        "net_pnl_usd": net_pnl,
        "completed_jobs": completed,
        "active_jobs": active_jobs,
        "avg_duration_s": float(rev_row.avg_duration),
        "sustainability_ratio": total_revenue / total_costs if total_costs > 0 else float("inf"),
        "survival_phase": pricing_state.current_phase,
        "demand_multiplier": pricing_state.demand_multiplier,
        "heartbeat_interval_min": pricing_state.heartbeat_interval_min,
        "margin_multiplier": pricing_state.current_margin,
        "jobs_last_hour": jobs_last_hour,
        "on_chain_proof_count": proof_count,
        "revenue_model": "guaranteed_margin_compute",
        "avg_cost_per_job": avg_cost_per_job,
        "avg_price_per_job": avg_price_per_job,
        "avg_margin_per_job": avg_margin_per_job,
    }


# ---------------------------------------------------------------------------
# GET /api/wallet — current balances + recent snapshots
# ---------------------------------------------------------------------------

@router.get("/api/wallet")
async def get_wallet(db: AsyncSession = Depends(get_db)):
    snapshots_q = await db.execute(
        select(WalletSnapshot)
        .order_by(WalletSnapshot.recorded_at.desc())
        .limit(100)
    )
    snapshots = snapshots_q.scalars().all()

    latest = snapshots[0] if snapshots else None

    return {
        "address": settings.WALLET_ADDRESS,
        "eth_balance_wei": str(latest.eth_balance) if latest else "0",
        "usdc_balance": float(latest.usdc_balance) if latest else 0.0,
        "eth_price_usd": float(latest.eth_price_usd) if latest and latest.eth_price_usd else 0.0,
        "snapshots": [
            {
                "eth_balance_wei": str(s.eth_balance),
                "usdc_balance": float(s.usdc_balance),
                "eth_price_usd": float(s.eth_price_usd) if s.eth_price_usd else None,
                "recorded_at": s.recorded_at.isoformat(),
            }
            for s in snapshots
        ],
    }


# ---------------------------------------------------------------------------
# GET /api/jobs — recent active + historical jobs
# ---------------------------------------------------------------------------

@router.get("/api/jobs")
async def get_jobs(db: AsyncSession = Depends(get_db), _=Depends(require_admin_key)):
    active_q = await db.execute(
        select(ActiveJob).order_by(ActiveJob.submitted_at.desc()).limit(20)
    )
    active = active_q.scalars().all()

    hist_q = await db.execute(
        select(HistoricalData).order_by(HistoricalData.completed_at.desc()).limit(50)
    )
    historical = hist_q.scalars().all()

    return {
        "active": [
            {
                "id": str(j.id),
                "slurm_job_id": j.slurm_job_id,
                "status": j.status,
                "price_usdc": float(j.price_usdc),
                "submitted_at": j.submitted_at.isoformat(),
                "script": j.payload.get("script") if j.payload else None,
            }
            for j in active
        ],
        "historical": [
            {
                "id": str(h.id),
                "slurm_job_id": h.slurm_job_id,
                "status": h.status,
                "price_usdc": float(h.price_usdc),
                "gas_paid_usd": float(h.gas_paid_usd) if h.gas_paid_usd else None,
                "proof_tx_hash": h.proof_tx_hash,
                "compute_duration_s": h.compute_duration_s,
                "completed_at": h.completed_at.isoformat(),
                "script": h.payload.get("script") if h.payload else None,
                "output_text": h.payload.get("output_text") if h.payload else None,
            }
            for h in historical
        ],
    }


# ---------------------------------------------------------------------------
# GET /api/attribution — builder code analytics
# ---------------------------------------------------------------------------

@router.get("/api/attribution")
async def get_attribution(db: AsyncSession = Depends(get_db)):
    total_q = await db.execute(select(func.count(AttributionLog.id)))
    total_txs = total_q.scalar_one()

    multi_q = await db.execute(
        select(func.count(AttributionLog.id)).where(AttributionLog.is_multi.is_(True))
    )
    multi_txs = multi_q.scalar_one()

    recent_q = await db.execute(
        select(AttributionLog).order_by(AttributionLog.created_at.desc()).limit(20)
    )
    recent = recent_q.scalars().all()

    total_gas_q = await db.execute(
        select(func.coalesce(func.sum(AttributionLog.gas_used), 0))
    )
    total_gas = int(total_gas_q.scalar_one())

    return {
        "total_attributed_txs": total_txs,
        "multi_code_txs": multi_txs,
        "total_gas_attributed": total_gas,
        "recent": [
            {
                "tx_hash": a.tx_hash,
                "codes": a.codes,
                "is_multi": a.is_multi,
                "gas_used": str(a.gas_used) if a.gas_used else None,
                "created_at": a.created_at.isoformat(),
            }
            for a in recent
        ],
    }


# ---------------------------------------------------------------------------
# GET /api/attribution/decode — decode ERC-8021 suffix from any tx
# ---------------------------------------------------------------------------

@router.get("/api/attribution/decode")
async def decode_attribution(tx_hash: str):
    try:
        tx = await _chain_client.w3.eth.get_transaction(tx_hash)
        input_data = bytes(tx.input)
        codes = erc8021.decode_builder_codes(input_data)
        return {
            "tx_hash": tx_hash,
            "has_attribution": codes is not None,
            "codes": codes,
        }
    except Exception as e:
        raise HTTPException(400, f"Failed to decode transaction: {e}")


# ---------------------------------------------------------------------------
# GET /api/jobs/user — jobs for a specific submitter address
# ---------------------------------------------------------------------------

@router.get("/api/jobs/user")
async def get_user_jobs(address: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin_key)):
    addr = address.lower()

    active_q = await db.execute(
        select(ActiveJob)
        .where(func.lower(ActiveJob.submitter_address) == addr)
        .order_by(ActiveJob.submitted_at.desc())
        .limit(50)
    )
    active = active_q.scalars().all()

    hist_q = await db.execute(
        select(HistoricalData)
        .where(func.lower(HistoricalData.submitter_address) == addr)
        .order_by(HistoricalData.completed_at.desc())
        .limit(100)
    )
    historical = hist_q.scalars().all()

    return {
        "active": [
            {
                "id": str(j.id),
                "slurm_job_id": j.slurm_job_id,
                "status": j.status,
                "price_usdc": float(j.price_usdc),
                "submitted_at": j.submitted_at.isoformat(),
                "script": j.payload.get("script") if j.payload else None,
            }
            for j in active
        ],
        "historical": [
            {
                "id": str(h.id),
                "slurm_job_id": h.slurm_job_id,
                "status": h.status,
                "price_usdc": float(h.price_usdc),
                "gas_paid_usd": float(h.gas_paid_usd) if h.gas_paid_usd else None,
                "proof_tx_hash": h.proof_tx_hash,
                "compute_duration_s": h.compute_duration_s,
                "completed_at": h.completed_at.isoformat(),
                "script": h.payload.get("script") if h.payload else None,
                "output_text": h.payload.get("output_text") if h.payload else None,
            }
            for h in historical
        ],
    }


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id} — single job detail (used by SDK polling)
# ---------------------------------------------------------------------------

def _parse_output_text(raw: str | None) -> dict:
    if not raw:
        return {"output": "", "error_output": "", "output_hash": ""}
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "output" in obj:
            return {
                "output": obj.get("output", ""),
                "error_output": obj.get("error_output", ""),
                "output_hash": obj.get("output_hash", ""),
            }
    except (ValueError, TypeError):
        pass
    return {"output": raw, "error_output": "", "output_hash": ""}


@router.get("/api/jobs/{job_id}")
async def get_job_by_id(job_id: str, db: AsyncSession = Depends(get_db)):
    active = await db.get(ActiveJob, job_id)
    if active:
        parsed = _parse_output_text(
            active.payload.get("output_text") if active.payload else None
        )
        return {
            "id": str(active.id),
            "slurm_job_id": active.slurm_job_id,
            "status": active.status,
            "price_usdc": float(active.price_usdc),
            "submitted_at": active.submitted_at.isoformat(),
            "completed_at": None,
            "script": active.payload.get("script") if active.payload else None,
            "output": parsed["output"],
            "error_output": parsed["error_output"],
            "output_hash": parsed["output_hash"],
            "proof_hash": None,
            "proof_tx_hash": None,
            "compute_duration_s": None,
            "gas_paid_usd": None,
        }

    hist_q = await db.execute(
        select(HistoricalData).where(HistoricalData.id == job_id).limit(1)
    )
    hist = hist_q.scalar_one_or_none()
    if hist:
        parsed = _parse_output_text(
            hist.payload.get("output_text") if hist.payload else None
        )
        return {
            "id": str(hist.id),
            "slurm_job_id": hist.slurm_job_id,
            "status": hist.status,
            "price_usdc": float(hist.price_usdc),
            "submitted_at": hist.submitted_at.isoformat(),
            "completed_at": hist.completed_at.isoformat(),
            "script": hist.payload.get("script") if hist.payload else None,
            "output": parsed["output"],
            "error_output": parsed["error_output"],
            "output_hash": parsed["output_hash"],
            "proof_hash": hist.output_hash.hex() if hist.output_hash else None,
            "proof_tx_hash": hist.proof_tx_hash,
            "compute_duration_s": hist.compute_duration_s,
            "gas_paid_usd": float(hist.gas_paid_usd) if hist.gas_paid_usd else None,
        }

    raise HTTPException(404, f"Job {job_id} not found")


# ---------------------------------------------------------------------------
# Payment sessions (for MCP pay flow; stored in DB so they survive restarts)
# ---------------------------------------------------------------------------

SESSION_TTL_SECONDS = 600  # 10 minutes


@router.post("/api/sessions")
async def create_session(request: Request, db: AsyncSession = Depends(get_db)):
    """Create a payment session. Called by MCP server."""
    raw_body = await request.json()

    try:
        body = CreateSessionRequest(**raw_body)
    except ValidationError as e:
        raise HTTPException(422, detail=e.errors())

    # Rate limit by client IP
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.check(f"session:{client_ip}"):
        return JSONResponse(
            status_code=429,
            content={"error": "Too many session requests"},
            headers={"Retry-After": "60"},
        )

    session = PaymentSession(
        status="pending",
        script=body.script,
        nodes=body.nodes,
        time_limit_min=body.time_limit_min,
        price=body.price,
        agent_url=settings.PUBLIC_API_URL or "",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {
        "id": str(session.id),
        "status": session.status,
        "script": session.script,
        "nodes": session.nodes,
        "time_limit_min": session.time_limit_min,
        "price": session.price,
        "agent_url": session.agent_url,
        "job_id": str(session.job_id) if session.job_id else None,
    }


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Get a payment session. Called by pay page."""
    from datetime import datetime, timezone

    session = await db.get(PaymentSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")
    if (datetime.now(timezone.utc) - session.created_at).total_seconds() > SESSION_TTL_SECONDS:
        raise HTTPException(404, "Session expired")
    return {
        "id": str(session.id),
        "status": session.status,
        "script": session.script,
        "nodes": session.nodes,
        "time_limit_min": session.time_limit_min,
        "price": session.price,
        "agent_url": session.agent_url or "",
        "job_id": str(session.job_id) if session.job_id else None,
    }


@router.post("/api/sessions/{session_id}/complete")
async def complete_session(session_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Mark session as paid with job_id. Called by pay page after successful submit."""
    from datetime import datetime, timezone

    raw_body = await request.json()

    try:
        body = CompleteSessionRequest(**raw_body)
    except ValidationError as e:
        raise HTTPException(422, detail=e.errors())

    # Validate job_id is a valid UUID
    try:
        parsed_job_id = uuid.UUID(body.job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format (expected UUID)")

    session = await db.get(PaymentSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    # TTL check (same as get_session)
    if (datetime.now(timezone.utc) - session.created_at).total_seconds() > SESSION_TTL_SECONDS:
        raise HTTPException(404, "Session expired")

    # Only pending sessions can be completed
    if session.status != "pending":
        raise HTTPException(409, f"Session already {session.status}")

    session.status = "paid"
    session.job_id = parsed_job_id
    await db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /api/capabilities — machine-readable service description for agents
# ---------------------------------------------------------------------------

@router.get("/api/capabilities")
async def get_capabilities():
    proof_count = 0
    if _chain_client:
        try:
            proof_count = await _chain_client.get_on_chain_proof_count()
        except Exception:
            pass

    return {
        "name": "Ouro",
        "description": "Autonomous HPC compute oracle on Base",
        "version": "1.0.0",
        "payment": {
            "protocol": "x402",
            "network": settings.CHAIN_CAIP2,
            "currency": "USDC",
            "endpoint": "/api/compute/submit",
        },
        "compute": {
            "engine": "slurm",
            "isolation": "apptainer",
            "max_nodes": 16,
            "max_time_min": 60,
            "max_script_bytes": MAX_SCRIPT_SIZE,
        },
        "trust": {
            "proof_contract": settings.PROOF_CONTRACT_ADDRESS,
            "on_chain_proofs": proof_count,
            "agent_address": settings.WALLET_ADDRESS,
        },
        "limits": {
            "max_active_jobs_per_wallet": MAX_ACTIVE_JOBS_PER_WALLET,
            "rate_limit_per_wallet": "10/min",
            "rate_limit_global": "100/min",
        },
    }


# ---------------------------------------------------------------------------
# GET /api/audit — structured audit log
# ---------------------------------------------------------------------------

@router.get("/api/audit")
async def get_audit(
    limit: int = 50,
    event_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_key),
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 200))
    if event_type:
        query = query.where(AuditLog.event_type == event_type)
    result = await db.execute(query)
    entries = result.scalars().all()
    return {
        "entries": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "job_id": str(e.job_id) if e.job_id else None,
                "wallet_address": e.wallet_address,
                "amount_usdc": float(e.amount_usdc) if e.amount_usdc else None,
                "detail": e.detail,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
    }
