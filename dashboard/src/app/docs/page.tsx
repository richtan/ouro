import Link from "next/link";
import CodeBlock from "@/components/docs/CodeBlock";

const MCP_JSON = `{
  "mcpServers": {
    "ouro-compute": {
      "url": "https://mcp.ourocompute.com/mcp"
    }
  }
}`;

const PATH_CARDS = [
  {
    href: "/docs/mcp",
    title: "Cursor / Claude Desktop",
    desc: "Add one MCP config line and start running jobs from your AI tool",
  },
  {
    href: "/docs/agent",
    title: "Build an Agent",
    desc: "TypeScript agent that pays for compute with its own wallet",
  },
  {
    href: "/docs/api",
    title: "REST API",
    desc: "Direct HTTP endpoints with curl examples",
  },
  {
    href: "/submit",
    title: "Web Dashboard",
    desc: "Submit jobs and pay from your browser — no code needed",
  },
];

export default function DocsGetStarted() {
  return (
    <>
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Get Started
        </h1>
        <p className="text-sm text-o-textSecondary mt-1">
          Pay-per-use compute on Base. Send code, pay in USDC, get results.
        </p>
      </div>

      {/* What is Ouro */}
      <section className="mb-10">
        <p className="text-sm text-o-textSecondary leading-relaxed">
          Ouro Compute is a pay-per-use compute service on Base. Send code, pay in USDC,
          get results. No accounts, no API keys — your wallet is your identity.
        </p>
      </section>

      {/* How Payment Works */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          How Payment Works
        </h2>
        <p className="text-sm text-o-textSecondary leading-relaxed mb-3">
          Ouro uses{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">x402</span>
          , a payment protocol built on HTTP 402 (Payment Required). Here&apos;s how it works:
        </p>
        <ol className="text-sm text-o-textSecondary leading-relaxed space-y-2 ml-5 list-decimal mb-3">
          <li>You send a request to the API without any payment.</li>
          <li>The server responds with <span className="font-mono text-xs text-o-text">402 Payment Required</span> and the price.</li>
          <li>Your code signs a USDC payment locally (your private key never leaves your machine).</li>
          <li>You re-send the request with the signed payment attached — done.</li>
        </ol>
        <p className="text-sm text-o-textSecondary leading-relaxed">
          If you&apos;re building an agent, the{" "}
          <Link href="/docs/agent" className="text-o-blueText hover:underline">
            <span className="font-mono text-xs">@x402/fetch</span>
          </Link>{" "}
          package handles this entire flow automatically.
          See the full flow with curl examples on the{" "}
          <Link href="/docs/api#payment-flow" className="text-o-blueText hover:underline">
            API page
          </Link>.
        </p>
      </section>

      {/* Choose Your Path */}
      <section className="mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Choose Your Path
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {PATH_CARDS.map((item) => (
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

      {/* Quick Start: MCP */}
      <section className="border-t border-o-border pt-10 mb-10">
        <h2 className="font-display text-lg font-bold text-o-text mb-4">
          Quick Start: MCP
        </h2>
        <p className="text-sm text-o-textSecondary mb-4">
          The fastest path — paste this into your Cursor, Claude Desktop, or custom agent MCP config:
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
        <p className="text-sm text-o-textSecondary mt-4">
          Then just say: &quot;Run <span className="text-o-blueText">echo hello world</span> on Ouro Compute&quot;
        </p>
      </section>
    </>
  );
}
