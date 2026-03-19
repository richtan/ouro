from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.agent.event_bus import EventBus
from src.agent.loop import autonomous_loop
from src.agent.processor import process_pending_jobs
from src.api.routes import init_routes, router
from src.chain.client import BaseChainClient
from src.config import settings
from src.db.session import async_session_maker
from src.slurm.client import SlurmClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MAX_REQUEST_BODY_BYTES = 1_048_576  # 1 MB


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BODY_BYTES, overrides: dict | None = None):
        super().__init__(app)
        self.max_bytes = max_bytes
        self.overrides = overrides or {}

    async def dispatch(self, request: Request, call_next):
        limit = self.overrides.get(request.url.path, self.max_bytes)
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > limit:
            return JSONResponse(
                status_code=413,
                content={"error": "Request body too large"},
            )
        return await call_next(request)


def _build_cdp_auth_provider():
    """Build an auth provider for the CDP facilitator using JWT tokens."""
    from cdp.auth.utils.jwt import generate_jwt, JwtOptions
    from x402.http import CreateHeadersAuthProvider

    CDP_HOST = "api.cdp.coinbase.com"
    key_id = settings.CDP_API_KEY_ID
    key_secret = settings.CDP_API_KEY_SECRET

    def create_headers() -> dict[str, dict[str, str]]:
        def _jwt(method: str, path: str) -> str:
            return generate_jwt(JwtOptions(
                api_key_id=key_id,
                api_key_secret=key_secret,
                request_method=method,
                request_host=CDP_HOST,
                request_path=path,
            ))

        base = "/platform/v2/x402"
        return {
            "verify": {"Authorization": f"Bearer {_jwt('POST', f'{base}/verify')}"},
            "settle": {"Authorization": f"Bearer {_jwt('POST', f'{base}/settle')}"},
            "supported": {"Authorization": f"Bearer {_jwt('GET', f'{base}/supported')}"},
        }

    return CreateHeadersAuthProvider(create_headers)


def _init_x402_server():
    """Initialize x402 resource server.

    Uses the CDP facilitator (with JWT auth) on mainnet and the open
    x402.org facilitator on testnet.
    """
    from x402 import x402ResourceServer
    from x402.extensions.bazaar.server import bazaar_resource_server_extension
    from x402.http import FacilitatorConfig, HTTPFacilitatorClient
    from x402.mechanisms.evm.exact import ExactEvmServerScheme

    use_cdp = bool(settings.CDP_API_KEY_ID and settings.CDP_API_KEY_SECRET)
    if use_cdp:
        url = "https://api.cdp.coinbase.com/platform/v2/x402"
        auth = _build_cdp_auth_provider()
        logger.info("Using CDP facilitator for x402 (mainnet)")
    else:
        url = settings.X402_FACILITATOR_URL
        auth = None
        logger.info("Using x402.org facilitator (testnet)")

    if not use_cdp and settings.CHAIN_CAIP2 and ":84532" not in settings.CHAIN_CAIP2:
        logger.warning(
            "x402 testnet facilitator selected but CHAIN_CAIP2=%s is not testnet — "
            "set CDP_API_KEY_ID and CDP_API_KEY_SECRET for mainnet",
            settings.CHAIN_CAIP2,
        )

    facilitator = HTTPFacilitatorClient(
        FacilitatorConfig(url=url, auth_provider=auth)
    )
    server = x402ResourceServer(facilitator)
    server.register("eip155:*", ExactEvmServerScheme())
    server.register_extension(bazaar_resource_server_extension)
    server.initialize()
    return server


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.db.migrate import run_migrations
    from src.db.session import engine

    await run_migrations(engine)

    if not settings.ADMIN_API_KEY:
        logger.critical(
            "ADMIN_API_KEY is empty — all admin endpoints are unauthenticated. "
            "Set ADMIN_API_KEY to a secure value (>= 32 chars) in production."
        )

    event_bus = EventBus()
    chain_client = BaseChainClient()
    slurm_client = SlurmClient()

    resource_server = _init_x402_server()

    init_routes(event_bus, chain_client, resource_server, slurm_client)

    event_bus.emit("system", "Ouro agent starting up")

    # ERC-8004 identity — resolve or register agentId
    if not settings.ERC8004_AGENT_ID:
        try:
            from src.chain.erc8004 import get_agent_id, register_agent

            # First check if we already have a registration
            existing_id = await get_agent_id(chain_client, settings.WALLET_ADDRESS)
            if existing_id is not None:
                settings.ERC8004_AGENT_ID = str(existing_id)
                event_bus.emit("erc8004", f"Existing agentId resolved: {existing_id}")
                logger.info("ERC-8004 agentId resolved from registry: %d", existing_id)
            elif settings.PUBLIC_DASHBOARD_URL:
                # No existing registration — register now
                tx, agent_id = await register_agent(
                    chain_client, settings.PUBLIC_DASHBOARD_URL, settings.PUBLIC_API_URL
                )
                if agent_id is not None:
                    settings.ERC8004_AGENT_ID = str(agent_id)
                event_bus.emit("erc8004", f"Agent registered on-chain: {tx} (agentId={agent_id})")
        except Exception as e:
            event_bus.emit("erc8004_error", f"ERC-8004 lookup/registration failed (non-fatal): {e}")

    loop_task = asyncio.create_task(
        autonomous_loop(
            chain_client=chain_client,
            slurm_client=slurm_client,
            session_maker=async_session_maker,
            event_bus=event_bus,
        )
    )

    processor_task = asyncio.create_task(
        process_pending_jobs(
            chain_client=chain_client,
            slurm_client=slurm_client,
            session_maker=async_session_maker,
            event_bus=event_bus,
        )
    )

    event_bus.emit("system", "Autonomous loop and job processor started")
    logger.info("Ouro agent ready")

    yield

    loop_task.cancel()
    processor_task.cancel()
    await slurm_client.close()
    event_bus.emit("system", "Ouro agent shutting down")


app = FastAPI(
    title="Ouro",
    description="Autonomous compute oracle on Base",
    lifespan=lifespan,
)

_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "payment-signature", "X-Admin-Key"],
)
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_bytes=MAX_REQUEST_BODY_BYTES,
    overrides={"/api/compute/submit": 10 * 1024 * 1024},  # 10MB for multi-file workspaces
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.include_router(router)
