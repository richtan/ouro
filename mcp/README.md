# ouro-mcp

[![npm](https://img.shields.io/npm/v/ouro-mcp)](https://www.npmjs.com/package/ouro-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

Run HPC compute jobs from any AI agent — paid in USDC on Base via [x402](https://www.x402.org/).

## What is Ouro?

Ouro is an autonomous agent that sells high-performance compute on a Slurm cluster. This MCP server lets any AI agent submit jobs, poll for results, and pay automatically — your wallet signs USDC payments locally via x402, so your private key never leaves your machine.

## Quick Start

You need Node.js 18+ and a wallet with USDC on Base.

```bash
npx -y ouro-mcp
```

Add to your MCP client config (works with Cursor, Claude Code, Claude Desktop, VS Code, Windsurf, and any MCP-compatible client):

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

> **Claude Code** also supports: `claude mcp add ouro -- npx -y ouro-mcp`

## Usage Examples

### Run a simple script

```
User: Run a Python script that computes the first 1000 primes

→ run_job(
    script: "python3 -c \"primes = []; n = 2\nwhile len(primes) < 1000:\n  if all(n % p for p in primes): primes.append(n)\n  n += 1\nprint(primes)\"",
    image: "ouro-python"
  )

← { "job_id": "abc123", "price_usdc": "0.01", "status": "pending" }
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

← { "job_id": "def456", "price_usdc": "0.03", "status": "pending" }
```

### Poll for results

```
→ get_job_status(job_id: "abc123")

← { "status": "completed", "output": "[2, 3, 5, 7, 11, ...]", "runtime_seconds": 4.2 }
```

### Check pricing first

```
→ get_price_quote(cpus: 4, time_limit_min: 10)

← { "price_usdc": "0.12", "breakdown": { "base": 0.01, "cpu_multiplier": 4, ... } }
```

## Tools

### `run_job`

Submit a compute job and pay automatically. Returns `job_id` when accepted.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `script` | string | One of `script` or `files` | — | Shell script to execute |
| `files` | array | One of `script` or `files` | — | Array of `{path, content}` objects (can include a Dockerfile) |
| `image` | string | No | `ouro-ubuntu` | Container image to use |
| `cpus` | integer | No | `1` | CPU cores (1–8) |
| `time_limit_min` | integer | No | `1` | Max runtime in minutes |
| `builder_code` | string | No | — | Builder code for [ERC-8021](https://eips.ethereum.org/EIPS/eip-8021) attribution |

### `get_job_status`

Check the status of a submitted job. Returns output when completed.

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

## Container Images

**Prebuilt (instant start):**
- `ouro-ubuntu` — Ubuntu 22.04
- `ouro-python` — Python 3.12 with pip
- `ouro-nodejs` — Node.js 20 LTS

**Custom:** Include a `Dockerfile` in your `files` array to use any Docker Hub image:
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
- [API Docs](https://github.com/richtan/ouro/blob/main/docs/api-reference.md)
- [GitHub](https://github.com/richtan/ouro)
