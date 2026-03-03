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

## Verification Checklist

- [ ] `docker compose up --build` — all services start, dashboard loads
- [ ] Submit job via `/submit` — payment flow works
- [ ] Invalid inputs (nodes=99, empty script, nodes="abc") → 422/400 not 500
- [ ] Double session complete → 409
- [ ] CORS blocks unauthorized origins
- [ ] `docker compose exec agent whoami` → `app`
- [ ] `docker compose exec dashboard whoami` → `nextjs`
