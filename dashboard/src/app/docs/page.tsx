import Link from "next/link";
import CodeBlock from "@/components/docs/CodeBlock";

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
    file: "~/.claude/mcp.json",
    language: "json" as const,
    code: `{
  "mcpServers": {
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

const PATH_CARDS = [
  {
    href: "/docs/mcp",
    title: "MCP Setup",
    desc: "Set up MCP for Cursor, Claude Code, Claude Desktop, VS Code, Windsurf, and more",
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
          Ouro is a pay-per-use compute service on Base. Send code, pay in USDC,
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
          With the MCP server, this is fully automatic — just call{" "}
          <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">run_job</span>
          {" "}and payment is handled for you.
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
          Set <span className="font-mono text-xs bg-o-bg px-1.5 py-0.5 rounded border border-o-border text-o-text">WALLET_PRIVATE_KEY</span> to your wallet&apos;s hex private key (starts with <span className="font-mono text-xs text-o-text">0x</span>). Paste the config for your client:
        </p>
        <div className="space-y-6">
          {CLIENT_CONFIGS.map((cfg) => (
            <div key={cfg.name}>
              <h3 className="font-display text-sm font-semibold text-o-text mb-2">
                {cfg.name}
              </h3>
              <CodeBlock filename={cfg.file} language={cfg.language} copyText={cfg.code}>
                {cfg.code}
              </CodeBlock>
            </div>
          ))}
        </div>
        <p className="text-sm text-o-textSecondary mt-6">
          Then just say: &quot;Run <span className="text-o-blueText">echo hello world</span> on Ouro&quot;
        </p>
      </section>
    </>
  );
}
