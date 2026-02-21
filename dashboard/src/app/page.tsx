import WalletBalance from "@/components/WalletBalance";
import FinancialPnL from "@/components/FinancialPnL";
import SustainabilityGauge from "@/components/SustainabilityGauge";
import TerminalFeed from "@/components/TerminalFeed";
import JobsPanel from "@/components/JobsPanel";
import AttributionPanel from "@/components/AttributionPanel";
import RevenueModel from "@/components/RevenueModel";

export default function Home() {
  return (
    <main className="relative z-10 min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-ouro-text">
          <span className="text-ouro-accent">OURO</span>
          <span className="text-ouro-muted mx-2">/</span>
          <span className="text-ouro-text/80">Proof-of-Compute Oracle</span>
        </h1>
        <p className="font-body text-sm text-ouro-muted mt-1">
          Autonomous HPC agent on Base &middot; Self-sustaining via x402
          &middot; ERC-8021 attributed
        </p>
      </div>

      {/* Wallet Balance — full width hero */}
      <div className="mb-6">
        <WalletBalance />
      </div>

      {/* Revenue Model — prominent positioning for judges */}
      <div className="mb-6">
        <RevenueModel />
      </div>

      {/* Financial P&L + Sustainability — 2 col */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <FinancialPnL />
        <SustainabilityGauge />
      </div>

      {/* Jobs Panel — full width, prominent */}
      <div className="mb-6">
        <JobsPanel />
      </div>

      {/* Terminal Feed — full width */}
      <div className="mb-6">
        <TerminalFeed />
      </div>

      {/* Attribution Panel — full width */}
      <div className="mb-6">
        <AttributionPanel />
      </div>

      {/* Footer */}
      <footer className="text-center py-6 border-t border-ouro-border">
        <p className="text-xs text-ouro-muted font-body">
          Built for ETHDenver 2026 &middot; Base Self-Sustaining Agents Bounty
          &middot; ERC-8021 + ERC-8004 + x402
        </p>
      </footer>
    </main>
  );
}
