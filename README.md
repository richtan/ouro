# Ouro — Proof-of-Compute Oracle

A self-sustaining autonomous agent on Base that sells HPC compute via x402, posts on-chain proofs with ERC-8021 Builder Codes, registers its identity via ERC-8004, and exposes a public dashboard with real-time P&L.

## Live URLs

| Service | URL |
|---|---|
| Dashboard | https://ourocompute.com |
| Agent API | https://api.ourocompute.com |
| MCP Server | https://mcp.ourocompute.com/mcp |

## Architecture

- **Agent** (Python/FastAPI) — PydanticAI oracle that processes compute requests, manages Slurm jobs, posts on-chain proofs, and runs an autonomous pricing/monitoring loop.
- **Dashboard** (Next.js) — Public, no-auth interface showing wallet balance, P&L, live terminal feed, cluster status, and builder code attribution analytics.
- **MCP Server** (Python/FastMCP) — Standalone MCP server that lets any AI agent (Cursor, Claude Desktop) submit compute jobs with browser-based USDC payments.
- **Contracts** (Foundry/Solidity) — `ProofOfCompute.sol` for on-chain proof attestation on Base.
- **Database** (PostgreSQL) — Active jobs, historical data (monthly partitioned), cost ledger, wallet snapshots, attribution log.

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
├── db/             # SQL schema + seed data
├── mcp-server/     # Standalone MCP server for AI agent compute
├── ouro-sdk/       # Python SDK for programmatic access
└── deploy/         # Slurm cluster setup scripts
```

---

## Local Development

```bash
cp .env.example .env
# Fill in your keys (see Environment Variables below)
docker compose up --build
```

- Dashboard: http://localhost:3000
- Agent API: http://localhost:8000
- Postgres: localhost:5432

This starts PostgreSQL, the agent, and the dashboard. Set `SLURMREST_URL` in `.env` to point at your Slurm cluster.

---

## Deployment (Railway)

All three services (agent, dashboard, mcp-server) are deployed to [Railway](https://railway.app) as separate services within a single project. Each service has its own Dockerfile.

### Prerequisites

- [Railway CLI](https://docs.railway.com/guides/cli) installed (`brew install railway`)
- Logged in: `railway login`
- Project linked: `railway link` (select the `ouro` project)

### Deploying

**Deploy all services:**

```bash
./deploy/deploy-all.sh                # All three (agent, mcp-server, dashboard)
./deploy/deploy-all.sh agent mcp      # Specific services only
```

**Or deploy agent only** (fetches Slurm controller IP from GCP automatically):

```bash
./deploy/deploy-agent.sh
```

**Important:** This is a monorepo. Each service must be deployed from the project root using `--path-as-root` to scope the build context to the correct subdirectory.

### Checking build logs

```bash
# Build logs for the latest deployment (even if failed)
railway logs --build --latest -s agent -n 100
railway logs --build --latest -s dashboard -n 100
railway logs --build --latest -s mcp-server -n 100

# Runtime logs (streaming)
railway logs -s agent
railway logs -s dashboard
railway logs -s mcp-server
```

### Railway Services & Environment Variables

#### agent

The core Python/FastAPI backend. Runs the autonomous pricing loop, processes jobs, posts on-chain proofs.

| Variable | Description |
|---|---|
| `DB_HOST` | PostgreSQL host (Railway provides this) |
| `DB_PORT` | PostgreSQL port (`5432`) |
| `DB_NAME` | Database name |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |
| `BASE_RPC_URL` | Base RPC endpoint (`https://mainnet.base.org`) |
| `CHAIN_ID` | Chain ID (`8453` for mainnet, `84532` for Sepolia) |
| `CHAIN_CAIP2` | CAIP-2 identifier (`eip155:8453`) |
| `WALLET_PRIVATE_KEY` | Agent wallet private key (holds ETH for gas) |
| `WALLET_ADDRESS` | Agent wallet address |
| `PROOF_CONTRACT_ADDRESS` | Deployed ProofOfCompute.sol address |
| `USDC_CONTRACT_ADDRESS` | USDC on Base (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`) |
| `BUILDER_CODE` | ERC-8021 builder code string |
| `SLURMREST_URL` | Slurm REST URL. Set automatically by `./deploy/deploy-agent.sh`; or set manually for local dev. |
| `SLURMREST_JWT` | Slurm auth token |
| `LLM_MODEL` | PydanticAI model (`openai:gpt-4o-mini`) |
| `OPENAI_API_KEY` | OpenAI API key |
| `CDP_API_KEY_ID` | Coinbase Developer Platform API key ID |
| `CDP_API_KEY_SECRET` | Coinbase Developer Platform API secret |
| `X402_FACILITATOR_URL` | x402 facilitator (`https://x402.org/facilitator`) |
| `PRICE_MARGIN_MULTIPLIER` | Profit margin multiplier (`1.5` = 50% margin) |
| `PUBLIC_API_URL` | Public URL of the agent |
| `PUBLIC_DASHBOARD_URL` | Public URL of the dashboard |
| `PORT` | Listening port (`8000`) |

#### dashboard

Next.js App Router frontend. Proxies API calls to the agent via internal Railway networking.

| Variable | Description |
|---|---|
| `AGENT_URL` | Internal agent URL (`http://agent.railway.internal:8000`) |
| `PORT` | Listening port (`3000`) |

#### mcp-server

Standalone MCP server. No secrets needed — it proxies to the agent and payment happens in the user's browser.

| Variable | Description |
|---|---|
| `OURO_API_URL` | Public agent URL (`https://api.ourocompute.com`) |
| `PUBLIC_URL` | Public URL of this MCP server (for generating payment links) |

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

The agent API is x402-compatible — any HTTP client that handles the x402 402→sign→retry flow can submit and pay for jobs programmatically without the MCP server.

---

## Python SDK

For programmatic access from Python scripts:

```bash
pip install ouro-sdk
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

The production Slurm cluster runs on GCP Compute Engine. Setup script is at `deploy/setup-slurm-cluster.sh`.

The agent connects to the Slurm controller's REST API (`slurmrestd`) via the `SLURMREST_URL` environment variable. Jobs are isolated using Apptainer containers on the worker nodes.

For local development, `docker compose` starts the agent and dashboard; `SLURMREST_URL` in `.env` must point to a running Slurm cluster.

---

## Smart Contracts

The `ProofOfCompute.sol` contract is deployed on Base mainnet. Deploy with Foundry:

```bash
cd contracts
forge build
forge create src/ProofOfCompute.sol:ProofOfCompute \
  --rpc-url https://mainnet.base.org \
  --private-key $WALLET_PRIVATE_KEY
```

Set the resulting address as `PROOF_CONTRACT_ADDRESS` in the agent's environment.
