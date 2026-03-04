export default function SubmitLoading() {
  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto animate-pulse">
      <div className="mb-8">
        <div className="h-8 w-56 bg-o-border/30 rounded" />
        <div className="h-4 w-96 bg-o-border/20 rounded mt-2" />
      </div>

      {/* Script editor */}
      <div className="card mb-6">
        <div className="h-5 w-16 bg-o-border/20 rounded mb-3" />
        <div className="h-64 bg-o-border/30 rounded" />
      </div>

      {/* Parameters */}
      <div className="card mb-6">
        <div className="h-5 w-24 bg-o-border/20 rounded mb-4" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="h-16 bg-o-border/30 rounded" />
          <div className="h-16 bg-o-border/30 rounded" />
          <div className="h-16 bg-o-border/30 rounded" />
        </div>
      </div>

      {/* Submit button */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div className="h-10 w-48 bg-o-border/20 rounded" />
          <div className="h-12 w-36 bg-o-border/30 rounded-lg" />
        </div>
      </div>
    </main>
  );
}
