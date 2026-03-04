export default function DocsLoading() {
  return (
    <div className="animate-pulse">
      <div className="h-8 w-48 bg-o-border/30 rounded mb-4" />
      <div className="space-y-3">
        <div className="h-4 w-full bg-o-border/20 rounded" />
        <div className="h-4 w-5/6 bg-o-border/20 rounded" />
        <div className="h-4 w-4/6 bg-o-border/20 rounded" />
        <div className="h-4 w-full bg-o-border/20 rounded" />
        <div className="h-4 w-3/4 bg-o-border/20 rounded" />
      </div>
    </div>
  );
}
