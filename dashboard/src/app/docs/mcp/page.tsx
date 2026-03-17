import Link from "next/link";
import CodeBlock from "@/components/docs/CodeBlock";
import ParamTable from "@/components/docs/ParamTable";
import McpSetupTabs from "@/components/docs/McpSetupTabs";

const CLIENT_CONFIGS = [
  {
    name: "Cursor",
    file: ".cursor/mcp.json",
    language: "json" as const,
    code: `{
  "mcpServers": {
    "ouro": {
      "command": "npx",
      "args": ["-y", "ouro-mcp"],
      "env": { "WALLET_PRIVATE_KEY": "0x..." }
    }
  }
}`,
  },
  {
    name: "Claude Code",
    file: "Terminal",
    language: "bash" as const,
    code: `claude mcp add ouro --transport stdio -e WALLET_PRIVATE_KEY=0x... -- npx -y ouro-mcp`,
  },
  {
    name: "Claude Desktop",
    file: "claude_desktop_config.json",
    language: "json" as const,
    code: `{
  "mcpServers": {
    "ouro": {
      "command": "npx",
      "args": ["-y", "ouro-mcp"],
      "env": { "WALLET_PRIVATE_KEY": "0x..." }
    }
  }
}`,
  },
  {
    name: "VS Code",
    file: ".vscode/mcp.json",
    language: "json" as const,
    code: `{
  "servers": {
    "ouro": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "ouro-mcp"],
      "env": { "WALLET_PRIVATE_KEY": "0x..." }
    }
  }
}`,
  },
  {
    name: "Windsurf",
    file: "~/.codeium/windsurf/mcp_config.json",
    language: "json" as const,
    code: `{
  "mcpServers": {
    "ouro": {
      "command": "npx",
      "args": ["-y", "ouro-mcp"],
      "env": { "WALLET_PRIVATE_KEY": "0x..." }
    }
  }
}`,
  },
  {
    name: "OpenClaw",
    file: "~/.openclaw/openclaw.json",
    language: "json" as const,
    code: `{
  "mcpServers": {
    "ouro": {
      "command": "npx",
      "args": ["-y", "ouro-mcp"],
      "env": { "WALLET_PRIVATE_KEY": "0x..." }
    }
  }
}`,
  },
  {
    name: "OpenAI Agents SDK",
    file: "agent.py",
    language: "python" as const,
    code: `from agents.mcp import MCPServerStdio

server = MCPServerStdio(
    command="npx",
    args=["-y", "ouro-mcp"],
    env={"WALLET_PRIVATE_KEY": "0x..."},
)`,
  },
];

const TOOLS = [
  {
    name: "run_job",
    description:
      "Submit a compute job and pay automatically. Signs USDC payment via x402 from your wallet. Returns job_id when accepted.",
    params: [
      { name: "script", type: "string", description: "Shell script to execute (use this OR files)" },
      { name: "files", type: "array", description: "Array of {path, content} file objects (can include a Dockerfile)" },
      { name: "image", type: "string", description: "Container image (default: ouro-ubuntu)" },
      { name: "cpus", type: "int", description: "CPU cores, 1-8 (default 1)" },
      { name: "time_limit_min", type: "int", description: "Max runtime in minutes (default 1)" },
      { name: "webhook_url", type: "string", description: "URL to receive POST notification on job completion/failure (optional)" },
      { name: "mount_storage", type: "boolean", description: "Mount persistent /scratch volume for this job (default: false). Limits: 1 GB, max 10,000 files." },
    ],
    response: `{
  "job_id": "a1b2c3d4-...",
  "status": "pending",
  "price": "$0.0100",
  "paid_with_credit": false,
  "credit_applied": 0,
  "webhook_configured": false,
  "mount_storage": false,
  "profitability": { "guaranteed": true, "estimated_profit_pct": 50.0 }
}`,
  },
  {
    name: "get_job_status",
    description:
      "Check the status of a job. Uses SSE streaming to wait for completion — call once and it returns when the job finishes. Returns full details including output.",
    params: [
      {
        name: "job_id",
        type: "string",
        description: "Job ID to check",
        required: true,
      },
    ],
    response: `{
  "id": "a1b2c3d4-...",
  "status": "completed",
  "price_usdc": 0.01,
  "submitted_at": "2025-01-01T00:00:00+00:00",
  "completed_at": "2025-01-01T00:00:04+00:00",
  "output": "Hello world\\n",
  "error_output": "",
  "failure_reason": null,
  "compute_duration_s": 2.4
}`,
  },
  {
    name: "get_price_quote",
    description: "Get a price quote without submitting or paying. Use this to check pricing before committing.",
    params: [
      { name: "cpus", type: "int", description: "Number of CPU cores (default 1, max 8)" },
      { name: "time_limit_min", type: "int", description: "Max runtime in minutes (default 1)" },
      { name: "submission_mode", type: "string", description: "Submission mode: script, multi_file (default: script)" },
    ],
    response: `{
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
}`,
  },
  {
    name: "get_allowed_images",
    description:
      "Returns the list of available container images for compute jobs. Each image is pre-built with common tools for its ecosystem.",
    params: [],
    response: `{
  "payment_protocol": "x402",
  "prebuilt_images": {
    "ouro-ubuntu": "Ubuntu 22.04 base image",
    "ouro-python": "Python 3.12 with pip",
    "ouro-nodejs": "Node.js 20 LTS"
  },
  "custom_images": "Any Docker Hub image via Dockerfile",
  "max_cpus": 8,
  "max_time_limit_min": 60,
  ...
}`,
  },
  {
    name: "list_storage",
    description:
      "List files in your persistent storage volume. Shows quota usage, file count, and max file limit. No parameters — uses the wallet from your WALLET_PRIVATE_KEY.",
    params: [],
    response: `{
  "wallet": "0x1234...abcd",
  "tier": "free",
  "quota_bytes": 1073741824,
  "used_bytes": 524288,
  "file_count": 3,
  "max_files": 10000,
  "files": [
    { "path": "model.pt", "size": 524288, "modified": "2025-01-01T00:00:00Z" }
  ]
}`,
  },
  {
    name: "delete_storage_file",
    description:
      "Delete a file or directory from your persistent storage. Automatically signs an EIP-191 message to prove wallet ownership.",
    params: [
      {
        name: "path",
        type: "string",
        description: "File path relative to /scratch (e.g. 'models/checkpoint.pt')",
        required: true,
      },
    ],
    response: `{
  "deleted": "models/checkpoint.pt"
}`,
  },
];

export default function McpPage() {
  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          MCP Setup & Tools
        </h1>
        <p className="text-sm text-o-textSecondary mt-1">
          Install the MCP server and explore available tools.
        </p>
      </div>

      {/* Setup section */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Setup
        </h2>
        <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
          Add the Ouro MCP server to your client. Set{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">WALLET_PRIVATE_KEY</span>
          {" "}to your wallet&apos;s hex private key (starts with{" "}
          <span className="font-mono text-xs text-o-text">0x</span>).
          Your key never leaves your machine.
        </p>
        <McpSetupTabs configs={CLIENT_CONFIGS} />
        <p className="text-sm text-o-textSecondary mt-4">
          Then just say: &quot;Run <span className="text-o-blueText">echo hello world</span> on Ouro&quot;
        </p>
      </section>

      {/* Tools Reference */}
      <section className="border-t border-o-border pt-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-6">
          Tools Reference
        </h2>

        {TOOLS.map((tool, i) => (
          <div
            key={tool.name}
            className={i > 0 ? "border-t border-o-border mt-10 pt-10" : ""}
          >
            <h3 className="font-display text-lg font-bold text-o-text mb-1">
              <span className="font-mono">{tool.name}</span>
            </h3>
            <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
              {tool.description}
            </p>

            {tool.params.length > 0 && (
              <div className="mb-4">
                <h4 className="font-display text-sm font-semibold text-o-text mb-3">
                  Parameters
                </h4>
                <ParamTable params={tool.params} />
              </div>
            )}

            <h4 className="font-display text-sm font-semibold text-o-text mb-3">
              Example Response
            </h4>
            <CodeBlock filename="response.json" language="json" copyText={tool.response}>
              {tool.response}
            </CodeBlock>
          </div>
        ))}
      </section>

      {/* Storage limits */}
      <section className="border-t border-o-border mt-10 pt-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Storage Limits
        </h2>
        <div className="text-sm text-o-textSecondary leading-relaxed space-y-2">
          <p>
            Each wallet gets <span className="text-o-text font-mono text-xs">1 GB</span> of persistent storage
            with a maximum of <span className="text-o-text font-mono text-xs">10,000 files</span>.
          </p>
          <p>
            Exceeding the file limit causes{" "}
            <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
              Disk quota exceeded
            </span>{" "}
            errors inside the container. Use{" "}
            <span className="font-mono text-xs text-o-text">list_storage</span> to check usage and{" "}
            <span className="font-mono text-xs text-o-text">delete_storage_file</span> to free space.
          </p>
        </div>
      </section>

      {/* Payment flow */}
      <section className="border-t border-o-border mt-10 pt-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Payment Flow
        </h2>
        <p className="text-sm text-o-textSecondary leading-relaxed">
          Payment is fully automatic. When you call{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">
            run_job
          </span>
          , the MCP server signs a USDC payment from your wallet via x402 and submits the job in one step. Your private key never leaves your machine.
        </p>
        <p className="text-sm text-o-textSecondary leading-relaxed mt-3">
          If your wallet has credits from a previous failed job, they&apos;re applied automatically — reducing or eliminating the payment.
          See the{" "}
          <Link href="/docs/api#payment-flow" className="text-o-blueText hover:underline">
            full payment flow with curl examples
          </Link>{" "}
          on the API page.
        </p>
      </section>

      {/* Bottom nav */}
      <div className="border-t border-o-border mt-12 pt-6 flex justify-between">
        <Link
          href="/docs"
          className="text-sm text-o-blueText hover:underline flex items-center gap-1"
        >
          <span aria-hidden="true">&larr;</span> Get Started
        </Link>
        <Link
          href="/docs/api"
          className="text-sm text-o-blueText hover:underline flex items-center gap-1"
        >
          REST API <span aria-hidden="true">&rarr;</span>
        </Link>
      </div>
    </>
  );
}
