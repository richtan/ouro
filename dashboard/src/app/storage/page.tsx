"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useWalletReady } from "@/hooks/useWalletReady";
import { useAuth } from "@/contexts/AuthContext";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import SignInButton from "@/components/SignInButton";
import {
  type TreeNode,
  buildTree,
  collectFolderPaths,
  FileIcon,
  FolderIcon,
  ChevronIcon,
} from "@/components/FileTreeIcons";


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
  max_files?: number;
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

function StorageTreeItem({
  node,
  depth,
  files,
  expandedFolders,
  onToggleFolder,
  deleting,
  onDelete,
}: {
  node: TreeNode;
  depth: number;
  files: StorageFile[];
  expandedFolders: Set<string>;
  onToggleFolder: (path: string) => void;
  deleting: string | null;
  onDelete: (path: string) => void;
}) {
  const isOpen = expandedFolders.has(node.path);

  if (node.isFolder) {
    return (
      <>
        <button
          onClick={() => onToggleFolder(node.path)}
          className="w-full flex items-center gap-1 py-2.5 sm:py-1.5 px-3 text-xs font-mono text-o-textSecondary hover:bg-o-surfaceHover transition-colors"
          style={{ paddingLeft: depth * 16 + 12 }}
        >
          <ChevronIcon open={isOpen} />
          <FolderIcon open={isOpen} />
          <span className="truncate">{node.name}</span>
        </button>
        {isOpen &&
          node.children.map((child) => (
            <StorageTreeItem
              key={child.path}
              node={child}
              depth={depth + 1}
              files={files}
              expandedFolders={expandedFolders}
              onToggleFolder={onToggleFolder}
              deleting={deleting}
              onDelete={onDelete}
            />
          ))}
      </>
    );
  }

  const file = node.fileIndex != null ? files[node.fileIndex] : null;

  return (
    <div
      className="flex items-center gap-1.5 py-2.5 sm:py-1.5 px-3 text-xs font-mono hover:bg-o-surfaceHover transition-colors group"
      style={{ paddingLeft: depth * 16 + 12 }}
    >
      <FileIcon name={node.name} />
      <span className="truncate text-o-text flex-1 min-w-0">{node.name}</span>
      {file && (
        <>
          <span className="text-o-muted flex-shrink-0 hidden sm:inline">
            {formatBytes(file.size)}
          </span>
          <span className="text-o-muted flex-shrink-0 hidden md:inline ml-3">
            {formatDate(file.modified)}
          </span>
        </>
      )}
      <button
        onClick={() => onDelete(node.path)}
        disabled={deleting === node.path}
        className="text-o-red/70 sm:text-o-red/0 sm:group-hover:text-o-red/70 hover:!text-o-red transition-colors disabled:opacity-40 flex-shrink-0 ml-2"
        title="Delete"
      >
        {deleting === node.path ? (
          <span className="text-o-muted">...</span>
        ) : (
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 4h12M5.5 4V2.5h5V4M6 7v5M10 7v5M3.5 4l.5 10h8l.5-10" />
          </svg>
        )}
      </button>
    </div>
  );
}

export default function StoragePage() {
  const { address, isConnected, isReady } = useWalletReady();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [info, setInfo] = useState<StorageInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const initializedRef = useRef(false);

  const fetchStorage = async () => {
    if (!address) return;
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ wallet: address });
      const res = await fetch(`/api/storage?${params}`);
      if (res.status === 401) return;
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      }
      setInfo(await res.json());
    } catch (err) {
      if (err instanceof Error && err.message.includes("429")) {
        setError("Too many requests — please wait a minute and try again");
      } else {
        setError(err instanceof Error ? err.message : "Failed to load");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isConnected && address && isAuthenticated) fetchStorage();
  }, [isConnected, address, isAuthenticated]);

  const handleDelete = async (path: string) => {
    if (!address || !confirm(`Delete ${path}?`)) return;
    setDeleting(path);
    try {
      const params = new URLSearchParams({ wallet: address, path });
      const res = await fetch(`/api/storage/files?${params}`, { method: "DELETE" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      }
      await fetchStorage();
    } catch (err) {
      if (err instanceof Error && err.message.includes("429")) {
        setError("Too many requests — please wait a minute and try again");
      } else {
        setError(err instanceof Error ? err.message : "Delete failed");
      }
    } finally {
      setDeleting(null);
    }
  };

  const tree = useMemo(() => {
    if (!info) return [];
    return buildTree(info.files);
  }, [info]);

  useEffect(() => {
    if (tree.length > 0 && !initializedRef.current) {
      initializedRef.current = true;
      setExpandedFolders(collectFolderPaths(tree));
    }
  }, [tree]);

  const toggleFolder = (path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const usedPct = info ? Math.min(100, (info.used_bytes / info.quota_bytes) * 100) : 0;

  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          My Files
        </h1>
        <p className="font-body text-sm text-o-textSecondary mt-1">
          Persistent volume mounted at /scratch in your containers
        </p>
      </div>

      {!isReady ? (
        <div className="card animate-pulse"><div className="h-32 bg-o-border/30 rounded" /></div>
      ) : !isConnected ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-o-textSecondary text-sm">Connect your wallet to manage storage</p>
          <ConnectButton />
        </div>
      ) : authLoading ? (
        <div className="card animate-pulse"><div className="h-32 bg-o-border/30 rounded" /></div>
      ) : !isAuthenticated ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-o-textSecondary text-sm">Sign in to verify wallet ownership</p>
          <SignInButton />
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
              <span className={`text-xs ${info.max_files && info.file_count / info.max_files > 0.9 ? "text-o-amber" : "text-o-muted"}`}>
                {info.file_count.toLocaleString()} / {(info.max_files ?? 10000).toLocaleString()} files
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
                className="text-o-muted hover:text-o-text transition-colors p-1"
                title="Refresh"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className={loading ? "animate-spin" : ""}
                >
                  <path d="M1.5 8a6.5 6.5 0 0 1 11.25-4.5M14.5 8a6.5 6.5 0 0 1-11.25 4.5" />
                  <path d="M13.5 2v3.5H10M2.5 14v-3.5H6" />
                </svg>
              </button>
            </div>
            {info.files.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <p className="text-sm text-o-muted">
                  No files yet. Run a job with storage enabled to get started.
                </p>
                <p className="text-xs text-o-muted mt-1">
                  Write files to /scratch/ inside your container to persist them.
                </p>
              </div>
            ) : (
              <div className="py-1">
                {tree.map((node) => (
                  <StorageTreeItem
                    key={node.path}
                    node={node}
                    depth={0}
                    files={info.files}
                    expandedFolders={expandedFolders}
                    onToggleFolder={toggleFolder}
                    deleting={deleting}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </main>
  );
}
