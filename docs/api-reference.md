# API Endpoint Reference

## Agent endpoints (defined in `agent/src/api/routes.py`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/compute/submit` | x402 payment | Submit compute job. No `payment-signature` header → 402 with price. Valid payment → job created. Body: `{script, nodes, time_limit_min, submitter_address}` (script mode) or `{files: [{path, content}], nodes, time_limit_min}` (multi-file mode). `files` can include a `Dockerfile` — when present, `entrypoint` is optional (extracted from Dockerfile ENTRYPOINT/CMD) and `image` is ignored (FROM line used). Supported Dockerfile instructions: FROM, RUN, ENV, WORKDIR, ENTRYPOINT, CMD, COPY, ADD, ARG, LABEL, EXPOSE, SHELL. Rejected with 422: USER, VOLUME, HEALTHCHECK, STOPSIGNAL, ONBUILD. COPY/ADD accept local workspace paths only (no globs, no URLs for ADD). Agent validates Dockerfile syntax (422 on invalid). Returns 422 if an external (non-prebuilt) Docker image doesn't exist on Docker Hub — check the image name and tag. Optional header: `X-BUILDER-CODE`. Optional body param: `webhook_url` (see Webhooks section below). |
| `GET` | `/api/jobs/{job_id}/stream` | None | SSE stream of job status events. Emits `job_update` events until the job reaches a terminal state (`completed` or `failed`). UUID serves as capability token. |
| `GET` | `/api/price` | None | Price quote without submitting. Query params: `nodes`, `time_limit_min`, `submission_mode` (script/multi_file/archive/git). |
| `GET` | `/api/stream` | Admin key | SSE event stream (live terminal feed). Returns `text/event-stream`. |
| `GET` | `/api/stats` | None | Aggregate P&L, job counts, sustainability ratio, pricing phase, demand multiplier. |
| `GET` | `/api/wallet` | None | Current ETH/USDC balances + up to 100 recent snapshots. |
| `GET` | `/api/jobs` | Admin key | Recent active (20) + historical (50) jobs. |
| `GET` | `/api/jobs/{job_id}` | None | Single job detail with output. UUID serves as capability token. |
| `GET` | `/api/jobs/user?address=0x...` | Admin key | Jobs for a specific submitter wallet (50 active, 100 historical). |
| `GET` | `/api/credits/user?address=0x...` | Admin key | Credit balance + history for a wallet. Returns `{available: number, history: [{amount_usdc, reason, redeemed, created_at}]}`. |
| `GET` | `/api/attribution` | None | Builder code analytics: total attributed txs, multi-code txs, recent 20 entries. |
| `GET` | `/api/attribution/decode?tx_hash=0x...` | None | Decode ERC-8021 builder code suffix from any on-chain transaction. |
| `GET` | `/health` | None | Liveness probe. Returns `{"status": "ok"}`. |
| `GET` | `/health/ready` | None | Readiness probe. Checks DB, wallet balance. Returns 503 if degraded. |
| `GET` | `/api/capabilities` | None | Machine-readable service description (payment protocol, compute limits, trust metrics, rate limits). |
| `GET` | `/api/audit` | Admin key | Structured audit log. Query params: `limit` (default 50), `event_type` (optional filter). |
| `GET` | `/.well-known/agent-card.json` | None | A2A Agent Card for agent-to-agent discovery. Returns name, skills, auth schemes. |
Admin key endpoints require `X-Admin-Key` header matching `ADMIN_API_KEY` env var. Uses `hmac.compare_digest` for constant-time comparison. If `ADMIN_API_KEY` is empty, auth is skipped (dev mode).

## Webhooks

Jobs can optionally include a `webhook_url` parameter in the submit request body. When the job completes or fails, Ouro sends a POST request to that URL with the job results.

### Submit request parameter

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `webhook_url` | string | No | HTTPS URL to receive job result notifications (max 2048 chars). HTTP is allowed only for `localhost`/`127.0.0.1` URLs. |

When `webhook_url` is provided, the submit response includes `"webhook_configured": true`.

### Webhook delivery

Ouro delivers webhooks with 3 attempts using exponential backoff. Each delivery is a `POST` request with the following headers:

| Header | Description |
|--------|-------------|
| `Content-Type` | `application/json` |
| `User-Agent` | `Ouro-Webhook/1.0` |
| `X-Ouro-Delivery` | Unique delivery UUID |
| `X-Ouro-Timestamp` | Unix timestamp (seconds) of the delivery attempt |
| `X-Ouro-Signature-256` | HMAC-SHA256 signature (only present when `WEBHOOK_SECRET` env var is set) |

### Webhook payload

```json
{
  "webhook_event": "job.completed",
  "job_id": "abc123-...",
  "status": "completed",
  "output": "Hello, world!\n",
  "exit_code": 0,
  "runtime_seconds": 4.2,
  "price_usdc": "0.01",
  "submitted_at": "2026-03-16T12:00:00Z",
  "completed_at": "2026-03-16T12:00:04Z"
}
```

The `webhook_event` field is `job.completed` or `job.failed`.

### Signature verification

When the `WEBHOOK_SECRET` environment variable is set, each delivery includes an `X-Ouro-Signature-256` header. Verify it by computing HMAC-SHA256 over `{timestamp}.{body}`:

```python
import hashlib, hmac

timestamp = request.headers["X-Ouro-Timestamp"]
signature = request.headers["X-Ouro-Signature-256"]
body = await request.body()

expected = hmac.new(
    WEBHOOK_SECRET.encode(),
    f"{timestamp}.{body.decode()}".encode(),
    hashlib.sha256
).hexdigest()

assert hmac.compare_digest(f"sha256={expected}", signature)
```

## Slurm proxy endpoints (defined in `deploy/slurm/slurm_proxy.py`, runs on controller:6820)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/slurm/v0.0.38/job/submit` | `X-SLURM-USER-TOKEN` header | Submit job via sbatch, wrapped in Docker container. Always requires `workspace_path` + `entrypoint`. Accepts optional `docker_image` (Docker Hub reference), `entrypoint_cmd` (exec-form command), and `dockerfile_content` (for docker build on worker). Has a transition fallback for legacy `script` payloads (converts to workspace internally). |
| `POST` | `/slurm/v0.0.38/workspace` | `X-SLURM-USER-TOKEN` header | Create workspace on NFS from files. Body: `{workspace_id, mode: "multi_file", files: [{path, content}]}`. Returns `{workspace_path}`. |
| `DELETE` | `/slurm/v0.0.38/workspace/{workspace_id}` | `X-SLURM-USER-TOKEN` header | Delete workspace from NFS after job completion. UUID-validated. |
| `GET` | `/slurm/v0.0.38/allowed-images` | `X-SLURM-USER-TOKEN` header | Return available Docker image aliases and their Docker Hub references. |
| `GET` | `/slurm/v0.0.38/job/{job_id}` | `X-SLURM-USER-TOKEN` header | Get job state via scontrol. Returns state, exit_code, timestamps. |
| `GET` | `/slurm/v0.0.38/job/{job_id}/output` | `X-SLURM-USER-TOKEN` header | Get stdout, stderr, and SHA-256 output hash. |
| `GET` | `/slurm/v0.0.38/nodes` | `X-SLURM-USER-TOKEN` header | Cluster node status via sinfo. Returns node name, state, CPUs, memory. |
| `GET` | `/health` | None | Cluster health check (calls sinfo). |

Also supports v0.0.37 paths for backward compatibility.

## Dashboard proxy routes (in `dashboard/src/app/api/`)

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
| `GET /api/proxy/credits?address=` | `AGENT_URL/api/credits/user?address=` | None | Forwards `X-Admin-Key` (credit balance is wallet-scoped) |
