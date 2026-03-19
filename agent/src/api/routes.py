from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import logging
import re
import time
import uuid
from collections import OrderedDict
from typing import Optional

import httpx

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.event_bus import EventBus
import src.api.pricing as pricing_state
from src.api.pricing import calculate_price
from src.chain.client import BaseChainClient
from src.chain import erc8021
from x402.schemas.errors import SchemeNotFoundError

from src.config import settings
from src.db.models import (
    ActiveJob,
    AgentCost,
    AttributionLog,
    AuditLog,
    Credit,
    HistoricalData,
    StorageQuota,
    WalletSnapshot,
)
from src.db.operations import get_available_credit, log_audit, redeem_credits
from src.db.session import async_session_maker, get_db

logger = logging.getLogger(__name__)
router = APIRouter()

X402_FACILITATOR_MIN_USD = 0.001


def _get_client_ip(request: Request) -> str:
    """Extract real client IP from X-Forwarded-For header (first entry), fall back to request.client.host."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        try:
            ipaddress.ip_address(first)
            return first
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class WorkspaceFile(BaseModel):
    path: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., max_length=65_536)


def _extract_dockerfile(files: list[WorkspaceFile] | None) -> str | None:
    """Return Dockerfile content if present in files, else None."""
    if not files:
        return None
    for f in files:
        if f.path.lower() == "dockerfile":
            return f.content
    return None


class ComputeSubmitRequest(BaseModel):
    # Mode 1: Script (existing — now optional)
    script: Optional[str] = Field(None, min_length=1, max_length=65_536)
    # Mode 2: Multi-file
    files: Optional[list[WorkspaceFile]] = None
    # Shared for modes 2/4
    entrypoint: Optional[str] = Field(None, max_length=255)
    # Container image (all modes)
    image: Optional[str] = None
    # Existing shared fields
    cpus: int = Field(default=1, ge=1, le=8)
    time_limit_min: int = Field(default=1, ge=1, le=60)
    submitter_address: Optional[str] = None
    webhook_url: Optional[str] = Field(None, max_length=2048)
    mount_storage: bool = Field(default=False, description="Mount persistent /scratch volume (read-write)")

    @property
    def submission_mode(self) -> str:
        if self.files:
            return "multi_file"
        if self.script:
            return "script"
        return "unknown"

    @model_validator(mode="after")
    def validate_mode(self):
        has_script = bool(self.script)
        has_files = bool(self.files)

        if not has_script and not has_files:
            raise ValueError("Provide one of: script, files")

        # Combined mode: script + files → script becomes the entrypoint
        if has_script and has_files:
            if self.entrypoint:
                raise ValueError(
                    "Do not set entrypoint when using script + files "
                    "(the script is the entrypoint)"
                )
            import secrets
            existing_paths = {f.path for f in self.files}
            for _ in range(10):
                name = f"_entrypoint_{secrets.token_hex(4)}.sh"
                if name not in existing_paths:
                    break
            else:
                raise ValueError(
                    "Could not generate unique entrypoint filename — "
                    "rename any file starting with '_entrypoint_'"
                )
            self.entrypoint = name

        has_dockerfile = _extract_dockerfile(self.files) is not None

        # entrypoint required for multi-file ONLY if no Dockerfile and no script
        if self.files and not self.entrypoint and not has_dockerfile:
            raise ValueError("entrypoint required for multi-file mode (or include a Dockerfile)")

        if self.files:
            # +1 for generated entrypoint when script+files combined
            effective_count = len(self.files) + (1 if has_script else 0)
            if effective_count > 100:
                raise ValueError("Max 100 files per workspace")
            total = sum(len(f.content.encode()) for f in self.files)
            if has_script:
                total += len(self.script.encode())
            if total > 10 * 1024 * 1024:
                raise ValueError("Total workspace size exceeds 10MB")
        return self

    def to_workspace_files(self) -> tuple[list[dict[str, str]], str]:
        """Normalize any submission mode into (files, entrypoint) for workspace creation."""
        if self.files and self.script:
            # Combined mode: user files + generated entrypoint script
            files = [{"path": f.path, "content": f.content} for f in self.files]
            files.append({"path": self.entrypoint, "content": self.script})
            return files, self.entrypoint
        if self.files:
            return [{"path": f.path, "content": f.content} for f in self.files], self.entrypoint or ""
        # Script mode → single-file workspace
        return [{"path": "job.sh", "content": self.script}], "job.sh"


_event_bus: EventBus | None = None
_chain_client: BaseChainClient | None = None
_resource_server = None
_slurm_client = None

MAX_SCRIPT_SIZE = 65_536
MAX_ACTIVE_JOBS_PER_WALLET = 20
_ETH_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_WORKSPACE_PATH_RE = re.compile(r"^[a-zA-Z0-9._/ -]+$")


def _validate_workspace_file_path(path: str) -> None:
    """Reject dangerous file paths."""
    import os
    if "\x00" in path:
        raise HTTPException(422, "Null bytes in file path")
    normalized = os.path.normpath(path)
    if normalized.startswith("..") or normalized.startswith("/"):
        raise HTTPException(422, f"Invalid file path: {path}")
    if normalized.count(os.sep) > 5:
        raise HTTPException(422, f"File path too deep: {path}")
    if not _WORKSPACE_PATH_RE.match(normalized):
        raise HTTPException(422, f"Invalid characters in file path: {path}")


def _validate_image(image: str | None) -> None:
    """Validate image name against allowlist."""
    if image and image not in settings.allowed_images_set:
        raise HTTPException(422, f"Unknown image: {image}. Allowed: {', '.join(sorted(settings.allowed_images_set))}")


def _validate_webhook_url(url: str) -> None:
    """Validate webhook URL: require HTTPS (HTTP allowed for localhost)."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(422, f"webhook_url must use http or https scheme, got: {parsed.scheme}")
    if not parsed.netloc:
        raise HTTPException(422, "webhook_url must include a host")
    hostname = parsed.hostname or ""
    if parsed.scheme == "http" and hostname not in ("localhost", "127.0.0.1", "::1"):
        raise HTTPException(422, "webhook_url must use HTTPS (HTTP allowed only for localhost)")


def _job_summary(payload: dict | None) -> dict:
    """Job summary for API responses. Handles both legacy (script key) and new (entrypoint) payloads."""
    if not payload:
        return {}
    base: dict = {}
    # Legacy payloads have a "script" key directly
    if "script" in payload:
        base["script"] = payload["script"]
    if "entrypoint" in payload:
        base["entrypoint"] = payload["entrypoint"]
    if "file_count" in payload:
        base["file_count"] = payload["file_count"]
    if "files" in payload:
        base["files"] = payload["files"]
    img = payload.get("image")
    if img and img != "ouro-ubuntu":
        base["image"] = img
    if "failure_reason" in payload:
        base["failure_reason"] = payload["failure_reason"]
    if "failure_stage" in payload:
        base["failure_stage"] = payload["failure_stage"]
    if "credit_applied" in payload:
        base["credit_applied"] = payload["credit_applied"]
    if "event_log" in payload:
        base["event_log"] = payload["event_log"]
    if payload.get("mount_storage"):
        base["mount_storage"] = True
    return base


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

# Storage rate limiter: 30 per-wallet per 60s, 200 global per 60s
# NOTE: MAX_STORAGE_FILES must match the same constant in deploy/slurm/slurm_proxy.py
_storage_rate_limiter = _RateLimiter(per_key_limit=30, global_limit=200, window_s=60.0)
MAX_STORAGE_FILES = 10_000


async def require_admin_key(request: Request):
    if not settings.ADMIN_API_KEY:
        return
    key = request.headers.get("x-admin-key", "")
    if not hmac.compare_digest(key, settings.ADMIN_API_KEY):
        raise HTTPException(403, "Invalid admin key")


def init_routes(event_bus: EventBus, chain_client: BaseChainClient, resource_server, slurm_client=None) -> None:
    global _event_bus, _chain_client, _resource_server, _slurm_client
    _event_bus = event_bus
    _chain_client = chain_client
    _resource_server = resource_server
    _slurm_client = slurm_client


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
            checks["wallet_usdc"] = "ok" if usdc_bal > 0 else "low"
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

    try:
        body = ComputeSubmitRequest(**raw_body)
    except ValidationError as e:
        raise HTTPException(422, detail=e.errors())

    if payment_header:
        logger.debug("x402 payment-signature header received (len=%d)", len(payment_header))

    cpus = body.cpus
    time_limit_min = body.time_limit_min
    submitter_address = body.submitter_address
    mode = body.submission_mode

    if submitter_address and not _ETH_ADDRESS_RE.match(submitter_address):
        raise HTTPException(422, "Invalid submitter_address format (expected 0x + 40 hex chars)")
    if payment_header and not submitter_address:
        raise HTTPException(422, "submitter_address is required for job submission")

    dockerfile_content = _extract_dockerfile(body.files)

    # Skip image validation when Dockerfile is present (FROM line replaces image field)
    if not dockerfile_content:
        _validate_image(body.image)

    # Validate Dockerfile syntax early if present
    if dockerfile_content:
        from src.agent.dockerfile import parse_dockerfile
        try:
            parsed = parse_dockerfile(dockerfile_content, require_entrypoint=not body.entrypoint)
        except ValueError as e:
            raise HTTPException(422, f"Invalid Dockerfile: {e}")

        # Validate COPY/ADD sources reference files that exist in the submission
        if parsed.copy_instructions and body.files:
            submitted = {f.path for f in body.files if f.path.lower() != "dockerfile"}
            missing = []
            for src, _ in parsed.copy_instructions:
                if src not in submitted:
                    # Check if src is a directory prefix (e.g., COPY src/ .)
                    prefix = src.rstrip("/") + "/"
                    is_dir = any(p.startswith(prefix) for p in submitted)
                    if not is_dir:
                        missing.append(src)
            if missing:
                raise HTTPException(
                    422,
                    f"Dockerfile COPY/ADD references files not in submission: {missing}. "
                    f"Submitted files: {sorted(submitted)}",
                )

    # Validate external Docker image exists on Docker Hub (before payment)
    if dockerfile_content:
        from src.agent.dockerfile import validate_docker_image, PREBUILT_ALIASES
        if parsed.from_image not in PREBUILT_ALIASES:
            try:
                await validate_docker_image(parsed.from_image)
            except ValueError as e:
                raise HTTPException(422, f"Invalid Dockerfile: {e}")

    # Validate file paths for multi-file mode
    if body.files:
        for f in body.files:
            _validate_workspace_file_path(f.path)
        if body.entrypoint:
            _validate_workspace_file_path(body.entrypoint)

    rate_key = submitter_address.lower() if submitter_address else f"ip:{_get_client_ip(request)}"
    if not _rate_limiter.check(rate_key):
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests"},
            headers={"Retry-After": "60"},
        )

    if submitter_address:
        # Advisory lock per wallet to serialize count-check + insert
        lock_key = int.from_bytes(submitter_address.lower().encode()[:8], "big") & 0x7FFFFFFFFFFFFFFF
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

        active_count_q = await db.execute(
            select(func.count(ActiveJob.id))
            .where(func.lower(ActiveJob.submitter_address) == submitter_address.lower())
        )
        if active_count_q.scalar_one() >= MAX_ACTIVE_JOBS_PER_WALLET:
            raise HTTPException(429, f"Too many active jobs (max {MAX_ACTIVE_JOBS_PER_WALLET})")

    cache_key = (mode, cpus, time_limit_min, pricing_state.current_phase, pricing_state.demand_multiplier)
    quote = _price_cache.get(cache_key)
    if not quote:
        quote = await calculate_price(db, cpus, time_limit_min, mode)
        _price_cache.set(cache_key, quote)

    # Read-only credit check — actual redemption is deferred until after
    # x402 payment verification (or done immediately if fully covered) to
    # prevent credit loss on the 402 round-trip.
    credit_applied = 0.0
    paid_with_credit = False
    if submitter_address:
        credit_balance = await get_available_credit(db, submitter_address)
        if credit_balance > 0:
            credit_applied = min(credit_balance, quote.price_usd)
            if credit_applied >= quote.price_usd:
                paid_with_credit = True
            elif (quote.price_usd - credit_applied) < X402_FACILITATOR_MIN_USD:
                paid_with_credit = True  # waive sub-minimum remainder

    # Fully covered by credit — redeem now, skip x402
    if paid_with_credit:
        redeemed = credit_applied
        await redeem_credits(db, submitter_address, redeemed)
        waived = quote.price_usd - redeemed
        if waived > 0:
            _event_bus.emit(
                "credit",
                f"Sub-minimum remainder ${waived:.4f} waived for {submitter_address[:10]}...",
            )
            credit_applied = quote.price_usd  # for job record: show fully covered
        _event_bus.emit(
            "credit",
            f"Credits redeemed: ${redeemed:.4f} from {submitter_address[:10]}... "
            f"(remaining: ${credit_balance - redeemed:.4f})",
        )

    if not paid_with_credit:
        remaining_price = max(0, quote.price_usd - credit_applied)
        remaining_price_str = f"${remaining_price:.4f}"
        config = ResourceConfig(
            scheme="exact",
            network=settings.CHAIN_CAIP2,
            pay_to=settings.WALLET_ADDRESS,
            price=remaining_price_str,
        )
        try:
            requirements = _resource_server.build_payment_requirements(config)
        except SchemeNotFoundError:
            logger.error(
                "x402 scheme 'exact' not available for %s — are CDP API keys configured?",
                settings.CHAIN_CAIP2,
            )
            raise HTTPException(
                503,
                f"Payment scheme not available for network {settings.CHAIN_CAIP2}. "
                "Ensure CDP_API_KEY_ID and CDP_API_KEY_SECRET are set.",
            )

        # Pre-flight: ensure Slurm is reachable before settling payment
        if _slurm_client:
            cluster = await _slurm_client.get_cluster_info()
            if cluster["status"] == "unreachable":
                raise HTTPException(
                    503,
                    "Compute cluster is temporarily unreachable. Please retry shortly.",
                )

        if not payment_header:
            resource_info = ResourceInfo(
                url="/api/compute/submit",
                description="Submit a compute job with Docker container isolation",
                mimeType="application/json",
            )
            bazaar_ext = declare_discovery_extension(
                input={"script": "echo hello", "cpus": 1, "time_limit_min": 1},
                input_schema={
                    "type": "object",
                    "properties": {
                        "script": {"type": "string", "description": "Script to execute"},
                        "cpus": {"type": "integer", "minimum": 1, "maximum": 8, "description": "CPU cores"},
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
                    "price": remaining_price_str,
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

        # Payment verified — now redeem partial credits (deferred until here)
        if credit_applied > 0:
            await redeem_credits(db, submitter_address, credit_applied)
            _event_bus.emit(
                "credit",
                f"Partial credits redeemed: ${credit_applied:.4f} from {submitter_address[:10]}... "
                f"(x402 charged: {remaining_price_str})",
            )

        _event_bus.emit(
            "x402",
            f"Payment verified: {remaining_price_str} from client "
            f"(cost floor: ${quote.cost_floor_usd:.4f}, guaranteed profit: {quote.profit_pct:.1f}%)",
        )

    job_id = str(uuid.uuid4())

    # Unified workspace creation — every submission becomes a workspace
    if not _slurm_client:
        raise HTTPException(503, "Slurm client not available for workspace creation")

    files_data, entrypoint = body.to_workspace_files()
    try:
        workspace_path = await _slurm_client.create_workspace(job_id, files_data)
    except (httpx.ConnectTimeout, httpx.ConnectError, httpx.TimeoutException) as e:
        logger.error("Slurm workspace creation failed after payment: %s", e)
        raise HTTPException(
            503,
            "Payment verified but compute cluster is unreachable. "
            "Your job will be retried. Contact support if funds are not returned.",
        )

    # Persistent storage mount
    storage_path = None
    if body.mount_storage and not submitter_address:
        raise HTTPException(422, "mount_storage requires submitter_address (wallet address)")
    if body.mount_storage and submitter_address:
        wallet_lower = submitter_address.lower()
        # Get or create storage quota
        quota = await db.get(StorageQuota, wallet_lower)
        if not quota:
            quota = StorageQuota(
                wallet_address=wallet_lower,
                quota_bytes=settings.STORAGE_FREE_TIER_BYTES,
            )
            db.add(quota)
            await db.flush()

        # Live quota check — fetch real-time usage from proxy (~50ms)
        try:
            live_usage = await _slurm_client.get_storage_usage(wallet_lower)
            current_bytes = live_usage["used_bytes"]
            quota.used_bytes = current_bytes  # update cached value
            quota.file_count = live_usage["file_count"]
        except Exception:
            # Proxy unavailable — fall back to cached value
            current_bytes = int(quota.used_bytes)

        if current_bytes >= quota.quota_bytes:
            raise HTTPException(
                422,
                f"Storage quota exceeded ({current_bytes / 1_073_741_824:.2f}GB / "
                f"{int(quota.quota_bytes) / 1_073_741_824:.2f}GB). "
                f"Delete files at /scratch to free space.",
            )

        # Init storage directory on NFS (idempotent)
        try:
            storage_path = await _slurm_client.init_storage(wallet_lower)
        except Exception as e:
            logger.error("Storage init failed for %s: %s", wallet_lower, e)
            raise HTTPException(503, "Failed to initialize persistent storage")

        # Update last_accessed_at
        from datetime import datetime, timezone
        quota.last_accessed_at = datetime.now(timezone.utc)

        _event_bus.emit(
            "storage",
            f"Storage mounted for {submitter_address[:10]}... "
            f"(usage: {current_bytes / 1_073_741_824:.2f}GB / {int(quota.quota_bytes) / 1_073_741_824:.2f}GB)",
        )

    job_payload: dict = {
        "cpus": cpus,
        "time_limit_min": time_limit_min,
        "image": body.image or "ouro-ubuntu",
        "entrypoint": entrypoint,
        "file_count": len(files_data),
        "workspace_path": workspace_path,
        "files": files_data,
    }
    job_payload["cost_floor"] = quote.cost_floor_usd
    job_payload["compute_cost"] = quote.breakdown["compute_cost"]
    if dockerfile_content:
        job_payload["dockerfile_content"] = dockerfile_content
    if credit_applied > 0:
        job_payload["credit_applied"] = credit_applied
    if body.webhook_url:
        _validate_webhook_url(body.webhook_url)
        job_payload["webhook_url"] = body.webhook_url
    if storage_path:
        job_payload["storage_path"] = storage_path
        job_payload["mount_storage"] = True

    job = ActiveJob(
        id=job_id,
        payload=job_payload,
        price_usdc=quote.price_usd,
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
        detail={"price_str": quote.price_str, "paid_with_credit": paid_with_credit, "credit_applied": credit_applied},
    )

    if storage_path:
        await log_audit(
            db,
            event_type="storage_mounted",
            job_id=uuid.UUID(job_id),
            wallet_address=submitter_address,
            detail={"storage_path": storage_path},
        )

    _event_bus.emit("job", f"Job {job_id[:8]} created, queued for processing")

    return {
        "job_id": job_id,
        "status": "pending",
        "price": quote.price_str,
        "paid_with_credit": paid_with_credit,
        "credit_applied": credit_applied,
        "webhook_configured": bool(body.webhook_url),
        "mount_storage": bool(storage_path),
        "profitability": {
            "guaranteed": quote.guaranteed_profitable,
            "estimated_profit_pct": round(quote.profit_pct, 1),
        },
    }


# ---------------------------------------------------------------------------
# GET /api/storage — storage info + file listing for a wallet
# ---------------------------------------------------------------------------

@router.get("/api/storage")
async def get_storage(
    wallet: str,
    request: Request,
    signature: str | None = None,
    timestamp: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get storage quota, usage, and file listing for a wallet."""
    if not _ETH_ADDRESS_RE.match(wallet):
        raise HTTPException(422, "Invalid wallet address format")
    wallet_lower = wallet.lower()

    _check_admin_or_wallet_sig(
        request, wallet, signature, timestamp,
        lambda w: f"ouro-storage-list:{w}:{timestamp}",
    )

    # Rate limit (skip for admin key — internal/operational)
    if not (settings.ADMIN_API_KEY and hmac.compare_digest(
        request.headers.get("x-admin-key", ""), settings.ADMIN_API_KEY
    )):
        if not _storage_rate_limiter.check(f"storage:{wallet_lower}"):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many storage requests — try again shortly"},
                headers={"Retry-After": "60"},
            )

    if not _slurm_client:
        raise HTTPException(503, "Storage service unavailable")

    # Read-only lookup — do NOT create quota on GET (prevents DoS via arbitrary addresses)
    quota = await db.get(StorageQuota, wallet_lower)

    # Fetch live usage + file list from proxy (may return empty if no storage dir exists)
    try:
        usage = await _slurm_client.get_storage_usage(wallet_lower)
        files = await _slurm_client.list_storage_files(wallet_lower)
    except Exception as e:
        logger.warning("Storage proxy call failed for %s: %s", wallet_lower, e)
        if not quota:
            return {
                "wallet": wallet_lower,
                "tier": "free",
                "quota_bytes": settings.STORAGE_FREE_TIER_BYTES,
                "used_bytes": 0,
                "file_count": 0,
                "max_files": MAX_STORAGE_FILES,
                "files": [],
                "last_accessed_at": None,
                "created_at": None,
            }
        usage = {"used_bytes": int(quota.used_bytes), "file_count": int(quota.file_count)}
        files = []

    # Update cached values only if quota record exists (created during first job submission)
    if quota:
        quota.used_bytes = usage["used_bytes"]
        quota.file_count = usage["file_count"]
        from datetime import datetime, timezone
        quota.last_synced_at = datetime.now(timezone.utc)
        await db.commit()

    return {
        "wallet": wallet_lower,
        "tier": quota.tier if quota else "free",
        "quota_bytes": int(quota.quota_bytes) if quota else settings.STORAGE_FREE_TIER_BYTES,
        "used_bytes": usage["used_bytes"],
        "file_count": usage["file_count"],
        "max_files": MAX_STORAGE_FILES,
        "files": files,
        "last_accessed_at": quota.last_accessed_at.isoformat() if quota and quota.last_accessed_at else None,
        "created_at": quota.created_at.isoformat() if quota and quota.created_at else None,
    }


def _verify_wallet_signature(
    wallet: str, message: str, signature: str, timestamp: str
) -> None:
    """Verify EIP-191 signature with 5-minute timestamp window.
    Callers construct the action-specific message.
    Raises HTTPException(401) on failure."""
    from eth_account.messages import encode_defunct
    from eth_account import Account
    from datetime import datetime, timezone

    try:
        ts = int(timestamp)
    except ValueError:
        raise HTTPException(401, "Invalid timestamp")
    now = int(datetime.now(timezone.utc).timestamp())
    if abs(now - ts) > 300:
        raise HTTPException(401, "Signature expired (must be within 5 minutes)")

    try:
        msg = encode_defunct(text=message)
        recovered = Account.recover_message(msg, signature=signature)
    except Exception:
        raise HTTPException(401, "Invalid signature")

    if recovered.lower() != wallet.lower():
        raise HTTPException(401, "Signature does not match wallet address")


def _check_admin_or_wallet_sig(
    request: Request,
    wallet: str | None,
    signature: str | None,
    timestamp: str | None,
    message_fn,
) -> str | None:
    """Check admin key or wallet signature. Returns verified wallet (lowercase) or None if admin.
    Raises HTTPException if neither auth method succeeds."""
    admin_key = request.headers.get("x-admin-key", "")
    if settings.ADMIN_API_KEY and hmac.compare_digest(admin_key, settings.ADMIN_API_KEY):
        return None

    if not wallet or not signature or not timestamp:
        raise HTTPException(401, "Authentication required (wallet signature or admin key)")
    if not _ETH_ADDRESS_RE.match(wallet):
        raise HTTPException(422, "Invalid wallet address format")
    wallet_lower = wallet.lower()
    message = message_fn(wallet_lower)
    _verify_wallet_signature(wallet_lower, message, signature, timestamp)
    return wallet_lower


# ---------------------------------------------------------------------------
# DELETE /api/storage/files — delete a file from persistent storage
# ---------------------------------------------------------------------------

@router.delete("/api/storage/files")
async def delete_storage_file_route(
    wallet: str,
    path: str,
    request: Request,
    signature: str | None = None,
    timestamp: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Delete a file from a wallet's persistent storage. Requires EIP-191 signature or admin key."""
    if not _ETH_ADDRESS_RE.match(wallet):
        raise HTTPException(422, "Invalid wallet address format")
    wallet_lower = wallet.lower()

    _check_admin_or_wallet_sig(
        request, wallet, signature, timestamp,
        lambda w: f"ouro-storage-delete:{w}:{path}:{timestamp}",
    )

    # Rate limit (skip for admin key — internal/operational)
    if not (settings.ADMIN_API_KEY and hmac.compare_digest(
        request.headers.get("x-admin-key", ""), settings.ADMIN_API_KEY
    )):
        if not _storage_rate_limiter.check(f"storage:{wallet_lower}"):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many storage requests — try again shortly"},
                headers={"Retry-After": "60"},
            )

    if not _slurm_client:
        raise HTTPException(503, "Storage service unavailable")

    # Verify wallet has storage
    quota = await db.get(StorageQuota, wallet_lower)
    if not quota:
        raise HTTPException(404, "No storage found for this wallet")

    try:
        deleted = await _slurm_client.delete_storage_file(wallet_lower, path)
    except Exception as e:
        logger.error("Storage delete failed for %s/%s: %s", wallet_lower, path, e)
        raise HTTPException(500, "Failed to delete file")

    await log_audit(
        db,
        event_type="storage_file_deleted",
        wallet_address=wallet_lower,
        detail={"path": path},
    )

    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# GET /api/stream — SSE live event feed
# ---------------------------------------------------------------------------

@router.get("/api/stream")
async def event_stream(request: Request, _=Depends(require_admin_key)):
    try:
        _event_bus.check_connection_limit()
    except ConnectionError as e:
        raise HTTPException(429, str(e))

    async def generate():
        async for event in _event_bus.subscribe():
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/events — SSE live event feed for a specific job
# ---------------------------------------------------------------------------

@router.get("/api/jobs/{job_id}/events")
async def job_event_stream(
    job_id: str,
    request: Request,
    wallet: str | None = None,
    signature: str | None = None,
    timestamp: str | None = None,
):
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job ID format")

    verified_wallet = _check_admin_or_wallet_sig(
        request, wallet, signature, timestamp,
        lambda w: f"ouro-job-events:{job_id}:{w}:{timestamp}",
    )
    # When admin key is used, allow dashboard proxy to enforce ownership via wallet query param
    if verified_wallet is None and wallet:
        verified_wallet = wallet.lower()

    async with async_session_maker() as db:
        active = await db.get(ActiveJob, job_id)
        if active:
            if verified_wallet is not None:
                submitter = (active.submitter_address or "").lower()
                if submitter != verified_wallet:
                    raise HTTPException(403, "Access denied — wallet does not match job submitter")
        else:
            hist_q = await db.execute(
                select(HistoricalData).where(HistoricalData.id == job_id).limit(1)
            )
            hist = hist_q.scalar_one_or_none()
            if not hist:
                raise HTTPException(404, f"Job {job_id} not found")
            if verified_wallet is not None:
                submitter = (hist.submitter_address or "").lower()
                if submitter != verified_wallet:
                    raise HTTPException(403, "Access denied — wallet does not match job submitter")

    try:
        _event_bus.check_job_connection_limit()
    except ConnectionError as e:
        raise HTTPException(429, str(e))

    async def generate():
        async for event in _event_bus.subscribe_job(job_id):
            yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /api/stats — aggregate P&L, job counts, revenue breakdown
# ---------------------------------------------------------------------------

@router.get("/api/stats")
async def get_stats():
    from datetime import datetime, timedelta, timezone

    async def _query_revenue():
        async with async_session_maker() as db:
            q = await db.execute(
                select(
                    func.coalesce(func.sum(HistoricalData.price_usdc), 0).label("total_revenue"),
                    func.count(HistoricalData.id).label("completed_jobs"),
                    func.coalesce(func.avg(HistoricalData.compute_duration_s), 0).label("avg_duration"),
                )
            )
            return q.one()

    async def _query_gas_costs():
        async with async_session_maker() as db:
            q = await db.execute(
                select(func.coalesce(func.sum(AgentCost.amount_usd), 0)).where(
                    AgentCost.cost_type == "gas"
                )
            )
            return float(q.scalar_one())

    async def _query_llm_costs():
        async with async_session_maker() as db:
            q = await db.execute(
                select(func.coalesce(func.sum(AgentCost.amount_usd), 0)).where(
                    AgentCost.cost_type == "llm_inference"
                )
            )
            return float(q.scalar_one())

    async def _query_compute_costs():
        async with async_session_maker() as db:
            q = await db.execute(
                select(func.coalesce(func.sum(AgentCost.amount_usd), 0)).where(
                    AgentCost.cost_type == "compute"
                )
            )
            return float(q.scalar_one())

    async def _query_active_count():
        async with async_session_maker() as db:
            q = await db.execute(select(func.count(ActiveJob.id)))
            return q.scalar_one()

    async def _query_jobs_last_hour():
        async with async_session_maker() as db:
            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            q = await db.execute(
                select(func.count(ActiveJob.id)).where(
                    ActiveJob.submitted_at >= one_hour_ago
                )
            )
            return int(q.scalar_one())

    async def _query_recent_jobs():
        async with async_session_maker() as db:
            historical = await db.execute(
                select(
                    HistoricalData.status,
                    HistoricalData.price_usdc,
                    HistoricalData.compute_duration_s,
                    HistoricalData.completed_at,
                )
                .order_by(HistoricalData.completed_at.desc())
                .limit(8)
            )
            active = await db.execute(
                select(
                    ActiveJob.status,
                    ActiveJob.price_usdc,
                    ActiveJob.submitted_at,
                )
                .order_by(ActiveJob.submitted_at.desc())
                .limit(3)
            )
            return historical.all(), active.all()

    rev_row, gas_costs, llm_costs, compute_costs, active_jobs, jobs_last_hour, recent = (
        await asyncio.gather(
            _query_revenue(),
            _query_gas_costs(),
            _query_llm_costs(),
            _query_compute_costs(),
            _query_active_count(),
            _query_jobs_last_hour(),
            _query_recent_jobs(),
        )
    )
    historical_rows, active_rows = recent

    total_revenue = float(rev_row.total_revenue)
    total_costs = gas_costs + llm_costs + compute_costs
    net_pnl = total_revenue - total_costs
    completed = rev_row.completed_jobs

    avg_cost_per_job = total_costs / completed if completed > 0 else 0
    avg_price_per_job = total_revenue / completed if completed > 0 else 0
    avg_margin_per_job = avg_price_per_job - avg_cost_per_job

    return {
        "total_revenue_usdc": total_revenue,
        "gas_costs_usd": gas_costs,
        "llm_costs_usd": llm_costs,
        "compute_costs_usd": compute_costs,
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
        "revenue_model": "guaranteed_margin_compute",
        "avg_cost_per_job": avg_cost_per_job,
        "avg_price_per_job": avg_price_per_job,
        "avg_margin_per_job": avg_margin_per_job,
        "recent_jobs": sorted(
            [
                {
                    "status": r.status,
                    "price_usdc": float(r.price_usdc or 0),
                    "duration_s": float(r.compute_duration_s or 0) if hasattr(r, "compute_duration_s") else None,
                    "timestamp": (r.completed_at if hasattr(r, "completed_at") else r.submitted_at).isoformat(),
                }
                for r in list(active_rows) + list(historical_rows)
            ],
            key=lambda j: j["timestamp"],
            reverse=True,
        ),
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
                "retry_count": j.retry_count,
                **_job_summary(j.payload),
            }
            for j in active
        ],
        "historical": [
            {
                "id": str(h.id),
                "slurm_job_id": h.slurm_job_id,
                "status": h.status,
                "price_usdc": float(h.price_usdc),
                "compute_duration_s": h.compute_duration_s,
                "completed_at": h.completed_at.isoformat(),
                "output_text": h.payload.get("output_text") if h.payload else None,
                **_job_summary(h.payload),
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
                "retry_count": j.retry_count,
                **_job_summary(j.payload),
            }
            for j in active
        ],
        "historical": [
            {
                "id": str(h.id),
                "slurm_job_id": h.slurm_job_id,
                "status": h.status,
                "price_usdc": float(h.price_usdc),
                "compute_duration_s": h.compute_duration_s,
                "completed_at": h.completed_at.isoformat(),
                "output_text": h.payload.get("output_text") if h.payload else None,
                **_job_summary(h.payload),
            }
            for h in historical
        ],
    }


# ---------------------------------------------------------------------------
# GET /api/credits/user — credit balance + history for a wallet
# ---------------------------------------------------------------------------

@router.get("/api/credits/user")
async def get_user_credits(address: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin_key)):
    wallet = address.lower()
    available = await get_available_credit(db, wallet)
    result = await db.execute(
        select(Credit).where(Credit.wallet_address == wallet)
        .order_by(Credit.created_at.desc()).limit(20)
    )
    history = [
        {
            "amount_usdc": float(c.amount_usdc),
            "reason": c.reason,
            "redeemed": c.redeemed,
            "created_at": c.created_at.isoformat(),
        }
        for c in result.scalars()
    ]
    return {"available": available, "history": history}


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id} — single job detail (used by SDK polling)
# ---------------------------------------------------------------------------

def _parse_output_text(raw: str | None) -> dict:
    if not raw:
        return {"output": "", "error_output": ""}
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "output" in obj:
            return {
                "output": obj.get("output", ""),
                "error_output": obj.get("error_output", ""),
            }
    except (ValueError, TypeError):
        pass
    return {"output": raw, "error_output": ""}


@router.get("/api/jobs/{job_id}")
async def get_job_by_id(
    job_id: str,
    request: Request,
    wallet: str | None = None,
    signature: str | None = None,
    timestamp: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    verified_wallet = _check_admin_or_wallet_sig(
        request, wallet, signature, timestamp,
        lambda w: f"ouro-job-view:{job_id}:{w}:{timestamp}",
    )
    # When admin key is used, allow dashboard proxy to enforce ownership via wallet query param
    if verified_wallet is None and wallet:
        verified_wallet = wallet.lower()

    active = await db.get(ActiveJob, job_id)
    if active:
        if verified_wallet is not None:
            submitter = (active.submitter_address or "").lower()
            if submitter != verified_wallet:
                raise HTTPException(403, "Access denied — wallet does not match job submitter")
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
            **_job_summary(active.payload),
            "output": parsed["output"],
            "error_output": parsed["error_output"],
            "compute_duration_s": None,
        }

    hist_q = await db.execute(
        select(HistoricalData).where(HistoricalData.id == job_id).limit(1)
    )
    hist = hist_q.scalar_one_or_none()
    if hist:
        if verified_wallet is not None:
            submitter = (hist.submitter_address or "").lower()
            if submitter != verified_wallet:
                raise HTTPException(403, "Access denied — wallet does not match job submitter")
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
            **_job_summary(hist.payload),
            "output": parsed["output"],
            "error_output": parsed["error_output"],
            "compute_duration_s": hist.compute_duration_s,
            "failure_reason": hist.payload.get("failure_reason") if hist.payload else None,
        }

    raise HTTPException(404, f"Job {job_id} not found")


# ---------------------------------------------------------------------------
# GET /api/price — dedicated pricing endpoint
# ---------------------------------------------------------------------------

@router.get("/api/price")
async def get_price(
    cpus: int = 1,
    time_limit_min: int = 1,
    submission_mode: str = "script",
    db: AsyncSession = Depends(get_db),
):
    """Get a price quote without submitting a job."""
    if submission_mode not in ("script", "multi_file", "archive", "git"):
        raise HTTPException(422, "Invalid submission_mode")
    quote = await calculate_price(db, cpus, time_limit_min, submission_mode)
    return {"price": quote.price_str, "breakdown": quote.breakdown}


# ---------------------------------------------------------------------------
# GET /api/capabilities — machine-readable service description for agents
# ---------------------------------------------------------------------------

@router.get("/api/capabilities")
async def get_capabilities():
    return {
        "name": "Ouro",
        "description": "Autonomous compute oracle on Base",
        "version": "1.0.0",
        "payment": {
            "protocol": "x402",
            "network": settings.CHAIN_CAIP2,
            "currency": "USDC",
            "endpoint": "/api/compute/submit",
        },
        "compute": {
            "engine": "slurm",
            "isolation": "docker",
            "max_cpus": 8,
            "max_time_min": 60,
            "max_script_bytes": MAX_SCRIPT_SIZE,
            "max_workspace_bytes": 10 * 1024 * 1024,
            "submission_modes": ["script", "multi_file"],
            "persistent_storage": True,
            "allowed_images": sorted(settings.allowed_images_set),
        },
        "storage": {
            "enabled": True,
            "mount_point": "/scratch",
            "free_tier_bytes": settings.STORAGE_FREE_TIER_BYTES,
            "max_files": MAX_STORAGE_FILES,
            "ttl_days": settings.STORAGE_TTL_DAYS,
            "access": "read-write",
        },
        "trust": {
            "agent_address": settings.WALLET_ADDRESS,
            "erc8004_agent_id": settings.ERC8004_AGENT_ID or None,
            "identity_registry": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
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
        "name": "Ouro",
        "description": (
            "Autonomous compute agent on Base. Submit scripts, "
            "pay with USDC via x402."
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
                "id": "submit_and_pay",
                "name": "Submit and Pay for Compute Job",
                "description": "Submit a compute job with x402 payment. Execute scripts in isolated Docker containers.",
                "tags": ["compute", "slurm", "execution"],
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
                "description": "Get status and output of a submitted compute job.",
                "tags": ["status", "results"],
                "inputModes": ["application/json"],
                "outputModes": ["application/json"],
            },
        ],
    }


