"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAccount } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";

const ADMIN_ADDRESS =
  process.env.NEXT_PUBLIC_ADMIN_ADDRESS?.toLowerCase() ?? "";

const BASE_NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/submit", label: "Submit" },
  { href: "/history", label: "My Jobs" },
];

export default function NavBar() {
  const pathname = usePathname();
  const { address } = useAccount();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  if (pathname === "/") return null;

  const isAdmin =
    address?.toLowerCase() === ADMIN_ADDRESS && ADMIN_ADDRESS !== "";

  const navItems = isAdmin
    ? [...BASE_NAV, { href: "/admin", label: "Admin" }]
    : BASE_NAV;

  return (
    <nav className="sticky top-0 z-50 border-b border-o-border bg-o-bg/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 md:px-8 lg:px-12 flex items-center justify-between h-14">
        <div className="flex items-center gap-4 sm:gap-6">
          <Link
            href="/"
            className="font-display text-base sm:text-lg font-bold text-o-blueText tracking-tight"
          >
            OURO
          </Link>
          <div className="hidden sm:flex items-center gap-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex items-center px-3 py-2 rounded-lg text-xs font-sans font-medium uppercase tracking-wider transition-colors ${
                  pathname === item.href
                    ? "bg-o-blue/10 text-o-blueText"
                    : "text-o-textSecondary hover:text-o-text hover:bg-o-surfaceHover"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/docs"
            className={`hidden sm:inline-flex items-center px-3 py-2 rounded-lg text-xs font-sans font-medium uppercase tracking-wider transition-colors ${
              pathname.startsWith("/docs")
                ? "bg-o-blue/10 text-o-blueText"
                : "text-o-textSecondary hover:text-o-text hover:bg-o-surfaceHover"
            }`}
          >
            Docs
          </Link>
          <a
            href="https://github.com/richtan/ouro"
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 text-o-muted hover:text-o-text transition-colors"
            aria-label="GitHub"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
            </svg>
          </a>
          <ConnectButton.Custom>
            {({
              account,
              chain,
              openAccountModal,
              openChainModal,
              openConnectModal,
            }) => {
              return (
                <div>
                  {(() => {
                    if (!account || !chain) {
                      return (
                        <button
                          onClick={openConnectModal}
                          type="button"
                          className="px-4 py-1.5 rounded-lg bg-o-blue hover:bg-o-blueHover text-white text-xs font-semibold tracking-wide transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-o-blueText/30"
                        >
                          Connect
                        </button>
                      );
                    }

                    if (chain.unsupported) {
                      return (
                        <button
                          onClick={openChainModal}
                          type="button"
                          className="px-3 py-1.5 rounded-lg bg-o-red/15 border border-o-red/40 text-o-red text-xs font-medium tracking-wide hover:bg-o-red/25 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-o-blueText/30"
                        >
                          Wrong network
                        </button>
                      );
                    }

                    return (
                      <button
                        onClick={openAccountModal}
                        type="button"
                        className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-o-surface border border-o-border hover:border-o-borderHover transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-o-blueText/30"
                      >
                        {chain.hasIcon && chain.iconUrl && (
                          <div
                            className="w-4 h-4 rounded-full overflow-hidden"
                            style={{ background: chain.iconBackground }}
                          >
                            <img
                              alt={chain.name ?? "Chain"}
                              src={chain.iconUrl}
                              className="w-4 h-4"
                            />
                          </div>
                        )}
                        <span className="hidden sm:inline font-mono text-xs text-o-text">
                          {account.displayName}
                        </span>
                      </button>
                    );
                  })()}
                </div>
              );
            }}
          </ConnectButton.Custom>
          <button
            type="button"
            className="sm:hidden p-2 text-o-muted hover:text-o-text transition-colors"
            onClick={() => setMobileOpen((o) => !o)}
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
          >
            {mobileOpen ? (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {mobileOpen && (
        <div className="sm:hidden border-t border-o-border bg-o-bg/95 backdrop-blur-md">
          <div className="flex flex-col px-4 py-2">
            {navItems.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileOpen(false)}
                  className={`inline-flex items-center min-h-[44px] px-3 rounded-lg text-xs font-sans font-medium uppercase tracking-wider transition-colors ${
                    active
                      ? "bg-o-blue/10 text-o-blueText"
                      : "text-o-textSecondary hover:text-o-text hover:bg-o-surfaceHover"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
            <div className="border-t border-o-border mt-1 pt-1">
              <Link
                href="/docs"
                onClick={() => setMobileOpen(false)}
                className={`inline-flex items-center min-h-[44px] px-3 rounded-lg text-xs font-sans font-medium uppercase tracking-wider transition-colors ${
                  pathname.startsWith("/docs")
                    ? "bg-o-blue/10 text-o-blueText"
                    : "text-o-textSecondary hover:text-o-text hover:bg-o-surfaceHover"
                }`}
              >
                Docs
              </Link>
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
