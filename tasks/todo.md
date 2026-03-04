# Phase 1: Security Hardening

## Status: COMPLETE

## Changes Made

- [x] **Fix 1: Heredoc Injection** (`deploy/slurm/slurm_proxy.py`) — Rewrote `wrap_in_apptainer()` to write user scripts to temp files via Python instead of bash heredoc. Changed Apptainer-unavailable fallback from silent bare execution to HTTP 503. Both wrapper and user script cleaned up in finally block.

- [x] **Fix 2: Session Endpoint Hardening** (`agent/src/api/routes.py`) — Added rate limiting by client IP on session creation. Added TTL check and status guard (409 Conflict on double-complete) to `complete_session`. Added UUID validation for job_id.

- [x] **Fix 3: Pydantic Request Models** (`agent/src/api/routes.py`) — Added `ComputeSubmitRequest`, `CreateSessionRequest`, `CompleteSessionRequest` Pydantic models with Field constraints (min/max length, ge/le bounds). All POST endpoints now validate input and return 422 on bad data instead of 500s.

- [x] **Fix 4: CORS Lockdown** (`agent/src/config.py`, `agent/src/main.py`, `mcp-server/src/ouro_mcp/server.py`) — Replaced `allow_origins=["*"]` with configurable origin list (default: ourocompute.com + localhost). Restricted methods to GET/POST/OPTIONS. Restricted headers to only those actually used.

- [x] **Fix 5: Non-root Docker Users** (`agent/Dockerfile`, `dashboard/Dockerfile`, `mcp-server/Dockerfile`) — All containers now run as non-root users (app/nextjs). Dashboard uses `--chown` on COPY for proper file ownership.

- [x] **Fix 6: Rate Limiter Cleanup** (`agent/src/api/routes.py`) — Added `_maybe_cleanup()` to `_RateLimiter` that removes empty key entries every 5 minutes, preventing unbounded `_per_key` dict growth.

## Files Modified

| File | Fixes |
|------|-------|
| `deploy/slurm/slurm_proxy.py` | 1 |
| `agent/src/api/routes.py` | 2, 3, 6 |
| `agent/src/config.py` | 4 |
| `agent/src/main.py` | 4 |
| `mcp-server/src/ouro_mcp/server.py` | 4 |
| `agent/Dockerfile` | 5 |
| `dashboard/Dockerfile` | 5 |
| `mcp-server/Dockerfile` | 5 |

---

# Phase 2: Security Audit Verification

## Status: COMPLETE

## Regression Fix
- [x] **C2 Regression**: Reverted JWT auth from `dashboard/src/app/api/proxy/jobs/route.ts` — route serves `/history` for regular (non-admin) users who don't have JWT cookies

## Build Fix
- [x] **Dockerfile**: Added `package-lock.json` to COPY, changed `npm install` → `npm ci --ignore-scripts` (fixes utf-8-validate native module build failure on arm64 Docker)

## Verification Results

| # | Test | Expected | Result |
|---|------|----------|--------|
| 1 | All services build and start | 3 containers up | PASS |
| 2 | Agent CRITICAL warning for empty ADMIN_API_KEY | Log message present | PASS |
| 3 | Security headers on agent `/health` | nosniff, DENY, HSTS, referrer-policy | PASS |
| 4 | 2MB payload → 413 | HTTP 413 | PASS |
| 5 | Invalid submitter_address → 422 | HTTP 422 + message | PASS |
| 6 | Invalid builder code → 422 | HTTP 422 + message | PASS |
| 7 | Session create | 200 + session object | PASS |
| 8 | Session get | 200 + details | PASS |
| 9 | Session complete (fake job_id) → 400 | HTTP 400 "Referenced job does not exist" | PASS |
| 10 | Dashboard loads | HTTP 200 | PASS |
| 11 | Dashboard CSP + security headers | All present | PASS |
| 12 | Error sanitization (invalid tx hash) | Generic message, no stack trace | PASS |
| 13 | Admin auth dev mode | 200, auth skipped | PASS |
| 14 | Price quote (402) | HTTP 402 | SKIP (x402 testnet/mainnet mismatch — pre-existing) |
