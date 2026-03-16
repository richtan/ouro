# Agent Internals

## Startup (in lifespan)

- **ERC-8004 agentId**: On startup, queries the Identity Registry for an existing `agentId` via `balanceOf`/`tokenOfOwnerByIndex`. If none found and `PUBLIC_DASHBOARD_URL` is set, registers a new agent identity. Stores the resolved `agentId` in `settings.ERC8004_AGENT_ID` at runtime.
- **x402 Bazaar**: Registers the `bazaar_resource_server_extension` on the x402 resource server so the 402 response includes Bazaar discovery metadata (input schema, output example).

## Background Tasks (started in lifespan)

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

## Oracle Agent Tools (PydanticAI)

1. `validate_request` — Checks workspace_path + entrypoint non-empty, nodes 1-16, time 1-60min (no mode branching)
2. `build_image_if_needed` — Parses Dockerfile (if present in `deps.dockerfile_content`), resolves image via three paths: (a) prebuilt alias → maps to Docker Hub image (e.g. `ouro-ubuntu` → `ubuntu:22.04`), sets `needs_docker_build=False` (just `docker pull`), (b) Dockerfile with RUN/ENV/COPY/ADD → generates Docker wrapper script, sets `needs_docker_build=True` (on-worker `docker build`), (c) Docker Hub image without customization → `docker pull` only. Docker builds happen on the worker inside the Slurm job script — the proxy no longer has image build endpoints. `DOCKER_BUILDKIT=0` is enforced; multi-stage builds (multiple FROM) and `RUN --mount`/`# syntax=` directives are rejected at parse time. Supported instructions: FROM, RUN, ENV, WORKDIR, ENTRYPOINT, CMD, COPY, ADD, ARG, LABEL, EXPOSE, SHELL. Rejected with error: USER, VOLUME, HEALTHCHECK, STOPSIGNAL, ONBUILD. External Docker Hub images are pre-validated at submission time via Docker Hub's tag API (`validate_docker_image()` in `dockerfile.py`). Fails open on timeout/5xx to avoid blocking submissions during Docker Hub outages. Mutates `deps.docker_image`, `deps.needs_docker_build`, and `deps.entrypoint_cmd`. Skips if no Dockerfile (legacy path).
3. `submit_to_slurm` — Calls SlurmClient.submit_job() with workspace_path + entrypoint (and optional `docker_image` + `needs_docker_build` + `entrypoint_cmd` from Dockerfile), updates DB status to `running`
4. `poll_slurm_status` — Polls every 5s for up to 5min, captures output on completion

The oracle agent is wrapped in `asyncio.wait_for(..., timeout=900)` (15 minutes) to prevent infinite hangs. `poll_slurm_status` wraps `get_job_status()` in try/except so transient network errors don't crash the run. Poll count scales with `time_limit_min`: `max(60, time_limit_min * 60 / 5 + 12)` polls at 5s intervals. On poll timeout, the Slurm job is cancelled.

## OracleDeps

The `OracleDeps` dataclass passed to the oracle agent has been simplified for the unified workspace model. Removed fields: `submission_mode`, `script`, `workspace_cleanup_needed`. The `workspace_path` and `entrypoint` fields are now required strings (never None), since every submission creates a workspace. Dockerfile-related fields: `dockerfile_content: str | None` (raw Dockerfile text), `docker_image: str | None` (resolved Docker image name/tag, set by `build_image_if_needed`), `needs_docker_build: bool` (whether a `docker build` is needed vs just `docker pull`), `entrypoint_cmd: list[str] | None` (exec-form command extracted from Dockerfile ENTRYPOINT/CMD).

## x402 Payment Flow

The agent uses `x402ResourceServer` with either:
- CDP facilitator (mainnet, with JWT auth) if `CDP_API_KEY_ID` and `CDP_API_KEY_SECRET` are set
- x402.org facilitator (testnet) otherwise

Payment verification happens in `POST /api/compute/submit`. No payment header → 402 response with price. Valid payment → job created.

## Dashboard

See `docs/architecture.md` § Dashboard Architecture for auth flow, proxy pattern, and wallet persistence. See `dashboard/DESIGN.md` for design tokens and visual guidelines.

## Agent Discoverability

See `docs/architecture.md` § Agent Discoverability.

## MCP Integration

See `mcp/README.md` for MCP setup, tools reference, and payment flow.
