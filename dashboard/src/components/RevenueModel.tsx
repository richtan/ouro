"use client";

import { useEffect, useState } from "react";
import { fetchStats } from "@/lib/api";

interface StatsData {
  margin_multiplier: number;
  demand_multiplier: number;
  on_chain_proof_count: number;
  avg_margin_per_job: number;
  avg_price_per_job: number;
  avg_cost_per_job: number;
  completed_jobs: number;
  revenue_model: string;
}

function FlowStep({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`flex-1 text-center rounded-lg p-3 border ${accent ? "border-ouro-accent/30 bg-ouro-accent/5" : "border-ouro-border/30 bg-black/30"}`}>
      <div className="text-[10px] text-ouro-muted uppercase tracking-wider">{label}</div>
      <div className={`font-display text-lg font-bold mt-0.5 ${accent ? "text-ouro-accent" : "text-ouro-text"}`}>{value}</div>
    </div>
  );
}

export default function RevenueModel() {
  const [stats, setStats] = useState<StatsData | null>(null);

  useEffect(() => {
    const load = () => fetchStats().then(setStats).catch(() => {});
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  if (!stats) {
    return (
      <div className="card animate-pulse">
        <div className="h-48 bg-ouro-border/30 rounded" />
      </div>
    );
  }

  const marginPositive = stats.avg_margin_per_job >= 0;

  return (
    <div className="card animate-slide-up col-span-full border-ouro-accent/20">
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="stat-label">Revenue Model</div>
          <h3 className="font-display text-lg font-bold text-ouro-accent glow-cyan mt-1">
            Verifiable Work &mdash; Guaranteed Margins
          </h3>
        </div>
        <div className="flex items-center gap-1.5 bg-ouro-accent/10 border border-ouro-accent/20 rounded px-2.5 py-1">
          <div className="w-1.5 h-1.5 rounded-full bg-ouro-accent animate-pulse-glow" />
          <span className="text-[10px] font-mono text-ouro-accent uppercase tracking-wider">
            Self-Sustaining
          </span>
        </div>
      </div>

      {/* Flow visualization */}
      <div className="flex items-center gap-2 mb-6">
        <FlowStep label="x402 Payment" value={`$${stats.avg_price_per_job.toFixed(4)}`} />
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-ouro-muted shrink-0">
          <path d="M5 12h14M12 5l7 7-7 7" />
        </svg>
        <FlowStep label="HPC Compute" value={`$${stats.avg_cost_per_job.toFixed(4)}`} />
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-ouro-muted shrink-0">
          <path d="M5 12h14M12 5l7 7-7 7" />
        </svg>
        <FlowStep label="On-Chain Proof" value={`${stats.on_chain_proof_count}`} accent />
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-ouro-muted shrink-0">
          <path d="M5 12h14M12 5l7 7-7 7" />
        </svg>
        <FlowStep
          label="Net Margin"
          value={`${marginPositive ? "+" : ""}$${stats.avg_margin_per_job.toFixed(4)}`}
        />
      </div>

      <p className="text-sm text-ouro-muted font-body leading-relaxed mb-5">
        Ouro prices every job to guarantee positive margin. The pricing engine dynamically adjusts
        based on real costs (gas + LLM + compute) multiplied by a survival-aware margin. Every
        completed job produces a SHA-256 proof attestation on Base, making this provably useful work.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">Margin Multiplier</div>
          <div className="font-display text-xl font-bold text-ouro-text mt-1">
            {stats.margin_multiplier.toFixed(2)}x
          </div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">Demand Factor</div>
          <div className="font-display text-xl font-bold text-ouro-text mt-1">
            {stats.demand_multiplier.toFixed(2)}x
          </div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">Completed Jobs</div>
          <div className="font-display text-xl font-bold text-ouro-green mt-1">
            {stats.completed_jobs}
          </div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">On-Chain Proofs</div>
          <div className="font-display text-xl font-bold text-ouro-accent mt-1">
            {stats.on_chain_proof_count}
          </div>
        </div>
      </div>

      <div className="bg-ouro-accent/5 border border-ouro-accent/15 rounded-lg p-3">
        <div className="flex items-center gap-2 mb-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="text-ouro-accent">
            <path
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="text-xs font-mono text-ouro-accent uppercase tracking-wider">
            Three Revenue Streams
          </span>
        </div>
        <p className="text-xs text-ouro-muted leading-relaxed">
          1. Direct x402 stablecoin payments for compute &mdash;
          2. ERC-8021 sequencer reward farming via builder codes &mdash;
          3. On-chain compute reputation (ProofOfCompute contract)
        </p>
      </div>
    </div>
  );
}
