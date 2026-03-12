"use client";

import { useState } from "react";
import Link from "next/link";
import { useStats } from "@/hooks/useData";
import { useInView } from "@/hooks/useInView";

function GithubIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Terminal — x402 HTTP flow                                          */
/* ------------------------------------------------------------------ */

const CLI_COMMAND = "claude mcp add ouro --transport stdio -e WALLET_PRIVATE_KEY=0x... -- npx -y ouro-mcp";

const MCP_JSON = `{
  "mcpServers": {
    "ouro": {
      "command": "npx",
      "args": ["-y", "ouro-mcp"],
      "env": { "WALLET_PRIVATE_KEY": "0x..." }
    }
  }
}`;

const TERM_LINES: { text: string; color: string; delay: number; parts?: { text: string; color: string }[] }[] = [
  { text: "...", color: "text-o-muted", delay: 0 },
  { text: "", color: "", delay: 0, parts: [
    { text: "Agent: ", color: "text-o-blueText" },
    { text: "I need to train the model. Let me run it on Ouro.", color: "text-o-text" },
  ]},
  { text: "", color: "", delay: 0 },
  { text: "\u26a1 run_job", color: "text-o-blueText", delay: 400 },
  { text: '  script: "python3 train.py --epochs 50"', color: "text-o-text", delay: 500 },
  { text: "  cpus: 2", color: "text-o-text", delay: 560 },
  { text: "", color: "", delay: 0 },
  { text: "\u21b3 paid $0.0841 USDC via x402 \u00b7 job f2a9c1e8\u2026", color: "text-o-amber", delay: 900 },
  { text: "", color: "", delay: 0 },
  { text: "\u26a1 get_job_status", color: "text-o-blueText", delay: 1300 },
  { text: '  job_id: "f2a9c1e8\u2026"', color: "text-o-text", delay: 1400 },
  { text: "", color: "", delay: 0 },
  { text: "\u2713 completed \u00b7 accuracy: 98.7%", color: "text-o-green", delay: 1800 },
  { text: "...", color: "text-o-muted", delay: 2000 },
];

function Terminal() {
  return (
    <div className="bg-o-surface border border-o-borderHover rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-o-borderHover">
        <div className="flex gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-o-red/80" />
          <span className="w-2.5 h-2.5 rounded-full bg-o-amber/80" />
          <span className="w-2.5 h-2.5 rounded-full bg-o-green/80" />
        </div>
        <span className="text-xs text-o-muted ml-1 select-none">agent</span>
      </div>

      <pre className="px-5 py-5 font-mono text-sm leading-[1.7] overflow-x-hidden break-words whitespace-pre-wrap">
        {TERM_LINES.map((l, i) =>
          l.text === "" && !l.parts ? (
            <br key={i} />
          ) : l.parts ? (
            <span
              key={i}
              className="terminal-line block"
              style={{ animationDelay: `${l.delay}ms` }}
            >
              {l.parts.map((p, j) => (
                <span key={j} className={p.color}>{p.text}</span>
              ))}
            </span>
          ) : (
            <span
              key={i}
              className={`terminal-line block ${l.color}`}
              style={{ animationDelay: `${l.delay}ms` }}
            >
              {l.text}
            </span>
          )
        )}
      </pre>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  How It Works steps                                                 */
/* ------------------------------------------------------------------ */

const STEPS = [
  {
    num: "1",
    title: "No signup required",
    desc: "POST your script to the API. No account, no API key, no billing page.",
  },
  {
    num: "2",
    title: "Pay per job",
    desc: "HTTP 402 tells you the exact price. Sign one USDC payment \u2014 that\u2019s it.",
  },
  {
    num: "3",
    title: "Get results",
    desc: "Poll for output. Jobs run in isolated containers on a real Slurm cluster.",
  },
];

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function LandingPage() {
  const { data: stats } = useStats();
  const [howRef, howVisible] = useInView();
  const [statsRef, statsVisible] = useInView();
  const [mcpRef, mcpVisible] = useInView();

  return (
    <>
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-o-border bg-o-bg/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 md:px-8 lg:px-12 flex items-center justify-between h-14">
          <Link
            href="/"
            className="font-display text-base sm:text-lg font-bold text-o-blueText tracking-tight"
          >
            OURO
          </Link>
          <div className="flex items-center gap-4">
            <Link
              href="/docs"
              className="text-sm font-medium text-o-textSecondary hover:text-o-text transition-colors py-2"
            >
              Docs
            </Link>
            <a
              href="https://github.com/richtan/ouro"
              target="_blank"
              rel="noopener noreferrer"
              className="p-2 text-o-muted hover:text-o-text transition-colors flex items-center"
              aria-label="GitHub"
            >
              <GithubIcon />
            </a>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 md:px-8 lg:px-12">
        {/* Hero */}
        <section className="pt-24 pb-10 md:pt-32 md:pb-14 lg:grid lg:grid-cols-2 lg:gap-12 lg:items-center">
          {/* Left: text */}
          <div className="animate-fade-in-up">
            <h1 className="font-display text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight text-o-text leading-[1.08]">
              Pay for compute
              <br />
              over HTTP.
            </h1>
            <p className="mt-5 text-base sm:text-lg text-o-textSecondary max-w-xl leading-relaxed">
              No accounts. No API keys. Just USDC and a{" "}
              <code className="font-mono text-o-text/80">POST</code> request.
            </p>
            <div className="flex flex-wrap items-center gap-3 mt-8">
              <Link
                href="/submit"
                className="px-6 py-3 bg-o-blue text-white font-display font-semibold text-sm rounded-lg hover:bg-o-blueHover transition-colors"
              >
                Submit a Job
              </Link>
              <Link
                href="/docs"
                className="px-6 py-3 border border-o-border text-o-textSecondary font-display font-medium text-sm rounded-lg hover:border-o-borderHover hover:text-o-text transition-colors"
              >
                View Docs
              </Link>
            </div>
          </div>

          {/* Right: terminal */}
          <div className="mt-10 lg:mt-0 animate-fade-in-up" style={{ animationDelay: "150ms" }}>
            <Terminal />
          </div>
        </section>

        {/* How It Works */}
        <section ref={howRef} className="border-t border-o-border pt-10 pb-10 md:pt-14 md:pb-14">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {STEPS.map((step, i) => (
              <div
                key={step.num}
                className={`reveal${howVisible ? " visible" : ""} reveal-delay-${i + 1} bg-o-surface border border-o-border rounded-lg px-5 py-5`}
              >
                <span className="font-display text-sm font-bold text-o-blueText">
                  {step.num}
                </span>
                <h3 className="font-display text-base font-semibold text-o-text mt-2">
                  {step.title}
                </h3>
                <p className="text-sm text-o-textSecondary mt-1.5 leading-relaxed">
                  {step.desc}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Stats */}
        <section ref={statsRef} className="border-t border-o-border pt-6 pb-10 md:pt-8 md:pb-14">
          <div className="flex flex-wrap items-baseline gap-x-8 gap-y-3 lg:justify-center lg:gap-x-16">
            {[
              { label: "jobs completed", value: stats ? stats.completed_jobs : "\u2014" },
              { label: "active now", value: stats ? stats.active_jobs : "\u2014" },
              { label: "earned", value: stats ? `$${(stats.total_revenue_usdc ?? 0).toFixed(2)}` : "\u2014" },
            ].map((s, i) => (
              <div key={s.label} className={`reveal${statsVisible ? " visible" : ""} reveal-delay-${i + 1}`}>
                <Stat label={s.label} value={s.value} />
              </div>
            ))}
          </div>
        </section>

        {/* MCP section */}
        <section ref={mcpRef} className="border-t border-o-border pt-10 pb-12 md:pt-14 md:pb-16 lg:grid lg:grid-cols-2 lg:gap-12 lg:items-center">
          <div className={`reveal${mcpVisible ? " visible" : ""}`}>
            <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-o-text leading-tight">
              Built for agents.
            </h2>
            <p className="mt-3 text-sm sm:text-base text-o-textSecondary leading-relaxed max-w-lg">
              One command to set up. Any AI agent&mdash;Cursor, Claude Code, Claude
              Desktop, VS Code&mdash;can submit and pay for compute jobs automatically.
            </p>
            <Link
              href="/docs/mcp"
              className="inline-block mt-4 text-sm font-medium text-o-blueText hover:text-o-text transition-colors"
            >
              Read the MCP docs &rarr;
            </Link>
          </div>

          <div className={`mt-8 lg:mt-0 reveal${mcpVisible ? " visible" : ""} reveal-delay-2`}>
            <McpInstallCard />
          </div>
        </section>
      </main>

    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function McpInstallCard() {
  const [tab, setTab] = useState<"cli" | "json">("cli");
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(tab === "cli" ? CLI_COMMAND : MCP_JSON);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-o-surface border border-o-border rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-o-border">
        <div className="flex gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
          <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
          <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
        </div>
        <div className="flex gap-3 ml-2">
          <button
            onClick={() => setTab("cli")}
            className={`text-xs font-medium pb-0.5 transition-colors ${
              tab === "cli"
                ? "text-o-text border-b border-o-text"
                : "text-o-muted hover:text-o-textSecondary"
            }`}
          >
            CLI
          </button>
          <button
            onClick={() => setTab("json")}
            className={`text-xs font-medium pb-0.5 transition-colors ${
              tab === "json"
                ? "text-o-text border-b border-o-text"
                : "text-o-muted hover:text-o-textSecondary"
            }`}
          >
            mcp.json
          </button>
        </div>
        <button
          onClick={handleCopy}
          className="ml-auto text-o-muted hover:text-o-text transition-colors"
          aria-label="Copy to clipboard"
        >
          {copied ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
          )}
        </button>
      </div>
      <pre className="px-5 py-5 font-mono text-xs sm:text-sm leading-relaxed overflow-x-auto">
        {tab === "cli" ? (
          <>
            <span className="text-o-text">$ claude mcp add ouro</span>
            <span className="text-o-muted"> \</span>{"\n"}
            <span className="text-o-textSecondary">    --transport</span>
            <span className="text-o-text"> stdio</span>
            <span className="text-o-muted"> \</span>{"\n"}
            <span className="text-o-textSecondary">    -e</span>
            <span className="text-o-text"> WALLET_PRIVATE_KEY=</span>
            <span className="text-o-muted">0x...</span>
            <span className="text-o-muted"> \</span>{"\n"}
            <span className="text-o-muted">    --</span>
            <span className="text-o-text"> npx -y </span>
            <span className="text-o-blueText">ouro-mcp</span>
          </>
        ) : (
          <>
            <span className="text-o-muted">{"{"}</span>{"\n"}
            <span className="text-o-muted">{"  "}&quot;mcpServers&quot;: {"{"}</span>{"\n"}
            <span className="text-o-muted">{"    "}&quot;</span>
            <span className="text-o-textSecondary">ouro</span>
            <span className="text-o-muted">&quot;: {"{"}</span>{"\n"}
            <span className="text-o-muted">{"      "}&quot;</span>
            <span className="text-o-textSecondary">command</span>
            <span className="text-o-muted">&quot;: &quot;</span>
            <span className="text-o-blueText">npx</span>
            <span className="text-o-muted">&quot;,</span>{"\n"}
            <span className="text-o-muted">{"      "}&quot;</span>
            <span className="text-o-textSecondary">args</span>
            <span className="text-o-muted">&quot;: [&quot;</span>
            <span className="text-o-blueText">-y</span>
            <span className="text-o-muted">&quot;, &quot;</span>
            <span className="text-o-blueText">ouro-mcp</span>
            <span className="text-o-muted">&quot;],</span>{"\n"}
            <span className="text-o-muted">{"      "}&quot;</span>
            <span className="text-o-textSecondary">env</span>
            <span className="text-o-muted">&quot;: {"{"} &quot;</span>
            <span className="text-o-textSecondary">WALLET_PRIVATE_KEY</span>
            <span className="text-o-muted">&quot;: &quot;</span>
            <span className="text-o-muted">0x...</span>
            <span className="text-o-muted">&quot; {"}"}</span>{"\n"}
            <span className="text-o-muted">{"    }"}</span>{"\n"}
            <span className="text-o-muted">{"  }"}</span>{"\n"}
            <span className="text-o-muted">{"}"}</span>
          </>
        )}
      </pre>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline gap-2">
      <span
        className="font-display text-2xl sm:text-3xl font-bold text-o-text"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {value}
      </span>
      <span className="text-xs text-o-muted">{label}</span>
    </div>
  );
}
