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
│       │   ├── client.py   # Web3 client (heartbeat, balances)
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
├── contracts/              # Foundry Solidity project (reserved for future contracts)
│   └── foundry.toml
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
├── mcp/
│   ├── package.json
│   ├── tsconfig.json
│   └── src/index.ts            # Local MCP server (npx ouro-mcp): run_job, get_job_status, get_price_quote, get_allowed_images, list_storage, delete_storage_file
├── .mcp/
│   └── server.json         # MCP Registry manifest for official registry publication
├── docker-compose.yml      # Local dev: postgres + agent + dashboard
├── .env.example
└── .gitignore
```

## Key Technologies

- **x402** — HTTP 402 payment protocol. Agent returns 402 with PAYMENT-REQUIRED header; client signs USDC authorization. Facilitated by Coinbase CDP on mainnet, x402.org on testnet.
- **ERC-8021** — Builder Code attribution appended to every on-chain transaction calldata. Format: `codesJoined + length(1 byte) + schemaId(0x00) + marker(16 bytes)`. See `agent/src/chain/erc8021.py`.
- **ERC-8004** — On-chain agent identity registry at `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`. Agent resolves or registers its `agentId` on startup (stored in `ERC8004_AGENT_ID`).
- **PydanticAI** — Typed LLM agent with tools. The oracle agent has tools: validate_request, build_image_if_needed, submit_to_slurm, poll_slurm_status. In production, the deterministic fast path (`process_job_fast`) executes these directly without the LLM; the LLM agent is a fallback for complex error recovery.
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

All modes support `cpus`, `time_limit_min`, `submitter_address`, `webhook_url`, `mount_storage`.

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
6. If `mount_storage: true`, check/create storage quota and init NFS directory
7. Agent calls `to_workspace_files()` to normalize input (script becomes `[{path: "job.sh", content: script}]`)
7. Validate external Docker image exists (Docker Hub tag API check)
8. Agent calls `slurm_client.create_workspace()` → proxy writes files to NFS workspace
9. Job created in `active_jobs` table with status `pending` (payload always contains `workspace_path` + `entrypoint`)
10. Background processor picks it up, runs oracle agent (validate → build image if needed → submit to Slurm → poll → cleanup workspace)
11. On completion, job moved to `historical_data`

### Job Submission (via MCP)
1. AI agent calls `run_job` MCP tool with job details (script or files — `files` can include a Dockerfile)
2. Local MCP server (`npx ouro-mcp`) POSTs to `{API_URL}/api/compute/submit` → receives 402
3. `@x402/fetch` automatically signs the USDC payment using the local `WALLET_PRIVATE_KEY` and retries
4. Job created, `job_id` returned to the calling agent
5. Agent polls with `get_job_status(job_id)` to get results
6. Private key never leaves the user's machine — the MCP server runs locally via stdio transport

## Database Schema

See `db/01-init.sql` for full schema. Key tables:

- **active_jobs** — Jobs currently in the pipeline (pending → processing → running → completed/failed). Includes `retry_count` for automatic retry on transient failures (max 2).
- **historical_data** — Completed jobs archive (partitioned by month via `completed_at`)
- **agent_costs** — Cost ledger (gas, llm_inference entries)
- **wallet_snapshots** — Periodic ETH/USDC balance records
- **attribution_log** — ERC-8021 builder code records per transaction
- **credits** — USDC credits issued to wallets when jobs fail after payment (auto-redeemable)
- **audit_log** — Structured audit trail for all financial events (payment_received, job_completed, credit_issued, errors)
- **storage_quotas** — Per-wallet persistent storage quotas (tier, quota bytes, cached usage, last access time)

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

Cost floor = `max_gas × 1.25 + max_llm × 1.25 + cpus × minutes × $0.0002/cpu-min + setup_cost`

## Credit System

Ouro issues USDC credits when jobs fail due to platform errors, automatically redeemable on future submissions.

### Fault Classification

`agent/src/agent/classifier.py` classifies failures by Slurm state (unforgeable from inside Docker with `--network none --cap-drop ALL`), not exit codes:

| Fault | When | Credit? |
|-------|------|---------|
| `platform_error` | Stage 1 capacity failure, Stage 2 errors, Slurm CANCELLED/NODE_FAIL | Yes |
| `user_error` | Stage 1 validation errors, Stage 3 FAILED/TIMEOUT | No |

This prevents free compute via intentional `exit 1`.

### Credit Redemption

Credits are integrated into the submit endpoint (`routes.py`):
- If credits ≥ job price → x402 payment skipped entirely, credits redeemed
- If credits < job price → credit redeemed, x402 charges the remainder (partial credit)
- `redeem_credits()` uses `SELECT ... FOR UPDATE` to prevent double-spend races
- Credit redemption is **deferred** until after x402 payment verification to prevent credit loss on the 402 round-trip
- `redeem_credits()` splits oversized credit rows (creates a "change" row for unused portion)
- `redeem_credits()` does not commit — caller commits atomically with job creation

### Unused Compute Credits

Jobs that finish early receive proportional credits for unused compute time:
- Calculated via `calculate_unused_compute_credit()` in `pricing.py`
- Based on the marked-up price (not raw cost); uses `cost_floor` and `compute_cost` from the job payload at submission time
- Credits below $0.001 are filtered out
- Only applies to jobs with `cost_floor` in payload (new jobs); legacy jobs skipped

### x402 Facilitator Minimum

The x402 facilitator rejects payments below $0.001 USDC. When partial credit reduces the remainder below this threshold, the job is treated as fully credit-covered (sub-$0.001 shortfall waived). Constant: `X402_FACILITATOR_MIN_USD` in `routes.py`. Dashboard mirrors this in `StickySubmitBar.tsx`.

### Compute Cost Tracking

`_finalize_success()` and `_mark_failed()` in `processor.py` log actual compute infrastructure costs via `log_cost(cost_type="compute")`. These appear in `/api/stats` as `compute_costs_usd` and factor into the sustainability ratio (which sums all `agent_costs`), enabling accurate phase transitions.

## Persistent Storage

Per-wallet persistent storage mounted at `/scratch` inside containers. NFS-backed on `/ouro-storage` on the Slurm controller, exported to all workers.

### Configuration

- `STORAGE_FREE_TIER_BYTES` (default 1GB) — per-wallet quota
- `STORAGE_TTL_DAYS` (default 90 days) — inactivity TTL with warning at 60 days
- DB table: `storage_quotas` — tracks wallet tier, quota, cached usage, last access time

### API Surface

| Endpoint | Description |
|----------|-------------|
| `GET /api/storage?wallet=0x...&signature=...&timestamp=...` | Quota usage + file listing (EIP-191 signed) |
| `DELETE /api/storage/files?wallet=...&path=...&signature=...&timestamp=...` | EIP-191 signed delete |
| `POST /api/compute/submit` with `mount_storage: true` | Creates quota on first use, validates quota, mounts `/scratch` |

MCP tools: `list_storage`, `delete_storage_file`, `mount_storage` param on `run_job`.
Dashboard: `/storage` page (quota bar, file list, signed delete), toggle in submit config.

### Security

- Path traversal: `os.path.realpath()` + prefix check, symlinks skipped, `followlinks=False`
- File deletion: EIP-191 signature required (`ouro-storage-delete:{wallet}:{path}:{timestamp}`, 5-min window)
- Storage paths: `shlex.quote()` + regex validation
- Docker mount: `-v /ouro-storage/0x...:/scratch`, protected by `--cap-drop ALL` + `--no-new-privileges`

### Known Limitations

- **No kernel quotas on NFS bind mounts** — containers can write beyond 1GB during a job. Post-job sync catches overages and blocks new `mount_storage=true` jobs until under quota.
- **Concurrent writes** — two jobs from the same wallet with `mount_storage=true` both write to `/scratch`. NFS provides POSIX semantics but file conflicts are last-writer-wins.
- **TTL cleanup race** — `_storage_cleanup()` uses `SELECT ... FOR UPDATE` to re-check `last_accessed_at` under row lock, preventing races with concurrent `submit_compute` calls.

### Infrastructure

`setup-slurm-cluster.sh` and `setup-elastic-infra.sh` create and export `/ouro-storage`. `node-startup.sh` mounts it on spot instances.

## Docker Security Model

All user code runs inside hardened Docker containers on Slurm workers.

### Container Hardening

Every container runs with:
```
--read-only --network none --cap-drop ALL --no-new-privileges
--user 65534:65534 --memory {limit} --pids-limit {limit} --tmpfs /tmp
```

### Worker-Level Hardening

- `userns-remap: "default"` in Docker daemon config — maps container root to unprivileged host user
- iptables rules block the GCP metadata server (`169.254.169.254`) to prevent credential theft

### Build Security

- Docker builds happen **on-worker** inside the Slurm job script (not as a separate step). The proxy generates Docker wrapper scripts.
- `DOCKER_BUILDKIT=0` enforced — `RUN --mount=...` and `# syntax=` directives rejected at Dockerfile parse time
- Multi-stage builds (multiple `FROM`) rejected to prevent build-time escapes
- Supported instructions: FROM, RUN, ENV, WORKDIR, ENTRYPOINT, CMD, COPY, ADD, ARG, LABEL, EXPOSE, SHELL
- Rejected with error: USER, VOLUME, HEALTHCHECK, STOPSIGNAL, ONBUILD
- COPY/ADD: local workspace paths only (no globs, no URLs for ADD)
- Build time is included in the Slurm job's `time_limit_min`

### Image Validation

External (non-prebuilt) Docker images are validated against Docker Hub's tag API at submission time (`validate_docker_image()` in `dockerfile.py`):
- Returns 422 if image/tag not found
- Fails open on timeout/5xx/429 to avoid blocking during Docker Hub outages
- Digest references (`@sha256:...`) and non-Docker-Hub registries skip validation
- Prebuilt aliases (`ouro-ubuntu`, `ouro-python`, `ouro-nodejs`) skip validation
- Validation runs before payment

### Image Cache

Two-layer cleanup prevents disk exhaustion:
1. Per-job `docker rmi` in `slurm_proxy.py` removes non-prebuilt images after each job
2. `deploy/slurm/docker-cleanup.sh` runs every 6h via cron, with aggressive cleanup at >85% disk usage

Prebuilt images (`ubuntu:22.04`, `python:3.12-slim`, `node:20-slim`) are re-pulled after aggressive prunes.

## Dashboard Architecture

### Views

- **Public dashboard** (`/`) — Aggregate stats only (WalletBalance, RevenueModel, FinancialPnL, SustainabilityGauge, PublicJobStats, AttributionPanel). No individual job scripts, outputs, or internal logs.
- **Admin page** (`/admin`) — Full JobsPanel, TerminalFeed, AuditPanel. Requires operator wallet + signature auth + JWT cookie.
- **My Jobs** (`/history`) — Wallet-scoped. Requires session cookie (sign once on connect); proxy verifies JWT then forwards `X-Admin-Key`.

### Auth Flow

1. Connect operator wallet matching `NEXT_PUBLIC_ADMIN_ADDRESS`
2. Sign timestamped message to prove ownership
3. `POST /api/admin/login` verifies via viem's `verifyMessage` + checks address match
4. Signs JWT with `jose` using `ADMIN_API_KEY` as secret
5. Sets HttpOnly cookie (Secure in prod, SameSite=Strict, 24h expiry)
6. Admin proxy routes verify the cookie before forwarding `X-Admin-Key` to the agent

Key files: `dashboard/src/lib/admin-auth.ts` (admin JWT helpers), `dashboard/src/lib/wallet-auth.ts` (user session JWT helpers), `dashboard/src/contexts/AuthContext.tsx` (session state management), `dashboard/src/app/api/auth/` (user login/logout/check), `dashboard/src/app/api/admin/` (admin login/logout/check).

### Proxy Pattern

All dashboard API calls go through Next.js API routes that proxy to the agent. This avoids exposing `AGENT_URL` to the client and works with Railway's internal networking. See `docs/api-reference.md` § Dashboard Proxy Routes for the full routing table.

### Wallet Persistence

Uses `cookieStorage` from wagmi so wallet connection survives page reloads with SSR. The layout reads cookies via `headers()` and passes `cookieToInitialState(config, cookie)` as `initialState` to `WagmiProvider`.

## Agent Discoverability

Ouro is discoverable by autonomous agents through multiple channels:

| Channel | URL / Endpoint | Purpose |
|---------|---------------|---------|
| **A2A Agent Card** | `GET /.well-known/agent-card.json` | Google A2A protocol discovery — skills, auth, capabilities |
| **MCP Registry** | `.mcp/server.json` (publish via `mcp-publisher`) | Official MCP server registry at registry.modelcontextprotocol.io |
| **x402 Bazaar** | Automatic via CDP facilitator | Discovery via Bazaar extension in 402 response (input schema, output example) |
| **ERC-8004 Identity** | On-chain at `0x8004...9432` | Agent identity NFT with service endpoints |
| **Capabilities** | `GET /api/capabilities` | Machine-readable service description with trust section |
