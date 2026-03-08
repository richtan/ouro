"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/docs", label: "Get Started" },
  { href: "/docs/mcp", label: "MCP Tools" },
  { href: "/docs/agent", label: "Autonomous Agents" },
  { href: "/docs/api", label: "REST API" },
  { href: "/docs/pricing", label: "Pricing" },
];

export default function DocsSidebar() {
  const pathname = usePathname();

  return (
    <>
      {/* Desktop: vertical sidebar */}
      <nav className="hidden lg:block w-56 shrink-0 sticky top-20 self-start">
        <div className="flex flex-col gap-0.5">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block px-3 py-2.5 rounded-lg text-xs font-sans font-medium tracking-wider transition-colors ${
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
      </nav>

      {/* Mobile: horizontal scroll strip */}
      <div className="lg:hidden mb-6 -mx-4 px-4 overflow-x-auto">
        <div className="flex gap-1 min-w-max">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex items-center px-3 py-2.5 rounded-lg text-xs font-sans font-medium tracking-wider whitespace-nowrap transition-colors ${
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
    </>
  );
}
