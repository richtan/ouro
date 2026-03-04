import DocsSidebar from "@/components/docs/DocsSidebar";

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-7xl mx-auto">
      <div className="lg:flex lg:gap-12">
        <DocsSidebar />
        <div className="flex-1 max-w-4xl">{children}</div>
      </div>
    </main>
  );
}
