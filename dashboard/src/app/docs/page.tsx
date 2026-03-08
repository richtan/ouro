import Link from "next/link";
import CodeBlock from "@/components/docs/CodeBlock";

const MCP_JSON = `{
  "mcpServers": {
    "ouro-compute": {
      "url": "https://mcp.ourocompute.com/mcp"
    }
  }
}`;

const MCP_TOOLS = [
  { name: "run_compute_job", description: "Submit a script and get a payment link" },
  { name: "get_job_status", description: "Poll for results" },
  { name: "get_price_quote", description: "Check pricing before committing" },
  { name: "get_payment_requirements", description: "Get x402 payment header for autonomous signing" },
  { name: "submit_and_pay", description: "Submit with a pre-signed x402 payment" },
  { name: "get_api_endpoint", description: "Get the direct API URL and schema" },
];

export default function DocsGetStarted() {
  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Get Started
        </h1>
        <p className="text-sm text-o-textSecondary mt-1">
          Add Ouro to your AI tool and run your first HPC job in 30 seconds.
        </p>
      </div>

      {/* What is Ouro */}
      <section className="mb-10">
        <p className="text-sm text-o-textSecondary leading-relaxed">
          Ouro is an autonomous agent on Base that sells HPC compute via{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">x402</span>{" "}
          and executes jobs on a real Slurm cluster.
          No accounts, no API keys — just MCP or HTTP.
        </p>
      </section>

      {/* MCP Config */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          1. Add the MCP server
        </h2>
        <p className="text-sm text-o-textSecondary mb-4">
          Paste this into your Cursor, Claude Desktop, or custom agent MCP config:
        </p>
        <CodeBlock filename="mcp.json" copyText={MCP_JSON}>
          <span className="text-o-muted">{"{"}</span>{"\n"}
          <span className="text-o-muted">{"  "}&quot;mcpServers&quot;: {"{"}</span>{"\n"}
          <span className="text-o-muted">{"    "}&quot;</span>
          <span className="text-o-textSecondary">ouro-compute</span>
          <span className="text-o-muted">&quot;: {"{"}</span>{"\n"}
          <span className="text-o-muted">{"      "}&quot;</span>
          <span className="text-o-textSecondary">url</span>
          <span className="text-o-muted">&quot;: &quot;</span>
          <span className="text-o-blueText">https://mcp.ourocompute.com/mcp</span>
          <span className="text-o-muted">&quot;</span>{"\n"}
          <span className="text-o-muted">{"    }"}</span>{"\n"}
          <span className="text-o-muted">{"  }"}</span>{"\n"}
          <span className="text-o-muted">{"}"}</span>
        </CodeBlock>
      </section>

      {/* First job */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          2. Run your first job
        </h2>
        <p className="text-sm text-o-textSecondary mb-4">
          In Cursor or Claude Desktop, just say:
        </p>
        <div className="bg-o-surface border border-o-border rounded-xl px-5 py-4">
          <p className="font-mono text-xs text-o-text">
            &quot;Run <span className="text-o-blueText">echo hello world</span> on Ouro Compute&quot;
          </p>
        </div>
        <p className="text-sm text-o-textSecondary mt-4">
          Your AI tool will call{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">run_compute_job</span>,
          show you a payment link, and once you pay with USDC on Base, poll for results automatically.
        </p>
      </section>

      {/* Available tools */}
      <section className="border-t border-o-border pt-10 mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Available MCP Tools
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {MCP_TOOLS.map((tool) => (
            <Link
              key={tool.name}
              href="/docs/mcp"
              className="bg-o-surface border border-o-border rounded-lg px-3.5 py-3 hover:border-o-borderHover transition-colors"
            >
              <span className="font-mono text-xs text-o-text">{tool.name}</span>
              <p className="text-xs text-o-muted mt-1">{tool.description}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* Next steps */}
      <section className="border-t border-o-border pt-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Next Steps
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[
            { href: "/docs/mcp", title: "MCP Tools Reference", desc: "Full schemas and example responses for all 6 tools" },
            { href: "/docs/agent", title: "Build an Autonomous Agent", desc: "TypeScript agent with x402 payment flow" },
            { href: "/docs/api", title: "REST API", desc: "Direct HTTP endpoints with x402 payments" },
          ].map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="bg-o-surface border border-o-border rounded-lg px-4 py-3.5 hover:border-o-borderHover transition-colors group"
            >
              <span className="text-sm font-display font-semibold text-o-text group-hover:text-o-blueText transition-colors">
                {item.title}
              </span>
              <p className="text-xs text-o-textSecondary mt-1">{item.desc}</p>
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
