from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    facilitator = HTTPFacilitatorClient(
        FacilitatorConfig(url=url, auth_provider=auth)
    )
    server = x402ResourceServer(facilitator)
    server.register("eip155:*", ExactEvmServerScheme())
    server.initialize()
    return server


@asynccontextmanager
async def lifespan(app: FastAPI):
    event_bus = EventBus()
    chain_client = BaseChainClient()
    slurm_client = SlurmClient()

    resource_server = _init_x402_server()

    init_routes(event_bus, chain_client, resource_server)

    event_bus.emit("system", "Ouro agent starting up")

    # ERC-8004 registration (one-time)
    if not settings.ERC8004_AGENT_ID and settings.PUBLIC_DASHBOARD_URL:
        try:
            from src.chain.erc8004 import register_agent

            tx = await register_agent(
                chain_client, settings.PUBLIC_DASHBOARD_URL, settings.PUBLIC_API_URL
            )
            event_bus.emit("erc8004", f"Agent registered on-chain: {tx}")
        except Exception as e:
            event_bus.emit("erc8004_error", f"Registration failed (non-fatal): {e}")

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
    title="Ouro — Proof-of-Compute Oracle",
    description="Autonomous HPC compute oracle on Base",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
