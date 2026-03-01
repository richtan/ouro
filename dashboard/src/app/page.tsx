import WalletBalance from "@/components/WalletBalance";
import FinancialPnL from "@/components/FinancialPnL";
import SustainabilityGauge from "@/components/SustainabilityGauge";
import PublicJobStats from "@/components/PublicJobStats";
import AttributionPanel from "@/components/AttributionPanel";
import RevenueModel from "@/components/RevenueModel";

export default function Home() {
  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Ouro Compute
        </h1>
        <p className="font-body text-sm text-o-textSecondary mt-1">
          Autonomous HPC agent on Base &middot; Self-sustaining via x402
          &middot; ERC-8021 attributed
        </p>
      </div>

      <div className="mb-6">
        <WalletBalance />
      </div>

      <div className="mb-6">
        <RevenueModel />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <FinancialPnL />
        <SustainabilityGauge />
      </div>

      <div className="mb-6">
        <PublicJobStats />
      </div>

      <div className="mb-6">
        <AttributionPanel />
      </div>

      <footer className="text-center py-6 border-t border-o-border">
        <p className="text-xs text-o-muted font-body">
          Autonomous HPC compute on Base &middot; ERC-8021 + ERC-8004 + x402
        </p>
      </footer>
    </main>
  );
}
