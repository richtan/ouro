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
| **Database** | PostgreSQL 16 | 5432 | Railway | Active jobs, historical data (monthly partitioned), cost ledger, wallet snapshots, attribution log, audit trail |
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
- **Slurm** — HPC workload manager via custom REST proxy (`deploy/slurm/slurm_proxy.py`). See `docs/operations.md` § GCP Slurm Cluster for deployment details
- **Docker** — Container isolation on Slurm workers; hardened `docker run` with `--read-only`, `--network none`, `--cap-drop ALL`, `--user 65534:65534`, etc. Workers use `userns-remap: "default"` and iptables blocking the metadata server
- **Prebuilt images** — `ouro-ubuntu` (ubuntu:22.04), `ouro-python` (python:3.12-slim), `ouro-nodejs` (node:20-slim) mapped to Docker Hub images; custom images built on-worker inside the Slurm job script. `needs_docker_build` distinguishes images needing `docker build` from those needing only `docker pull`

## Reference Docs

| Area | Read |
|------|------|
| Full project tree, data flows, DB schema, pricing engine | `docs/architecture.md` |
| API endpoints (agent, Slurm proxy, dashboard proxy) | `docs/api-reference.md` |
| Agent startup, oracle tools, job processing | `docs/agent-internals.md` |
| Deployment, secrets (Doppler), env vars, testing, common ops | `docs/operations.md` |
| Dashboard UI design, tokens, components | `dashboard/DESIGN.md` |
| MCP tools and payment flows | `mcp/README.md` |
| Environment variables (full list with comments) | `.env.example` |
| Full DB schema SQL | `db/01-init.sql` |

## Database Schema

Tables: `active_jobs`, `historical_data`, `agent_costs`, `wallet_snapshots`, `attribution_log`, `credits`, `audit_log`, `storage_quotas`, `scaling_events`.

Job lifecycle: `pending` → `processing` → `running` → `completed` (archived) or `failed` (archived). Both `complete_job()` and `fail_job()` in `db/operations.py` archive to `historical_data` and delete from `active_jobs`.

Retry: transient failures with retry_count < 2 reset to `pending`. After max retries, job fails and credit issued only for `platform_error` faults.

Recovery on startup: `recover_stuck_jobs()` resets `processing` → `pending`, archives `running` → `failed` via `fail_job()` with `fault="platform_error"` and issues credits.

Fault classification and credit system details: `docs/architecture.md` § Credit System. Auto-migration: `docs/operations.md` § Database Migrations. Full schema SQL: `db/01-init.sql`.

## Persistent Storage

Per-wallet NFS storage mounted at `/storage` inside containers. 1GB free tier, 90-day TTL with 60-day warning. Enable with `mount_storage: true` in submit. MCP tools: `list_storage`, `delete_storage_file`.

Full details (API, security, limitations, infrastructure): `docs/architecture.md` § Persistent Storage.

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

## Development Gotchas

Active gotchas that affect day-to-day code changes. For operational gotchas (Slurm, spot instances, Docker), see `docs/operations.md` § Operational Gotchas. For architectural decisions (credits, storage, Docker security), see `docs/architecture.md`.

- **SLURMREST_URL must be the external IP** of the GCP controller. It changes when instances restart. `deploy/deploy.sh` handles this automatically.
- **Failed jobs must be archived** — `_mark_failed()` and `recover_stuck_jobs()` must call `fail_job()` (which inserts into `historical_data` and deletes from `active_jobs`), not just update status to `"failed"`. Leaving failed rows in `active_jobs` causes the `MAX_ACTIVE_JOBS_PER_WALLET` check in `routes.py` to block new submissions with 429.
- **Concurrent submission race** — `MAX_ACTIVE_JOBS_PER_WALLET` check uses `pg_advisory_xact_lock` (per-wallet advisory lock) to serialize count-check + insert. `FOR UPDATE` cannot be used with aggregate functions like `count()`.
- **Credit redemption deferred** — `redeem_credits()` runs after x402 payment verification, not before, to prevent credit loss on the 402 round-trip. Does not commit — caller commits atomically with job creation.
- **Partial credit splits rows** — `redeem_credits()` splits oversized credit rows (creates a "change" row for unused portion) to prevent silent credit loss. `price_usdc` on the job record reflects the full price (for P&L), not the x402-charged amount.
- **x402 facilitator minimum ($0.001)** — The facilitator rejects payments below $0.001 USDC. When partial credit reduces the remainder below this threshold, the job is treated as fully credit-covered. Constant: `X402_FACILITATOR_MIN_USD` in `routes.py`. Dashboard mirrors in `StickySubmitBar.tsx`.
- **External Docker images require ENTRYPOINT/CMD** — When using non-prebuilt images (e.g., `ruby:latest`), the Dockerfile must include `ENTRYPOINT` or `CMD`. The proxy's extension-based executor map only covers prebuilt aliases. `parse_dockerfile()` enforces this.
- **MCP version must be checked against npm** — Before bumping the MCP version, run `npm view ouro-mcp version` to find the latest published version. The new version must be higher than what's on npm. All 3 version locations must match: `mcp/package.json`, `mcp/src/index.ts` (McpServer constructor), `.mcp/server.json`. See `mcp/CLAUDE.md` for the full publishing checklist.

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
  - Development gotchas (affect code changes) → `CLAUDE.md` § Development Gotchas
  - Operational gotchas (Slurm, infra, deploy) → `docs/operations.md` § Operational Gotchas
  - Architectural decisions (credits, storage, security) → `docs/architecture.md`
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
