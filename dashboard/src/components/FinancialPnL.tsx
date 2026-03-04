"use client";

import { useStats } from "@/hooks/useData";

interface StatsData {
  total_revenue_usdc: number;
  gas_costs_usd: number;
  llm_costs_usd: number;
  total_costs_usd: number;
  net_pnl_usd: number;
  completed_jobs: number;
  active_jobs: number;
  avg_duration_s: number;
  sustainability_ratio: number;
  avg_cost_per_job: number;
  avg_price_per_job: number;
  avg_margin_per_job: number;
}

function Bar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs mb-1.5">
        <span className="text-o-textSecondary">{label}</span>
        <span className="font-mono text-o-text font-medium">${value.toFixed(4)}</span>
      </div>
      <div className="h-2 bg-o-border/50 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

export default function FinancialPnL() {
  const { data: stats } = useStats() as { data: StatsData | undefined };

  if (!stats) {
    return (
      <div className="card animate-pulse">
        <div className="h-48 bg-o-border/30 rounded" />
      </div>
    );
  }

  const maxVal = Math.max(stats.total_revenue_usdc, stats.total_costs_usd, 0.01);
  const pnlPositive = stats.net_pnl_usd >= 0;
  const marginPositive = stats.avg_margin_per_job >= 0;
  const ratioDisplay = isFinite(stats.sustainability_ratio)
    ? (stats.sustainability_ratio ?? 0).toFixed(1) + "x"
    : "∞";

  return (
    <div className="card animate-slide-up">
      <div className="flex items-center justify-between mb-4">
        <div className="stat-label">Financial P&L</div>
        <div className={`font-mono text-xs px-2 py-0.5 rounded-full ${pnlPositive ? "bg-o-green/10 text-o-green" : "bg-o-red/10 text-o-red"}`}>
          {ratioDisplay} ratio
        </div>
      </div>

      <div className="text-center mb-5">
        <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Net Profit / Loss</div>
        <div
          className={`font-display text-4xl font-bold ${
            pnlPositive ? "text-o-green" : "text-o-red"
          }`}
        >
          {pnlPositive ? "+" : ""}${(stats.net_pnl_usd ?? 0).toFixed(4)}
        </div>
      </div>

      <div className="space-y-1">
        <Bar label="x402 Revenue" value={stats.total_revenue_usdc} max={maxVal} color="#22c55e" />
        <Bar label="Gas Costs" value={stats.gas_costs_usd} max={maxVal} color="#ef4444" />
        <Bar label="LLM Costs" value={stats.llm_costs_usd} max={maxVal} color="#eab308" />
      </div>

      <div className="mt-5 pt-4 border-t border-o-border">
        <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-3">Per-Job Economics</div>
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-o-bg rounded-lg p-2.5 text-center">
            <div className="text-xs text-o-textSecondary uppercase tracking-wider">Avg Cost</div>
            <div className="font-display text-sm font-semibold text-o-red mt-1">
              ${(stats.avg_cost_per_job ?? 0).toFixed(4)}
            </div>
          </div>
          <div className="bg-o-bg rounded-lg p-2.5 text-center">
            <div className="text-xs text-o-textSecondary uppercase tracking-wider">Avg Price</div>
            <div className="font-display text-sm font-semibold text-o-text mt-1">
              ${(stats.avg_price_per_job ?? 0).toFixed(4)}
            </div>
          </div>
          <div className="bg-o-bg rounded-lg p-2.5 text-center">
            <div className="text-xs text-o-textSecondary uppercase tracking-wider">Avg Margin</div>
            <div
              className={`font-display text-sm font-semibold mt-1 ${
                marginPositive ? "text-o-green" : "text-o-red"
              }`}
            >
              {marginPositive ? "+" : ""}${(stats.avg_margin_per_job ?? 0).toFixed(4)}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mt-4 pt-4 border-t border-o-border">
        <div>
          <div className="stat-label">Completed</div>
          <div className="font-display text-lg font-semibold text-o-text">{stats.completed_jobs}</div>
        </div>
        <div>
          <div className="stat-label">Active</div>
          <div className="font-display text-lg font-semibold text-o-blueText">{stats.active_jobs}</div>
        </div>
      </div>
    </div>
  );
}
