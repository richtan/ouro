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
        <div className="h-32 bg-ouro-border/30 rounded" />
      </div>
    );
  }

  const gasEth = (data.total_gas_attributed ?? 0) / 1e18;

  const uniqueCodes = Array.from(
    new Set((data.recent ?? []).flatMap((tx) => tx.codes ?? []))
  );

  return (
    <div className="card col-span-full animate-slide-up">
      <div className="stat-label mb-5">ERC-8021 Builder Code Attribution</div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">Attributed TXs</div>
          <div className="font-display text-xl font-bold text-ouro-accent mt-1">{data.total_attributed_txs ?? 0}</div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">Gas Attributed</div>
          <div className="font-display text-xl font-bold text-ouro-text mt-1">{gasEth.toFixed(6)} ETH</div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">Multi-Code TXs</div>
          <div className="font-display text-xl font-bold text-ouro-green mt-1">{data.multi_code_txs ?? 0}</div>
        </div>
        <div className="bg-black/30 rounded-lg p-3 border border-ouro-border/30">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider">Unique Codes</div>
          <div className="font-display text-xl font-bold text-ouro-text mt-1">{uniqueCodes.length}</div>
        </div>
      </div>

      {uniqueCodes.length > 0 && (
        <div className="mb-6">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-2">Registered Codes</div>
          <div className="flex flex-wrap gap-1.5">
            {uniqueCodes.map((code) => (
              <span
                key={code}
                className="px-2 py-0.5 bg-ouro-accent/10 text-ouro-accent rounded text-xs font-mono border border-ouro-accent/20"
              >
                {code}
              </span>
            ))}
          </div>
        </div>
      )}

      {(data.recent ?? []).length > 0 && (
        <div className="mb-6">
          <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-3">Recent Attributed Transactions</div>
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
                  className="flex items-center justify-between gap-3 py-2 px-3 bg-black/20 rounded-lg border border-ouro-border/20"
                >
                  <a
                    href={`https://basescan.org/tx/0x${tx.tx_hash}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-xs text-ouro-accent hover:underline shrink-0"
                  >
                    0x{tx.tx_hash.slice(0, 10)}...
                  </a>
                  <div className="flex items-center gap-1.5 flex-wrap justify-center">
                    {tx.codes.map((c) => (
                      <span
                        key={c}
                        className="px-1.5 py-0.5 bg-ouro-accent/10 text-ouro-accent rounded text-[10px] font-mono"
                      >
                        {c}
                      </span>
                    ))}
                    {tx.is_multi && (
                      <span className="text-[10px] text-ouro-green font-mono">DUAL</span>
                    )}
                  </div>
                  <span className="text-[10px] text-ouro-muted shrink-0">{ts}</span>
                  <span className="font-mono text-[10px] text-ouro-muted shrink-0">
                    {(parseInt(tx.gas_used || "0") / 1e18).toFixed(8)} ETH
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="pt-4 border-t border-ouro-border/50">
        <div className="text-[10px] text-ouro-muted uppercase tracking-wider mb-2">
          Live Decoder
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={decodeInput}
            onChange={(e) => setDecodeInput(e.target.value)}
            placeholder="Paste calldata or tx data to decode..."
            className="flex-1 bg-black/40 border border-ouro-border/40 rounded px-3 py-2 font-mono text-xs text-ouro-text placeholder-ouro-muted/50 focus:outline-none focus:border-ouro-accent/50"
          />
          <button
            onClick={handleDecode}
            className="px-4 py-2 bg-ouro-accent/20 text-ouro-accent border border-ouro-accent/30 rounded text-xs font-mono hover:bg-ouro-accent/30 transition-colors"
          >
            Decode
          </button>
        </div>
        {decoded && (
          <div className="mt-2 font-mono text-xs">
            {decoded.length > 0 ? (
              <span className="text-ouro-green">
                Found codes: {decoded.join(", ")}
              </span>
            ) : (
              <span className="text-ouro-muted">No builder codes found</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
