# Operations & Deployment

## Secrets Management (Doppler)

Secrets are managed via [Doppler](https://doppler.com) as the single source of truth. Doppler project: `ouro`, configs: `dev` (local), `prd` (production, shared across all Railway services).

- **Local dev (hot reload)**: `doppler run -- docker compose up --build` (or fall back to `.env` file). Uses `docker-compose.override.yml` automatically — runs `next dev` with volume-mounted source for instant Fast Refresh, and uvicorn `--reload` for the agent.
- **Local dev (production build)**: `doppler run -- docker compose -f docker-compose.yml up --build` (explicitly skips the override file)
- **Port override**: `DASHBOARD_PORT=3001 doppler run -- docker compose up --build` (if 3000 is in use)
- **Production**: Doppler → Railway integration auto-syncs `prd` config to all three services
- **`SLURMREST_URL`** and **`PORT`** are NOT in Doppler — `SLURMREST_URL` is dynamically fetched from GCP by `deploy.sh`; `PORT` is set per-service in Railway

Config file: `doppler.yaml` at repo root (sets default project/config for CLI).

## Environment Variables

See `.env.example` for the full list with comments. Key groups:

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
ALLOWED_IMAGES=base,python312,node20,pytorch,r-base  # Prebuilt Docker image aliases mapped to Docker Hub (e.g. base → ubuntu:22.04). Custom Dockerfiles built on-worker
ERC8004_REPUTATION_REGISTRY  # ERC-8004 Reputation Registry address (optional)
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
4. Installs Slurm + Docker on all nodes (Docker configured with `userns-remap: "default"` and iptables blocking metadata server)
5. Deploys slurm_proxy.py on the controller
6. Clears stale Slurm state and undrains nodes
7. Verifies with test job and Docker container test

GCP instances: `ouro-slurm` (e2-small controller), `ouro-worker-1`, `ouro-worker-2` (e2-medium).

The Slurm proxy (`slurm_proxy.py`) runs on the controller at port 6820 as a systemd service (`slurm-proxy`). It wraps sbatch calls with Docker container isolation (generates wrapper scripts with hardened `docker run` flags).

### Smart Contracts

```bash
cd contracts
forge build
forge create src/ProofOfCompute.sol:ProofOfCompute \
  --rpc-url https://mainnet.base.org \
  --private-key $WALLET_PRIVATE_KEY
```

Set the resulting address as `PROOF_CONTRACT_ADDRESS`.

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

### Agent
```bash
cd agent
python -m pytest tests/ -v --tb=short          # Run all tests
python -m pytest tests/ --cov=src --cov-report=term-missing  # With coverage
```

Tests cover 5 core modules: erc8021 (encoding/decoding), pricing (phases, demand, calculate_price), processor (retry logic, recovery, failure handling), operations (DB ops, credits, job archival), oracle (validation, Slurm submission, polling, proof posting).

### Dashboard
No automated test suite. Manual verification:
- Visit `http://localhost:3000`, check that all panels load data
- MCP: Add server to Cursor config, ask agent to run a compute job

## Companion Documentation

- **`README.md`** — Project overview: live URLs, architecture summary, environment variable tables for all services, deployment instructions, MCP config snippet, Slurm cluster overview, and smart contract deployment.
- **`mcp-server/README.md`** — MCP-specific quick start for Cursor/Claude Desktop, tool reference (run_compute_job, submit_compute_job, get_job_status, get_price_quote), self-hosting instructions, and the browser payment workflow.
- **`.env.example`** — All environment variables with comments explaining each group. Copy to `.env` for local dev.
- **`db/01-init.sql`** — Full PostgreSQL schema: all CREATE TABLE statements, indexes, and the monthly partition generator for historical_data.
- **`db/02-seed.sql`** — Sample seed data: 7 historical jobs, 10 cost entries (gas + LLM), 7 wallet snapshots, and 7 attribution log entries with realistic values.
