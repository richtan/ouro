# Lessons Learned

## x402 Python SDK Signing Bug (2026-03-02)

**Problem**: The x402 Python SDK v2.2.0 produces EIP-712 signatures that the CDP facilitator rejects as `invalid_payload`.

**Root cause**: Two issues in the SDK:
1. `build_typed_data_for_signing()` converts nonce to `bytes` but `eth_account.sign_typed_data()` expects hex strings for `bytes32` fields. The SDK's own verify path even has a workaround that converts bytes→hex, confirming the inconsistency.
2. Addresses passed to the EIP-712 message without checksumming.

**Fix**: Bypass the SDK's signing path with a manual helper (`x402_signer.py`) that mirrors the JS SDK: checksummed addresses, hex string nonce, plain dicts.

**Diagnostic approach**: Compared the live 402 error against the JS SDK's working behavior. Generated a throwaway keypair to test payload structure without needing USDC. When the error changed from `invalid_payload` to `insufficient_funds`, the fix was confirmed.

**Rule**: When an SDK produces incorrect cryptographic outputs, don't monkey-patch — build a standalone helper that matches the reference (JS) implementation exactly. Compare by testing against the live facilitator.
