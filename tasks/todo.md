# Fix x402 Python Signing for Autonomous MCP Payment Flow

## Status: VERIFIED

## Root Cause
The Python x402 SDK v2.2.0 has two bugs causing the CDP facilitator to reject payloads:

1. **Nonce format mismatch**: `build_typed_data_for_signing()` converts nonce to `bytes` before passing to `eth_account.sign_typed_data()`. But the SDK's own verify path (and the JS SDK) uses hex strings. The EIP-712 hash differs, causing signature verification failure.

2. **Address checksumming**: The `payTo` address from payment requirements is passed as-is without checksumming. The JS SDK checksums all addresses via `getAddress()`.

## Changes Made

- [x] `agent/src/api/routes.py` — Debug logging for payment-signature headers + improved facilitator error handling (returns 403 with structured error instead of 503 for client errors like insufficient_funds)
- [x] `mcp-server/src/ouro_mcp/x402_signer.py` — Manual EIP-3009 signing helper that bypasses the SDK and mirrors JS SDK behavior (checksummed addresses, hex string nonce)
- [x] `mcp-server/test_e2e.py` — End-to-end test script
- [x] `mcp-server/pyproject.toml` — Added eth-account and eth-utils to dev dependencies
- [x] `mcp-server/src/ouro_mcp/server.py` — Improved 403 error messages (distinguishes insufficient_funds vs invalid_payload)

## Verification

E2E test with throwaway keypair confirms:
- Facilitator accepts the payload structure (no more `invalid_payload`)
- Correctly recovers the signer address
- Only rejects due to `insufficient_funds` (expected with no USDC)

## Next Steps

- [ ] Deploy agent changes (`./deploy/deploy.sh agent`)
- [ ] Test with funded wallet: `PRIVATE_KEY=0x... python test_e2e.py`
- [ ] Consider upstreaming the fix to the x402 Python SDK
