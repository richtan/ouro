"use client";

import { useCallback, useEffect, useState } from "react";
import { useAccount, useSignMessage } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import JobsPanel from "@/components/JobsPanel";
import TerminalFeed from "@/components/TerminalFeed";
import AuditPanel from "@/components/AuditPanel";

const ADMIN_ADDRESS = process.env.NEXT_PUBLIC_ADMIN_ADDRESS?.toLowerCase() ?? "";

export default function AdminPage() {
  const { address, isConnected } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = isConnected && address?.toLowerCase() === ADMIN_ADDRESS;

  useEffect(() => {
    if (!isAdmin) {
      setChecking(false);
      setAuthenticated(false);
      return;
    }
    fetch("/api/admin/check")
      .then((r) => {
        setAuthenticated(r.ok);
        setChecking(false);
      })
      .catch(() => {
        setAuthenticated(false);
        setChecking(false);
      });
  }, [isAdmin]);

  const handleSignIn = useCallback(async () => {
    if (!address) return;
    setSigning(true);
    setError(null);
    try {
      const ts = Math.floor(Date.now() / 1000);
      const message = `Ouro Admin Auth ${ts}`;
      const signature = await signMessageAsync({ message });
      const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address, message, signature }),
      });
      if (res.ok) {
        setAuthenticated(true);
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.error ?? "Authentication failed");
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Signing cancelled";
      setError(msg);
    } finally {
      setSigning(false);
    }
  }, [address, signMessageAsync]);

  const handleSignOut = useCallback(async () => {
    await fetch("/api/admin/logout", { method: "POST" }).catch(() => {});
    setAuthenticated(false);
  }, []);

  // State 1: Not connected
  if (!isConnected) {
    return (
      <main className="relative z-10 min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-ouro-text">
            Operator Panel
          </h1>
          <p className="font-body text-sm text-ouro-muted mt-1">
            Connect your wallet to access the admin dashboard
          </p>
        </div>
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="text-ouro-muted"
          >
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0110 0v4" />
          </svg>
          <p className="text-ouro-muted text-sm">
            Connect your wallet to continue
          </p>
          <ConnectButton />
        </div>
      </main>
    );
  }

  // State 2: Wrong wallet
  if (!isAdmin) {
    return (
      <main className="relative z-10 min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-ouro-text">
            Operator Panel
          </h1>
        </div>
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="text-ouro-red"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          <p className="text-ouro-muted text-sm">
            Access restricted to the Ouro operator
          </p>
          <p className="font-mono text-xs text-ouro-muted/60">
            Connected: {address?.slice(0, 6)}...{address?.slice(-4)}
          </p>
        </div>
      </main>
    );
  }

  // State 3: Correct wallet, checking / not signed in
  if (checking) {
    return (
      <main className="relative z-10 min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-7xl mx-auto">
        <div className="card flex items-center justify-center py-16">
          <div className="w-6 h-6 border-2 border-ouro-accent border-t-transparent rounded-full animate-spin" />
        </div>
      </main>
    );
  }

  if (!authenticated) {
    return (
      <main className="relative z-10 min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-ouro-text">
            Operator Panel
          </h1>
          <p className="font-body text-sm text-ouro-muted mt-1">
            Sign a message to verify wallet ownership
          </p>
        </div>
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="text-ouro-accent"
          >
            <path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4" />
            <polyline points="10 17 15 12 10 7" />
            <line x1="15" y1="12" x2="3" y2="12" />
          </svg>
          <p className="text-ouro-muted text-sm">
            Sign to authenticate as operator
          </p>
          <button
            onClick={handleSignIn}
            disabled={signing}
            className="px-6 py-2.5 bg-ouro-accent/10 text-ouro-accent border border-ouro-accent/20 rounded text-sm font-mono hover:bg-ouro-accent/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {signing ? "Waiting for signature..." : "Sign to authenticate"}
          </button>
          {error && (
            <p className="text-ouro-red text-xs font-mono mt-2">{error}</p>
          )}
        </div>
      </main>
    );
  }

  // State 4: Authenticated
  return (
    <main className="relative z-10 min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-ouro-text">
            Operator Panel
          </h1>
          <p className="font-body text-sm text-ouro-muted mt-1">
            Full system visibility &middot; Admin access
          </p>
        </div>
        <button
          onClick={handleSignOut}
          className="px-3 py-1.5 text-xs font-mono text-ouro-muted hover:text-ouro-red border border-ouro-border rounded hover:border-ouro-red/30 transition-colors"
        >
          Sign out
        </button>
      </div>

      <div className="mb-6">
        <JobsPanel />
      </div>

      <div className="mb-6">
        <TerminalFeed />
      </div>

      <div className="mb-6">
        <AuditPanel />
      </div>
    </main>
  );
}
