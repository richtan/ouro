"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useAccount, useWalletClient, usePublicClient } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { x402Client } from "@x402/fetch";
import { ExactEvmScheme, toClientEvmSigner } from "@x402/evm";
import { wrapFetchWithPayment } from "@x402/fetch";

const MCP_URL = process.env.NEXT_PUBLIC_MCP_URL ?? "";

interface Session {
  id: string;
  status: string;
  script: string;
  nodes: number;
  time_limit_min: number;
  price: string;
  agent_url: string;
  job_id: string | null;
}

type PayStatus = "loading" | "ready" | "submitting" | "paying" | "success" | "error" | "not_found";

export default function PayPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { address, isConnected } = useAccount();
  const { data: walletClient } = useWalletClient();
  const publicClient = usePublicClient();

  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<PayStatus>("loading");
  const [error, setError] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    fetch(`${MCP_URL}/api/sessions/${sessionId}`)
      .then((r) => {
        if (!r.ok) throw new Error("Session not found or expired");
        return r.json();
      })
      .then((data: Session) => {
        if (data.status === "paid" && data.job_id) {
          setSession(data);
          setJobId(data.job_id);
          setStatus("success");
        } else {
          setSession(data);
          setStatus("ready");
        }
      })
      .catch(() => setStatus("not_found"));
  }, [sessionId]);

  const handlePay = async () => {
    if (!walletClient || !publicClient || !isConnected || !session) return;
    setStatus("submitting");
    setError("");

    try {
      const signer = toClientEvmSigner(
        {
          address: walletClient.account.address,
          signTypedData: (args: Record<string, unknown>) =>
            walletClient.signTypedData(args as Parameters<typeof walletClient.signTypedData>[0]),
        },
        publicClient,
      );
      const client = new x402Client();
      client.register("eip155:*", new ExactEvmScheme(signer));
      const fetchWithPay = wrapFetchWithPayment(fetch, client);

      setStatus("paying");

      const res = await fetchWithPay("/api/proxy/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          script: session.script,
          nodes: session.nodes,
          time_limit_min: session.time_limit_min,
          submitter_address: address,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setJobId(data.job_id);

      await fetch(`${MCP_URL}/api/sessions/${sessionId}/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: data.job_id }),
      });

      setStatus("success");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Payment failed");
      setStatus("error");
    }
  };

  if (status === "loading") {
    return (
      <main className="relative z-10 min-h-screen flex items-center justify-center">
        <div className="card text-center py-16 px-8">
          <div className="w-6 h-6 border-2 border-ouro-accent/30 border-t-ouro-accent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-ouro-muted text-sm">Loading session...</p>
        </div>
      </main>
    );
  }

  if (status === "not_found") {
    return (
      <main className="relative z-10 min-h-screen flex items-center justify-center">
        <div className="card text-center py-16 px-8 max-w-md">
          <div className="w-3 h-3 rounded-full bg-ouro-red mx-auto mb-4" />
          <h1 className="font-display text-xl font-bold text-ouro-text mb-2">Session Not Found</h1>
          <p className="text-ouro-muted text-sm">
            This payment link has expired or is invalid. Request a new one from your AI agent.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="relative z-10 min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-ouro-text">
          Pay for Compute Job
        </h1>
        <p className="font-body text-sm text-ouro-muted mt-1">
          Review the job details and pay with USDC via x402
        </p>
      </div>

      {/* Job Details */}
      <div className="card mb-6">
        <label className="stat-label mb-3 block">Job Details</label>
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-xs text-ouro-muted">Network</span>
            <span className="px-2 py-0.5 text-[10px] font-semibold bg-blue-500/20 text-blue-400 rounded">
              Base Mainnet
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-ouro-muted">Nodes</span>
            <span className="font-mono text-sm text-ouro-text">{session?.nodes}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-ouro-muted">Time Limit</span>
            <span className="font-mono text-sm text-ouro-text">{session?.time_limit_min} min</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-ouro-muted">Price</span>
            <span className="font-mono text-sm font-semibold text-green-400">{session?.price} USDC</span>
          </div>
        </div>
      </div>

      {/* Script Preview */}
      <div className="card mb-6">
        <label className="stat-label mb-3 block">Script</label>
        <pre className="bg-black/40 border border-ouro-border/40 rounded-lg p-4 font-mono text-xs text-ouro-text whitespace-pre-wrap break-all max-h-40 overflow-y-auto leading-relaxed">
          {session?.script}
        </pre>
      </div>

      {status === "success" ? (
        <div className="card border-green-500/30">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2.5 h-2.5 rounded-full bg-green-400" />
            <span className="stat-label text-green-400">Job Submitted</span>
          </div>
          <p className="font-mono text-xs text-ouro-muted mb-2">
            Job ID: {jobId}
          </p>
          <p className="text-sm text-ouro-muted">
            Your AI agent will automatically pick up the result. You can close this tab.
          </p>
        </div>
      ) : !isConnected ? (
        <div className="card flex flex-col items-center justify-center py-10 gap-4">
          <p className="text-ouro-muted text-sm">Connect your wallet to pay for this compute job</p>
          <ConnectButton />
        </div>
      ) : (
        <>
          <div className="card">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-ouro-muted">
                  Payment via <span className="text-ouro-accent">x402</span> protocol
                  &mdash; sign a USDC authorization to pay
                </p>
                <p className="text-xs text-ouro-muted/60 mt-1">
                  Connected: {address?.slice(0, 6)}...{address?.slice(-4)}
                </p>
              </div>
              <button
                onClick={handlePay}
                disabled={status === "submitting" || status === "paying"}
                className="px-6 py-3 bg-ouro-accent text-ouro-bg font-display font-bold text-sm rounded-lg hover:bg-ouro-accent/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {status === "submitting"
                  ? "Preparing..."
                  : status === "paying"
                    ? "Sign Payment..."
                    : `Pay ${session?.price} USDC`}
              </button>
            </div>
          </div>

          {status === "error" && (
            <div className="card border-ouro-red/30 mt-6">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2.5 h-2.5 rounded-full bg-ouro-red" />
                <span className="stat-label text-ouro-red">Payment Failed</span>
              </div>
              <p className="font-mono text-xs text-ouro-red/80">{error}</p>
            </div>
          )}
        </>
      )}
    </main>
  );
}
