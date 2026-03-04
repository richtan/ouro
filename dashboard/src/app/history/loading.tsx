export default function HistoryLoading() {
  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto animate-pulse">
      <div className="mb-8">
        <div className="h-8 w-32 bg-o-border/30 rounded" />
        <div className="h-4 w-72 bg-o-border/20 rounded mt-2" />
      </div>

      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="card">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-5 w-20 bg-o-border/30 rounded" />
                <div className="h-5 w-24 bg-o-border/20 rounded-full" />
              </div>
              <div className="h-4 w-4 bg-o-border/20 rounded" />
            </div>
            <div className="flex items-center gap-3 mt-2">
              <div className="h-4 w-16 bg-o-border/20 rounded" />
              <div className="h-4 w-32 bg-o-border/20 rounded" />
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
