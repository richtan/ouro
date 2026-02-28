"use client";

import { useEffect, useState } from "react";
import { fetchAudit } from "@/lib/api";

interface AuditEntry {
  id: string;
  event_type: string;
  job_id: string | null;
  wallet_address: string | null;
  amount_usdc: number | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

const EVENT_STYLES: Record<string, string> = {
  payment_received: "text-ouro-green",
  job_completed: "text-ouro-accent",
  job_failed: "text-ouro-red",
  credit_issued: "text-ouro-amber",
};

export default function AuditPanel() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () =>
      fetchAudit(100)
        .then((data) => {
          setEntries(data.entries ?? []);
          setLoading(false);
        })
        .catch(() => setLoading(false));
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, []);

  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-48 bg-ouro-border/30 rounded" />
      </div>
    );
  }

  return (
    <div className="card col-span-full animate-slide-up">
      <div className="flex items-center justify-between mb-5">
        <div className="stat-label">Audit Log</div>
        <span className="text-xs text-ouro-muted font-mono">
          {entries.length} entries
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="text-[10px] text-ouro-muted uppercase tracking-wider border-b border-ouro-border/30">
              <th className="text-left py-2 pr-4">Time</th>
              <th className="text-left py-2 pr-4">Event</th>
              <th className="text-left py-2 pr-4">Job</th>
              <th className="text-left py-2 pr-4">Wallet</th>
              <th className="text-right py-2 pr-4">Amount</th>
              <th className="text-left py-2">Detail</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="text-center py-8 text-ouro-muted"
                >
                  No audit entries yet
                </td>
              </tr>
            )}
            {entries.map((e) => {
              const ts = new Date(e.created_at).toLocaleString("en-US", {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                hour12: false,
              });
              const color =
                EVENT_STYLES[e.event_type] ?? "text-ouro-text";
              return (
                <tr
                  key={e.id}
                  className="border-b border-ouro-border/20 hover:bg-white/[0.02] transition-colors"
                >
                  <td className="py-2 pr-4 text-ouro-muted whitespace-nowrap">
                    {ts}
                  </td>
                  <td className={`py-2 pr-4 ${color} whitespace-nowrap`}>
                    {e.event_type.replace(/_/g, " ")}
                  </td>
                  <td className="py-2 pr-4 text-ouro-accent">
                    {e.job_id ? e.job_id.slice(0, 8) : "—"}
                  </td>
                  <td className="py-2 pr-4 text-ouro-text/70">
                    {e.wallet_address
                      ? `${e.wallet_address.slice(0, 6)}...${e.wallet_address.slice(-4)}`
                      : "—"}
                  </td>
                  <td className="py-2 pr-4 text-right text-ouro-green">
                    {e.amount_usdc != null
                      ? `$${e.amount_usdc.toFixed(4)}`
                      : "—"}
                  </td>
                  <td className="py-2 text-ouro-muted max-w-[200px] truncate">
                    {e.detail
                      ? JSON.stringify(e.detail).slice(0, 60)
                      : "—"}
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
