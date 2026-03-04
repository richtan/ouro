export default function AdminLoading() {
  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-7xl mx-auto animate-pulse">
      <div className="mb-6">
        <div className="h-8 w-32 bg-o-border/30 rounded" />
        <div className="h-4 w-64 bg-o-border/20 rounded mt-2" />
      </div>

      <div className="space-y-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="card">
            <div className="h-48 bg-o-border/30 rounded" />
          </div>
        ))}
      </div>
    </main>
  );
}
