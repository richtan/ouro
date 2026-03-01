"use client";

import { useEffect, useState } from "react";
import { fetchAudit } from "@/lib/api";

interface AuditEntry {
  id: number;
  event_type: string;
  event_data: Record<string, unknown>;
  created_at: string;
}

const EVENT_STYLES: Record<string, string> = {
  job_submitted: "text-o-blueText",
  job_completed: "text-o-green",
  job_failed: "text-o-red",
  payment_received: "text-o-green",
  proof_submitted: "text-o-blueText",
  gas_spent: "text-o-red",
  credit_issued: "text-o-amber",
  phase_change: "text-o-amber",
};

export default function AuditPanel() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () =>
      fetchAudit()
        .then((data) => {
          setEntries(data?.entries ?? []);
          setLoading(false);
        })
        .catch(() => setLoading(false));
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  if (loading && entries.length === 0) {
    return (
      <div className="card animate-pulse">
        <div className="h-32 bg-o-border/30 rounded" />
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="stat-label">Audit Log</div>
        <span className="text-xs font-mono text-o-textSecondary">{entries.length} events</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[600px]">
          <thead>
            <tr className="text-xs text-o-muted uppercase tracking-wider border-b border-o-border">
              <th className="text-left pb-2 pr-4">Time</th>
              <th className="text-left pb-2 pr-4">Event</th>
              <th className="text-left pb-2 pr-4">Job ID</th>
              <th className="text-right pb-2 pr-4">Amount</th>
              <th className="text-left pb-2">Details</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => {
              const ts = new Date(entry.created_at).toLocaleString("en-US", {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                hour12: false,
              });
              const color = EVENT_STYLES[entry.event_type] ?? "text-o-textSecondary";
              const d = entry.event_data ?? {};
              const jobId = (d.job_id as string) ?? "";
              const amount = (d.amount_usdc as number) ?? (d.gas_usd as number) ?? null;

              return (
                <tr
                  key={entry.id}
                  className="border-b border-o-border/50 hover:bg-o-surfaceHover transition-colors"
                >
                  <td className="py-2 pr-4 text-xs text-o-muted whitespace-nowrap">{ts}</td>
                  <td className={`py-2 pr-4 font-mono text-xs uppercase tracking-wider ${color}`}>
                    {entry.event_type}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-o-blueText">
                    {jobId ? jobId.slice(0, 8) : "—"}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-right">
                    {amount != null ? (
                      <span className={amount >= 0 ? "text-o-green" : "text-o-red"}>
                        ${Math.abs(amount).toFixed(6)}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="py-2 text-xs text-o-muted truncate max-w-[200px]">
                    {Object.entries(d)
                      .filter(([k]) => k !== "job_id" && k !== "amount_usdc" && k !== "gas_usd")
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(", ") || "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
