"use client";

import { useEffect, useState } from "react";
import { fetchStats } from "@/lib/api";
import Link from "next/link";

interface StatsData {
  completed_jobs: number;
  active_jobs: number;
  total_revenue_usdc: number;
  avg_duration_s: number;
  on_chain_proof_count: number;
}

export default function PublicJobStats() {
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
        <div className="h-32 bg-ouro-border/30 rounded" />
      </div>
    );
  }

  return (
    <div className="card col-span-full animate-slide-up">
      <div className="flex items-center justify-between mb-5">
        <div className="stat-label">Compute Jobs</div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-ouro-muted">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="text-ouro-accent"
            >
              <rect x="2" y="3" width="20" height="14" rx="2" />
              <line x1="8" y1="21" x2="16" y2="21" />
              <line x1="12" y1="17" x2="12" y2="21" />
            </svg>
            GCP Slurm Cluster
          </div>
          <Link
            href="/history"
            className="text-[10px] font-mono text-ouro-accent hover:underline uppercase tracking-wider"
          >
            My Jobs &rarr;
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">
            Active
          </div>
          <div className="font-display text-xl font-bold text-ouro-amber mt-1">
            {stats.active_jobs}
          </div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">
            Completed
          </div>
          <div className="font-display text-xl font-bold text-ouro-green mt-1">
            {stats.completed_jobs}
          </div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">
            Total Revenue
          </div>
          <div className="font-display text-xl font-bold text-ouro-text mt-1">
            ${stats.total_revenue_usdc.toFixed(4)}
          </div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">
            Avg Duration
          </div>
          <div className="font-display text-xl font-bold text-ouro-accent mt-1">
            {stats.avg_duration_s.toFixed(1)}s
          </div>
        </div>
      </div>

      {stats.on_chain_proof_count > 0 && (
        <div className="mt-4 pt-4 border-t border-ouro-border/30 flex items-center justify-between">
          <span className="text-xs text-ouro-muted">
            On-chain proofs submitted
          </span>
          <span className="font-mono text-sm font-bold text-ouro-green">
            {stats.on_chain_proof_count}
          </span>
        </div>
      )}
    </div>
  );
}
