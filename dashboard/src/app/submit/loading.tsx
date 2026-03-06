export default function SubmitLoading() {
  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto animate-pulse">
      <div className="mb-8">
        <div className="h-8 w-56 bg-o-border/30 rounded" />
        <div className="h-4 w-96 bg-o-border/20 rounded mt-2" />
      </div>

      {/* Configuration */}
      <div className="border border-o-border rounded-xl p-4 mb-6">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="h-4 w-12 bg-o-border/30 rounded" />
            <div className="h-8 w-24 bg-o-border/30 rounded-full" />
          </div>
          <div className="flex items-center justify-between">
            <div className="h-4 w-20 bg-o-border/30 rounded" />
            <div className="h-8 w-24 bg-o-border/30 rounded-full" />
          </div>
        </div>
      </div>

      {/* Environment picker */}
      <div className="h-12 bg-o-border/30 rounded-xl mb-6" />

      {/* File explorer */}
      <div className="card mb-6">
        <div className="h-5 w-16 bg-o-border/20 rounded mb-3" />
        <div className="h-64 bg-o-border/30 rounded" />
      </div>

      {/* Submit bar */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div className="h-10 w-48 bg-o-border/20 rounded" />
          <div className="h-12 w-36 bg-o-border/30 rounded-lg" />
        </div>
      </div>
    </main>
  );
}
