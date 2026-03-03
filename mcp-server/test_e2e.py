#!/usr/bin/env python3
"""End-to-end test for the autonomous x402 payment flow.

Tests:  get_payment_requirements → sign → submit_and_pay → get_job_status

Usage:
    # Step 1: Test payload structure with a throwaway key (no USDC needed).
    # If the error changes from 'invalid_payload' to 'insufficient funds',
    # the signing fix is working.
    python test_e2e.py

    # Step 2: Full flow with a funded wallet.
    PRIVATE_KEY=0x... python test_e2e.py

    # Against a specific agent URL:
    AGENT_URL=http://localhost:8000 python test_e2e.py

Environment variables:
    AGENT_URL       Agent base URL (default: https://api.ourocompute.com)
    PRIVATE_KEY     Hex private key (generates a throwaway key if not set)
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx

# Allow importing from the MCP server package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from ouro_mcp.x402_signer import decode_payment_required_header, sign_x402_payment

AGENT_URL = os.environ.get("AGENT_URL", "https://api.ourocompute.com")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY", "")


def _get_private_key() -> str:
    """Return configured key or generate a throwaway one."""
    if PRIVATE_KEY:
        return PRIVATE_KEY
    from eth_account import Account

    acct = Account.create()
    print(f"[info] Generated throwaway keypair: {acct.address}")
    print(f"[info] (no USDC — testing payload structure only)\n")
    return acct.key.hex()


async def step1_get_payment_requirements(
    client: httpx.AsyncClient,
) -> tuple[dict, str]:
    """Hit the agent submit endpoint without payment to get 402 + requirements."""
    print("=== Step 1: Get payment requirements ===")
    resp = await client.post(
        f"{AGENT_URL}/api/compute/submit",
        json={"script": "echo hello from e2e test", "nodes": 1, "time_limit_min": 1},
    )
    print(f"  Status: {resp.status_code}")

    if resp.status_code != 402:
        print(f"  ERROR: Expected 402, got {resp.status_code}")
        print(f"  Body: {resp.text[:500]}")
        sys.exit(1)

    body = resp.json()
    print(f"  Price: {body.get('price')}")
    print(f"  Breakdown: {body.get('breakdown')}")

    raw_header = resp.headers.get("payment-required", "")
    if not raw_header:
        print("  ERROR: No PAYMENT-REQUIRED header in response")
        sys.exit(1)

    payment_required = decode_payment_required_header(raw_header)
    requirements = payment_required["accepts"][0]
    print(f"  Scheme: {requirements.get('scheme')}")
    print(f"  Network: {requirements.get('network')}")
    print(f"  Asset: {requirements.get('asset')}")
    print(f"  Amount: {requirements.get('amount')}")
    print(f"  PayTo: {requirements.get('payTo')}")
    print(f"  Extra: {requirements.get('extra')}")
    print()

    return payment_required, raw_header


def step2_sign_payment(private_key: str, payment_required: dict) -> str:
    """Sign the payment using the manual helper."""
    print("=== Step 2: Sign payment ===")
    from eth_account import Account

    acct = Account.from_key(private_key)
    print(f"  Signer: {acct.address}")

    signature = sign_x402_payment(private_key, payment_required)
    print(f"  Signature length: {len(signature)}")

    # Decode and show the payload structure for debugging
    import base64
    import json

    decoded = json.loads(base64.b64decode(signature.encode()).decode())
    auth = decoded.get("payload", {}).get("authorization", {})
    print(f"  Payload from: {auth.get('from')}")
    print(f"  Payload to: {auth.get('to')}")
    print(f"  Payload value: {auth.get('value')}")
    print(f"  Payload nonce: {auth.get('nonce', '')[:20]}...")
    print(f"  Signature: {decoded.get('payload', {}).get('signature', '')[:20]}...")
    print()

    return signature


async def step3_submit_with_payment(
    client: httpx.AsyncClient,
    payment_signature: str,
) -> dict:
    """Submit the job with the signed payment."""
    print("=== Step 3: Submit with payment ===")
    resp = await client.post(
        f"{AGENT_URL}/api/compute/submit",
        json={"script": "echo hello from e2e test", "nodes": 1, "time_limit_min": 1},
        headers={"payment-signature": payment_signature},
    )
    print(f"  Status: {resp.status_code}")
    body = resp.json()
    print(f"  Body: {json.dumps(body, indent=2)[:500]}")
    print()

    return {"status_code": resp.status_code, "body": body}


async def step4_poll_job(client: httpx.AsyncClient, job_id: str) -> None:
    """Poll for job completion."""
    print(f"=== Step 4: Poll job {job_id[:8]}... ===")
    for i in range(60):
        resp = await client.get(f"{AGENT_URL}/api/jobs/{job_id}")
        if resp.status_code == 404:
            print(f"  [{i}] Job not found yet...")
            await asyncio.sleep(5)
            continue

        data = resp.json()
        status = data.get("status", "unknown")
        print(f"  [{i}] Status: {status}")

        if status in ("completed", "failed"):
            print(f"  Output: {data.get('output', '')[:200]}")
            print(f"  Error: {data.get('error_output', '')[:200]}")
            print(f"  Proof TX: {data.get('proof_tx_hash')}")
            print(f"  Duration: {data.get('compute_duration_s')}s")
            return

        await asyncio.sleep(5)

    print("  TIMEOUT: Job did not complete within 5 minutes")


import json


async def main():
    print(f"Agent URL: {AGENT_URL}\n")

    private_key = _get_private_key()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Get payment requirements
        payment_required, raw_header = await step1_get_payment_requirements(client)

        # Step 2: Sign the payment
        payment_signature = step2_sign_payment(private_key, payment_required)

        # Step 3: Submit with payment
        result = await step3_submit_with_payment(client, payment_signature)

        status = result["status_code"]
        body = result["body"]

        if status == 200:
            job_id = body.get("job_id")
            print(f"SUCCESS: Job created: {job_id}")
            print(f"Price: {body.get('price')}")

            # Step 4: Poll for results
            await step4_poll_job(client, job_id)

        elif status == 402:
            print("RESULT: 402 - Payment not recognized")
            print("The payment-signature header was not accepted.")
            print("This likely means the signing format still differs from JS SDK.")
            sys.exit(1)

        elif status == 403:
            print("RESULT: 403 - Payment verification failed")
            detail = body.get("detail", "")
            error = body.get("error", "")
            print(f"Detail: {detail}")
            print(f"Error: {error}")
            # If we see 'insufficient funds' or 'balance' errors, the signing is correct!
            if any(
                kw in str(body).lower()
                for kw in ["insufficient", "balance", "funds", "allowance"]
            ):
                print("\n*** SIGNING FIX WORKS! ***")
                print("The facilitator accepted the payload structure but the wallet")
                print("has insufficient USDC. Run with a funded PRIVATE_KEY for full flow.")
            else:
                print("\nThe payload was rejected. Check agent logs for details.")
            sys.exit(1)

        elif status == 503:
            detail = str(body.get("detail", ""))
            if any(
                kw in detail.lower()
                for kw in ["insufficient", "balance", "funds", "allowance"]
            ):
                print("RESULT: 503 (facilitator rejected for insufficient funds)")
                print(f"Detail: {detail}")
                print("\n*** SIGNING FIX WORKS! ***")
                print("The facilitator accepted the payload structure and recovered the")
                print("correct signer address, but the wallet has no USDC.")
                print("Run with a funded PRIVATE_KEY for the full end-to-end flow.")
            else:
                print("RESULT: 503 - Facilitator unavailable or payload rejected")
                print(f"Detail: {body}")
                sys.exit(1)

        else:
            print(f"RESULT: Unexpected status {status}")
            print(f"Body: {body}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
