from __future__ import annotations

import hmac
import json
import logging
import re
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
_ETH_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_BUILDER_CODE_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


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
    from x402.extensions.bazaar.resource_service import OutputConfig, declare_discovery_extension
    from x402.http.utils import (
        decode_payment_signature_header,
        encode_payment_required_header,
    )
    from x402.schemas import ResourceInfo

    payment_header = request.headers.get("payment-signature")
    raw_body = await request.json()
    client_code = request.headers.get("X-BUILDER-CODE")

    try:
        body = ComputeSubmitRequest(**raw_body)
    except ValidationError as e:
        raise HTTPException(422, detail=e.errors())

    if payment_header:
        logger.debug("x402 payment-signature header received (len=%d)", len(payment_header))

    script = body.script
    nodes = body.nodes
    time_limit_min = body.time_limit_min
    submitter_address = body.submitter_address

    if submitter_address and not _ETH_ADDRESS_RE.match(submitter_address):
        raise HTTPException(422, "Invalid submitter_address format (expected 0x + 40 hex chars)")
    if client_code and not _BUILDER_CODE_RE.match(client_code):
        raise HTTPException(422, "Invalid builder code format (alphanumeric, 1-32 chars)")

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
        resource_info = ResourceInfo(
            url="/api/compute/submit",
            description="Submit an HPC compute job to a Slurm cluster with Apptainer isolation",
            mimeType="application/json",
        )
        bazaar_ext = declare_discovery_extension(
            input={"script": "echo hello", "nodes": 1, "time_limit_min": 1},
            input_schema={
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "Script to execute"},
                    "nodes": {"type": "integer", "minimum": 1, "maximum": 16, "description": "Compute nodes"},
                    "time_limit_min": {"type": "integer", "minimum": 1, "maximum": 60, "description": "Max runtime (min)"},
                    "submitter_address": {"type": "string", "description": "0x wallet address"},
                },
                "required": ["script"],
            },
            body_type="json",
            output=OutputConfig(example={"job_id": "uuid", "status": "pending", "price": "$0.01"}),
        )
        bazaar_ext = _resource_server.enrich_extensions(bazaar_ext, request)
        payment_required = _resource_server.create_payment_required_response(
            requirements, resource_info, "Payment required", bazaar_ext,
        )
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
            reason = facilitator_reason.get("invalidReason", "verification_failed")
            return JSONResponse(
                status_code=403,
                content={
                    "error": reason,
                    "detail": "Payment verification failed",
                },
            )
        logger.error("x402 facilitator error: %s", e)
        return JSONResponse(
            status_code=503,
            content={"error": "Payment verification temporarily unavailable"},
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

    from datetime import datetime, timedelta, timezone
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    jobs_last_hour_q = await db.execute(
        select(func.count(ActiveJob.id)).where(
            ActiveJob.submitted_at >= one_hour_ago
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
        logger.error("Failed to decode transaction %s: %s", tx_hash, e)
        raise HTTPException(400, "Failed to decode transaction")


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

    # Verify the job actually exists (prevents fake completion)
    job = await db.get(ActiveJob, str(parsed_job_id))
    if not job:
        raise HTTPException(400, "Referenced job does not exist")

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
            "erc8004_agent_id": settings.ERC8004_AGENT_ID or None,
            "identity_registry": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
            "reputation_endpoint": "/api/reputation",
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


# ---------------------------------------------------------------------------
# GET /.well-known/agent-card.json — A2A Agent Card
# ---------------------------------------------------------------------------

@router.get("/.well-known/agent-card.json")
async def agent_card():
    base_url = settings.PUBLIC_API_URL or "https://api.ourocompute.com"
    dashboard_url = settings.PUBLIC_DASHBOARD_URL or "https://ourocompute.com"
    return {
        "name": "Ouro Compute",
        "description": (
            "Autonomous HPC compute agent on Base. Submit scripts, "
            "pay with USDC via x402, get on-chain proofs of execution."
        ),
        "url": base_url,
        "version": "1.0.0",
        "provider": {
            "organization": "Ouro",
            "url": dashboard_url,
        },
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "authentication": {"schemes": ["x402"]},
        "skills": [
            {
                "id": "run_compute_job",
                "name": "Run HPC Compute Job",
                "description": "Execute a script on a Slurm HPC cluster with Apptainer isolation. Pay per job with USDC.",
                "tags": ["compute", "hpc", "slurm", "execution"],
                "inputModes": ["application/json"],
                "outputModes": ["application/json"],
            },
            {
                "id": "get_price_quote",
                "name": "Get Price Quote",
                "description": "Get a price quote for a compute job without submitting it.",
                "tags": ["pricing", "quote"],
                "inputModes": ["application/json"],
                "outputModes": ["application/json"],
            },
            {
                "id": "get_job_status",
                "name": "Check Job Status",
                "description": "Get status, output, and proof hash of a submitted compute job.",
                "tags": ["status", "results", "proof"],
                "inputModes": ["application/json"],
                "outputModes": ["application/json"],
            },
        ],
    }


# ---------------------------------------------------------------------------
# GET /api/reputation — aggregated trust signals
# ---------------------------------------------------------------------------

@router.get("/api/reputation")
async def get_reputation(db: AsyncSession = Depends(get_db)):
    proof_count = 0
    if _chain_client:
        try:
            proof_count = await _chain_client.get_on_chain_proof_count()
        except Exception:
            pass

    completed_q = await db.execute(
        select(func.count(HistoricalData.id)).where(HistoricalData.status == "completed")
    )
    failed_q = await db.execute(
        select(func.count(HistoricalData.id)).where(HistoricalData.status == "failed")
    )
    total_completed = completed_q.scalar_one()
    total_failed = failed_q.scalar_one()

    # On-chain reputation from ERC-8004 Reputation Registry
    on_chain_feedback = None
    if _chain_client and settings.ERC8004_AGENT_ID:
        try:
            on_chain_feedback = await _chain_client.get_reputation_feedback(
                int(settings.ERC8004_AGENT_ID)
            )
        except Exception:
            pass

    result = {
        "agent_address": settings.WALLET_ADDRESS,
        "erc8004_agent_id": settings.ERC8004_AGENT_ID or None,
        "identity_registry": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
        "proof_contract": settings.PROOF_CONTRACT_ADDRESS,
        "on_chain_proofs": proof_count,
        "success_rate": round(total_completed / max(total_completed + total_failed, 1), 4),
        "total_jobs_completed": total_completed,
        "total_jobs_failed": total_failed,
        "verify": {
            "proof_contract": f"https://basescan.org/address/{settings.PROOF_CONTRACT_ADDRESS}#events",
            "identity_nft": "https://basescan.org/token/0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
        },
    }

    if on_chain_feedback:
        result["on_chain_feedback"] = on_chain_feedback

    return result


# ---------------------------------------------------------------------------
# GET /api/reputation/feedback-calldata — encoded calldata for giveFeedback
# ---------------------------------------------------------------------------

@router.get("/api/reputation/feedback-calldata")
async def get_feedback_calldata(job_id: str, score: int):
    """Returns encoded calldata for giveFeedback() so client agents
    can submit on-chain feedback about Ouro without building the tx themselves."""
    if not settings.ERC8004_AGENT_ID:
        raise HTTPException(503, "Agent ID not yet registered on ERC-8004")
    if not (1 <= score <= 5):
        raise HTTPException(422, "Score must be between 1 and 5")
    if not settings.ERC8004_REPUTATION_REGISTRY:
        raise HTTPException(503, "Reputation Registry not configured")

    if not _chain_client:
        raise HTTPException(503, "Chain client not available")

    calldata = _chain_client.encode_feedback_calldata(
        agent_id=int(settings.ERC8004_AGENT_ID),
        score=score,
        job_id=job_id,
    )

    return {
        "to": settings.ERC8004_REPUTATION_REGISTRY,
        "data": f"0x{calldata.hex()}",
        "chain_id": settings.CHAIN_ID,
        "description": f"Submit feedback (score={score}) for Ouro agent (agentId={settings.ERC8004_AGENT_ID})",
    }
