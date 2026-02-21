"""ERC-8004 Agent Identity Registration."""

from __future__ import annotations

import base64
import json
import logging

from src.chain.abi import ERC8004_ABI
from src.config import settings

logger = logging.getLogger(__name__)

ERC8004_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"


async def register_agent(chain_client, dashboard_url: str, api_url: str) -> str:
    registration = {
        "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        "name": "Ouro Proof-of-Compute Oracle",
        "description": (
            "Autonomous HPC compute oracle on Base. Accepts x402 USDC payments "
            "for running scripts on Slurm clusters, posts verifiable on-chain proofs. "
            "Self-sustaining via dynamic pricing."
        ),
        "image": "",
        "active": True,
        "x402Support": True,
        "services": [
            {"name": "web", "endpoint": dashboard_url},
            {"name": "x402-compute", "endpoint": f"{api_url}/api/compute/submit"},
        ],
    }
    uri = "data:application/json;base64," + base64.b64encode(
        json.dumps(registration).encode()
    ).decode()

    contract = chain_client.w3.eth.contract(
        address=chain_client.w3.to_checksum_address(ERC8004_REGISTRY),
        abi=ERC8004_ABI,
    )
    calldata = contract.encode_abi("register", args=[uri])
    result = await chain_client.send_tx(ERC8004_REGISTRY, calldata)
    logger.info("ERC-8004 agent registered: tx=%s", result.tx_hash)
    return result.tx_hash
