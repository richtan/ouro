"use client";

import { useEffect, useState } from "react";
import { useWalletReady } from "@/hooks/useWalletReady";
import { useSignMessage } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";

interface StorageFile {
  path: string;
  size: number;
  modified: number;
}

interface StorageInfo {
  wallet: string;
  tier: string;
  quota_bytes: number;
  used_bytes: number;
  file_count: number;
  files: StorageFile[];
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(i > 1 ? 2 : 0)} ${sizes[i]}`;
}

function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function StoragePage() {
  const { address, isConnected, isReady } = useWalletReady();
  const { signMessageAsync } = useSignMessage();
  const [info, setInfo] = useState<StorageInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchStorage = async () => {
    if (!address) return;
    setLoading(true);
    setError("");
    try {
      const timestamp = String(Math.floor(Date.now() / 1000));
      const message = `ouro-storage-list:${address.toLowerCase()}:${timestamp}`;
      const signature = await signMessageAsync({ message });
      const params = new URLSearchParams({
        wallet: address,
        signature,
        timestamp,
      });
      const res = await fetch(`/api/storage?${params}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      }
      setInfo(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isConnected && address) fetchStorage();
  }, [isConnected, address]);

  const handleDelete = async (path: string) => {
    if (!address || !confirm(`Delete ${path}?`)) return;
    setDeleting(path);
    try {
      // Sign EIP-191 message to prove wallet ownership
      const timestamp = String(Math.floor(Date.now() / 1000));
      const message = `ouro-storage-delete:${address.toLowerCase()}:${path}:${timestamp}`;
      const signature = await signMessageAsync({ message });

      const params = new URLSearchParams({
        wallet: address,
        path,
        signature,
        timestamp,
      });
      const res = await fetch(`/api/storage/files?${params}`, { method: "DELETE" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      }
      await fetchStorage();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(null);
    }
  };

  const usedPct = info ? Math.min(100, (info.used_bytes / info.quota_bytes) * 100) : 0;

  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Storage
        </h1>
        <p className="font-body text-sm text-o-textSecondary mt-1">
          Persistent volume mounted at /storage in your containers
        </p>
      </div>

      {!isReady ? (
        <div className="card animate-pulse"><div className="h-32 bg-o-border/30 rounded" /></div>
      ) : !isConnected ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-o-textSecondary text-sm">Connect your wallet to manage storage</p>
          <ConnectButton />
        </div>
      ) : loading && !info ? (
        <div className="card animate-pulse"><div className="h-32 bg-o-border/30 rounded" /></div>
      ) : error && !info ? (
        <div className="card">
          <p className="text-o-red text-sm">{error}</p>
        </div>
      ) : info ? (
        <div className="space-y-6">
          {/* Quota bar */}
          <div className="border border-o-border rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-o-textSecondary">Usage</span>
              <span className="font-mono text-xs text-o-text">
                {formatBytes(info.used_bytes)} / {formatBytes(info.quota_bytes)}
              </span>
            </div>
            <div className="h-2 bg-o-bg rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  usedPct > 90 ? "bg-o-red" : usedPct > 70 ? "bg-o-amber" : "bg-o-blue"
                }`}
                style={{ width: `${usedPct}%` }}
              />
            </div>
            <div className="flex items-center justify-between mt-2">
              <span className="text-xs text-o-muted">
                {info.file_count} file{info.file_count !== 1 ? "s" : ""}
              </span>
              <span className="text-xs text-o-muted uppercase tracking-wider">
                {info.tier} tier
              </span>
            </div>
          </div>

          {/* File list */}
          <div className="border border-o-border rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-o-border flex items-center justify-between">
              <span className="text-sm font-medium text-o-text">Files</span>
              <button
                onClick={fetchStorage}
                className="text-xs text-o-blueText hover:text-o-blue transition-colors"
              >
                Refresh
              </button>
            </div>
            {info.files.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <p className="text-sm text-o-muted">
                  No files yet. Run a job with storage enabled to get started.
                </p>
                <p className="text-xs text-o-muted mt-1">
                  Write files to /storage/ inside your container to persist them.
                </p>
              </div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="text-xs text-o-muted uppercase tracking-wider">
                    <th className="text-left px-4 py-2 font-medium">Name</th>
                    <th className="text-right px-4 py-2 font-medium hidden sm:table-cell">Size</th>
                    <th className="text-right px-4 py-2 font-medium hidden md:table-cell">Modified</th>
                    <th className="text-right px-4 py-2 font-medium w-16" />
                  </tr>
                </thead>
                <tbody>
                  {info.files.map((f) => (
                    <tr key={f.path} className="border-t border-o-border/50 hover:bg-o-surfaceHover transition-colors">
                      <td className="px-4 py-2.5">
                        <span className="font-mono text-xs text-o-text truncate block max-w-[300px]">
                          {f.path}
                        </span>
                      </td>
                      <td className="text-right px-4 py-2.5 hidden sm:table-cell">
                        <span className="font-mono text-xs text-o-muted">{formatBytes(f.size)}</span>
                      </td>
                      <td className="text-right px-4 py-2.5 hidden md:table-cell">
                        <span className="text-xs text-o-muted">{formatDate(f.modified)}</span>
                      </td>
                      <td className="text-right px-4 py-2.5">
                        <button
                          onClick={() => handleDelete(f.path)}
                          disabled={deleting === f.path}
                          className="text-xs text-o-red/70 hover:text-o-red transition-colors disabled:opacity-40"
                        >
                          {deleting === f.path ? "..." : "Delete"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      ) : null}
    </main>
  );
}
