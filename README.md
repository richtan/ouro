# Ouro

Pay for compute over HTTP. No accounts. No API keys. Just USDC and a POST request.

Submit a script via HTTP, get an x402 price quote, sign a USDC payment on Base, and your job runs on an HPC cluster. Integrate via MCP (AI agents), REST API (any HTTP client), or the Python SDK.

**[ourocompute.com](https://ourocompute.com)** · **[Docs](https://ourocompute.com/docs)** · **[API](https://api.ourocompute.com)**

## Quick Start

### MCP (AI Agents)

Add to your `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ouro": {
      "command": "npx",
      "args": ["-y", "ouro-mcp"],
      "env": { "WALLET_PRIVATE_KEY": "0x..." }
    }
  }
}
```

Works with Cursor, Claude Code, Claude Desktop, VS Code, Windsurf, OpenClaw, and OpenAI Agents SDK. See [`mcp/README.md`](mcp/README.md) for all client configs.

**Claude Code CLI:** `claude mcp add ouro --transport stdio -e WALLET_PRIVATE_KEY=0x... -- npx -y ouro-mcp`

Then ask your agent: *"Run `echo hello world` on the Ouro cluster."* Payment is automatic — your wallet signs USDC via x402.

### REST API

**1. Get price** — POST without payment to receive a 402 with the price:

```bash
curl -X POST https://api.ourocompute.com/api/compute/submit \
  -H "Content-Type: application/json" \
  -d '{"script": "echo hello", "nodes": 1, "time_limit_min": 1}'

# 402 Payment Required
# Header: payment-required: eyJ0eXAiOiJ4NDAyL...
# Body: { "price": "$0.0841", "breakdown": { ... } }
```

**2. Submit with payment** — sign the x402 payment and include it:

```bash
curl -X POST https://api.ourocompute.com/api/compute/submit \
  -H "Content-Type: application/json" \
  -H "payment-signature: <your-signed-x402-payment>" \
  -d '{"script": "echo hello", "nodes": 1, "time_limit_min": 1}'

# 200 OK
# Body: { "job_id": "a1b2c3d4-...", "status": "pending", "price": "$0.0841" }
```

**Multi-file with Dockerfile:**

```bash
curl -X POST https://api.ourocompute.com/api/compute/submit \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {"path": "Dockerfile", "content": "FROM ouro-python\nRUN pip install requests\nENTRYPOINT [\"python\", \"main.py\"]"},
      {"path": "main.py", "content": "import requests\nprint(requests.get(\"https://httpbin.org/ip\").json())"}
    ],
    "nodes": 1, "time_limit_min": 1
  }'
```

Include a `Dockerfile` in `files` to configure the environment — `FROM` picks the base image (prebuilt alias or Docker Hub), `RUN` installs deps (cached by content hash), `ENTRYPOINT`/`CMD` defines what to execute.

**3. Poll for results:**

```bash
curl https://api.ourocompute.com/api/jobs/{job_id}

# { "status": "completed", "output": "hello\n", ... }
```

## How It Works

1. **No signup** — POST your code with a Dockerfile that defines the environment (or just a script)
2. **Pay per job** — the 402 response tells you the price, sign one USDC payment on Base
3. **Get results** — stdout, stderr, and compute duration returned when complete

```
POST → 402 + price → sign USDC → 200 + job_id → poll → results
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Railway (PaaS)                             │
│                                                                     │
│  ┌───────────────┐   ┌──────────────────┐   ┌────────────────────┐  │
│  ┌───────────────┐   ┌──────────────────┐                           │
│  │  Dashboard    │   │  Agent (FastAPI) │                           │
│  │  Next.js 15   │──▶│  Python 3.12     │                           │
│  │  :3000        │   │  :8000           │                           │
│  └───────────────┘   └────────┬─────────┘                           │
│                               │                                     │
│                     ┌─────────▼───────────┐                         │
│                     │  PostgreSQL 16      │                         │
│                     │  (Railway managed)  │                         │
│                     └─────────────────────┘                         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP (slurmrestd proxy)
                     ┌──────────▼──────────┐
                     │  GCP Compute Engine │
                     │  Slurm HPC Cluster  │
                     └─────────────────────┘
```

- **Agent** (Python/FastAPI + PydanticAI) — Processes compute requests, manages Slurm jobs, runs autonomous pricing loop
- **Dashboard** (Next.js 15) — Public stats, wallet-gated admin, job submission UI
- **MCP Server** (Node.js, `npx ouro-mcp`) — Local MCP server for AI agents, signs x402 payments from your wallet
- **Database** (PostgreSQL 16) — Jobs, cost ledger, wallet snapshots, attribution log, audit trail

Key protocols: [x402](https://www.x402.org/) (HTTP payments), [ERC-8021](https://eip.tools/eip/8021) (builder attribution), [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004) (agent identity)

## Project Structure

```
ouro/
├── agent/          # Python FastAPI backend
├── dashboard/      # Next.js App Router frontend
├── contracts/      # Foundry Solidity project
├── db/             # SQL schema + seed data
├── mcp/            # Local MCP server for AI agents (npx ouro-mcp)
└── deploy/         # Railway deploy scripts + Slurm cluster setup
```

## Local Development

```bash
cp .env.example .env
# Set: OPENAI_API_KEY, WALLET_PRIVATE_KEY, WALLET_ADDRESS
docker compose up --build
```

- Dashboard: http://localhost:3000
- Agent API: http://localhost:8000

Without `SLURMREST_URL`/`SLURMREST_JWT`, the stack runs but submitted jobs won't execute. Without `CDP_API_KEY_ID`/`CDP_API_KEY_SECRET`, x402 payments won't work. See `.env.example` for all options.

For secrets management via Doppler: `doppler run -- docker compose up --build`

## Deployment

```bash
./deploy/deploy.sh                    # All services to Railway (fetches Slurm IP from GCP)
./deploy/deploy.sh agent dashboard    # Specific services only
./deploy/setup-slurm-cluster.sh       # Provision/update GCP Slurm cluster
```

## Testing

```bash
# Agent tests
cd agent && python -m pytest tests/ -v
```
