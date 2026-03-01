export default function Footer() {
  return (
    <footer className="border-t border-o-border">
      <div className="max-w-7xl mx-auto px-4 md:px-8 py-6 flex items-center justify-between">
        <span className="font-display text-sm font-bold text-o-blueText tracking-tight">
          OURO
        </span>
        <div className="flex items-center gap-4 text-xs text-o-muted">
          <a
            href="https://github.com/richtan/ouro"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-o-text transition-colors"
          >
            GitHub
          </a>
          <span className="text-o-border">·</span>
          <a
            href="https://basescan.org/address/0x1451b27680f54F5FF608ebf5B171Ce480FbAe7e5"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-o-text transition-colors"
          >
            Contract
          </a>
          <span className="text-o-border">·</span>
          <a
            href="https://x402.org"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-o-text transition-colors"
          >
            x402
          </a>
        </div>
        <span className="text-xs text-o-muted">Built on Base</span>
      </div>
    </footer>
  );
}
