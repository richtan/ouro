"use client";

import { useEffect, useState } from "react";
import { fetchWallet } from "@/lib/api";

interface WalletData {
  address: string;
  eth_balance_wei: string;
  usdc_balance: number;
  eth_price_usd: number;
  snapshots: {
    eth_balance_wei: string;
    usdc_balance: number;
    eth_price_usd: number | null;
    recorded_at: string;
  }[];
}

function weiToEth(wei: string): number {
  return parseInt(wei) / 1e18;
}

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 200;
  const h = 48;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  });
  const areaPoints = `0,${h} ${points.join(" ")} ${w},${h}`;
  const lineColor = data[data.length - 1] >= data[0] ? "#10b981" : "#ef4444";
  return (
    <svg width={w} height={h} className="opacity-80">
      <defs>
        <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={lineColor} stopOpacity="0.2" />
          <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon fill="url(#sparkFill)" points={areaPoints} />
      <polyline fill="none" stroke={lineColor} strokeWidth="1.5" points={points.join(" ")} />
    </svg>
  );
}

export default function WalletBalance() {
  const [data, setData] = useState<WalletData | null>(null);

  useEffect(() => {
    const load = () => fetchWallet().then(setData).catch(() => {});
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  if (!data) {
    return (
      <div className="card animate-pulse">
        <div className="h-28 bg-ouro-border/30 rounded" />
      </div>
    );
  }

  const ethBalance = weiToEth(data.eth_balance_wei ?? "0");
  const totalUsd = ethBalance * (data.eth_price_usd ?? 0) + (data.usdc_balance ?? 0);
  const shortAddr = data.address
    ? `${data.address.slice(0, 6)}...${data.address.slice(-4)}`
    : "—";
  const sparkData = [...(data.snapshots ?? [])]
    .reverse()
    .map((s) => weiToEth(s.eth_balance_wei ?? "0") * (s.eth_price_usd ?? 0) + (s.usdc_balance ?? 0));

  return (
    <div className="card col-span-full animate-fade-in">
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-3">
            <div className="stat-label">Agent Wallet</div>
            <a
              href={`https://basescan.org/address/${data.address}`}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-xs text-ouro-accent hover:underline"
            >
              {shortAddr}
            </a>
          </div>

          <div className="font-display text-4xl md:text-5xl font-bold text-ouro-accent glow-cyan tracking-tight">
            ${totalUsd.toFixed(2)}
          </div>
          <div className="text-sm text-ouro-muted mt-1">Total Portfolio Value (USD)</div>
        </div>
        <div className="shrink-0">
          <Sparkline data={sparkData} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6 mt-6 pt-5 border-t border-ouro-border/50">
        <div>
          <div className="stat-label">ETH Balance</div>
          <div className="font-display text-xl font-bold text-ouro-text mt-1">
            {ethBalance.toFixed(4)}
            <span className="text-sm text-ouro-muted ml-1.5 font-normal">ETH</span>
          </div>
          <div className="text-xs text-ouro-muted mt-0.5">
            @ ${(data.eth_price_usd ?? 0).toFixed(0)}/ETH
          </div>
        </div>
        <div>
          <div className="stat-label">USDC Balance</div>
          <div className="font-display text-xl font-bold text-ouro-text mt-1">
            {(data.usdc_balance ?? 0).toFixed(2)}
            <span className="text-sm text-ouro-muted ml-1.5 font-normal">USDC</span>
          </div>
        </div>
        <div>
          <div className="stat-label">Network</div>
          <div className="font-display text-xl font-bold text-ouro-text mt-1">
            Base
            <span className="text-sm text-ouro-green ml-1.5 font-normal">Mainnet</span>
          </div>
        </div>
      </div>
    </div>
  );
}
