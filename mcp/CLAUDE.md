# MCP Server (ouro-mcp)

Local MCP server that lets AI agents submit HPC jobs and pay with USDC via x402.

## Build & Dev

```bash
npm run build          # tsc → dist/
npm run dev            # tsx watch src/index.ts
npm start              # node dist/index.js
```

## Tool → API Endpoint Mapping

| MCP Tool | HTTP Method | Agent Endpoint | Notes |
|----------|-------------|----------------|-------|
| `run_job` | `POST` | `/api/compute/submit` | x402 paid via `@x402/fetch` |
| `get_job_status` | `GET` | `/api/jobs/{id}` + `/api/jobs/{id}/events` (SSE) | Checks status, then streams SSE if still running |
| `get_price_quote` | `GET` | `/api/price?cpus=&time_limit_min=&submission_mode=` | Public, no auth |
| `get_allowed_images` | `GET` | `/api/capabilities` | Public, no auth |
| `list_storage` | `GET` | `/api/storage?wallet=&signature=&timestamp=` | EIP-191 signed |
| `delete_storage_file` | `DELETE` | `/api/storage/files?wallet=&path=&signature=&timestamp=` | EIP-191 signed |

## setup_commands Transformation

When `setup_commands` is provided to `run_job`, the MCP server auto-generates a Dockerfile and `_run.sh` entrypoint, then sends the job as a normal Dockerfile submission. This is purely an MCP-side transformation — no API changes. The API sees a standard `files` submission with a Dockerfile.

## Version Locations

Version must match across these 3 files:

1. `mcp/package.json` → `"version"` (source of truth for npm)
2. `mcp/src/index.ts` → `McpServer({ version: "..." })` (reported to MCP clients)
3. `.mcp/server.json` → `"version"` (MCP Registry manifest)

## Publishing Checklist

1. Update version in all 3 locations above
2. `npm run build`
3. `npm publish`

## Keep in Sync

When modifying tools in `src/index.ts`, also update:

- `mcp/README.md` — tool docs, response examples, parameter tables
- `mcp/CLAUDE.md` — tool → endpoint mapping table (this file)
- MCP instructions string in `src/index.ts` (lines ~105-123)
- Root `CLAUDE.md` — Services table (MCP Server row), Project Structure (mcp/ line)
- `dashboard/src/app/docs/mcp/page.tsx` — MCP tools reference page
- `docs/architecture.md` — MCP tool list in project tree (line ~89)
