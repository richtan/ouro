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
from src.chain.abi import ERC20_BALANCE_OF_ABI
from src.config import settings

logger = logging.getLogger(__name__)

_eth_price_cache: dict[str, Any] = {"price": 0.0, "ts": 0.0}


@dataclass
class TxResult:
    tx_hash: str
    gas_cost_usd: float
    gas_cost_wei: int
    codes: list[str]
    receipt: dict | None = None


class BaseChainClient:
    def __init__(self) -> None:
        self.w3 = AsyncWeb3(AsyncHTTPProvider(settings.BASE_RPC_URL))
        self.account = Account.from_key(settings.WALLET_PRIVATE_KEY)
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
    ) -> TxResult:
        async with self._tx_lock:
            codes = [settings.BUILDER_CODE]

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
            receipt=dict(receipt),
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

