"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useAccount, useWalletClient, usePublicClient } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { x402Client } from "@x402/fetch";
import { ExactEvmScheme, toClientEvmSigner } from "@x402/evm";
import { wrapFetchWithPayment } from "@x402/fetch";

interface Session {
  id: string;
  status: string;
  script: string | null;
  job_payload: Record<string, unknown> | null;
  cpus: number;
  time_limit_min: number;
  price: string;
  agent_url: string;
  job_id: string | null;
}

type PayStatus = "loading" | "ready" | "submitting" | "paying" | "success" | "error" | "not_found";

function JobSummary({ session }: { session: Session }) {
  const payload = session.job_payload;
  const entrypoint = payload?.entrypoint as string | undefined;
  const fileCount = (payload?.file_count as number) ?? (payload?.files as unknown[])?.length;
  const dockerfileContent = payload?.dockerfile_content as string | undefined;
  const image = (payload?.image as string) || "base";

  // Parse FROM line from dockerfile_content for display
  let fromImage: string | null = null;
  if (dockerfileContent) {
    const fromMatch = dockerfileContent.match(/^FROM\s+(\S+)/im);
    if (fromMatch) fromImage = fromMatch[1];
  }

  const displayImage = fromImage ?? (image !== "base" ? image : null);

  return (
    <>
      <div className="card mb-6">
        <label className="stat-label mb-3 block">Job Details</label>
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-xs text-o-textSecondary">Network</span>
            <span className="px-2 py-0.5 text-xs font-semibold bg-o-blue/20 text-o-blueText rounded">
              Base Mainnet
            </span>
          </div>
          {displayImage && (
            <div className="flex justify-between items-center">
              <span className="text-xs text-o-textSecondary">Image</span>
              <span className="font-mono text-sm text-o-text">{displayImage}</span>
            </div>
          )}
          {entrypoint && (
            <div className="flex justify-between items-center">
              <span className="text-xs text-o-textSecondary">Entrypoint</span>
              <span className="font-mono text-sm text-o-text">{entrypoint}</span>
            </div>
          )}
          {fileCount != null && fileCount > 1 && (
            <div className="flex justify-between items-center">
              <span className="text-xs text-o-textSecondary">Files</span>
              <span className="font-mono text-sm text-o-text">{fileCount}</span>
            </div>
          )}
          {dockerfileContent && (
            <div className="flex justify-between items-center">
              <span className="text-xs text-o-textSecondary">Environment</span>
              <span className="font-mono text-xs text-o-blueText">Dockerfile</span>
            </div>
          )}
          <div className="flex justify-between items-center">
            <span className="text-xs text-o-textSecondary">CPUs</span>
            <span className="font-mono text-sm text-o-text">{session.cpus}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-o-textSecondary">Time Limit</span>
            <span className="font-mono text-sm text-o-text">{session.time_limit_min} min</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-xs text-o-textSecondary">Price</span>
            <span className="font-mono text-sm font-semibold text-o-green">{session.price} USDC</span>
          </div>
        </div>
      </div>
      {session.script && (
        <div className="card mb-6">
          <label className="stat-label mb-3 block">Script</label>
          <pre className="bg-o-bg border border-o-border rounded-lg p-4 font-mono text-xs text-o-text whitespace-pre-wrap break-all max-h-40 overflow-y-auto leading-relaxed">
            {session.script}
          </pre>
        </div>
      )}
    </>
  );
}

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
    fetch(`/api/proxy/sessions/${sessionId}`)
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

      // Use session-based submit — no need to re-send script/files
      const res = await fetchWithPay("/api/proxy/submit/from-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          submitter_address: address,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setJobId(data.job_id);

      // Mark session as complete
      await fetch(`/api/proxy/sessions/${sessionId}/complete`, {
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
      <main className="min-h-screen flex items-center justify-center">
        <div className="card text-center py-16 px-8">
          <div className="w-6 h-6 border-2 border-o-border border-t-o-blueText rounded-full animate-spin mx-auto mb-4" />
          <p className="text-o-textSecondary text-sm">Loading session...</p>
        </div>
      </main>
    );
  }

  if (status === "not_found") {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <div className="card text-center py-16 px-8 max-w-md">
          <div className="w-3 h-3 rounded-full bg-o-red mx-auto mb-4" />
          <h1 className="font-display text-xl font-bold text-o-text mb-2">Session Not Found</h1>
          <p className="text-o-textSecondary text-sm">
            This payment link has expired or is invalid. Request a new one from your AI agent.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Pay for Compute Job
        </h1>
        <p className="font-body text-sm text-o-textSecondary mt-1">
          Review the job details and pay with USDC via x402
        </p>
      </div>

      {session && <JobSummary session={session} />}

      {status === "success" ? (
        <div className="card border-o-green/30">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2.5 h-2.5 rounded-full bg-o-green" />
            <span className="stat-label !text-o-green">Job Submitted</span>
          </div>
          <p className="font-mono text-xs text-o-textSecondary mb-2">
            Job ID: {jobId}
          </p>
          <p className="text-sm text-o-textSecondary">
            Your AI agent will automatically pick up the result. You can close this tab.
          </p>
        </div>
      ) : !isConnected ? (
        <div className="card flex flex-col items-center justify-center py-10 gap-4">
          <p className="text-o-textSecondary text-sm">Connect your wallet to pay for this compute job</p>
          <ConnectButton />
        </div>
      ) : (
        <>
          <div className="card">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div>
                <p className="text-sm text-o-textSecondary">
                  Payment via <span className="text-o-blueText">x402</span> protocol
                  &mdash; sign a USDC authorization to pay
                </p>
                <p className="text-xs text-o-muted mt-1">
                  Connected: {address?.slice(0, 6)}...{address?.slice(-4)}
                </p>
              </div>
              <button
                onClick={handlePay}
                disabled={status === "submitting" || status === "paying"}
                className="w-full sm:w-auto px-6 py-3 bg-o-blue text-white font-display font-semibold text-sm rounded-lg hover:bg-o-blueHover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
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
            <div className="card border-o-red/30 mt-6">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2.5 h-2.5 rounded-full bg-o-red" />
                <span className="stat-label !text-o-red">Payment Failed</span>
              </div>
              <p className="text-xs text-o-red/80">{error}</p>
            </div>
          )}
        </>
      )}
    </main>
  );
}
