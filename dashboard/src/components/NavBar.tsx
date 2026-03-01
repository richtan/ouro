"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAccount } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";

const ADMIN_ADDRESS =
  process.env.NEXT_PUBLIC_ADMIN_ADDRESS?.toLowerCase() ?? "";

const BASE_NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/submit", label: "Submit" },
  { href: "/history", label: "My Jobs" },
];

export default function NavBar() {
  const pathname = usePathname();
  const { address } = useAccount();

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
          <div className="flex items-center gap-0.5">
            {navItems.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-2 py-1.5 sm:px-3 sm:py-2 rounded-lg text-[11px] sm:text-xs font-mono uppercase tracking-wider transition-colors ${
                    active
                      ? "bg-o-blue/10 text-o-blueText"
                      : "text-o-textSecondary hover:text-o-text hover:bg-o-surfaceHover"
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
