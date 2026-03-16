# Ouro

A self-sustaining autonomous agent on Base that sells HPC compute via x402, uses ERC-8021 Builder Codes for attribution, registers its identity via ERC-8004, and exposes a public dashboard with real-time P&L.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Railway (PaaS)                             │
│                                                                     │
│  ┌──────────────┐   ┌──────────────────┐                            │
│  │  Dashboard    │   │  Agent (FastAPI)  │                            │
│  │  Next.js 15   │──▶│  Python 3.12     │                            │
│  │  :3000        │   │  :8000           │                            │
│  └──────────────┘   └────────┬─────────┘                            │
│                              │                                      │
│                    ┌─────────▼──────────┐                          │
│                    │  PostgreSQL 16      │                          │
│                    │  (Railway managed)  │                          │
│                    └────────────────────┘                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP (slurmrestd proxy)
                    ┌──────────▼──────────┐
                    │  GCP Compute Engine  │
                    │  Slurm HPC Cluster   │
                    │  ouro-slurm (ctrl)   │
                    │  ouro-worker-{1,2}   │
                    └─────────────────────┘
```

### Services

| Service | Tech | Port | Location | Purpose |
|---------|------|------|----------|---------|
| **Agent** | Python/FastAPI + PydanticAI | 8000 | Railway | Core backend: x402 payments, job processing, Slurm orchestration, autonomous pricing loop, webhook delivery |
| **Dashboard** | Next.js 15 App Router + RainbowKit + wagmi | 3000 | Railway | Public UI: wallet balance, P&L, job list, terminal feed, submit page, payment page |
| **MCP Server** | Node.js / @modelcontextprotocol/sdk | stdio | Local (npx) | Local MCP server for AI agents — signs x402 payments from user's wallet, SSE streaming for job status. Tools: run_job, get_job_status, get_price_quote, get_allowed_images, list_storage, delete_storage_file |
| **Database** | PostgreSQL 16 | 5432 | Railway | Active jobs, historical data (monthly partitioned), cost ledger, wallet snapshots, attribution log, payment sessions |
| **Slurm Cluster** | Slurm + Docker + NFS | 6820 | GCP (us-central1-a) | HPC job execution with container isolation |

### Live URLs

- Dashboard: `https://ourocompute.com`
- Agent API: `https://api.ourocompute.com`

## Project Structure

```
ouro/
├── agent/          # Python FastAPI backend (src/: main, config, agent/, api/, chain/, db/, slurm/)
├── dashboard/      # Next.js 15 App Router (src/: app/, components/, lib/)
├── contracts/      # Foundry Solidity (reserved for future contracts)
├── db/             # SQL schema (01-init.sql) + seed data (02-seed.sql)
├── deploy/         # deploy.sh, setup-slurm-cluster.sh, slurm/ (proxy, configs)
├── mcp/            # Local Node.js MCP server (npx ouro-mcp) — run_job, get_job_status, get_price_quote, get_allowed_images, list_storage, delete_storage_file
├── docs/           # Detailed reference docs (see table below)
└── .mcp/           # MCP Registry manifest
```

Full annotated tree: `docs/architecture.md`

## Key Technologies

- **x402** — HTTP 402 payment protocol; USDC authorization via Coinbase CDP (mainnet) or x402.org (testnet)
- **ERC-8021** — Builder Code attribution in transaction calldata (`agent/src/chain/erc8021.py`)
- **ERC-8004** — On-chain agent identity registry at `0x8004...9432`
- **PydanticAI** — Typed LLM agent; deterministic fast path in production, LLM fallback for error recovery
- **Slurm** — HPC workload manager via custom REST proxy (`deploy/slurm/slurm_proxy.py`). Deployed on `ouro-slurm` at `/opt/slurmrest/slurm_proxy.py`, runs via systemd `slurm-proxy` service using venv at `/opt/slurmrest/bin/python3`. See `docs/operations.md` § GCP Slurm Cluster for redeploy steps
- **Docker** — Container isolation on Slurm workers; hardened `docker run` with `--read-only`, `--network none`, `--cap-drop ALL`, `--user 65534:65534`, etc. Workers use `userns-remap: "default"` and iptables blocking the metadata server
- **Prebuilt images** — `ouro-ubuntu` (ubuntu:22.04), `ouro-python` (python:3.12-slim), `ouro-nodejs` (node:20-slim) mapped to Docker Hub images; custom images built on-worker inside the Slurm job script. `needs_docker_build` distinguishes images needing `docker build` from those needing only `docker pull`

## Reference Docs

| Area | Read |
|------|------|
| Full project tree, data flows, DB schema, pricing engine | `docs/architecture.md` |
| API endpoints (agent, Slurm proxy, dashboard proxy) | `docs/api-reference.md` |
| Agent internals, oracle tools, auth, dashboard, MCP, discoverability | `docs/agent-internals.md` |
| Deployment, secrets (Doppler), env vars, testing, common ops | `docs/operations.md` |
| Dashboard UI design, tokens, components | `dashboard/DESIGN.md` |
| MCP tools and payment flows | `mcp/README.md` |
| Environment variables (full list with comments) | `.env.example` |
| Full DB schema SQL | `db/01-init.sql` |

## Database Schema

Tables: `active_jobs`, `historical_data`, `agent_costs`, `wallet_snapshots`, `attribution_log`, `credits`, `audit_log`, `storage_quotas`.

Job lifecycle: `pending` → `processing` → `running` → `completed` (archived) or `failed` (archived).

Retry: transient failures with retry_count < 2 reset to `pending`. After max retries, job fails and credit issued only for `platform_error` faults.

Recovery on startup: `recover_stuck_jobs()` resets `processing` → `pending`, archives `running` → `failed` via `fail_job()` with `fault="platform_error"` and issues credits.

Fault classification: `agent/src/agent/classifier.py` classifies failures as `platform_error` (credit issued) or `user_error` (no credit). Classification is by Slurm state (unforgeable from inside Docker), not exit codes. Stage 1 validation errors = `user_error`, stage 1 capacity failures = `platform_error`, stage 2 = `platform_error`, stage 3 FAILED/TIMEOUT = `user_error`, CANCELLED/NODE_FAIL = `platform_error`.

Credit redemption: If a wallet has credits >= job price, x402 payment is skipped entirely and credits are redeemed. Implemented in `submit_compute`. `redeem_credits()` uses `SELECT ... FOR UPDATE` to prevent double-spend race conditions.

Both `complete_job()` and `fail_job()` in `db/operations.py` archive to `historical_data` and delete from `active_jobs`.

Auto-migration: `agent/src/db/migrate.py` runs on every agent startup — handles `ADD/DROP COLUMN IF [NOT] EXISTS` and idempotent data migrations. No manual SQL needed for schema changes. See `docs/operations.md` § Database migrations.

Full details: `docs/architecture.md` § Database Schema, `db/01-init.sql`

## Persistent Storage

Per-wallet persistent storage mounted at `/storage` inside containers. NFS-backed on `/ouro-storage` on the Slurm controller, exported to all workers.

- **Config**: `STORAGE_FREE_TIER_BYTES` (default 1GB), `STORAGE_TTL_DAYS` (default 90 days)
- **DB table**: `storage_quotas` — tracks wallet tier, quota, cached usage, last access time
- **API**: `GET /api/storage?wallet=0x...` (usage + file list), `DELETE /api/storage/files?wallet=...&path=...&signature=...&timestamp=...` (EIP-191 signed delete)
- **Submit**: `mount_storage: true` in `POST /api/compute/submit` creates quota on first use, validates quota, inits NFS directory, passes `storage_path` through to Slurm proxy
- **MCP tools**: `list_storage`, `delete_storage_file`, `mount_storage` param on `run_job`
- **Dashboard**: `/storage` page (quota bar, file list, signed delete), toggle in submit Advanced section
- **Proxy endpoints**: `POST /slurm/v0.0.38/storage/init`, `GET .../storage/{wallet}/usage`, `GET .../storage/{wallet}/files`, `DELETE .../storage/{wallet}/files/{path}`, `DELETE .../storage/{wallet}`
- **Docker mount**: `-v /ouro-storage/0x...:/storage` added to both Dockerfile-build and simple-pull paths in `wrap_in_docker()`
- **TTL cleanup**: `_storage_cleanup()` in `loop.py` runs daily, warns at 60 days inactive, deletes at 90 days
- **Security**: Path traversal prevention via `os.path.realpath()` + prefix check. Symlinks skipped in file listing. `shlex.quote()` + regex validation on storage paths. EIP-191 signature required for file deletion. No `noexec` on bind mount (Docker `--cap-drop ALL` + `--no-new-privileges` prevent escalation). `followlinks=False` in `os.walk()`.
- **Infrastructure**: `setup-slurm-cluster.sh` and `setup-elastic-infra.sh` create and export `/ouro-storage`. `node-startup.sh` mounts it on spot instances.

## Local Development

```bash
# Option A: With Doppler (recommended)
doppler login && doppler setup   # First time only
doppler run -- docker compose up --build

# If port 3000 is in use:
DASHBOARD_PORT=3001 doppler run -- docker compose up --build

# Option B: Without Doppler (fallback)
cp .env.example .env
# Fill in keys (WALLET_PRIVATE_KEY, OPENAI_API_KEY, etc.)
docker compose up --build
```

- Dashboard: http://localhost:3000 (or 3001 if overridden)
- Agent API: http://localhost:8000
- Postgres: localhost:5432

## Known Issues & Lessons

- **SLURMREST_URL must be the external IP** of the GCP controller. It changes when instances restart. `deploy/deploy.sh` handles this automatically.
- **Payment sessions were previously in-memory** in the MCP server, causing "Session Not Found" errors after restarts. Now stored in PostgreSQL via the agent API.
- **Slurm nodes drain** if `slurm.conf` specifies more CPUs/memory than the actual hardware. The setup script's Phase 12 handles undraining, and `slurm.conf` must match the instance specs.
- **Wallet disconnects on reload** were caused by using localStorage with SSR. Fixed by using `cookieStorage` + `cookieToInitialState` hydration in the layout.
- **Jobs stuck in "processing"** after agent restart are recovered by `recover_stuck_jobs()` on startup.
- **Oracle agent timeout**: Wrapped in `asyncio.wait_for(..., timeout=900)` to prevent infinite hangs.
- **Slurm poll errors**: `poll_slurm_status` wraps `get_job_status()` in try/except so transient network errors don't crash the run.
- **Dashboard Docker build needs native toolchain**: `dashboard/Dockerfile` installs `python3 make g++` via `apk add` in the deps stage to compile native npm dependencies (bufferutil, etc.).
- **Dockerfile COPY/ADD supported** — `COPY` and `ADD` (local only, no URLs) are parsed and validated in the agent. `ARG`, `LABEL`, `SHELL`, `EXPOSE` also supported. `USER`, `VOLUME`, `HEALTHCHECK`, `STOPSIGNAL`, `ONBUILD` are rejected with clear error messages. Glob patterns (`*`, `?`) in COPY sources are not supported.
- **Docker build happens on-worker** — builds run inside the Slurm job script on the worker node, not as a separate async step. The proxy generates Docker wrapper scripts; it no longer has image build endpoints.
- **DOCKER_BUILDKIT=0** — BuildKit is disabled on workers for security. This means `RUN --mount=...` and `# syntax=` directives are rejected at Dockerfile parse time.
- **Multi-stage builds rejected** — Dockerfiles with multiple `FROM` instructions are rejected to prevent build-time escapes.
- **Worker Docker hardening** — Workers run with `userns-remap: "default"` in Docker daemon config and iptables rules blocking the GCP metadata server (169.254.169.254) to prevent credential theft.
- **Build time for custom images** is included in the Slurm job's `time_limit_min` since builds happen on-worker.
- **Custom image cache** — Two-layer cleanup: (1) per-job `docker rmi` in `slurm_proxy.py` removes non-prebuilt images after each job, (2) `deploy/slurm/docker-cleanup.sh` runs every 6h via cron to prune missed images, with aggressive cleanup at >85% disk usage. Prebuilt images (`ubuntu:22.04`, `python:3.12-slim`, `node:20-slim`) are re-pulled after aggressive prunes.
- **Failed jobs must be archived** — `_mark_failed()` and `recover_stuck_jobs()` must call `fail_job()` (which inserts into `historical_data` and deletes from `active_jobs`), not just update status to `"failed"`. Leaving failed rows in `active_jobs` causes the `MAX_ACTIVE_JOBS_PER_WALLET` check in `routes.py` to block new submissions with 429.
- **External Docker images require ENTRYPOINT/CMD** — When using non-prebuilt images (e.g., `ruby:latest`), the Dockerfile must include `ENTRYPOINT` or `CMD`. The proxy's extension-based executor map only covers prebuilt aliases; for external images, the user must specify the interpreter. `parse_dockerfile()` enforces this even when `require_entrypoint=False`.
- **Spot node boot too slow** — `node-startup.sh` previously blocked on `docker pull` (3 images) before registering IDLE with Slurm, causing multi-CPU jobs to timeout. Fix: (1) bake base images into the golden image (`build-golden-image.sh`), (2) reorder `node-startup.sh` to register IDLE first and run iptables/pulls in background, (3) oracle polling timeout set to 120s (`oracle.py:_ensure_capacity`, `range(12)`), (4) `ResumeTimeout=180` in `slurm.conf`.
- **Autoscaler 409 "already exists" race** — Two independent `AutoScaler` instances (in `oracle.py` and `loop.py`) have separate `_booting` dicts. If both try to boot the same node, GCP returns 409. `_boot_spot_instance()` in `scaler.py` treats "already exists" errors as successful `scale_out` events so the caller proceeds to poll for the node becoming IDLE.
- **NFS exports block spot instances** — `/etc/exports` on `ouro-slurm` originally listed only the two permanent worker IPs. Spot instances get dynamic IPs not in the allow list, so `mount` fails, `set -euo pipefail` kills `node-startup.sh`, and the node never registers IDLE. Fix: use subnet-based export `/ouro-jobs 10.128.0.0/20(rw,sync,no_subtree_check,root_squash)` covering the full GCP us-central1 VPC subnet. `deploy/setup-elastic-infra.sh:92-94` has this fix; ensure `setup-slurm-cluster.sh` doesn't overwrite it.
- **Docker Hub image pre-validation** — External (non-prebuilt) images are validated against Docker Hub's tag API at submission time (`validate_docker_image()` in `dockerfile.py`). Returns 422 if image/tag not found. Fails open on timeout/5xx/429 to avoid blocking submissions during Docker Hub outages. Digest references (`@sha256:...`) and non-Docker-Hub registries (`ghcr.io/...`) skip validation. Prebuilt aliases skip validation. Validation runs before payment in `/api/compute/submit`.
- **Fault-based credit system** — Credits only issued for `platform_error` faults, not `user_error`. Classification in `agent/src/agent/classifier.py` uses Slurm state (unforgeable from Docker with `--network none --cap-drop ALL`), not exit codes. Prevents free compute via intentional `exit 1`. Credit redemption integrated in the submit endpoint — wallets with credits >= job price skip x402 entirely. `redeem_credits()` uses `FOR UPDATE` to prevent double-spend races.
- **Partial credit redemption** — Credits are applied proportionally. If credit < job price, credit is redeemed and x402 charges only the remainder. `redeem_credits()` splits overshooting credit rows (creates a "change" row for the unused portion) to prevent silent credit loss. `price_usdc` on the job record reflects the full price (for P&L), not the x402-charged amount. Credit redemption is **deferred** until after x402 payment verification to prevent credit loss on the 402 round-trip. `redeem_credits()` does not commit — caller commits atomically with job creation.
- **Poll timeout scaled to time_limit** — `poll_slurm_status_impl` now scales poll count to `max(60, time_limit_min * 60 / 5 + 12)` instead of fixed 60 polls. Jobs longer than 5 min no longer hit false poll timeouts. On poll timeout, the Slurm job is cancelled to prevent free compute.
- **Concurrent submission race** — `MAX_ACTIVE_JOBS_PER_WALLET` check uses `pg_advisory_xact_lock` (per-wallet advisory lock) to serialize count-check + insert. `FOR UPDATE` cannot be used with aggregate functions like `count()`.
- **x402 facilitator minimum ($0.001)** — The facilitator rejects payments below $0.001 USDC. When partial credit reduces the remainder below this threshold, the job is treated as fully credit-covered (sub-$0.001 shortfall waived). Constant: `X402_FACILITATOR_MIN_USD` in `routes.py`. Dashboard threshold mirrors this in `StickySubmitBar.tsx`.
- **Unused compute credits** — Jobs that finish early get proportional credits for unused compute time. Credit is based on the marked-up price (not raw cost), calculated via `calculate_unused_compute_credit()` in `pricing.py`. `cost_floor` and `compute_cost` are stored in the job payload at submission so the credit calculation uses submission-time values. Credits below $0.001 are filtered out. Only applies to jobs with `cost_floor` in payload (new jobs); legacy jobs are skipped gracefully.
- **Compute cost tracking in P&L** — `_finalize_success()` and `_mark_failed()` in `processor.py` log actual compute infrastructure costs via `log_cost(cost_type="compute")`. These are included in `/api/stats` as `compute_costs_usd` and automatically factor into the sustainability ratio (which sums all `agent_costs`), enabling accurate phase transitions.
- **Webhook notifications** — Jobs accept an optional `webhook_url` parameter at submission. On completion or failure, a POST is sent with job results. HMAC-SHA256 signing via `WEBHOOK_SECRET` env var (optional, set in Doppler). 3 delivery attempts with exponential backoff. HTTPS required (HTTP allowed only for localhost). See `docs/api-reference.md` § Webhooks.
- **MCP SSE streaming** — `get_job_status` in the MCP server now uses SSE streaming (`/api/jobs/{id}/stream`) instead of manual polling. Call once and it returns when the job reaches a terminal state. Eliminates the need for repeated poll calls from AI agents.
- **Persistent storage quota bypass during job execution** — No kernel quotas on NFS bind mounts. Containers can write beyond the 1GB limit during a job. Post-job sync catches overages and blocks new jobs with `mount_storage=true` until usage is under quota.
- **Storage concurrent writes** — Two jobs from the same wallet with `mount_storage=true` can write to `/storage` concurrently. NFS provides POSIX semantics but file conflicts are "last writer wins". User responsibility.
- **Storage TTL cleanup race** — `_storage_cleanup()` uses `SELECT ... FOR UPDATE` to re-check `last_accessed_at` under row lock before deletion, preventing races with concurrent `submit_compute` calls that update `last_accessed_at`.
- **Storage DELETE requires EIP-191 signature** — `DELETE /api/storage/files` requires a signed message `"ouro-storage-delete:{wallet}:{path}:{timestamp}"` with a 5-minute timestamp window. Prevents unauthorized deletion. MCP server signs automatically; dashboard uses wagmi `useSignMessage`.
- **MCP version must be checked against npm** — Before bumping the MCP version, run `npm view ouro-mcp version` (or check https://www.npmjs.com/package/ouro-mcp) to find the latest published version. The new version must be higher than what's on npm. All 3 version locations must match: `mcp/package.json`, `mcp/src/index.ts` (McpServer constructor), `.mcp/server.json`. See `mcp/CLAUDE.md` for the full publishing checklist.

## Workflow Preferences

- Plan first for non-trivial tasks (3+ steps or architectural decisions)
- Use subagents for research and parallel exploration
- Verify changes work before marking complete
- Keep changes minimal and focused
- Find root causes, no temporary fixes
- Before making any dashboard changes, read `dashboard/DESIGN.md` first to align with the overall theme, design tokens, and visual patterns

### Continuous Documentation
- **After every change** to code, environment, infrastructure, or configuration: update `CLAUDE.md` and/or the relevant `docs/` file
  - Code/architecture changes → update `CLAUDE.md` sections (Architecture, Project Structure, Key Technologies, etc.) and `docs/architecture.md`
  - API changes → `docs/api-reference.md`
  - Deploy/infra/env changes → `docs/operations.md`
  - Agent behavior changes → `docs/agent-internals.md`
  - Dashboard changes → `dashboard/DESIGN.md`
  - New bugs found or resolved → add to `Known Issues & Lessons` in `CLAUDE.md`
- **Findings and discoveries** (debug insights, gotchas, non-obvious behavior) go in `Known Issues & Lessons`
- **Keep `CLAUDE.md` as the index** — it should reference `docs/` files so readers can drill down. Never bury information only in a `docs/` file without a pointer from `CLAUDE.md`
- **Be specific**: include file paths, function names, and error messages so future readers can find the right context fast

### Secrets & Credentials
- **NEVER** put secrets, API keys, private keys, or credentials in `CLAUDE.md`, `docs/`, or any file that is not gitignored
- Secrets live in Doppler (production) or `.env` (local, gitignored). Reference them by variable name only (e.g., "set `OPENAI_API_KEY` in Doppler"), never by value
- If you encounter a secret in tracked files, remove it immediately and rotate the key
- **Before every commit**: scan all staged changes for secrets, API keys, tokens, private keys, passwords, or anything that should not be in a public repo. If anything suspicious is found, **stop and ask the user** before committing — never silently commit secrets

- When adding or modifying agent code, write or update corresponding tests in `agent/tests/`
- New features and bug fixes require tests before marking complete
- Run `cd agent && python -m pytest tests/ -v` to verify before committing
