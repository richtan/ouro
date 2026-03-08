"""ERC-8004 Agent Identity Registration."""

from __future__ import annotations

import base64
import json
import logging

from src.chain.abi import ERC8004_ABI, MULTICALL3_ABI
from src.config import settings

logger = logging.getLogger(__name__)

ERC8004_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"

# ERC-721 Transfer event topic for receipt parsing only (not eth_getLogs)
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


async def _find_upper_bound(registry, multicall) -> int | None:
    """Find an upper bound for tokenId via multicall exponential probe.

    Returns the smallest power-of-2 that exceeds all existing tokens,
    or None if no tokens exist. No binary search needed — the scan
    handles non-existent tokens gracefully.
    """
    probes = [2**i for i in range(18)]  # [1, 2, 4, ..., 131072]
    calls = [
        (registry.address, registry.encode_abi("ownerOf", args=[p]))
        for p in probes
    ]
    results = await multicall.functions.tryAggregate(False, calls).call()

    max_existing = None
    for probe, (success, _) in zip(probes, results):
        if success:
            max_existing = probe

    if max_existing is None:
        return None
    if max_existing == probes[-1]:
        return max_existing  # All probes succeeded — cap here
    return max_existing * 2  # Upper bound: next power of 2


async def get_agent_id(chain_client, wallet_address: str) -> int | None:
    """Look up the agentId (ERC-721 tokenId) owned by a wallet.

    Uses balanceOf as a quick check, then reverse-scans via Multicall3-batched
    ownerOf calls. ~3 RPC requests total instead of hundreds.
    """
    registry_addr = chain_client.w3.to_checksum_address(ERC8004_REGISTRY)
    registry = chain_client.w3.eth.contract(address=registry_addr, abi=ERC8004_ABI)
    multicall = chain_client.w3.eth.contract(
        address=chain_client.w3.to_checksum_address(MULTICALL3_ADDRESS),
        abi=MULTICALL3_ABI,
    )
    wallet_cs = chain_client.w3.to_checksum_address(wallet_address)
    try:
        balance = await registry.functions.balanceOf(wallet_cs).call()
        if balance == 0:
            return None

        upper_bound = await _find_upper_bound(registry, multicall)
        if upper_bound is None:
            return None

        # Reverse scan in multicall batches of 2000 (1 RPC per batch)
        batch_size = 2000
        for start in range(upper_bound, 0, -batch_size):
            end = max(start - batch_size + 1, 1)
            ids = list(range(start, end - 1, -1))

            calls = [
                (registry_addr, registry.encode_abi("ownerOf", args=[tid]))
                for tid in ids
            ]
            try:
                results = await multicall.functions.tryAggregate(False, calls).call()
            except Exception as e:
                logger.warning("Multicall failed for batch at %d: %s", start, e)
                continue

            for tid, (success, return_data) in zip(ids, results):
                if success and len(return_data) >= 32:
                    owner = "0x" + return_data[-20:].hex()
                    if chain_client.w3.to_checksum_address(owner) == wallet_cs:
                        return tid

        logger.warning("balanceOf>0 but ownerOf scan found no match for %s", wallet_address)
    except Exception as e:
        logger.warning("Failed to look up agentId for %s: %s", wallet_address, e)
    return None


def _extract_agent_id_from_receipt(receipt: dict, wallet_address: str) -> int | None:
    """Extract agentId from a register() transaction receipt's Transfer logs."""
    wallet_lower = wallet_address.lower()
    for log in receipt.get("logs", []):
        topics = log.get("topics", [])
        if len(topics) < 4:
            continue
        topic0 = topics[0].hex() if isinstance(topics[0], bytes) else str(topics[0])
        if not topic0.endswith(_TRANSFER_TOPIC[2:]):
            continue
        # topics[1] = from (should be address(0) for mint)
        from_raw = topics[1].hex() if isinstance(topics[1], bytes) else str(topics[1])
        if int(from_raw, 16) != 0:
            continue
        # topics[2] = to (should be our wallet)
        to_raw = topics[2].hex() if isinstance(topics[2], bytes) else str(topics[2])
        to_addr = "0x" + to_raw[-40:]
        if to_addr.lower() != wallet_lower:
            continue
        # topics[3] = tokenId
        id_raw = topics[3].hex() if isinstance(topics[3], bytes) else str(topics[3])
        return int(id_raw, 16)
    return None


async def register_agent(chain_client, dashboard_url: str, api_url: str) -> tuple[str, int | None]:
    """Register agent on ERC-8004 Identity Registry.

    Returns (tx_hash, agent_id). Extracts agentId from the tx receipt's Transfer log.
    Falls back to ownerOf scan if receipt parsing fails.
    """
    registration = {
        "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
        "name": "Ouro",
        "description": (
            "Autonomous HPC compute oracle on Base. Accepts x402 USDC payments "
            "for running scripts on Slurm clusters. "
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

    # Extract agentId from the receipt's Transfer log
    agent_id = None
    if result.receipt:
        agent_id = _extract_agent_id_from_receipt(result.receipt, settings.WALLET_ADDRESS)
    if agent_id is None:
        logger.info("Receipt parsing failed, falling back to ownerOf scan")
        agent_id = await get_agent_id(chain_client, settings.WALLET_ADDRESS)
    if agent_id is not None:
        logger.info("ERC-8004 agentId resolved: %d", agent_id)

    return result.tx_hash, agent_id
