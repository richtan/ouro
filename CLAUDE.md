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

- Dashboard: `https://dashboard-production-80cd.up.railway.app`
- Agent API: `https://agent-production-fdde.up.railway.app`
- MCP Server: `https://mcp-server-production-3752.up.railway.app/mcp`

## Project Structure

```
Ouros/
├── agent/                  # Python FastAPI backend
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/
│       ├── main.py         # FastAPI app, lifespan, x402 init
│       ├── config.py       # pydantic-settings (all env vars)
│       ├── agent/
│       │   ├── oracle.py   # PydanticAI agent with tools (validate, submit, poll, proof)
│       │   ├── processor.py # Background job loop, recovery, timeout handling
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
│       │   ├── models.py   # SQLAlchemy models
│       │   ├── operations.py # complete_job, log_cost, log_attribution
│       │   └── session.py  # Async engine + session maker
│       └── slurm/
│           └── client.py   # HTTP client for Slurm REST proxy
├── dashboard/              # Next.js App Router frontend
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── app/
│       │   ├── layout.tsx      # Root layout (Web3Provider with cookie hydration)
│       │   ├── page.tsx        # Main dashboard
│       │   ├── submit/page.tsx # Job submission page
│       │   ├── history/page.tsx # User job history (wallet-scoped)
│       │   ├── pay/[sessionId]/page.tsx # MCP payment page
│       │   └── api/
│       │       ├── proxy/submit/route.ts    # Proxies to agent /api/compute/submit
│       │       ├── proxy/jobs/route.ts      # Proxies to agent /api/jobs/user
│       │       ├── proxy/sessions/[sessionId]/route.ts          # GET session
│       │       └── proxy/sessions/[sessionId]/complete/route.ts # POST complete
│       │       ├── jobs/route.ts       # Proxies to agent /api/jobs
│       │       ├── stats/route.ts      # Proxies to agent /api/stats
│       │       ├── wallet/route.ts     # Proxies to agent /api/wallet
│       │       ├── attribution/route.ts
│       │       └── stream/route.ts     # SSE proxy
│       ├── components/
│       │   ├── Web3Provider.tsx    # wagmi/RainbowKit config (cookieStorage for persistence)
│       │   ├── NavBar.tsx
│       │   ├── JobsPanel.tsx       # All jobs table (sorted by time desc)
│       │   ├── WalletBalance.tsx
│       │   ├── FinancialPnL.tsx
│       │   ├── SustainabilityGauge.tsx
│       │   ├── RevenueModel.tsx
│       │   ├── TerminalFeed.tsx    # SSE event stream
│       │   ├── AttributionPanel.tsx
│       │   ├── ClusterStatus.tsx
│       │   └── OutputDisplay.tsx
│       └── lib/
│           └── api.ts          # Client-side fetch helpers
├── contracts/              # Foundry Solidity project
│   ├── foundry.toml
│   ├── src/ProofOfCompute.sol
│   ├── script/Deploy.s.sol
│   └── test/ProofOfCompute.t.sol
├── db/
│   ├── 01-init.sql         # Full schema (tables, indexes, partitions)
│   └── 02-seed.sql
├── deploy/
│   ├── deploy-agent.sh     # Fetches GCP IP, sets SLURMREST_URL, deploys to Railway
│   ├── setup-slurm-cluster.sh # Full GCP cluster provisioning (13 phases)
│   └── slurm/
│       ├── slurm.conf      # Slurm config (e2-small controller, e2-medium workers)
│       ├── cgroup.conf
│       └── slurm_proxy.py  # FastAPI proxy wrapping sbatch with Apptainer isolation
├── mcp-server/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/ouro_mcp/server.py  # MCP tools: run_compute_job, get_job_status, get_price_quote
├── docker-compose.yml      # Local dev: postgres + agent + dashboard
├── .env.example
└── .gitignore
```

## Key Technologies

- **x402** — HTTP 402 payment protocol. Agent returns 402 with PAYMENT-REQUIRED header; client signs USDC authorization. Facilitated by Coinbase CDP on mainnet, x402.org on testnet.
- **ERC-8021** — Builder Code attribution appended to every on-chain transaction calldata. Format: `codesJoined + length(1 byte) + schemaId(0x00) + marker(16 bytes)`. See `agent/src/chain/erc8021.py`.
- **ERC-8004** — On-chain agent identity registry at `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`. Agent registers itself on startup.
- **PydanticAI** — Typed LLM agent with tools. The oracle agent has 4 tools: validate_request, submit_to_slurm, poll_slurm_status, submit_onchain_proof.
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

- **active_jobs** — Jobs currently in the pipeline (pending → processing → running → completed/failed)
- **historical_data** — Completed jobs archive (partitioned by month via `completed_at`)
- **agent_costs** — Cost ledger (gas, llm_inference entries)
- **wallet_snapshots** — Periodic ETH/USDC balance records
- **payment_sessions** — MCP payment flow sessions (pending → paid, TTL 10min)
- **attribution_log** — ERC-8021 builder code records per transaction

Job status lifecycle: `pending` → `processing` → `running` → `completed` (moved to historical) or `failed`.

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

## Environment Variables

### Agent (Railway service: `agent`)
```
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
BASE_RPC_URL=https://mainnet.base.org
CHAIN_ID=8453
CHAIN_CAIP2=eip155:8453
WALLET_PRIVATE_KEY, WALLET_ADDRESS
PROOF_CONTRACT_ADDRESS
USDC_CONTRACT_ADDRESS=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
BUILDER_CODE=ouro
SLURMREST_URL        # Set automatically by deploy/deploy-agent.sh
SLURMREST_JWT
LLM_MODEL=openai:gpt-4o-mini
OPENAI_API_KEY
CDP_API_KEY_ID, CDP_API_KEY_SECRET
X402_FACILITATOR_URL=https://x402.org/facilitator
PRICE_MARGIN_MULTIPLIER=1.5
PUBLIC_API_URL, PUBLIC_DASHBOARD_URL
PORT=8000
```

### Dashboard (Railway service: `dashboard`)
```
AGENT_URL=http://agent.railway.internal:8000   # Internal Railway networking
NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID            # For RainbowKit
PORT=3000
```

### MCP Server (Railway service: `mcp-server`)
```
OURO_API_URL=https://agent-production-fdde.up.railway.app  # Public agent URL
DASHBOARD_URL=https://dashboard-production-80cd.up.railway.app
PORT=8080
```

## Local Development

```bash
cp .env.example .env
# Fill in keys (WALLET_PRIVATE_KEY, OPENAI_API_KEY, etc.)
# SLURMREST_URL can point to a local mock or GCP cluster
docker compose up --build
```

- Dashboard: http://localhost:3000
- Agent API: http://localhost:8000
- Postgres: localhost:5432

## Deployment

### Railway (Agent, Dashboard, MCP Server)

All three services deploy to Railway as separate services in a single project. Each has its own Dockerfile.

```bash
# Recommended: auto-sets SLURMREST_URL from GCP controller IP
./deploy/deploy-agent.sh

# Manual deployment (must set SLURMREST_URL yourself)
railway up agent --path-as-root --detach
railway up dashboard --path-as-root --detach
railway up mcp-server --path-as-root --detach
```

Monorepo: use `--path-as-root` to scope build context to the subdirectory.

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
| `GET` | `/api/stream` | None | SSE event stream (live terminal feed). Returns `text/event-stream`. |
| `GET` | `/api/stats` | None | Aggregate P&L, job counts, sustainability ratio, pricing phase, demand multiplier. |
| `GET` | `/api/wallet` | None | Current ETH/USDC balances + up to 100 recent snapshots. |
| `GET` | `/api/jobs` | None | Recent active (20) + historical (50) jobs. |
| `GET` | `/api/jobs/{job_id}` | None | Single job detail with output, proof hash. Works for both active and historical. |
| `GET` | `/api/jobs/user?address=0x...` | None | Jobs for a specific submitter wallet (50 active, 100 historical). |
| `GET` | `/api/attribution` | None | Builder code analytics: total attributed txs, multi-code txs, recent 20 entries. |
| `GET` | `/api/attribution/decode?tx_hash=0x...` | None | Decode ERC-8021 builder code suffix from any on-chain transaction. |
| `POST` | `/api/sessions` | None | Create payment session (called by MCP server). Body: `{script, nodes, time_limit_min, price}`. |
| `GET` | `/api/sessions/{session_id}` | None | Get payment session details. 10-minute TTL; returns 404 if expired. |
| `POST` | `/api/sessions/{session_id}/complete` | None | Mark session as paid. Body: `{job_id}`. Called by pay page after successful x402 payment. |

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

These Next.js API routes proxy client requests to the agent via `AGENT_URL` (Railway internal networking):

| Dashboard Route | Proxies To | Notes |
|-----------------|-----------|-------|
| `GET /api/stats` | `AGENT_URL/api/stats` | |
| `GET /api/wallet` | `AGENT_URL/api/wallet` | |
| `GET /api/jobs` | `AGENT_URL/api/jobs` | |
| `GET /api/attribution` | `AGENT_URL/api/attribution` | |
| `GET /api/attribution/decode` | `AGENT_URL/api/attribution/decode` | Forwards query params |
| `GET /api/stream` | `AGENT_URL/api/stream` | SSE passthrough (streams ReadableStream) |
| `POST /api/proxy/submit` | `AGENT_URL/api/compute/submit` | Forwards `payment-signature` and `X-BUILDER-CODE` headers |
| `GET /api/proxy/jobs?address=` | `AGENT_URL/api/jobs/user?address=` | User-scoped job history |
| `GET /api/proxy/sessions/{id}` | `AGENT_URL/api/sessions/{id}` | Payment session lookup |
| `POST /api/proxy/sessions/{id}/complete` | `AGENT_URL/api/sessions/{id}/complete` | Mark session paid |

## Dashboard Internals

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
      "url": "https://mcp-server-production-3752.up.railway.app/mcp"
    }
  }
}
```

MCP tools:
- `run_compute_job(script, nodes, time_limit_min)` → Returns payment URL + session_id
- `get_job_status(job_id_or_session_id)` → Returns job details, output, proof hash
- `get_price_quote(nodes, time_limit_min)` → Returns price without submitting

## Common Operations

### Redeploying after code changes
```bash
# All three services (if all changed):
./deploy/deploy-agent.sh                    # Agent (also refreshes SLURMREST_URL)
railway up dashboard --path-as-root --detach
railway up mcp-server --path-as-root --detach
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

- **SLURMREST_URL must be the external IP** of the GCP controller. It changes when instances restart. `deploy/deploy-agent.sh` handles this automatically.
- **Payment sessions were previously in-memory** in the MCP server, causing "Session Not Found" errors after restarts. Now stored in PostgreSQL via the agent API.
- **Slurm nodes drain** if `slurm.conf` specifies more CPUs/memory than the actual hardware. The setup script's Phase 12 handles undraining, and `slurm.conf` must match the instance specs.
- **Wallet disconnects on reload** were caused by using localStorage with SSR. Fixed by using `cookieStorage` + `cookieToInitialState` hydration in the layout.
- **Jobs stuck in "processing"** after agent restart are recovered by `recover_stuck_jobs()` on startup.
- **Oracle agent timeout**: Wrapped in `asyncio.wait_for(..., timeout=900)` to prevent infinite hangs.
- **Slurm poll errors**: `poll_slurm_status` wraps `get_job_status()` in try/except so transient network errors don't crash the run.

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
- Update this file when significant architectural changes are made
