"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAccount } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";

const ADMIN_ADDRESS =
  process.env.NEXT_PUBLIC_ADMIN_ADDRESS?.toLowerCase() ?? "";

const BASE_NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/submit", label: "Submit Job" },
  { href: "/history", label: "My Jobs" },
];

export default function NavBar() {
  const pathname = usePathname();
  const { address } = useAccount();

  const isAdmin = address?.toLowerCase() === ADMIN_ADDRESS && ADMIN_ADDRESS !== "";

  const navItems = isAdmin
    ? [...BASE_NAV, { href: "/admin", label: "Admin" }]
    : BASE_NAV;

  return (
    <nav className="sticky top-0 z-50 border-b border-ouro-border bg-ouro-bg/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 md:px-8 lg:px-12 flex items-center justify-between h-14">
        <div className="flex items-center gap-6">
          <Link href="/" className="font-display text-lg font-bold text-ouro-accent tracking-tight">
            OURO
          </Link>
          <div className="flex items-center gap-1">
            {navItems.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3 py-1.5 rounded text-xs font-mono uppercase tracking-wider transition-colors ${
                    active
                      ? "bg-ouro-accent/10 text-ouro-accent"
                      : "text-ouro-muted hover:text-ouro-text hover:bg-white/[0.03]"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
        <ConnectButton
          chainStatus="icon"
          accountStatus="address"
          showBalance={false}
        />
      </div>
    </nav>
  );
}
