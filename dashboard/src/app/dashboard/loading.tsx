export default function DashboardLoading() {
  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-7xl mx-auto animate-pulse">
      <div className="mb-6">
        <div className="h-8 w-48 bg-o-border/30 rounded" />
        <div className="h-4 w-80 bg-o-border/20 rounded mt-2" />
      </div>

      {/* WalletBalance */}
      <div className="card mb-6">
        <div className="h-28 bg-o-border/30 rounded" />
      </div>

      {/* RevenueModel */}
      <div className="card mb-6">
        <div className="h-48 bg-o-border/30 rounded" />
      </div>

      {/* PnL + Gauge */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div className="card">
          <div className="h-48 bg-o-border/30 rounded" />
        </div>
        <div className="card">
          <div className="h-48 bg-o-border/30 rounded" />
        </div>
      </div>

      {/* PublicJobStats */}
      <div className="card mb-6">
        <div className="h-32 bg-o-border/30 rounded" />
      </div>

      {/* Attribution */}
      <div className="card mb-6">
        <div className="h-32 bg-o-border/30 rounded" />
      </div>
    </main>
  );
}
