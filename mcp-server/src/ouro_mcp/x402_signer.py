"""Manual x402 EIP-3009 signing helper that mirrors the JS SDK behavior.

The Python x402 SDK v2.2.0 has two issues that cause the CDP facilitator
to reject payloads as ``invalid_payload``:

1. **Nonce format** -- the SDK converts the nonce to ``bytes`` before passing
   it to ``eth_account.sign_typed_data``, but the facilitator (and the JS SDK)
   use hex strings.  The SDK's own verify path even converts bytes back to hex
   before calling ``eth_account`` (see ``FacilitatorWeb3Signer.verify_typed_data``),
   confirming the mismatch.

2. **Address checksumming** -- ``build_typed_data_for_signing`` passes the
   ``payTo`` address as-is from the payment requirements.  If the server sends
   a non-checksummed address the EIP-712 hash may differ from what the
   facilitator computes (viem always checksums via ``getAddress``).

This module bypasses the SDK's signing path and constructs payloads that
exactly match what the JS ``@x402/evm`` v2.4.0 ``ExactEvmScheme`` produces.
"""

from __future__ import annotations

import base64
import json
import os
import time

from eth_account import Account
from eth_utils import to_checksum_address


def decode_payment_required_header(header_value: str) -> dict:
    """Decode a base64-encoded ``PAYMENT-REQUIRED`` header.

    Args:
        header_value: Raw base64 string from the ``PAYMENT-REQUIRED`` header.

    Returns:
        Parsed JSON dict (``x402Version``, ``accepts``, ...).
    """
    return json.loads(base64.b64decode(header_value.encode()).decode())


def sign_x402_payment(
    private_key: str,
    payment_required: dict,
    *,
    validity_seconds: int | None = None,
) -> str:
    """Sign an x402 payment and return the base64-encoded ``payment-signature``.

    Mirrors the JS SDK's ``ExactEvmScheme.createPaymentPayload`` exactly:
    - All addresses checksummed via ``to_checksum_address``
    - Nonce passed as hex string (not bytes)
    - Timestamps as ints in the message, strings in the payload JSON

    Args:
        private_key: Hex private key (with or without ``0x`` prefix).
        payment_required: Decoded ``PAYMENT-REQUIRED`` header dict.
        validity_seconds: Override validity window (defaults to
            ``maxTimeoutSeconds`` from requirements).

    Returns:
        Base64-encoded payment-signature header value.
    """
    requirements = payment_required["accepts"][0]

    network = requirements["network"]
    asset = requirements["asset"]
    amount = requirements["amount"]
    pay_to = requirements["payTo"]
    max_timeout = validity_seconds or requirements.get("maxTimeoutSeconds", 3600)
    extra = requirements.get("extra", {})

    # EIP-712 domain parameters from token metadata
    token_name = extra.get("name", "USD Coin")
    token_version = extra.get("version", "2")

    # Chain ID from CAIP-2 identifier
    chain_id = int(network.split(":")[1])

    # Account setup
    account = Account.from_key(private_key)
    from_address = to_checksum_address(account.address)
    to_address = to_checksum_address(pay_to)
    verifying_contract = to_checksum_address(asset)

    # Random 32-byte nonce as hex string (matches JS toHex(crypto.getRandomValues))
    nonce = "0x" + os.urandom(32).hex()

    # Validity window with clock-skew buffer (matches JS SDK)
    now = int(time.time())
    valid_after = now - 30
    valid_before = now + max_timeout

    # -- EIP-712 typed data (matching JS SDK exactly) --
    domain = {
        "name": token_name,
        "version": token_version,
        "chainId": chain_id,
        "verifyingContract": verifying_contract,
    }

    types = {
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ]
    }

    message = {
        "from": from_address,
        "to": to_address,
        "value": int(amount),
        "validAfter": valid_after,
        "validBefore": valid_before,
        "nonce": nonce,  # hex string, NOT bytes -- this is the key fix
    }

    # Sign with eth_account
    signed = account.sign_typed_data(
        domain_data=domain,
        message_types=types,
        message_data=message,
    )
    signature = "0x" + bytes(signed.signature).hex()

    # -- Build the payload JSON matching JS SDK's PaymentPayload structure --
    payload = {
        "x402Version": 2,
        "payload": {
            "authorization": {
                "from": from_address,
                "to": to_address,
                "value": str(amount),
                "validAfter": str(valid_after),
                "validBefore": str(valid_before),
                "nonce": nonce,
            },
            "signature": signature,
        },
        "accepted": requirements,
    }

    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
