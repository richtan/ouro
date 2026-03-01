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

/* ------------------------------------------------------------------ */
/*  Terminal — the centerpiece                                         */
/* ------------------------------------------------------------------ */

const TERM_LINES: { text: string; color: string; delay: number }[] = [
  { text: "> train my MNIST model, 50 epochs", color: "text-o-text", delay: 0 },
  { text: "", color: "", delay: 0 },
  { text: "claude  too compute-heavy to run locally", color: "text-o-blueText", delay: 300 },
  { text: "        → invoking run_compute_job", color: "text-o-blueText", delay: 420 },
  { text: "", color: "", delay: 0 },
  { text: "tool    nodes: 2 · time_limit: 30min", color: "text-o-textSecondary", delay: 620 },
  { text: '        script: "python3 train.py --epochs 50"', color: "text-o-textSecondary", delay: 720 },
  { text: "", color: "", delay: 0 },
  { text: "ouro    payment required · $0.0841 USDC", color: "text-o-amber", delay: 920 },
  { text: "        → ourocompute.com/pay/sess_f2a9c1", color: "text-o-amber", delay: 1020 },
  { text: "", color: "", delay: 0 },
  { text: "user    ✓ paid", color: "text-o-muted", delay: 1300 },
  { text: "", color: "", delay: 0 },
  { text: "ouro    running · 2 nodes · 4m 12s elapsed", color: "text-o-textSecondary", delay: 1500 },
  { text: "        ✓ complete", color: "text-o-green", delay: 1700 },
  { text: "        accuracy: 98.7% · loss: 0.041", color: "text-o-green", delay: 1800 },
  { text: "        proof: 0x4f2a...c981 (Base)", color: "text-o-muted", delay: 1900 },
];

function Terminal() {
  return (
    <div className="bg-o-surface border border-o-border rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-o-border">
        <div className="flex gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
          <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
          <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
        </div>
        <span className="text-xs text-o-muted ml-1 select-none">terminal</span>
      </div>

      <pre className="px-5 py-5 font-mono text-xs leading-[1.7] overflow-x-auto">
        {TERM_LINES.map((l, i) =>
          l.text === "" ? (
            <br key={i} />
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
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function LandingPage() {
  const stats = useStats();

  return (
    <>
      {/* Header */}
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
        <section className="pt-24 pb-6 md:pt-32 md:pb-8 animate-fade-in">
          <h1 className="font-display text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight text-o-text leading-[1.08]">
            Compute that
            <br />
            runs itself.
          </h1>
          <p className="mt-5 text-base sm:text-lg text-o-textSecondary max-w-xl leading-relaxed">
            An autonomous agent on Base that prices HPC jobs, takes USDC,
            and posts SHA-256 proofs on-chain. No accounts. Just{" "}
            <code className="font-mono text-o-text/80">curl</code>.
          </p>
          <div className="flex flex-wrap items-center gap-3 mt-8">
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

        {/* Terminal */}
        <section className="pb-10 md:pb-14">
          <Terminal />
        </section>

        {/* Stats */}
        <section className="border-t border-o-border pt-6 pb-10 md:pt-8 md:pb-14">
          <div className="flex flex-wrap items-baseline gap-x-8 gap-y-3">
            <Stat label="jobs completed" value={stats ? stats.completed_jobs : "—"} />
            <Stat label="active now" value={stats ? stats.active_jobs : "—"} />
            <Stat
              label="earned"
              value={stats ? `$${stats.total_revenue_usdc.toFixed(2)}` : "—"}
            />
            <Stat
              label="on-chain proofs"
              value={stats ? stats.on_chain_proof_count : "—"}
            />
          </div>
        </section>

        {/* Agent section */}
        <section className="pb-10 md:pb-14">
          <div className="text-xs text-o-muted uppercase tracking-wider mb-2">
            For agents
          </div>
          <h2 className="font-display text-lg font-semibold text-o-text mb-3">
            Other agents can buy compute too.
          </h2>
          <p className="text-sm text-o-textSecondary leading-relaxed max-w-2xl">
            Ouro exposes an MCP server. AI agents discover pricing, submit
            jobs, and verify proofs&nbsp;&mdash; no human in the loop.
          </p>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-o-border">
        <div className="max-w-5xl mx-auto px-4 md:px-8 py-6 flex items-center justify-between">
          <p className="text-xs text-o-textSecondary">Built on Base</p>
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

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

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
