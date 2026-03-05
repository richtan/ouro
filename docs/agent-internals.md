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
2. `build_image_if_needed` — Parses Dockerfile (if present in `deps.dockerfile_content`), resolves image via three paths: (a) prebuilt alias → use `/ouro-jobs/images/{alias}.sif` instantly, (b) Dockerfile with RUN/ENV → convert to `.def`, send to proxy `POST /image/build`, cache by SHA256, (c) Docker Hub image → proxy pulls and builds. Mutates `deps.sif_path` and `deps.entrypoint_cmd`. Skips if no Dockerfile (legacy path).
3. `submit_to_slurm` — Calls SlurmClient.submit_job() with workspace_path + entrypoint (and optional `sif_path` + `entrypoint_cmd` from Dockerfile), updates DB status to `running`
4. `poll_slurm_status` — Polls every 5s for up to 5min, captures output on completion
5. `submit_onchain_proof` — Hashes output, calls ProofOfCompute.submitProof(), logs gas cost + attribution

## OracleDeps

The `OracleDeps` dataclass passed to the oracle agent has been simplified for the unified workspace model. Removed fields: `submission_mode`, `script`, `workspace_cleanup_needed`. The `workspace_path` and `entrypoint` fields are now required strings (never None), since every submission creates a workspace. Dockerfile-related fields: `dockerfile_content: str | None` (raw Dockerfile text), `sif_path: str | None` (built image path, set by `build_image_if_needed`), `entrypoint_cmd: list[str] | None` (exec-form command extracted from Dockerfile ENTRYPOINT/CMD).

## x402 Payment Flow

The agent uses `x402ResourceServer` with either:
- CDP facilitator (mainnet, with JWT auth) if `CDP_API_KEY_ID` and `CDP_API_KEY_SECRET` are set
- x402.org facilitator (testnet) otherwise

Payment verification happens in `POST /api/compute/submit`. No payment header → 402 response with price. Valid payment → job created.

## Dashboard Security Architecture

The dashboard splits into public and admin views:

- **Public dashboard** (`/`) — Aggregate stats only (WalletBalance, RevenueModel, FinancialPnL, SustainabilityGauge, PublicJobStats, AttributionPanel). No individual job scripts, outputs, or internal logs.
- **Admin page** (`/admin`) — Full JobsPanel, TerminalFeed, AuditPanel. Requires: (1) connecting the operator wallet matching `NEXT_PUBLIC_ADMIN_ADDRESS`, (2) signing a timestamped message to prove ownership, (3) server-verified JWT cookie (HttpOnly, Secure in prod, SameSite=Strict, 24h expiry).
- **My Jobs** (`/history`) — Wallet-scoped. The proxy forwards `X-Admin-Key` unconditionally since data is inherently filtered by address.

Auth flow: wallet signature → `POST /api/admin/login` verifies via viem's `verifyMessage` + checks address match → signs JWT with `jose` using `ADMIN_API_KEY` as secret → sets HttpOnly cookie. Admin proxy routes verify the cookie before forwarding `X-Admin-Key` to the agent.

Key files: `dashboard/src/lib/admin-auth.ts` (JWT helpers), `dashboard/src/app/api/admin/` (login/logout/check routes).

## Dashboard Wallet Persistence

Uses `cookieStorage` from wagmi so wallet connection survives page reloads with SSR. The layout reads cookies via `headers()` and passes `cookieToInitialState(config, cookie)` as `initialState` to `WagmiProvider`.

## Dashboard Proxy Pattern

All dashboard API calls go through Next.js API routes that proxy to the agent:
- `/api/stats` → `AGENT_URL/api/stats`
- `/api/proxy/submit` → `AGENT_URL/api/compute/submit` (forwards x402 payment headers)
- `/api/proxy/sessions/{id}` → `AGENT_URL/api/sessions/{id}`

This avoids exposing `AGENT_URL` to the client and works with Railway's internal networking.

## Job Sorting

Jobs are merged (active + historical) and sorted by timestamp descending (newest first). Active jobs use `submitted_at`, historical use `completed_at`.

## Design Tokens (Tailwind)

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

## Agent Discoverability

Ouro is discoverable by autonomous agents through multiple channels:

| Channel | URL / Endpoint | Purpose |
|---------|---------------|---------|
| **A2A Agent Card** | `GET /.well-known/agent-card.json` | Google A2A protocol discovery — skills, auth, capabilities |
| **MCP Registry** | `.mcp/server.json` (publish via `mcp-publisher`) | Official MCP server registry at registry.modelcontextprotocol.io |
| **x402 Bazaar** | Automatic via CDP facilitator | Discovery via Bazaar extension in 402 response (input schema, output example) |
| **ERC-8004 Identity** | On-chain at `0x8004...9432` | Agent identity NFT with service endpoints |
| **Reputation API** | `GET /api/reputation` | Aggregated trust signals: proofs, success rate, on-chain feedback |
| **Capabilities** | `GET /api/capabilities` | Machine-readable service description with trust section |

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
- `run_compute_job(script?, files?, entrypoint?, image?, nodes, time_limit_min)` → Returns payment URL + session_id (browser flow). Provide `script` OR `files`. Include a `Dockerfile` in `files` for custom environments; `entrypoint`/`image` optional when Dockerfile present.
- `get_job_status(job_id_or_session_id)` → Returns job details, output, proof hash
- `get_price_quote(nodes, time_limit_min, submission_mode?)` → Returns price without submitting (uses `GET /api/price`)
- `get_payment_requirements(script?, files?, entrypoint?, image?, nodes, time_limit_min, submitter_address?, builder_code?)` → Returns price + x402 payment header for autonomous signing. `files` can include a Dockerfile.
- `submit_and_pay(payment_signature, script?, files?, entrypoint?, image?, nodes, time_limit_min, submitter_address?, builder_code?)` → Submits job with pre-signed x402 payment (autonomous flow)
- `get_allowed_images()` → Returns available container images (base, python312, node20, pytorch, r-base)
- `get_api_endpoint()` → Returns direct API URL + body schema for programmatic access
