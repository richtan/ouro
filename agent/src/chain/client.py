from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
from eth_account import Account
from web3 import AsyncWeb3, AsyncHTTPProvider

from src.chain import erc8021
from src.chain.abi import (
    CODE_REGISTRY_ABI,
    ERC20_BALANCE_OF_ABI,
    ERC8004_ABI,
    PROOF_OF_COMPUTE_ABI,
    PROOF_OF_COMPUTE_REPUTATION_ABI,
)
from src.config import settings

logger = logging.getLogger(__name__)

_eth_price_cache: dict[str, Any] = {"price": 0.0, "ts": 0.0}


@dataclass
class TxResult:
    tx_hash: str
    gas_cost_usd: float
    gas_cost_wei: int
    codes: list[str]


class BaseChainClient:
    def __init__(self) -> None:
        self.w3 = AsyncWeb3(AsyncHTTPProvider(settings.BASE_RPC_URL))
        self.account = Account.from_key(settings.WALLET_PRIVATE_KEY)
        self.contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(settings.PROOF_CONTRACT_ADDRESS),
            abi=PROOF_OF_COMPUTE_ABI,
        )
        self.contract_address = settings.PROOF_CONTRACT_ADDRESS
        self.usdc_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(settings.USDC_CONTRACT_ADDRESS),
            abi=ERC20_BALANCE_OF_ABI,
        )
        self._tx_lock = asyncio.Lock()
        self._local_nonce: int | None = None

    @staticmethod
    def _to_bytes(data: bytes | str) -> bytes:
        if isinstance(data, str):
            return bytes.fromhex(data.removeprefix("0x"))
        return data

    async def send_tx(
        self,
        to: str,
        data: bytes | str,
        value: int = 0,
        extra_codes: list[str] | None = None,
    ) -> TxResult:
        async with self._tx_lock:
            codes = [settings.BUILDER_CODE]
            if extra_codes:
                codes.extend(extra_codes)

            data_bytes = self._to_bytes(data)
            data_with_suffix = erc8021.append_builder_codes(data_bytes, codes)

            # Use local nonce to avoid race conditions between rapid transactions
            if self._local_nonce is None:
                self._local_nonce = await self.w3.eth.get_transaction_count(self.account.address)
            nonce = self._local_nonce

            tx = {
                "to": self.w3.to_checksum_address(to),
                "data": data_with_suffix,
                "value": value,
                "from": self.account.address,
                "gas": await self._estimate_gas(to, data_with_suffix, value),
                "gasPrice": await self.w3.eth.gas_price,
                "nonce": nonce,
                "chainId": settings.CHAIN_ID,
            }
            signed = self.account.sign_transaction(tx)
            raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
            try:
                tx_hash = await self.w3.eth.send_raw_transaction(raw)
                self._local_nonce = nonce + 1
            except Exception:
                # Reset local nonce on failure so next call re-fetches from network
                self._local_nonce = None
                raise

        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)
        gas_cost_wei = receipt.gasUsed * receipt.effectiveGasPrice
        eth_price = await self.get_eth_price_usd()
        gas_cost_usd = float(self.w3.from_wei(gas_cost_wei, "ether")) * eth_price

        logger.info(
            "tx_sent hash=%s gas_usd=%.4f codes=%s",
            tx_hash.hex(),
            gas_cost_usd,
            codes,
        )
        return TxResult(
            tx_hash=tx_hash.hex(),
            gas_cost_usd=gas_cost_usd,
            gas_cost_wei=gas_cost_wei,
            codes=codes,
        )

    async def _estimate_gas(self, to: str, data: bytes, value: int) -> int:
        try:
            return await self.w3.eth.estimate_gas(
                {
                    "to": self.w3.to_checksum_address(to),
                    "data": data,
                    "value": value,
                    "from": self.account.address,
                }
            )
        except Exception:
            return 100_000

    async def submit_proof(
        self,
        job_id: str,
        output_hash: bytes,
        client_builder_code: str | None = None,
    ) -> TxResult:
        calldata = self.contract.encode_abi("submitProof", args=[job_id, output_hash])
        extra = [client_builder_code] if client_builder_code else None
        return await self.send_tx(self.contract_address, calldata, extra_codes=extra)

    async def send_heartbeat(self) -> TxResult:
        return await self.send_tx(self.account.address, b"", value=0)

    async def get_balances(self) -> tuple[int, float]:
        eth = await self.w3.eth.get_balance(self.account.address)
        usdc_raw = await self.usdc_contract.functions.balanceOf(
            self.account.address
        ).call()
        return eth, usdc_raw / 1e6

    async def get_eth_price_usd(self) -> float:
        now = time.time()
        if now - _eth_price_cache["ts"] < 60:
            return _eth_price_cache["price"]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.coinbase.com/v2/prices/ETH-USD/spot",
                    timeout=5,
                )
                price = float(resp.json()["data"]["amount"])
                _eth_price_cache.update(price=price, ts=now)
                return price
        except Exception:
            return _eth_price_cache["price"] or 3000.0

    async def verify_builder_code(self, code: str) -> dict:
        if not settings.CODE_REGISTRY_ADDRESS:
            return {"code": code, "registered": False, "payout_address": None}
        registry = self.w3.eth.contract(
            address=self.w3.to_checksum_address(settings.CODE_REGISTRY_ADDRESS),
            abi=CODE_REGISTRY_ABI,
        )
        is_registered = await registry.functions.isRegistered(code).call()
        payout = (
            await registry.functions.payoutAddress(code).call()
            if is_registered
            else None
        )
        return {"code": code, "registered": is_registered, "payout_address": payout}

    async def get_on_chain_proof_count(self) -> int:
        try:
            reputation_contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(settings.PROOF_CONTRACT_ADDRESS),
                abi=PROOF_OF_COMPUTE_REPUTATION_ABI,
            )
            result = await reputation_contract.functions.getReputation(
                self.account.address
            ).call()
            return result[0]
        except Exception:
            try:
                return await self.contract.functions.proofCount().call()
            except Exception:
                return 0

    async def get_erc8004_agent_count(self) -> int:
        from src.chain.erc8004 import ERC8004_REGISTRY

        try:
            registry = self.w3.eth.contract(
                address=self.w3.to_checksum_address(ERC8004_REGISTRY),
                abi=ERC8004_ABI,
            )
            return await registry.functions.agentCount().call()
        except Exception:
            return 0
