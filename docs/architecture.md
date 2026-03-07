# Architecture Details

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
│       │   ├── dockerfile.py # Dockerfile parser, prebuilt alias map, Docker wrapper script generation
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
│           ├── admin-auth.ts   # JWT sign/verify helpers, cookie name constant
│           └── dockerfile.ts   # Lightweight Dockerfile parser for UI validation and display
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
│       └── slurm_proxy.py  # FastAPI proxy wrapping sbatch with Docker container isolation
├── mcp-server/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/ouro_mcp/server.py  # MCP tools: run_compute_job, get_job_status, get_price_quote, get_payment_requirements, submit_and_pay, get_api_endpoint
├── ouro-sdk/               # Python SDK for programmatic access
│   ├── pyproject.toml
│   └── src/ouro_sdk/
│       ├── client.py       # OuroClient: run, submit, wait, quote, capabilities
│       └── models.py       # JobResult, Quote dataclasses
├── .mcp/
│   └── server.json         # MCP Registry manifest for official registry publication
├── docker-compose.yml      # Local dev: postgres + agent + dashboard
├── .env.example
└── .gitignore
```

## Key Technologies

- **x402** — HTTP 402 payment protocol. Agent returns 402 with PAYMENT-REQUIRED header; client signs USDC authorization. Facilitated by Coinbase CDP on mainnet, x402.org on testnet.
- **ERC-8021** — Builder Code attribution appended to every on-chain transaction calldata. Format: `codesJoined + length(1 byte) + schemaId(0x00) + marker(16 bytes)`. See `agent/src/chain/erc8021.py`.
- **ERC-8004** — On-chain agent identity registry at `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`. Agent resolves or registers its `agentId` on startup (stored in `ERC8004_AGENT_ID`). Supports the Reputation Registry (`ERC8004_REPUTATION_REGISTRY`) for on-chain feedback via `giveFeedback()`.
- **PydanticAI** — Typed LLM agent with tools. The oracle agent has 4 tools: validate_request, submit_to_slurm, poll_slurm_status, submit_onchain_proof. In production, the deterministic fast path (`process_job_fast`) executes these directly without the LLM; the LLM agent is a fallback for complex error recovery.
- **Slurm** — HPC workload manager. Jobs are submitted via a custom REST proxy (`slurm_proxy.py`) that wraps sbatch with Docker container isolation.
- **Docker** — Container isolation for user scripts on Slurm workers. Containers run with hardened flags: `--read-only`, `--network none`, `--cap-drop ALL`, `--user 65534:65534`, `--memory`, `--pids-limit`, `--tmpfs /tmp`. Workers use `userns-remap: "default"` and iptables rules blocking the GCP metadata server.
- **Dockerfile → Docker** — Users write standard Dockerfiles. The agent parses them (`agent/src/agent/dockerfile.py`) and generates Docker wrapper scripts that build and run on-worker inside the Slurm job. Prebuilt aliases (`ouro-ubuntu` → `ubuntu:22.04`, `ouro-python` → `python:3.12-slim`, `ouro-nodejs` → `node:20-slim`) map directly to Docker Hub images and are pulled on demand; custom Dockerfiles are built on-worker with `DOCKER_BUILDKIT=0`. Multi-stage builds (multiple FROM) and `RUN --mount`/`# syntax=` directives are rejected. `needs_docker_build` flag distinguishes images needing `docker build` from those needing only `docker pull`.

## Data Flow

### Submission Modes

| Mode | Body Fields | Description |
|------|-------------|-------------|
| **Script** | `script` | Single shell script string — normalized to workspace with `job.sh` |
| **Multi-File** | `files: [{path, content}]` | Multiple files including a `Dockerfile` that defines the environment (FROM, RUN, ENTRYPOINT). If no Dockerfile, `entrypoint` and `image` fields required. |

The API accepts either format, but internally all submissions are normalized to a unified workspace model via `to_workspace_files()`. A single `script` string becomes `[{path: "job.sh", content: script}]` with `entrypoint="job.sh"`. This means there is ONE code path through the entire pipeline — every job gets a workspace on NFS with an entrypoint.

All modes support `nodes`, `time_limit_min`, `submitter_address`, `builder_code`.

**Dockerfile-based environments:** Include a file named `Dockerfile` in `files` to configure the compute environment:
- `FROM` selects the base image (prebuilt alias or Docker Hub image)
- `RUN` installs dependencies (built once, cached by content hash)
- `ENTRYPOINT` or `CMD` defines what to execute
- `COPY`/`ADD` copy workspace files into the image during build (local paths only; no URLs, no globs)
- `ARG` defines build-time variables with `$VAR`/`${VAR}` substitution into RUN, ENV, WORKDIR, COPY/ADD
- `LABEL` adds metadata to the image
- `SHELL` sets the shell for RUN commands (JSON exec form only)
- `EXPOSE` stores port metadata as a label (no runtime effect — containers run with `--network none`)
- `USER`, `VOLUME`, `HEALTHCHECK`, `STOPSIGNAL`, `ONBUILD` are rejected with clear error messages
- Build time is included in the Slurm job's `time_limit_min` since Docker builds happen on-worker inside the job script. `DOCKER_BUILDKIT=0` is enforced; multi-stage builds and `RUN --mount`/`# syntax=` are rejected
- Prebuilt aliases: `ouro-ubuntu` (Ubuntu 22.04), `ouro-python` (Python 3.12), `ouro-nodejs` (Node.js 20)
- Without a Dockerfile, use `entrypoint` and `image` fields directly (backward compat for MCP/SDK)

### Job Submission (via Dashboard)
1. User picks a template on `/submit` (each ships a Dockerfile + source files) or writes files from scratch, connects wallet via RainbowKit
2. Dockerfile defines FROM image, RUN deps, and ENTRYPOINT/CMD. Dashboard validates Dockerfile (must have FROM + ENTRYPOINT/CMD) before enabling submit
3. Dashboard sends POST to `/api/proxy/submit` with x402 payment signature
4. Proxy forwards to agent's `POST /api/compute/submit`
5. Agent verifies x402 payment via CDP facilitator
6. Agent calls `to_workspace_files()` to normalize input (script becomes `[{path: "job.sh", content: script}]`)
7. Agent calls `slurm_client.create_workspace()` → proxy writes files to NFS workspace
8. Job created in `active_jobs` table with status `pending` (payload always contains `workspace_path` + `entrypoint`)
9. Background processor picks it up, runs oracle agent (validate → build image if needed → submit to Slurm → poll → cleanup workspace → proof)
10. On completion, job moved to `historical_data`, proof posted on-chain

### Job Submission (via MCP — Browser Flow)
1. AI agent calls `run_compute_job` MCP tool (with `script` or `files` — `files` can include a Dockerfile; `entrypoint`/`image` optional when Dockerfile present)
2. MCP server creates payment session via `POST {AGENT_URL}/api/sessions` (stores `job_payload` JSONB for non-script modes)
3. Returns payment URL: `https://dashboard.../pay/{sessionId}`
4. User opens link, connects wallet — pay page shows FROM image from Dockerfile if present, or file count/entrypoint summary
5. Pay page submits to `POST /api/proxy/submit/from-session` with just `{session_id, submitter_address}` + payment header (no large payload re-sent)
6. Agent reads `session.job_payload`, normalizes via `to_workspace_files()`, creates workspace, creates job, marks session paid
7. AI agent polls with `get_job_status(session_id)` to get results

### Job Submission (via MCP — Autonomous Flow)
1. AI agent calls `get_payment_requirements` MCP tool with job details (script or files — `files` can include a Dockerfile)
2. MCP server forwards to `POST {AGENT_URL}/api/compute/submit` without payment → receives 402 + `PAYMENT-REQUIRED` header
3. Returns price + raw payment header to calling agent
4. Calling agent decodes header with its x402 library, signs USDC payment locally
5. Agent calls `submit_and_pay` with the signed `payment-signature`
6. MCP server forwards to `POST {AGENT_URL}/api/compute/submit` with payment header → job created
7. Agent polls with `get_job_status(job_id)` to get results
8. No private keys leave the calling agent — only the opaque payment signature is transmitted

### Payment Sessions
Sessions are stored in PostgreSQL (not in-memory) so they survive MCP server restarts and work across replicas. The MCP server creates/reads sessions via the agent API. Sessions support `job_payload` JSONB for storing submission parameters. On submit, payloads are normalized to workspace+entrypoint like all other submissions.

## Database Schema

See `db/01-init.sql` for full schema. Key tables:

- **active_jobs** — Jobs currently in the pipeline (pending → processing → running → completed/failed). Includes `retry_count` for automatic retry on transient failures (max 2).
- **historical_data** — Completed jobs archive (partitioned by month via `completed_at`)
- **agent_costs** — Cost ledger (gas, llm_inference entries)
- **wallet_snapshots** — Periodic ETH/USDC balance records
- **payment_sessions** — MCP payment flow sessions (pending → paid, TTL 10min). `script` (nullable, legacy) and `job_payload` (JSONB) store the submission parameters; both are normalized to workspace+entrypoint on submit
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
