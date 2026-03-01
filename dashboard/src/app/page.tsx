"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchStats } from "@/lib/api";
import { ConnectButton } from "@rainbow-me/rainbowkit";

interface LiveStats {
  completed_jobs: number;
  active_jobs: number;
  total_revenue_usdc: number;
  on_chain_proof_count: number;
}

function useStats() {
  const [stats, setStats] = useState<LiveStats | null>(null);
  useEffect(() => {
    const load = () => fetchStats().then(setStats).catch(() => {});
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, []);
  return stats;
}

function GithubIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}

export default function LandingPage() {
  const stats = useStats();

  return (
    <>
      <header className="sticky top-0 z-50 border-b border-o-border bg-o-bg/80 backdrop-blur-md">
        <div className="max-w-5xl mx-auto px-4 md:px-8 flex items-center justify-between h-14">
          <Link
            href="/"
            className="font-display text-base sm:text-lg font-bold text-o-blueText tracking-tight"
          >
            OURO
          </Link>
          <div className="flex items-center gap-5">
            <Link
              href="/dashboard"
              className="hidden sm:inline-block text-sm font-medium text-o-textSecondary hover:text-o-text transition-colors"
            >
              Dashboard
            </Link>
            <a
              href="https://github.com/richtan/ouro"
              target="_blank"
              rel="noopener noreferrer"
              className="text-o-muted hover:text-o-text transition-colors flex items-center"
              aria-label="GitHub"
            >
              <GithubIcon />
            </a>
            <ConnectButton
              chainStatus="icon"
              accountStatus="address"
              showBalance={false}
            />
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 md:px-8">
        {/* Hero */}
        <section className="pt-32 pb-16 md:pt-40 md:pb-24 animate-fade-in">
          <h1 className="font-display text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight text-o-text leading-[1.08]">
            Run compute.
            <br />
            Pay in <span className="text-o-blueText">USDC</span>.
            <br />
            Prove it on-chain.
          </h1>
          <p className="mt-6 text-base sm:text-lg text-o-textSecondary max-w-xl leading-relaxed">
            Ouro is an autonomous agent that sells HPC compute on Base.
            You submit a script, pay with stablecoins, and get a SHA-256
            proof stored on-chain. No accounts. No API keys.
          </p>
          <div className="flex flex-wrap items-center gap-3 mt-10">
            <Link
              href="/submit"
              className="px-6 py-3 bg-o-blue text-white font-display font-semibold text-sm rounded-lg hover:bg-o-blueHover transition-colors"
            >
              Submit a Job
            </Link>
            <Link
              href="/dashboard"
              className="px-6 py-3 border border-o-border text-o-textSecondary font-display font-medium text-sm rounded-lg hover:border-o-borderHover hover:text-o-text transition-colors"
            >
              Dashboard
            </Link>
          </div>
        </section>

        {/* Live stats strip */}
        <section className="pb-20 md:pb-32 animate-slide-up">
          <div className="flex flex-wrap items-baseline gap-x-10 gap-y-4 border-t border-o-border pt-8">
            <Stat label="jobs completed" value={stats ? stats.completed_jobs : "—"} />
            <Stat label="active now" value={stats ? stats.active_jobs : "—"} />
            <Stat label="earned" value={stats ? `$${stats.total_revenue_usdc.toFixed(2)}` : "—"} />
            <Stat label="on-chain proofs" value={stats ? stats.on_chain_proof_count : "—"} />
          </div>
        </section>

        {/* How it works */}
        <section className="pb-20 md:pb-32">
          <div className="text-xs text-o-muted uppercase tracking-wider mb-8">
            How it works
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            <Step n={1} title="Write a script">
              Bash, Python, whatever you need. Set your node count and
              time limit, then hit submit.
            </Step>
            <Step n={2} title="Pay with USDC">
              The agent quotes a price via x402. You sign one USDC
              authorization — no subscriptions, no accounts.
            </Step>
            <Step n={3} title="Get your proof">
              Your job runs on an HPC cluster. When it finishes, the output
              hash is attested on Base. Verifiable forever.
            </Step>
          </div>
          
          {/* Narrative bridge moved inside the section */}
          <div className="mt-12 md:mt-16 max-w-3xl">
            <p className="text-sm sm:text-base text-o-textSecondary leading-relaxed">
              Ouro prices every job dynamically, pays its own infrastructure
              costs, and exposes an MCP interface so other AI agents can
              discover and buy compute programmatically.
            </p>
          </div>
        </section>

        {/* Developer quick start */}
        <section className="pb-24 md:pb-32">
          <div className="text-xs text-o-muted uppercase tracking-wider mb-2">
            For developers
          </div>
          <h2 className="font-display text-lg font-semibold text-o-text mb-6">
            Start in one request
          </h2>
          <pre className="bg-o-surface border border-o-border rounded-xl p-5 font-mono text-xs text-o-text/80 overflow-x-auto whitespace-pre leading-relaxed">
{`curl -X POST https://ourocompute.com/api/submit \\
  -H "Content-Type: application/json" \\
  -d '{
    "script": "#!/bin/bash\\necho Hello from Ouro",
    "nodes": 1,
    "time_limit_min": 1
  }'

# Returns x402 payment headers
# Sign the USDC authorization → job runs → proof on Base`}
          </pre>
          <Link
            href="/submit"
            className="inline-block mt-5 text-sm font-medium text-o-blueText hover:underline"
          >
            Or use the web UI &rarr;
          </Link>
        </section>
      </main>

      <footer className="border-t border-o-border">
        <div className="max-w-5xl mx-auto px-4 md:px-8 py-8 flex items-center justify-between">
          <p className="text-xs text-o-textSecondary">
            Built on Base
          </p>
          <div className="flex items-center gap-4">
            <Link
              href="/dashboard"
              className="text-xs text-o-textSecondary hover:text-o-text transition-colors"
            >
              Dashboard
            </Link>
            <Link
              href="/submit"
              className="text-xs text-o-textSecondary hover:text-o-text transition-colors"
            >
              Submit
            </Link>
          </div>
        </div>
      </footer>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-display text-2xl sm:text-3xl font-bold text-o-text" style={{ fontVariantNumeric: "tabular-nums" }}>
        {value}
      </span>
      <span className="text-xs text-o-muted">{label}</span>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div className="bg-o-surface border border-o-border rounded-xl p-6">
      <div className="font-mono text-sm text-o-blueText mb-3">
        {String(n).padStart(2, "0")}
      </div>
      <h3 className="font-display text-base font-semibold text-o-text mb-2">
        {title}
      </h3>
      <p className="text-sm text-o-textSecondary leading-relaxed">
        {children}
      </p>
    </div>
  );
}
