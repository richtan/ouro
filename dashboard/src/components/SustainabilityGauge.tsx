"use client";

import { useStats } from "@/hooks/useData";

interface StatsData {
  sustainability_ratio: number;
  survival_phase: string;
  heartbeat_interval_min: number;
  margin_multiplier: number;
  demand_multiplier: number;
}

const PHASE_COLORS: Record<string, { text: string; bg: string }> = {
  OPTIMAL: { text: "text-o-green", bg: "bg-o-green" },
  CAUTIOUS: { text: "text-o-amber", bg: "bg-o-amber" },
  SURVIVAL: { text: "text-orange-400", bg: "bg-orange-400" },
  CRITICAL: { text: "text-o-red", bg: "bg-o-red" },
};

const PHASE_DESCRIPTIONS: Record<string, string> = {
  OPTIMAL: "Revenue healthy — normal operations",
  CAUTIOUS: "Margins thin — margin raised 10%",
  SURVIVAL: "Costs exceeding revenue — conserving gas",
  CRITICAL: "Emergency — maximum margins, pre-paid only",
};

export default function SustainabilityGauge() {
  const { data: stats } = useStats() as { data: StatsData | undefined };

  const ratio = stats?.sustainability_ratio ?? 0;
  const displayRatio = isFinite(ratio) ? ratio : 99.9;
  const clampedRatio = Math.min(displayRatio, 3);
  const angle = (clampedRatio / 3) * 180;
  const isSustainable = displayRatio >= 1;
  const phase = stats?.survival_phase ?? "OPTIMAL";
  const phaseStyle = PHASE_COLORS[phase] ?? PHASE_COLORS.OPTIMAL;

  const r = 70;
  const cx = 80;
  const cy = 80;
  const startAngle = Math.PI;
  const endAngle = startAngle - (angle * Math.PI) / 180;
  const x1 = cx + r * Math.cos(startAngle);
  const y1 = cy + r * Math.sin(startAngle);
  const x2 = cx + r * Math.cos(endAngle);
  const y2 = cy + r * Math.sin(endAngle);
  const largeArc = angle > 180 ? 1 : 0;

  return (
    <div className="card animate-slide-up flex flex-col items-center">
      <div className="stat-label mb-4 self-start">Sustainability Score</div>

      <div className="relative">
        <svg width="160" height="90" viewBox="0 0 160 90">
          <path
            d="M 10 80 A 70 70 0 0 1 150 80"
            fill="none"
            stroke="#1e2025"
            strokeWidth="10"
            strokeLinecap="round"
          />
          {stats && (
            <path
              d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 0 ${x2} ${y2}`}
              fill="none"
              stroke={isSustainable ? "#0052ff" : "#ef4444"}
              strokeWidth="10"
              strokeLinecap="round"
              className="transition-all duration-1000"
            />
          )}
        </svg>
        <div className="absolute inset-0 flex items-end justify-center pb-1">
          <span
            className={`font-display text-3xl font-bold ${
              isSustainable ? "text-o-blueText" : "text-o-red"
            }`}
          >
            {displayRatio.toFixed(2)}x
          </span>
        </div>
      </div>

      <div className="mt-4 w-full">
        <div className="flex items-center justify-center gap-2 mb-2">
          <div className={`w-2.5 h-2.5 rounded-full ${phaseStyle.bg} animate-pulse`} />
          <span className={`font-display text-sm font-bold tracking-wider ${phaseStyle.text}`}>
            {phase}
          </span>
        </div>
        <div className="text-xs text-o-textSecondary text-center leading-relaxed">
          {PHASE_DESCRIPTIONS[phase]}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 w-full mt-5 pt-4 border-t border-o-border">
        <div className="text-center">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider">Margin</div>
          <div className="font-display text-lg font-semibold text-o-text mt-1">
            {(stats?.margin_multiplier ?? 0).toFixed(2)}x
          </div>
        </div>
        <div className="text-center">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider">Demand</div>
          <div className="font-display text-lg font-semibold text-o-text mt-1">
            {(stats?.demand_multiplier ?? 0).toFixed(2)}x
          </div>
        </div>
        <div className="text-center">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider">Heartbeat</div>
          <div className="font-display text-lg font-semibold text-o-text mt-1">
            {(stats?.heartbeat_interval_min ?? 0) > 0
              ? `${stats?.heartbeat_interval_min}m`
              : "OFF"}
          </div>
        </div>
      </div>

      <div className="flex justify-between w-full mt-3 text-xs text-o-muted px-2">
        <span>0x</span>
        <span>1.0x</span>
        <span>2.0x</span>
        <span>3.0x</span>
      </div>
    </div>
  );
}
