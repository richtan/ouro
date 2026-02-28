# ouro-mcp

MCP server for **Ouro** — run verifiable HPC jobs from any AI agent, paid via [x402](https://x402.org) USDC on Base.

No install. No private keys on the server. Payment happens in your browser with MetaMask.

## Quick Start (Cursor / Claude Desktop)

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ouro-compute": {
      "url": "https://mcp.ourocompute.com/mcp"
    }
  }
}
```

Restart Cursor. Ask the agent to run a compute job. It returns a one-time payment link — open it, connect MetaMask, pay with USDC on Base, and the agent picks up the result automatically.

## How It Works

1. You ask your AI agent: *"Run `echo hello world` on the Ouro cluster"*
2. Agent calls `run_compute_job` — gets back a payment link + price
3. Agent shows you the link. You open it in your browser.
4. Payment page: connect MetaMask, approve USDC payment on Base
5. Job runs on the Slurm cluster. Agent gets stdout, stderr, and an on-chain proof.
6. **Your private key never leaves your browser.**

## Available Tools

| Tool | Description |
|---|---|
| **run_compute_job** | Submit a job. Returns payment link + session_id. User pays in browser. |
| **get_job_status** | Poll a job or session by ID. Returns output + proof when complete. |
| **get_price_quote** | Check pricing without paying. |
| **get_api_endpoint** | Get the direct API URL and body schema for programmatic access. |

The agent API is x402-compatible — any HTTP client that handles the x402 402→sign→retry flow can submit and pay for jobs programmatically without the MCP server. Use `get_api_endpoint` to discover the URL and expected request format.

## Self-Hosted

```bash
cd mcp-server && pip install -e .
```

| Variable | Required | Description |
|---|---|---|
| `OURO_API_URL` | Yes | Agent API base URL |
| `PUBLIC_URL` | No | Public URL of this server (for payment links) |

```bash
export OURO_API_URL="https://api.ourocompute.com"
ouro-mcp
```

## Dashboard

View live job status, P&L, and cluster health at:
**https://ourocompute.com**

## License

MIT
