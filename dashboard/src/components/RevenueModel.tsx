"use client";

import { useStats } from "@/hooks/useData";

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
    <div className={`flex-1 text-center rounded-lg p-3 border ${accent ? "border-o-blue/30 bg-o-blue/5" : "border-o-border bg-o-bg"}`}>
      <div className="text-xs text-o-textSecondary uppercase tracking-wider">{label}</div>
      <div className={`font-display text-lg font-semibold mt-0.5 ${accent ? "text-o-blueText" : "text-o-text"}`}>{value}</div>
    </div>
  );
}

function FlowArrow({ className }: { className?: string }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={`text-o-muted shrink-0 ${className ?? ""}`}>
      <path d="M5 12h14M12 5l7 7-7 7" />
    </svg>
  );
}

export default function RevenueModel() {
  const { data: stats } = useStats() as { data: StatsData | undefined };

  if (!stats) {
    return (
      <div className="card animate-pulse">
        <div className="h-48 bg-o-border/30 rounded" />
      </div>
    );
  }

  const marginPositive = stats.avg_margin_per_job >= 0;

  return (
    <div className="card animate-slide-up">
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="stat-label">Revenue Model</div>
          <h3 className="font-display text-lg font-bold text-o-text mt-1">
            Verifiable Work &mdash; Guaranteed Margins
          </h3>
        </div>
        <div className="flex items-center gap-1.5 bg-o-blue/10 border border-o-blue/20 rounded px-2.5 py-1">
          <div className="w-1.5 h-1.5 rounded-full bg-o-blue animate-pulse" />
          <span className="text-xs font-medium text-o-blueText uppercase tracking-wider">
            Self-Sustaining
          </span>
        </div>
      </div>

      {/* Flow: responsive vertical on mobile, horizontal on desktop */}
      <div className="flex flex-col sm:flex-row items-stretch gap-2 mb-6">
        <FlowStep label="x402 Payment" value={`$${(stats.avg_price_per_job ?? 0).toFixed(4)}`} />
        <FlowArrow className="rotate-90 sm:rotate-0 self-center" />
        <FlowStep label="HPC Compute" value={`$${(stats.avg_cost_per_job ?? 0).toFixed(4)}`} />
        <FlowArrow className="rotate-90 sm:rotate-0 self-center" />
        <FlowStep label="On-Chain Proof" value={`${stats.on_chain_proof_count}`} accent />
        <FlowArrow className="rotate-90 sm:rotate-0 self-center" />
        <FlowStep
          label="Net Margin"
          value={`${marginPositive ? "+" : ""}$${(stats.avg_margin_per_job ?? 0).toFixed(4)}`}
        />
      </div>

      <p className="text-sm text-o-textSecondary font-body leading-relaxed mb-5">
        Ouro prices every job to guarantee positive margin. The pricing engine dynamically adjusts
        based on real costs (gas + LLM + compute) multiplied by a survival-aware margin. Every
        completed job produces a SHA-256 proof attestation on Base.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <div className="bg-o-bg rounded-lg p-3 border border-o-border">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider">Margin Multiplier</div>
          <div className="font-display text-xl font-semibold text-o-text mt-1">
            {(stats.margin_multiplier ?? 0).toFixed(2)}x
          </div>
        </div>
        <div className="bg-o-bg rounded-lg p-3 border border-o-border">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider">Demand Factor</div>
          <div className="font-display text-xl font-semibold text-o-text mt-1">
            {(stats.demand_multiplier ?? 0).toFixed(2)}x
          </div>
        </div>
        <div className="bg-o-bg rounded-lg p-3 border border-o-border">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider">Completed Jobs</div>
          <div className="font-display text-xl font-semibold text-o-green mt-1">
            {stats.completed_jobs}
          </div>
        </div>
        <div className="bg-o-bg rounded-lg p-3 border border-o-border">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider">On-Chain Proofs</div>
          <div className="font-display text-xl font-semibold text-o-blueText mt-1">
            {stats.on_chain_proof_count}
          </div>
        </div>
      </div>

      <div className="bg-o-blue/5 border border-o-blue/15 rounded-lg p-3">
        <div className="flex items-center gap-2 mb-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="text-o-blueText">
            <path
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="text-xs font-medium text-o-blueText uppercase tracking-wider">
            Three Revenue Streams
          </span>
        </div>
        <p className="text-xs text-o-textSecondary leading-relaxed">
          1. Direct x402 stablecoin payments for compute &mdash;
          2. ERC-8021 sequencer reward farming via builder codes &mdash;
          3. On-chain compute reputation (ProofOfCompute contract)
        </p>
      </div>
    </div>
  );
}
