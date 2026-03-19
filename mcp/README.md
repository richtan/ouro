# ouro-mcp

[![npm](https://img.shields.io/npm/v/ouro-mcp)](https://www.npmjs.com/package/ouro-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

Run compute jobs from any AI agent — paid in USDC on Base via [x402](https://www.x402.org/).

## What is Ouro?

Ouro is a pay-per-use compute service on Base. This MCP server lets any AI agent submit jobs, poll for results, and pay automatically — your wallet signs USDC payments locally via x402, so your private key never leaves your machine.

## Container Constraints

Jobs run in Docker containers with these restrictions:

- **No network at runtime** — containers use `--network none`. You cannot `pip install`, `npm install`, `curl`, or `git clone` in your script. Use `setup_commands` to install dependencies at build time (which has network access).
- **Mostly read-only filesystem** — writable paths: `/workspace` (current directory, ephemeral), `/tmp` (100 MB, ephemeral), `/scratch` (1 GB, persisted with `mount_storage: true`). All other paths are read-only.
- **Memory: 1.6 GB per CPU** — jobs exceeding this are killed.

## Quick Start

### Prerequisites

- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **Wallet private key** — hex string starting with `0x`. Export from MetaMask (Account Details → Export Private Key) or generate with `cast wallet new`
- **USDC on Base** — Bridge via [bridge.base.org](https://bridge.base.org) or buy on [Coinbase](https://www.coinbase.com). Jobs start at ~$0.01

### Setup by client

**Cursor** — add to `.cursor/mcp.json`:

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

**Claude Code** — run in terminal:

```bash
claude mcp add ouro --transport stdio -e WALLET_PRIVATE_KEY=0x... -- npx -y ouro-mcp
```

**Claude Desktop** — add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

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

**VS Code** — add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "ouro": {
      "command": "npx",
      "args": ["-y", "ouro-mcp"],
      "env": { "WALLET_PRIVATE_KEY": "0x..." }
    }
  }
}
```

**Other MCP clients** — use command `npx -y ouro-mcp` with env var `WALLET_PRIVATE_KEY=0x...`.

## Usage Examples

### Run a simple script

```
User: Run a Python script that computes the first 1000 primes

→ run_job(
    script: "python3 -c \"primes = []; n = 2\nwhile len(primes) < 1000:\n  if all(n % p for p in primes): primes.append(n)\n  n += 1\nprint(primes)\"",
    image: "ouro-python"
  )

← {
    "job_id": "abc123",
    "status": "pending",
    "price": "$0.0100",
    "paid_with_credit": false,
    "credit_applied": 0,
    "webhook_configured": false,
    "mount_storage": false,
    "profitability": { "guaranteed": true, "estimated_profit_pct": 50.0 }
  }
```

### Multi-file project with custom Dockerfile

```
→ run_job(
    files: [
      { "path": "main.py", "content": "import numpy as np\nprint(np.random.rand(3, 3))" },
      { "path": "Dockerfile", "content": "FROM python:3.12-slim\nRUN pip install numpy\nENTRYPOINT [\"python\", \"main.py\"]" }
    ],
    image: "python:3.12-slim",
    cpus: 2,
    time_limit_min: 5
  )

← {
    "job_id": "def456",
    "status": "pending",
    "price": "$0.0300",
    "paid_with_credit": false,
    "credit_applied": 0,
    "webhook_configured": false,
    "mount_storage": false,
    "profitability": { "guaranteed": true, "estimated_profit_pct": 50.0 }
  }
```

### Create files and run a command

```
→ run_job(
    script: "python3 analyze.py",
    files: [
      { "path": "analyze.py", "content": "import json\ndata = {'result': 42}\nprint(json.dumps(data))" }
    ],
    image: "ouro-python"
  )

← {
    "job_id": "xyz789",
    "status": "pending",
    "price": "$0.0100",
    "paid_with_credit": false,
    "credit_applied": 0,
    "webhook_configured": false,
    "mount_storage": false,
    "profitability": { "guaranteed": true, "estimated_profit_pct": 50.0 }
  }
```

### Install packages with setup_commands

```
→ run_job(
    script: "python3 main.py",
    files: [
      { "path": "main.py", "content": "import numpy as np\nprint(np.random.rand(3, 3))" }
    ],
    image: "ouro-python",
    setup_commands: ["pip install numpy"],
    time_limit_min: 3
  )

← {
    "job_id": "sc1234",
    "status": "pending",
    "price": "$0.0200",
    ...
  }
```

### Wait for results

```
→ get_job_status(job_id: "abc123")
  # Streams SSE events internally, returns when the job finishes

← {
    "id": "abc123",
    "status": "completed",
    "price_usdc": 0.01,
    "submitted_at": "2025-01-01T00:00:00+00:00",
    "completed_at": "2025-01-01T00:00:04+00:00",
    "output": "[2, 3, 5, 7, 11, ...]",
    "error_output": "",
    "failure_reason": null,
    "compute_duration_s": 4.2
  }
```

### Run multiple jobs in parallel

```
User: Benchmark Python vs Node vs Rust for computing the first 10,000 primes

→ run_job(script: "python3 -c \"...\"", image: "ouro-python")
← { "job_id": "py001", ... }

→ run_job(script: "node -e \"...\"", image: "ouro-nodejs")
← { "job_id": "nd002", ... }

→ run_job(script: "./primes", image: "ouro-ubuntu")
← { "job_id": "rs003", ... }

# Call get_job_status for all 3 as parallel tool calls —
# all results return when the slowest job finishes

→ get_job_status(job_id: "py001")   ┐
→ get_job_status(job_id: "nd002")   ├── parallel tool calls
→ get_job_status(job_id: "rs003")   ┘

← { "id": "py001", "status": "completed", "output": "...", "compute_duration_s": 4.2 }
← { "id": "nd002", "status": "completed", "output": "...", "compute_duration_s": 1.8 }
← { "id": "rs003", "status": "completed", "output": "...", "compute_duration_s": 0.3 }
```

### Persistent storage (write in job 1, read in job 2)

```
→ run_job(
    script: "echo 'trained model weights' > /scratch/model.pt",
    mount_storage: true
  )

← { "job_id": "ghi789", "status": "pending", "price": "$0.0100", "mount_storage": true, ... }

→ get_job_status(job_id: "ghi789")
← { "status": "completed", "output": "", ... }

→ run_job(
    script: "cat /scratch/model.pt",
    mount_storage: true
  )

← { "job_id": "jkl012", "status": "pending", "price": "$0.0100", "mount_storage": true, ... }

→ get_job_status(job_id: "jkl012")
← { "status": "completed", "output": "trained model weights\n", ... }
```

### Check pricing first

```
→ get_price_quote(cpus: 4, time_limit_min: 10)

← {
    "price": "$0.0100",
    "breakdown": {
      "gas_upper_bound": 0.0025,
      "llm_upper_bound": 0.01,
      "compute_cost": 0.0002,
      "setup_cost": 0.0,
      "cost_floor": 0.0127,
      "margin_multiplier": 1.5,
      "demand_multiplier": 1.0,
      "phase": "OPTIMAL",
      "min_profit_pct": 20.0,
      "safety_factor": 1.25
    }
  }
```

## Tools

### `run_job`

Submit a compute job and pay automatically. Returns `job_id` when accepted.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `script` | string | At least one of `script`, `files`, or both | — | Shell command(s) to execute. Use alone for simple jobs, or combine with files |
| `files` | array | At least one of `script`, `files`, or both | — | Array of `{path, content}` objects. Combine with script to create files + run a command, or include a Dockerfile |
| `image` | string | No | `ouro-ubuntu` | Container image to use |
| `cpus` | integer | No | `1` | CPU cores (1–8) |
| `time_limit_min` | integer | No | `1` | Max runtime in minutes |
| `webhook_url` | string | No | — | URL to receive a POST notification when the job completes or fails |
| `setup_commands` | string[] | No | — | Shell commands to run during container build (with network). Auto-generates a Dockerfile. Cannot combine with a Dockerfile in files. Build adds ~30s-2min. |
| `mount_storage` | boolean | No | `false` | Mount persistent `/scratch` volume (read-write). Files persist between jobs. |

### `get_job_status`

Check the status of a submitted job. Uses SSE streaming to wait for the job to finish — call it once and it returns when the job reaches a terminal state (`completed` or `failed`). No manual polling needed. Authentication is handled automatically by the MCP server.

**Tip:** If you have multiple jobs, call `get_job_status` for each one as parallel tool calls — all results return in the time of the slowest job instead of waiting sequentially.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | Yes | Job ID returned by `run_job` |

### `get_price_quote`

Get a price quote without submitting or paying.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `cpus` | integer | No | `1` | CPU cores |
| `time_limit_min` | integer | No | `1` | Max runtime in minutes |
| `submission_mode` | string | No | `script` | `script` or `multi_file` |

### `get_allowed_images`

List available container images. No parameters.

### `list_storage`

List files in your persistent storage. Shows quota usage and file listing. No parameters. Authentication is handled automatically by the MCP server.

### `delete_storage_file`

Delete a file or directory from your persistent storage. Signs an EIP-191 message automatically to prove wallet ownership.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | File path relative to `/scratch` (e.g. `models/checkpoint.pt`) |

## Persistent Storage

Each wallet gets a persistent `/scratch` volume (1 GB free tier) that survives between jobs. Use it for model checkpoints, datasets, build caches, or any data you want to reuse across runs.

- **Mount**: pass `mount_storage: true` to `run_job` — the volume appears at `/scratch` inside the container (read-write)
- **List files**: call `list_storage` to see quota usage and file listing
- **Delete files**: call `delete_storage_file` with a relative path
- **File count limit**: max 10,000 files per wallet (enforced by filesystem quotas)
- Jobs that exceed the file limit see `Disk quota exceeded` errors
- Use `list_storage` to check current file count; use `delete_storage_file` to free up space
- **TTL**: storage is cleaned up after 90 days of inactivity (warning at 60 days)

## Container Images

**Prebuilt (instant start, stdlib only — no third-party packages):**
- `ouro-ubuntu` — Ubuntu 22.04: bash, coreutils
- `ouro-python` — Python 3.12: stdlib only, use `setup_commands` for pip packages
- `ouro-nodejs` — Node.js 20: core runtime only, use `setup_commands` for npm packages

**With dependencies:** Use `setup_commands` to install packages at build time:
```
run_job(script: "python3 main.py", image: "ouro-python", setup_commands: ["pip install numpy pandas"])
```

**Custom:** Include a `Dockerfile` in your `files` array for full control:
```dockerfile
FROM python:3.12-slim
RUN pip install numpy pandas
ENTRYPOINT ["python", "main.py"]
```

## Pricing

Jobs start at ~$0.01 USDC (1 CPU, 1 minute). Price scales with CPUs and time limit. Ouro uses dynamic pricing — use `get_price_quote` to check the current price before submitting.

Jobs that finish early receive proportional credits for unused compute time, automatically applied to future jobs.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `WALLET_PRIVATE_KEY` | Yes | Hex private key (starting with `0x`) for USDC payment signing |
| `OURO_API_URL` | No | API base URL (default: `https://api.ourocompute.com`) |

## Security

Your private key **never leaves your machine**. The MCP server runs locally as a stdio process and only uses the key to sign USDC payment authorizations via x402. No keys are sent to any remote server.

## Links

- [Dashboard](https://ourocompute.com) — live P&L, job stats, submit jobs
- [API Docs](https://ourocompute.com/docs/api)
- [GitHub](https://github.com/richtan/ouro)
