"use client";

import { useEffect, useState } from "react";
import { fetchAttribution, decodeBuilderCodes } from "@/lib/api";

interface AttributionData {
  total_attributed_txs: number;
  total_gas_attributed: number;
  multi_code_txs: number;
  recent: {
    tx_hash: string;
    codes: string[];
    gas_used: string | null;
    is_multi: boolean;
    created_at: string;
  }[];
}

export default function AttributionPanel() {
  const [data, setData] = useState<AttributionData | null>(null);
  const [decodeInput, setDecodeInput] = useState("");
  const [decoded, setDecoded] = useState<string[] | null>(null);

  useEffect(() => {
    const load = () => fetchAttribution().then(setData).catch(() => {});
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, []);

  const handleDecode = async () => {
    if (!decodeInput.trim()) return;
    try {
      const result = await decodeBuilderCodes(decodeInput.trim());
      setDecoded(result.codes);
    } catch {
      setDecoded([]);
    }
  };

  if (!data) {
    return (
      <div className="card animate-pulse">
        <div className="h-32 bg-o-border/30 rounded" />
      </div>
    );
  }

  const gasEth = (data.total_gas_attributed ?? 0) / 1e18;
  const uniqueCodes = Array.from(
    new Set((data.recent ?? []).flatMap((tx) => tx.codes ?? []))
  );

  return (
    <div className="card animate-slide-up">
      <div className="stat-label mb-5">ERC-8021 Builder Code Attribution</div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-o-bg rounded-lg p-3 border border-o-border">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider">Attributed TXs</div>
          <div className="font-display text-xl font-semibold text-o-blueText mt-1">{data.total_attributed_txs ?? 0}</div>
        </div>
        <div className="bg-o-bg rounded-lg p-3 border border-o-border">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider">Gas Attributed</div>
          <div className="font-display text-xl font-semibold text-o-text mt-1">{gasEth.toFixed(6)} ETH</div>
        </div>
        <div className="bg-o-bg rounded-lg p-3 border border-o-border">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider">Multi-Code TXs</div>
          <div className="font-display text-xl font-semibold text-o-green mt-1">{data.multi_code_txs ?? 0}</div>
        </div>
        <div className="bg-o-bg rounded-lg p-3 border border-o-border">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider">Unique Codes</div>
          <div className="font-display text-xl font-semibold text-o-text mt-1">{uniqueCodes.length}</div>
        </div>
      </div>

      {uniqueCodes.length > 0 && (
        <div className="mb-6">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-2">Registered Codes</div>
          <div className="flex flex-wrap gap-1.5">
            {uniqueCodes.map((code) => (
              <span
                key={code}
                className="px-2 py-0.5 bg-o-blue/10 text-o-blueText rounded text-xs font-mono border border-o-blue/20"
              >
                {code}
              </span>
            ))}
          </div>
        </div>
      )}

      {(data.recent ?? []).length > 0 && (
        <div className="mb-6">
          <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-3">Recent Attributed Transactions</div>
          <div className="space-y-1.5 max-h-60 overflow-y-auto">
            {data.recent.map((tx) => {
              const ts = new Date(tx.created_at).toLocaleString("en-US", {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                hour12: false,
              });
              return (
                <div
                  key={tx.tx_hash}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-3 py-2 px-3 bg-o-bg rounded-lg border border-o-border"
                >
                  <a
                    href={`https://basescan.org/tx/0x${tx.tx_hash}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-xs text-o-blueText hover:underline shrink-0"
                  >
                    0x{tx.tx_hash.slice(0, 10)}...
                  </a>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {tx.codes.map((c) => (
                      <span
                        key={c}
                        className="px-1.5 py-0.5 bg-o-blue/10 text-o-blueText rounded text-xs font-mono"
                      >
                        {c}
                      </span>
                    ))}
                    {tx.is_multi && (
                      <span className="text-xs text-o-green font-semibold">DUAL</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-xs text-o-muted">{ts}</span>
                    <span className="font-mono text-xs text-o-muted">
                      {(parseInt(tx.gas_used || "0") / 1e18).toFixed(8)} ETH
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="pt-4 border-t border-o-border">
        <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-2">
          Live Decoder
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={decodeInput}
            onChange={(e) => setDecodeInput(e.target.value)}
            placeholder="Paste calldata or tx data to decode..."
            className="flex-1 bg-o-bg border border-o-border rounded-lg px-3 py-2.5 font-mono text-xs text-o-text placeholder-o-muted focus:outline-none focus:border-o-blueText"
          />
          <button
            onClick={handleDecode}
            className="px-4 py-2.5 bg-o-blue/10 text-o-blueText border border-o-blue/20 rounded-lg text-xs font-medium hover:bg-o-blue/20 transition-colors"
          >
            Decode
          </button>
        </div>
        {decoded && (
          <div className="mt-2 font-mono text-xs">
            {decoded.length > 0 ? (
              <span className="text-o-green">
                Found codes: {decoded.join(", ")}
              </span>
            ) : (
              <span className="text-o-textSecondary">No builder codes found</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
