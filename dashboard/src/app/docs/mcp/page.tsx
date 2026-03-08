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
    ],
    response: `{
  "job_id": "a1b2c3d4-...",
  "status": "pending",
  "submission_mode": "script",
  "price": "$0.0841",
  "message": "Job a1b2c3d4-... submitted successfully."
}`,
  },
  {
    name: "get_job_status",
    description:
      "Check the status of a job. Returns full details including output when completed.",
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
  "output": "Hello world\\n",
  "compute_duration_s": 2.4,
  "price_usdc": 0.0841
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
  "price": "$0.0841",
  "breakdown": {
    "gas_upper_bound": 0.0025,
    "llm_upper_bound": 0.01,
    "compute_cost": 0.0006,
    "setup_cost": 0.0,
    "cost_floor": 0.0131,
    "margin_multiplier": 1.5,
    "demand_multiplier": 1.0,
    "submission_mode": "script",
    "phase": "OPTIMAL"
  },
  "guaranteed_profitable": true
}`,
  },
  {
    name: "get_allowed_images",
    description:
      "Returns the list of available container images for compute jobs. Each image is pre-built with common tools for its ecosystem.",
    params: [],
    response: `{
  "images": [
    { "id": "ouro-ubuntu", "description": "Ubuntu 22.04 base image" },
    { "id": "ouro-python", "description": "Python 3.12 with pip" },
    { "id": "ouro-nodejs", "description": "Node.js 20 LTS" }
  ],
  "default": "ouro-ubuntu"
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
    </>
  );
}
