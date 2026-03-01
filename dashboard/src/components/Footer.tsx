export default function Footer() {
  return (
    <footer className="mt-auto border-t border-o-border">
      <div className="max-w-7xl mx-auto px-4 md:px-8 lg:px-12 py-6 flex flex-col sm:flex-row items-center justify-between gap-4">
        <span className="font-display text-sm font-bold text-o-blueText tracking-tight">
          OURO
        </span>

        <span className="flex items-center gap-1.5 text-xs text-o-muted">
          Built on
          <svg width="16" height="16" viewBox="0 0 111 111" fill="none" aria-label="Base">
            <circle cx="55.5" cy="55.5" r="55.5" fill="#0052FF" />
            <path
              d="M55.39 93.72c21.14 0 38.28-17.14 38.28-38.28S76.53 17.16 55.39 17.16c-20.05 0-36.46 15.42-38.12 35.07h50.48v6.42H17.27c1.66 19.65 18.07 35.07 38.12 35.07z"
              fill="white"
            />
          </svg>
          Base
        </span>
      </div>
    </footer>
  );
}
