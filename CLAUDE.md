# Ouro — Proof-of-Compute Oracle

A self-sustaining autonomous agent on Base that sells HPC compute via x402, posts on-chain proofs with ERC-8021 Builder Codes, registers its identity via ERC-8004, and exposes a public dashboard with real-time P&L.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Railway (PaaS)                             │
│                                                                     │
│  ┌──────────────┐   ┌──────────────────┐   ┌────────────────────┐  │
│  │  Dashboard    │   │  Agent (FastAPI)  │   │  MCP Server        │  │
│  │  Next.js 15   │──▶│  Python 3.12     │◀──│  FastMCP           │  │
│  │  :3000        │   │  :8000           │   │  :8080             │  │
│  └──────────────┘   └────────┬─────────┘   └────────────────────┘  │
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
| **Agent** | Python/FastAPI + PydanticAI | 8000 | Railway | Core backend: x402 payments, job processing, Slurm orchestration, on-chain proofs, autonomous pricing loop |
| **Dashboard** | Next.js 15 App Router + RainbowKit + wagmi | 3000 | Railway | Public UI: wallet balance, P&L, job list, terminal feed, submit page, payment page |
| **MCP Server** | Python/FastMCP | 8080 | Railway | Standalone MCP server for AI agents (Cursor, Claude Desktop) to submit compute jobs |
| **Database** | PostgreSQL 16 | 5432 | Railway | Active jobs, historical data (monthly partitioned), cost ledger, wallet snapshots, attribution log, payment sessions |
| **Slurm Cluster** | Slurm + Apptainer + NFS | 6820 | GCP (us-central1-a) | HPC job execution with container isolation |

### Live URLs

- Dashboard: `https://ourocompute.com`
- Agent API: `https://api.ourocompute.com`
- MCP Server: `https://mcp.ourocompute.com/mcp`

## Project Structure

```
ouro/
├── agent/          # Python FastAPI backend (src/: main, config, agent/, api/, chain/, db/, slurm/)
├── dashboard/      # Next.js 15 App Router (src/: app/, components/, lib/)
├── contracts/      # Foundry Solidity (ProofOfCompute)
├── db/             # SQL schema (01-init.sql) + seed data (02-seed.sql)
├── deploy/         # deploy.sh, setup-slurm-cluster.sh, slurm/ (proxy, configs)
├── mcp-server/     # FastMCP server (run_compute_job, get_job_status, etc.)
├── ouro-sdk/       # Python SDK (OuroClient: run, submit, wait, quote)
├── docs/           # Detailed reference docs (see table below)
└── .mcp/           # MCP Registry manifest
```

Full annotated tree: `docs/architecture.md`

## Key Technologies

- **x402** — HTTP 402 payment protocol; USDC authorization via Coinbase CDP (mainnet) or x402.org (testnet)
- **ERC-8021** — Builder Code attribution in transaction calldata (`agent/src/chain/erc8021.py`)
- **ERC-8004** — On-chain agent identity registry at `0x8004...9432` with reputation feedback
- **PydanticAI** — Typed LLM agent; deterministic fast path in production, LLM fallback for error recovery
- **Slurm** — HPC workload manager via custom REST proxy (`deploy/slurm/slurm_proxy.py`)
- **Apptainer** — Container isolation on Slurm workers; Dockerfiles converted to `.def` files
- **Prebuilt images** — `base`, `python312`, `node20`, `pytorch`, `r-base` (instant); custom Docker Hub images cached by SHA256

## Reference Docs

| Area | Read |
|------|------|
| Full project tree, data flows, DB schema, pricing engine | `docs/architecture.md` |
| API endpoints (agent, Slurm proxy, dashboard proxy) | `docs/api-reference.md` |
| Agent internals, oracle tools, auth, dashboard, MCP, discoverability | `docs/agent-internals.md` |
| Deployment, secrets (Doppler), env vars, testing, common ops | `docs/operations.md` |
| Dashboard UI design, tokens, components | `dashboard/DESIGN.md` |
| MCP tools and payment flows | `mcp-server/README.md` |
| Environment variables (full list with comments) | `.env.example` |
| Full DB schema SQL | `db/01-init.sql` |

## Database Schema

Tables: `active_jobs`, `historical_data`, `agent_costs`, `wallet_snapshots`, `payment_sessions`, `attribution_log`, `credits`, `audit_log`.

Job lifecycle: `pending` → `processing` → `running` → `completed` (archived) or `failed`.

Retry: transient failures with retry_count < 2 reset to `pending`. After max retries, job fails and credit issued.

Recovery on startup: `recover_stuck_jobs()` resets `processing` → `pending`, `running` → `failed`.

Full details: `docs/architecture.md` § Database Schema, `db/01-init.sql`

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
- **Dockerfile COPY/ADD supported** — `COPY` and `ADD` (local only, no URLs) are parsed and validated in the agent, then staged in an isolated temp build context on the proxy. 10 layers of defense-in-depth prevent path traversal. `ARG`, `LABEL`, `SHELL`, `EXPOSE` also supported. `USER`, `VOLUME`, `HEALTHCHECK`, `STOPSIGNAL`, `ONBUILD` are rejected with clear error messages. Glob patterns (`*`, `?`) in COPY sources are not supported.
- **COPY disables image caching** — when `copy_instructions` are present, the proxy skips the cache fast-path since copied files may change between builds.
- **Build time for custom images** doesn't count toward `time_limit_min` — it's infrastructure overhead handled before Slurm submission.
- **Custom image cache** at `/ouro-jobs/images/custom/` has no automatic cleanup yet — images accumulate.

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

- When adding or modifying agent code, write or update corresponding tests in `agent/tests/`
- New features and bug fixes require tests before marking complete
- Run `cd agent && python -m pytest tests/ -v` to verify before committing
