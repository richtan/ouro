import Link from "next/link";
import CodeBlock from "@/components/docs/CodeBlock";
import ParamTable from "@/components/docs/ParamTable";

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
      { name: "builder_code", type: "string", description: "Builder code for ERC-8021 attribution (optional)" },
      { name: "webhook_url", type: "string", description: "URL to receive POST notification on job completion/failure (optional)" },
      { name: "mount_storage", type: "boolean", description: "Mount persistent /storage volume for this job (default: false)" },
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
      "List files in your persistent storage volume. Shows quota usage and file listing. No parameters — uses the wallet from your WALLET_PRIVATE_KEY.",
    params: [],
    response: `{
  "wallet": "0x1234...abcd",
  "tier": "free",
  "quota_bytes": 1073741824,
  "used_bytes": 524288,
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
        description: "File path relative to /storage (e.g. 'models/checkpoint.pt')",
        required: true,
      },
    ],
    response: `{
  "deleted": "models/checkpoint.pt"
}`,
  },
];

export default function McpToolsPage() {
  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          MCP Tools Reference
        </h1>
        <p className="text-sm text-o-textSecondary mt-1">
          Reference for all MCP tools — works with any MCP-compatible client.
        </p>
      </div>

      {/* Setup callout */}
      <div className="bg-o-surface border border-o-border rounded-lg px-4 py-3 mb-8">
        <p className="text-sm text-o-textSecondary">
          Need to set up MCP?{" "}
          <Link href="/docs" className="text-o-blueText hover:underline">
            See the Get Started page
          </Link>{" "}
          for setup instructions.
        </p>
      </div>

      {/* Tool sections */}
      {TOOLS.map((tool, i) => (
        <section
          key={tool.name}
          className={i > 0 ? "border-t border-o-border mt-10 pt-10" : ""}
        >
          <h2 className="font-display text-lg font-bold text-o-text mb-1">
            <span className="font-mono">{tool.name}</span>
          </h2>
          <p className="text-sm text-o-textSecondary leading-relaxed mb-4">
            {tool.description}
          </p>

          {tool.params.length > 0 && (
            <div className="mb-4">
              <h3 className="font-display text-sm font-semibold text-o-text mb-3">
                Parameters
              </h3>
              <ParamTable params={tool.params} />
            </div>
          )}

          <h3 className="font-display text-sm font-semibold text-o-text mb-3">
            Example Response
          </h3>
          <CodeBlock filename="response.json" language="json" copyText={tool.response}>
            {tool.response}
          </CodeBlock>
        </section>
      ))}

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

      {/* Next page */}
      <div className="border-t border-o-border mt-12 pt-6 flex justify-end">
        <Link
          href="/docs/api"
          className="text-sm text-o-blueText hover:underline flex items-center gap-1"
        >
          REST API <span aria-hidden="true">→</span>
        </Link>
      </div>
    </>
  );
}
