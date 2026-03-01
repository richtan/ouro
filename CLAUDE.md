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
├── agent/                  # Python FastAPI backend
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/
│       ├── main.py         # FastAPI app, lifespan, x402 init
│       ├── config.py       # pydantic-settings (all env vars)
│       ├── agent/
│       │   ├── oracle.py   # PydanticAI agent + _impl functions + process_job_fast (deterministic fast path)
│       │   ├── processor.py # Background job loop with fast path, retry logic, credit issuance
│       │   ├── loop.py     # Autonomous monitoring loop (wallet, pricing, heartbeat)
│       │   └── event_bus.py # Pub/sub for SSE events
│       ├── api/
│       │   ├── routes.py   # All HTTP endpoints (compute, jobs, stats, sessions, etc.)
│       │   └── pricing.py  # Dynamic pricing engine (4-phase survival, demand elasticity)
│       ├── chain/
│       │   ├── client.py   # Web3 client (proofs, heartbeat, balances)
│       │   ├── erc8021.py  # Builder Code suffix encoder/decoder
│       │   ├── erc8004.py  # Agent identity registration
│       │   └── abi.py      # Minimal ABI definitions
│       ├── db/
│       │   ├── models.py   # SQLAlchemy models (ActiveJob, HistoricalData, Credit, AuditLog, etc.)
│       │   ├── operations.py # complete_job, log_cost, log_attribution, issue_credit, log_audit
│       │   └── session.py  # Async engine + session maker
│       └── slurm/
│           └── client.py   # HTTP client for Slurm REST proxy
├── dashboard/              # Next.js App Router frontend
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── app/
│       │   ├── layout.tsx      # Root layout (Web3Provider with cookie hydration)
│       │   ├── page.tsx        # Public dashboard (aggregate stats only)
│       │   ├── admin/page.tsx  # Admin page (wallet-gated, signature auth, JWT cookie)
│       │   ├── submit/page.tsx # Job submission page
│       │   ├── history/page.tsx # User job history (wallet-scoped)
│       │   ├── pay/[sessionId]/page.tsx # MCP payment page
│       │   └── api/
│       │       ├── admin/login/route.ts    # Verify wallet signature, set JWT cookie
│       │       ├── admin/logout/route.ts   # Clear JWT cookie
│       │       ├── admin/check/route.ts    # Verify JWT cookie validity
│       │       ├── audit/route.ts          # Proxies to agent /api/audit (JWT-gated)
│       │       ├── proxy/submit/route.ts   # Proxies to agent /api/compute/submit
│       │       ├── proxy/jobs/route.ts     # Proxies to agent /api/jobs/user (admin key, no JWT)
│       │       ├── proxy/sessions/[sessionId]/route.ts          # GET session
│       │       ├── proxy/sessions/[sessionId]/complete/route.ts # POST complete
│       │       ├── jobs/route.ts       # Proxies to agent /api/jobs (JWT-gated)
│       │       ├── stats/route.ts      # Proxies to agent /api/stats (public)
│       │       ├── wallet/route.ts     # Proxies to agent /api/wallet (public)
│       │       ├── attribution/route.ts
│       │       └── stream/route.ts     # SSE proxy (JWT-gated)
│       ├── components/
│       │   ├── Web3Provider.tsx    # wagmi/RainbowKit config (cookieStorage for persistence)
│       │   ├── NavBar.tsx          # Conditional "Admin" link for operator wallet
│       │   ├── JobsPanel.tsx       # All jobs table (admin-only, sorted by time desc)
│       │   ├── PublicJobStats.tsx   # Aggregate job stats (public dashboard)
│       │   ├── AuditPanel.tsx      # Audit log table (admin-only)
│       │   ├── WalletBalance.tsx
│       │   ├── FinancialPnL.tsx
│       │   ├── SustainabilityGauge.tsx
│       │   ├── RevenueModel.tsx
│       │   ├── TerminalFeed.tsx    # SSE event stream (admin-only)
│       │   ├── AttributionPanel.tsx
│       │   ├── ClusterStatus.tsx
│       │   └── OutputDisplay.tsx
│       └── lib/
│           ├── api.ts          # Client-side fetch helpers
│           └── admin-auth.ts   # JWT sign/verify helpers, cookie name constant
├── contracts/              # Foundry Solidity project
│   ├── foundry.toml
│   ├── src/ProofOfCompute.sol
│   ├── script/Deploy.s.sol
│   └── test/ProofOfCompute.t.sol
├── db/
│   ├── 01-init.sql         # Full schema (tables, indexes, partitions)
│   └── 02-seed.sql
├── deploy/
│   ├── deploy.sh            # Deploys all services (or specific ones) to Railway in parallel
│   ├── setup-slurm-cluster.sh # Full GCP cluster provisioning (13 phases)
│   └── slurm/
│       ├── slurm.conf      # Slurm config (e2-small controller, e2-medium workers)
│       ├── cgroup.conf
│       └── slurm_proxy.py  # FastAPI proxy wrapping sbatch with Apptainer isolation
├── mcp-server/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/ouro_mcp/server.py  # MCP tools: run_compute_job, get_job_status, get_price_quote, get_api_endpoint
├── ouro-sdk/               # Python SDK for programmatic access
│   ├── pyproject.toml
│   └── src/ouro_sdk/
│       ├── client.py       # OuroClient: run, submit, wait, quote, capabilities
│       └── models.py       # JobResult, Quote dataclasses
├── docker-compose.yml      # Local dev: postgres + agent + dashboard
├── .env.example
└── .gitignore
```

## Key Technologies

- **x402** — HTTP 402 payment protocol. Agent returns 402 with PAYMENT-REQUIRED header; client signs USDC authorization. Facilitated by Coinbase CDP on mainnet, x402.org on testnet.
- **ERC-8021** — Builder Code attribution appended to every on-chain transaction calldata. Format: `codesJoined + length(1 byte) + schemaId(0x00) + marker(16 bytes)`. See `agent/src/chain/erc8021.py`.
- **ERC-8004** — On-chain agent identity registry at `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`. Agent registers itself on startup.
- **PydanticAI** — Typed LLM agent with tools. The oracle agent has 4 tools: validate_request, submit_to_slurm, poll_slurm_status, submit_onchain_proof. In production, the deterministic fast path (`process_job_fast`) executes these directly without the LLM; the LLM agent is a fallback for complex error recovery.
- **Slurm** — HPC workload manager. Jobs are submitted via a custom REST proxy (`slurm_proxy.py`) that wraps sbatch with Apptainer container isolation.
- **Apptainer** — Container isolation for user scripts on Slurm workers. Base image is ubuntu:22.04 stored at `/ouro-jobs/images/base.sif`.

## Data Flow

### Job Submission (via Dashboard)
1. User writes script on `/submit`, connects wallet via RainbowKit
2. Dashboard sends POST to `/api/proxy/submit` with x402 payment signature
3. Proxy forwards to agent's `POST /api/compute/submit`
4. Agent verifies x402 payment via CDP facilitator
5. Job created in `active_jobs` table with status `pending`
6. Background processor picks it up, runs oracle agent (validate → submit to Slurm → poll → proof)
7. On completion, job moved to `historical_data`, proof posted on-chain

### Job Submission (via MCP)
1. AI agent calls `run_compute_job` MCP tool
2. MCP server creates payment session via `POST {AGENT_URL}/api/sessions`
3. Returns payment URL: `https://dashboard.../pay/{sessionId}`
4. User opens link, connects wallet, pays (same x402 flow as above)
5. Pay page marks session complete via `POST /api/proxy/sessions/{id}/complete`
6. AI agent polls with `get_job_status(session_id)` to get results

### Payment Sessions
Sessions are stored in PostgreSQL (not in-memory) so they survive MCP server restarts and work across replicas. The MCP server creates/reads sessions via the agent API.

## Database Schema

See `db/01-init.sql` for full schema. Key tables:

- **active_jobs** — Jobs currently in the pipeline (pending → processing → running → completed/failed). Includes `retry_count` for automatic retry on transient failures (max 2).
- **historical_data** — Completed jobs archive (partitioned by month via `completed_at`)
- **agent_costs** — Cost ledger (gas, llm_inference entries)
- **wallet_snapshots** — Periodic ETH/USDC balance records
- **payment_sessions** — MCP payment flow sessions (pending → paid, TTL 10min)
- **attribution_log** — ERC-8021 builder code records per transaction
- **credits** — USDC credits issued to wallets when jobs fail after payment (auto-redeemable)
- **audit_log** — Structured audit trail for all financial events (payment_received, job_completed, credit_issued, errors)

Job status lifecycle: `pending` → `processing` → `running` → `completed` (moved to historical) or `failed`.

On transient failure, jobs with retry_count < 2 are reset to `pending` for automatic retry. After max retries (or permanent failure), the job is marked `failed` and a credit equal to the payment amount is issued to the submitter's wallet.

On startup, the processor runs `recover_stuck_jobs()`: resets `processing` → `pending` and `running` → `failed`.

## Pricing Engine

Dynamic pricing with 4 survival phases based on sustainability ratio (revenue/costs over 24h):

| Phase | Ratio Threshold | Margin Factor | Heartbeat |
|-------|----------------|---------------|-----------|
| OPTIMAL | ≥ 1.5 | 1.0x | 60 min |
| CAUTIOUS | ≥ 1.0 | 1.1x | 120 min |
| SURVIVAL | ≥ 0.5 | 1.3x | Off |
| CRITICAL | < 0.5 | 3.0x | Off |

Price formula: `max(cost_floor × margin × demand_multiplier, cost_floor × 1.2, $0.01)`

Cost floor = `max_gas × 1.25 + max_llm × 1.25 + nodes × minutes × $0.0006/node-min`

Builder code holders get 10% discount (but never below cost floor).

## Secrets Management (Doppler)

Secrets are managed via [Doppler](https://doppler.com) as the single source of truth. Doppler project: `ouro`, configs: `dev` (local), `prd` (production, shared across all Railway services).

- **Local dev (hot reload)**: `doppler run -- docker compose up --build` (or fall back to `.env` file). Uses `docker-compose.override.yml` automatically — runs `next dev` with volume-mounted source for instant Fast Refresh, and uvicorn `--reload` for the agent.
- **Local dev (production build)**: `doppler run -- docker compose -f docker-compose.yml up --build` (explicitly skips the override file)
- **Port override**: `DASHBOARD_PORT=3001 doppler run -- docker compose up --build` (if 3000 is in use)
- **Production**: Doppler → Railway integration auto-syncs `prd` config to all three services
- **`SLURMREST_URL`** and **`PORT`** are NOT in Doppler — `SLURMREST_URL` is dynamically fetched from GCP by `deploy.sh`; `PORT` is set per-service in Railway

Config file: `doppler.yaml` at repo root (sets default project/config for CLI).

## Environment Variables

### Agent (Railway service: `agent`)
```
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
BASE_RPC_URL=https://mainnet.base.org
CHAIN_ID=8453
CHAIN_CAIP2=eip155:8453
WALLET_PRIVATE_KEY, WALLET_ADDRESS
PROOF_CONTRACT_ADDRESS
USDC_CONTRACT_ADDRESS=0x...
BUILDER_CODE=ouro
SLURMREST_URL        # Set automatically by deploy/deploy.sh
SLURMREST_JWT
LLM_MODEL=openai:gpt-4o-mini
OPENAI_API_KEY
CDP_API_KEY_ID, CDP_API_KEY_SECRET
X402_FACILITATOR_URL=https://x402.org/facilitator
PRICE_MARGIN_MULTIPLIER=1.5
PUBLIC_API_URL, PUBLIC_DASHBOARD_URL
ADMIN_API_KEY                    # Shared secret for admin endpoint access (empty = skip in dev)
PORT=8000                        # Per-service in Railway, not in Doppler
```

### Dashboard (Railway service: `dashboard`)
```
AGENT_URL=http://agent.railway.internal:8000   # Internal Railway networking
NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID            # For RainbowKit
ADMIN_API_KEY                    # Same value as agent (server-side only, never reaches browser)
NEXT_PUBLIC_ADMIN_ADDRESS        # Operator wallet address for admin UI gating
PORT=3000                        # Per-service in Railway, not in Doppler
```

### MCP Server (Railway service: `mcp-server`)
```
OURO_API_URL=https://api.ourocompute.com  # Public agent URL
DASHBOARD_URL=https://ourocompute.com
PORT=8080                        # Per-service in Railway, not in Doppler
```

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

## Deployment

### Railway (Agent, Dashboard, MCP Server)

All three services deploy to Railway as separate services in a single project. Each has its own Dockerfile.

```bash
# Deploy all services (fetches Slurm IP from GCP, deploys in parallel)
./deploy/deploy.sh

# Deploy specific services only
./deploy/deploy.sh agent mcp
```

Check logs:
```bash
railway logs -s agent
railway logs --build --latest -s agent -n 100
```

### GCP Slurm Cluster

```bash
./deploy/setup-slurm-cluster.sh
```

This script:
1. Creates worker VMs (e2-medium) if they don't exist
2. Distributes /etc/hosts, munge keys, JWT keys
3. Sets up NFS shared filesystem at /ouro-jobs
4. Installs Slurm + Apptainer on all nodes
5. Deploys slurm_proxy.py on the controller
6. Clears stale Slurm state and undrains nodes
7. Verifies with test job and Apptainer test

GCP instances: `ouro-slurm` (e2-small controller), `ouro-worker-1`, `ouro-worker-2` (e2-medium).

The Slurm proxy (`slurm_proxy.py`) runs on the controller at port 6820 as a systemd service (`slurm-proxy`). It wraps sbatch calls with Apptainer container isolation.

### Smart Contracts

```bash
cd contracts
forge build
forge create src/ProofOfCompute.sol:ProofOfCompute \
  --rpc-url https://mainnet.base.org \
  --private-key $WALLET_PRIVATE_KEY
```

Set the resulting address as `PROOF_CONTRACT_ADDRESS`.

## Agent Internals

### Background Tasks (started in lifespan)

1. **autonomous_loop** (`agent/loop.py`) — Runs every 60s:
   - Snapshots wallet balances
   - Computes sustainability ratio and adjusts pricing phase
   - Updates demand multiplier based on jobs/hour
   - Checks Slurm cluster health
   - Sends on-chain heartbeat (if phase allows)
   - ERC-8004 agent discovery scan (every 10 cycles)

2. **process_pending_jobs** (`agent/processor.py`) — Continuous loop:
   - Picks up `pending` jobs with `SELECT ... FOR UPDATE SKIP LOCKED`
   - Sets status to `processing`
   - Runs PydanticAI oracle agent with 15-minute timeout
   - On success: moves job to `historical_data`, logs costs, verifies profitability
   - On failure/timeout: marks job as `failed`
   - On startup: recovers stuck jobs (`processing` → `pending`, `running` → `failed`)

### Oracle Agent Tools (PydanticAI)

1. `validate_request` — Checks script non-empty, nodes 1-16, time 1-60min
2. `submit_to_slurm` — Calls SlurmClient.submit_job(), updates DB status to `running`
3. `poll_slurm_status` — Polls every 5s for up to 5min, captures output on completion
4. `submit_onchain_proof` — Hashes output, calls ProofOfCompute.submitProof(), logs gas cost + attribution

### x402 Payment Flow

The agent uses `x402ResourceServer` with either:
- CDP facilitator (mainnet, with JWT auth) if `CDP_API_KEY_ID` and `CDP_API_KEY_SECRET` are set
- x402.org facilitator (testnet) otherwise

Payment verification happens in `POST /api/compute/submit`. No payment header → 402 response with price. Valid payment → job created.

## API Endpoint Reference

### Agent endpoints (defined in `agent/src/api/routes.py`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/compute/submit` | x402 payment | Submit compute job. No `payment-signature` header → 402 with price. Valid payment → job created. Body: `{script, nodes, time_limit_min, submitter_address}`. Optional header: `X-BUILDER-CODE`. |
| `GET` | `/api/stream` | Admin key | SSE event stream (live terminal feed). Returns `text/event-stream`. |
| `GET` | `/api/stats` | None | Aggregate P&L, job counts, sustainability ratio, pricing phase, demand multiplier. |
| `GET` | `/api/wallet` | None | Current ETH/USDC balances + up to 100 recent snapshots. |
| `GET` | `/api/jobs` | Admin key | Recent active (20) + historical (50) jobs. |
| `GET` | `/api/jobs/{job_id}` | None | Single job detail with output, proof hash. UUID serves as capability token. |
| `GET` | `/api/jobs/user?address=0x...` | Admin key | Jobs for a specific submitter wallet (50 active, 100 historical). |
| `GET` | `/api/attribution` | None | Builder code analytics: total attributed txs, multi-code txs, recent 20 entries. |
| `GET` | `/api/attribution/decode?tx_hash=0x...` | None | Decode ERC-8021 builder code suffix from any on-chain transaction. |
| `POST` | `/api/sessions` | None | Create payment session (called by MCP server). Body: `{script, nodes, time_limit_min, price}`. |
| `GET` | `/api/sessions/{session_id}` | None | Get payment session details. 10-minute TTL; returns 404 if expired. |
| `POST` | `/api/sessions/{session_id}/complete` | None | Mark session as paid. Body: `{job_id}`. Called by pay page after successful x402 payment. |
| `GET` | `/health` | None | Liveness probe. Returns `{"status": "ok"}`. |
| `GET` | `/health/ready` | None | Readiness probe. Checks DB, wallet balance. Returns 503 if degraded. |
| `GET` | `/api/capabilities` | None | Machine-readable service description (payment protocol, compute limits, trust metrics, rate limits). |
| `GET` | `/api/audit` | Admin key | Structured audit log. Query params: `limit` (default 50), `event_type` (optional filter). |

Admin key endpoints require `X-Admin-Key` header matching `ADMIN_API_KEY` env var. Uses `hmac.compare_digest` for constant-time comparison. If `ADMIN_API_KEY` is empty, auth is skipped (dev mode).

### Slurm proxy endpoints (defined in `deploy/slurm/slurm_proxy.py`, runs on controller:6820)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/slurm/v0.0.38/job/submit` | `X-SLURM-USER-TOKEN` header | Submit job via sbatch, wrapped in Apptainer container. |
| `GET` | `/slurm/v0.0.38/job/{job_id}` | `X-SLURM-USER-TOKEN` header | Get job state via scontrol. Returns state, exit_code, timestamps. |
| `GET` | `/slurm/v0.0.38/job/{job_id}/output` | `X-SLURM-USER-TOKEN` header | Get stdout, stderr, and SHA-256 output hash. |
| `GET` | `/slurm/v0.0.38/nodes` | `X-SLURM-USER-TOKEN` header | Cluster node status via sinfo. Returns node name, state, CPUs, memory. |
| `GET` | `/health` | None | Cluster health check (calls sinfo). |

Also supports v0.0.37 paths for backward compatibility.

### Dashboard proxy routes (in `dashboard/src/app/api/`)

These Next.js API routes proxy client requests to the agent via `AGENT_URL` (Railway internal networking). Admin-protected routes verify a JWT cookie (obtained via wallet signature on `/admin` page) before forwarding the `X-Admin-Key` header.

| Dashboard Route | Proxies To | Auth | Notes |
|-----------------|-----------|------|-------|
| `GET /api/stats` | `AGENT_URL/api/stats` | None | Public |
| `GET /api/wallet` | `AGENT_URL/api/wallet` | None | Public |
| `GET /api/jobs` | `AGENT_URL/api/jobs` | JWT cookie | Admin-only; forwards `X-Admin-Key` |
| `GET /api/audit` | `AGENT_URL/api/audit` | JWT cookie | Admin-only; forwards `X-Admin-Key` |
| `GET /api/attribution` | `AGENT_URL/api/attribution` | None | Public |
| `GET /api/attribution/decode` | `AGENT_URL/api/attribution/decode` | None | Forwards query params |
| `GET /api/stream` | `AGENT_URL/api/stream` | JWT cookie | Admin-only SSE; forwards `X-Admin-Key` |
| `POST /api/proxy/submit` | `AGENT_URL/api/compute/submit` | None | Forwards `payment-signature` and `X-BUILDER-CODE` |
| `GET /api/proxy/jobs?address=` | `AGENT_URL/api/jobs/user?address=` | None | Forwards `X-Admin-Key` (data is wallet-scoped) |
| `GET /api/proxy/sessions/{id}` | `AGENT_URL/api/sessions/{id}` | None | Payment session lookup |
| `POST /api/proxy/sessions/{id}/complete` | `AGENT_URL/api/sessions/{id}/complete` | Mark session paid |

## Dashboard Internals

### Security Architecture

The dashboard splits into public and admin views:

- **Public dashboard** (`/`) — Aggregate stats only (WalletBalance, RevenueModel, FinancialPnL, SustainabilityGauge, PublicJobStats, AttributionPanel). No individual job scripts, outputs, or internal logs.
- **Admin page** (`/admin`) — Full JobsPanel, TerminalFeed, AuditPanel. Requires: (1) connecting the operator wallet matching `NEXT_PUBLIC_ADMIN_ADDRESS`, (2) signing a timestamped message to prove ownership, (3) server-verified JWT cookie (HttpOnly, Secure in prod, SameSite=Strict, 24h expiry).
- **My Jobs** (`/history`) — Wallet-scoped. The proxy forwards `X-Admin-Key` unconditionally since data is inherently filtered by address.

Auth flow: wallet signature → `POST /api/admin/login` verifies via viem's `verifyMessage` + checks address match → signs JWT with `jose` using `ADMIN_API_KEY` as secret → sets HttpOnly cookie. Admin proxy routes verify the cookie before forwarding `X-Admin-Key` to the agent.

Key files: `dashboard/src/lib/admin-auth.ts` (JWT helpers), `dashboard/src/app/api/admin/` (login/logout/check routes).

### Wallet Persistence

Uses `cookieStorage` from wagmi so wallet connection survives page reloads with SSR. The layout reads cookies via `headers()` and passes `cookieToInitialState(config, cookie)` as `initialState` to `WagmiProvider`.

### Proxy Pattern

All dashboard API calls go through Next.js API routes that proxy to the agent:
- `/api/stats` → `AGENT_URL/api/stats`
- `/api/proxy/submit` → `AGENT_URL/api/compute/submit` (forwards x402 payment headers)
- `/api/proxy/sessions/{id}` → `AGENT_URL/api/sessions/{id}`

This avoids exposing `AGENT_URL` to the client and works with Railway's internal networking.

### Job Sorting

Jobs are merged (active + historical) and sorted by timestamp descending (newest first). Active jobs use `submitted_at`, historical use `completed_at`.

### Design Tokens (Tailwind)

Defined in `dashboard/tailwind.config.ts`. All dashboard components use these `ouro-*` tokens:

| Token | Value | Usage |
|-------|-------|-------|
| `ouro-bg` | `#0a0e17` | Page background |
| `ouro-card` | `#111827` | Card/panel backgrounds |
| `ouro-border` | `#1e293b` | Borders, dividers |
| `ouro-accent` | `#22d3ee` | Primary accent (cyan) — links, highlights, active states |
| `ouro-green` | `#10b981` | Positive values (revenue, completed) |
| `ouro-red` | `#ef4444` | Negative values (costs, errors, failed) |
| `ouro-amber` | `#f59e0b` | Warnings, pending states |
| `ouro-muted` | `#64748b` | Secondary text, labels |
| `ouro-text` | `#e2e8f0` | Primary text |

Fonts: `JetBrains Mono` (display headings + monospace code), `IBM Plex Sans` (body text).

Custom animations: `pulse-glow`, `fade-in`, `slide-up`. CSS class `.card` is used across all panel components.

## MCP Integration

Add to `.cursor/mcp.json` or Claude Desktop config:
```json
{
  "mcpServers": {
    "ouro-compute": {
      "url": "https://mcp.ourocompute.com/mcp"
    }
  }
}
```

MCP tools:
- `run_compute_job(script, nodes, time_limit_min)` → Returns payment URL + session_id
- `get_job_status(job_id_or_session_id)` → Returns job details, output, proof hash
- `get_price_quote(nodes, time_limit_min)` → Returns price without submitting
- `get_api_endpoint()` → Returns direct API URL + body schema for programmatic access

## Common Operations

### Redeploying after code changes
```bash
./deploy/deploy.sh                      # All services (fetches Slurm IP, deploys in parallel)
./deploy/deploy.sh agent mcp            # Specific services only
```

### Running the Slurm setup script after VM resize
```bash
./deploy/setup-slurm-cluster.sh
# Script handles: SSH wait, package install, NFS, munge, config distribution,
# service restart, node undrain, and verification
```

### Checking Slurm cluster health
```bash
gcloud compute ssh ouro-slurm --project=ouro-hpc-2026 --zone=us-central1-a \
  --command="sinfo && scontrol show nodes"
```

### Database migration (new table)
If adding a new table to `db/01-init.sql`, run the CREATE TABLE manually on the Railway Postgres instance, or recreate the database.

## Testing

### Smart Contracts
```bash
cd contracts
forge test          # Runs all tests in test/ProofOfCompute.t.sol
forge test -vvv     # Verbose output with traces
```

Tests cover: proof submission, duplicate prevention, nonexistent proof lookup, multiple proofs, reputation tracking, and per-submitter isolation.

### Agent / Dashboard
No automated test suite currently. Manual verification:
- Agent: `docker compose up --build` then `curl http://localhost:8000/api/stats`
- Dashboard: Visit `http://localhost:3000`, check that all panels load data
- MCP: Add server to Cursor config, ask agent to run a compute job

## Known Issues & Lessons

- **SLURMREST_URL must be the external IP** of the GCP controller. It changes when instances restart. `deploy/deploy.sh` handles this automatically.
- **Payment sessions were previously in-memory** in the MCP server, causing "Session Not Found" errors after restarts. Now stored in PostgreSQL via the agent API.
- **Slurm nodes drain** if `slurm.conf` specifies more CPUs/memory than the actual hardware. The setup script's Phase 12 handles undraining, and `slurm.conf` must match the instance specs.
- **Wallet disconnects on reload** were caused by using localStorage with SSR. Fixed by using `cookieStorage` + `cookieToInitialState` hydration in the layout.
- **Jobs stuck in "processing"** after agent restart are recovered by `recover_stuck_jobs()` on startup.
- **Oracle agent timeout**: Wrapped in `asyncio.wait_for(..., timeout=900)` to prevent infinite hangs.
- **Slurm poll errors**: `poll_slurm_status` wraps `get_job_status()` in try/except so transient network errors don't crash the run.
- **Dashboard Docker build needs native toolchain**: `dashboard/Dockerfile` installs `python3 make g++` via `apk add` in the deps stage to compile native npm dependencies (bufferutil, etc.).

## Companion Documentation

- **`README.md`** — Project overview: live URLs, architecture summary, environment variable tables for all services, deployment instructions, MCP config snippet, Slurm cluster overview, and smart contract deployment.
- **`mcp-server/README.md`** — MCP-specific quick start for Cursor/Claude Desktop, tool reference (run_compute_job, submit_compute_job, get_job_status, get_price_quote), self-hosting instructions, and the browser payment workflow.
- **`.env.example`** — All environment variables with comments explaining each group. Copy to `.env` for local dev.
- **`db/01-init.sql`** — Full PostgreSQL schema: all CREATE TABLE statements, indexes, and the monthly partition generator for historical_data.
- **`db/02-seed.sql`** — Sample seed data: 7 historical jobs, 10 cost entries (gas + LLM), 7 wallet snapshots, and 7 attribution log entries with realistic values.

## Workflow Preferences

- Plan first for non-trivial tasks (3+ steps or architectural decisions)
- Use subagents for research and parallel exploration
- Verify changes work before marking complete
- Keep changes minimal and focused
- Find root causes, no temporary fixes
- Before making any dashboard changes, read `dashboard/DESIGN.md` first to align with the overall theme, design tokens, and visual patterns
- After making changes, update `CLAUDE.md`, `dashboard/DESIGN.md`, and `README.md` if the changes affect architecture, design, APIs, or project structure
