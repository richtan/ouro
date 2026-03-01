# Ouro Compute

A self-sustaining autonomous agent on Base that sells HPC compute via x402, posts on-chain proofs with ERC-8021 Builder Codes, registers its identity via ERC-8004, and exposes a public dashboard with real-time P&L.

## Live URLs

| Service | URL |
|---|---|
| Dashboard | https://ourocompute.com |
| Agent API | https://api.ourocompute.com |
| MCP Server | https://mcp.ourocompute.com/mcp |

## Architecture

- **Agent** (Python/FastAPI) — PydanticAI oracle that processes compute requests, manages Slurm jobs, posts on-chain proofs, and runs an autonomous pricing/monitoring loop.
- **Dashboard** (Next.js) — Public interface showing wallet balance, P&L, live terminal feed, cluster status, and builder code attribution analytics. Admin section gated by wallet signature.
- **MCP Server** (Python/FastMCP) — Standalone MCP server that lets any AI agent (Cursor, Claude Desktop) submit compute jobs with browser-based USDC payments.
- **Contracts** (Foundry/Solidity) — `ProofOfCompute.sol` for on-chain proof attestation on Base.
- **Database** (PostgreSQL) — Active jobs, historical data (monthly partitioned), cost ledger, wallet snapshots, attribution log, audit log.

## Key Technologies

- **x402** — HTTP 402 payment protocol (Coinbase CDP facilitator)
- **ERC-8021** — Builder Code attribution on every transaction
- **ERC-8004** — On-chain agent identity registry
- **PydanticAI** — Structured LLM agent with typed tools
- **Slurm** — HPC workload manager (via slurmrestd REST API)

## Project Structure

```
Ouros/
├── agent/          # Python FastAPI backend
├── dashboard/      # Next.js App Router frontend
├── contracts/      # Foundry Solidity project
├── db/             # SQL schema (01-init.sql) + seed data (02-seed.sql)
├── mcp-server/     # Standalone MCP server for AI agent compute
├── ouro-sdk/       # Python SDK for programmatic access
└── deploy/         # Railway deploy scripts + Slurm cluster setup
```

---

## Prerequisites

| Tool | Version | Required for |
|---|---|---|
| [Docker](https://docs.docker.com/get-docker/) + Docker Compose | Latest | Full-stack local dev |
| [Node.js](https://nodejs.org/) | 20+ | Dashboard (if running without Docker) |
| [Python](https://www.python.org/) | 3.11+ | Agent / MCP server (if running without Docker) |
| [Foundry](https://getfoundry.sh/) | Latest | Contract deployment |
| [Railway CLI](https://docs.railway.com/guides/cli) | Latest | Production deployment |
| [gcloud CLI](https://cloud.google.com/sdk/docs/install) | Latest | Slurm cluster management + production deploy |
| [Doppler CLI](https://docs.doppler.com/docs/install-cli) | Latest | Secrets management (optional, falls back to `.env`) |

---

## Local Development

### Option A: Docker Compose (full stack, recommended)

This starts PostgreSQL, the agent, and the dashboard together. The database schema is auto-created from `db/01-init.sql` and `db/02-seed.sql`.

**With Doppler** (recommended — secrets injected automatically):

```bash
brew install dopplerhq/cli/doppler
doppler login
doppler setup    # Selects project "ouro", config "dev" (from doppler.yaml)
doppler run -- docker compose up --build

# If port 3000 is already in use:
DASHBOARD_PORT=3001 doppler run -- docker compose up --build
```

**Without Doppler** (fallback — uses `.env` file):

```bash
# 1. Copy the example env file
cp .env.example .env

# 2. Fill in the required values (see below)

# 3. Start everything
docker compose up --build

# If port 3000 is already in use:
DASHBOARD_PORT=3001 docker compose up --build
```

#### Hot reload vs production build

By default, `docker compose up` merges `docker-compose.override.yml` which enables **hot reload** for both services:

- **Dashboard**: Runs `next dev` with source files volume-mounted — edits to `dashboard/src/` trigger instant Fast Refresh
- **Agent**: Runs uvicorn with `--reload` and `agent/src/` volume-mounted — Python changes auto-restart the server

To run the **production build** locally (full `next build` + standalone server), skip the override:

```bash
# With Doppler:
doppler run -- docker compose -f docker-compose.yml up --build

# Without Doppler:
docker compose -f docker-compose.yml up --build
```

Once running:

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| Agent API | http://localhost:8000 |
| PostgreSQL | localhost:5432 (user: `ouro`, db: `ouro`) |

#### Required `.env` values

These **must** be set for the agent to start:

```bash
OPENAI_API_KEY=sk-...          # OpenAI API key (for PydanticAI oracle)
WALLET_PRIVATE_KEY=0x...       # Agent wallet private key (holds ETH for gas)
WALLET_ADDRESS=0x...           # Corresponding wallet address
```

These are needed for **jobs to actually execute** on a Slurm cluster:

```bash
SLURMREST_URL=http://<controller-ip>:6820   # Slurm REST API endpoint
SLURMREST_JWT=...                            # Slurm auth token
```

Without `SLURMREST_URL` and `SLURMREST_JWT`, the agent and dashboard still start, but submitted jobs will fail at the processing stage.

These are needed for **x402 payments** to work:

```bash
CDP_API_KEY_ID=...             # Coinbase Developer Platform API key ID
CDP_API_KEY_SECRET=...         # Coinbase Developer Platform API secret
```

Everything else in `.env.example` has working defaults for local dev. `ADMIN_API_KEY` can be left empty to disable auth checks (all admin endpoints open in dev).

### Option B: Individual services (without Docker)

Use this when you only need to work on one service, or need faster iteration than Docker rebuilds.

**Dashboard only:**

```bash
cd dashboard
npm install
npm run dev
```

Set `AGENT_URL` to point to a running agent (local or remote):

```bash
AGENT_URL=http://localhost:8000 npm run dev
# or point to production:
AGENT_URL=https://api.ourocompute.com npm run dev
```

**Agent only** (requires PostgreSQL running separately):

```bash
cd agent
pip install -e .
# With Doppler:
doppler run -- uvicorn src.main:app --host 0.0.0.0 --port 8000
# Without Doppler: set all required env vars (DB_HOST, OPENAI_API_KEY, WALLET_*, etc.)
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

**MCP server only:**

```bash
cd mcp-server
pip install -e .
OURO_API_URL=https://api.ourocompute.com ouro-mcp
```

---

## Environment Variables

### Agent service

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_HOST` | Yes | `postgres` | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `DB_NAME` | No | `ouro` | Database name |
| `DB_USER` | No | `ouro` | Database user |
| `DB_PASSWORD` | Yes | — | Database password |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key for PydanticAI |
| `LLM_MODEL` | No | `openai:gpt-4o-mini` | LLM model identifier |
| `WALLET_PRIVATE_KEY` | Yes | — | Agent wallet private key |
| `WALLET_ADDRESS` | Yes | — | Agent wallet address |
| `BASE_RPC_URL` | No | `https://mainnet.base.org` | Base RPC endpoint |
| `CHAIN_ID` | No | `8453` | Chain ID (8453=mainnet, 84532=Sepolia) |
| `CHAIN_CAIP2` | No | `eip155:8453` | CAIP-2 identifier |
| `PROOF_CONTRACT_ADDRESS` | Yes | — | Deployed ProofOfCompute.sol address |
| `USDC_CONTRACT_ADDRESS` | No | `0x...` | USDC on Base |
| `BUILDER_CODE` | No | — | ERC-8021 builder code (set to `ouro` in .env.example) |
| `SLURMREST_URL` | Yes* | — | Slurm REST API URL (*agent starts without it, but jobs won't run) |
| `SLURMREST_JWT` | Yes* | — | Slurm auth token |
| `CDP_API_KEY_ID` | Yes* | — | Coinbase CDP key ID (*needed for x402 payments) |
| `CDP_API_KEY_SECRET` | Yes* | — | Coinbase CDP key secret |
| `X402_FACILITATOR_URL` | No | `https://x402.org/facilitator` | x402 facilitator |
| `PRICE_MARGIN_MULTIPLIER` | No | `1.5` | Profit margin (1.5 = 50% margin) |
| `ADMIN_API_KEY` | No | — | Shared secret for admin endpoints (empty = no auth) |
| `PUBLIC_API_URL` | No | — | Public URL of the agent (for payment link generation) |
| `PUBLIC_DASHBOARD_URL` | No | — | Public URL of the dashboard |
| `PORT` | No | `8000` | Listening port (per-service in Railway; not in Doppler) |

### Dashboard service

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENT_URL` | Yes | — | Agent URL. Docker Compose: `http://agent:8000`. Railway: `http://agent.railway.internal:8000` |
| `ADMIN_API_KEY` | No | — | Must match the agent's `ADMIN_API_KEY` for admin features |
| `NEXT_PUBLIC_ADMIN_ADDRESS` | No | — | Wallet address that sees the Admin nav link and can authenticate |
| `PORT` | No | `3000` | Listening port (per-service in Railway; not in Doppler) |

### MCP server service

| Variable | Required | Default | Description |
|---|---|---|---|
| `OURO_API_URL` | No | `https://api.ourocompute.com` | Agent API URL |
| `DASHBOARD_URL` | No | `https://ourocompute.com` | Dashboard URL (for payment links) |
| `PUBLIC_URL` | No | — | Public URL of this MCP server |
| `PORT` | No | `8080` | Listening port (per-service in Railway; not in Doppler) |

---

## Production Deployment (Railway)

All three services (agent, dashboard, mcp-server) deploy to [Railway](https://railway.app) as separate services within a single project. Each has its own Dockerfile.

### First-time setup

1. **Install Railway CLI:**

   ```bash
   brew install railway
   railway login
   ```

2. **Create the project** (or use the Railway web dashboard):

   ```bash
   railway init
   ```

3. **Add services** in the Railway dashboard:
   - Create three services: `agent`, `dashboard`, `mcp-server`
   - Add a **PostgreSQL** plugin (Railway provisions it automatically)
   - Railway provides `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` for the PostgreSQL plugin — set these on the `agent` service

4. **Set environment variables** — use one of:

   **Option A: Doppler (recommended)** — In the Doppler dashboard, go to **Integrations → Railway**, connect the Railway project, and map the `prd` config to the `agent`, `dashboard`, and `mcp-server` services. Secrets auto-sync on every change.

   **Option B: Manual** — Set variables directly in Railway for each service:
   - `agent`: All agent env vars. Set `AGENT_URL` internally via `http://agent.railway.internal:8000` on the dashboard.
   - `dashboard`: `AGENT_URL=http://agent.railway.internal:8000`, `ADMIN_API_KEY`, `NEXT_PUBLIC_ADMIN_ADDRESS`
   - `mcp-server`: `OURO_API_URL=https://api.ourocompute.com`

   Note: `SLURMREST_URL` is always set by the deploy script (not Doppler) since it's dynamically fetched from GCP.

5. **Custom domains** (optional): In Railway Settings > Networking > Custom Domain for each service. Add CNAME records at your DNS provider pointing to the Railway-provided targets.

6. **Link the project locally:**

   ```bash
   railway link    # Select the project
   ```

### Deploying

**Deploy all services:**

```bash
./deploy/deploy.sh                  # All three services
./deploy/deploy.sh agent mcp        # Specific services only
./deploy/deploy.sh dashboard        # Dashboard only
```

The deploy script automatically fetches the Slurm controller IP from GCP and updates `SLURMREST_URL` on Railway when deploying the agent.

**Requirements for deploy scripts:** `gcloud` CLI configured with access to the GCP project, `railway` CLI logged in and linked to the project.

### Checking logs

```bash
# Build logs (even if deployment failed)
railway logs --build --latest -s agent -n 100
railway logs --build --latest -s dashboard -n 100
railway logs --build --latest -s mcp-server -n 100

# Runtime logs (streaming)
railway logs -s agent
railway logs -s dashboard
railway logs -s mcp-server
```

---

## MCP Integration (for AI Agents)

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

Then ask your AI agent: *"Run `echo hello world` on the Ouro cluster"*

The agent will return a one-time payment link. Open it in your browser, connect your wallet, pay USDC on Base, and the job executes on the Slurm cluster. No private keys leave your browser.

The agent API is x402-compatible — any HTTP client that handles the 402→sign→retry flow can submit and pay for jobs programmatically without the MCP server.

---

## Python SDK

For programmatic access from Python scripts:

```bash
pip install ./ouro-sdk
```

```python
from ouro_sdk import OuroClient

async with OuroClient() as ouro:
    quote = await ouro.quote(nodes=1, time_limit_min=1)
    print(f"Price: {quote.price}")

    job_id = await ouro.submit("echo hello world")
    result = await ouro.wait(job_id)
    print(result.status, result.output)
```

See [`ouro-sdk/README.md`](ouro-sdk/README.md) for full API docs.

---

## Slurm Cluster (GCP)

The production Slurm cluster runs on GCP Compute Engine with one controller node and two worker nodes.

### Prerequisites

- GCP project with billing enabled
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- SSH keys configured for GCP Compute Engine

### Setup

The setup script creates and configures the cluster:

```bash
./deploy/setup-slurm-cluster.sh
```

This script:
1. Creates GCP Compute Engine instances (controller: `e2-small`, workers: `e2-medium`)
2. Installs Slurm on all nodes
3. Deploys a custom REST proxy (`slurm_proxy.py`, slurmrestd-compatible) on the controller
4. Installs Apptainer on workers for job isolation
5. Starts all Slurm services

### Configuration

The deploy scripts (`deploy.sh`, `setup-slurm-cluster.sh`) support overriding via environment variables:

| Variable | Default | Overridable in |
|---|---|---|
| `GCP_PROJECT` | `ouro-hpc-2026` | deploy.sh, setup-slurm-cluster.sh |
| `GCP_ZONE` | `us-central1-a` | deploy.sh, setup-slurm-cluster.sh |
| `SLURM_CONTROLLER` | `ouro-slurm` | deploy.sh, setup-slurm-cluster.sh |

Slurm config files are in `deploy/slurm/`:
- `slurm.conf` — cluster configuration (CPU, memory, partitions)
- `cgroup.conf` — resource isolation
- `slurm_proxy.py` — REST proxy for slurmrestd

### Connecting the agent

The deploy script handles this automatically. When you run `./deploy/deploy.sh`, it fetches the controller's external IP from GCP and sets `SLURMREST_URL` on Railway.

For local dev, set `SLURMREST_URL` in your `.env` manually:

```bash
SLURMREST_URL=http://<controller-external-ip>:6820
```

Without a Slurm cluster, the agent and dashboard still start and function — the dashboard shows data, the agent accepts requests — but submitted jobs will fail at the processing stage.

---

## Smart Contracts

`ProofOfCompute.sol` is deployed on Base mainnet. To deploy a new instance:

```bash
cd contracts
forge build
forge create src/ProofOfCompute.sol:ProofOfCompute \
  --rpc-url https://mainnet.base.org \
  --private-key $WALLET_PRIVATE_KEY
```

For testnet (Base Sepolia):

```bash
forge create src/ProofOfCompute.sol:ProofOfCompute \
  --rpc-url https://sepolia.base.org \
  --private-key $WALLET_PRIVATE_KEY
```

Set the resulting contract address as `PROOF_CONTRACT_ADDRESS` in the agent's environment variables.

Foundry config is in `contracts/foundry.toml` (Solc 0.8.24, optimizer enabled with 200 runs).
