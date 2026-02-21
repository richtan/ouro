"use client";

import { useMemo, useState } from "react";

interface ParsedOutput {
  output: string;
  error_output: string;
  output_hash: string;
}

function tryParse(raw: string): ParsedOutput | null {
  try {
    const obj = JSON.parse(raw);
    if (typeof obj === "object" && obj !== null && "output" in obj) {
      return {
        output: String(obj.output ?? ""),
        error_output: String(obj.error_output ?? ""),
        output_hash: String(obj.output_hash ?? ""),
      };
    }
  } catch {}
  return null;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-mono border border-ouro-border/40 hover:border-ouro-accent/40 text-ouro-muted hover:text-ouro-accent transition-colors"
      title="Copy to clipboard"
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}

export default function OutputDisplay({ raw }: { raw: string }) {
  const parsed = useMemo(() => tryParse(raw), [raw]);

  if (!parsed) {
    return (
      <pre className="bg-emerald-950/20 border border-emerald-500/20 rounded p-3 font-mono text-xs text-emerald-300/90 overflow-x-auto max-h-48 whitespace-pre-wrap">
        {raw}
      </pre>
    );
  }

  const hasStdout = parsed.output.trim().length > 0;
  const hasStderr = parsed.error_output.trim().length > 0;

  return (
    <div className="space-y-3">
      {hasStdout && (
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-400">
              <polyline points="4 17 10 11 4 5" />
              <line x1="12" y1="19" x2="20" y2="19" />
            </svg>
            <span className="text-[10px] text-emerald-400 uppercase tracking-wider font-mono">stdout</span>
          </div>
          <pre className="bg-emerald-950/20 border border-emerald-500/20 rounded p-3 font-mono text-xs text-emerald-300/90 overflow-x-auto max-h-48 whitespace-pre-wrap">
            {parsed.output.trimEnd()}
          </pre>
        </div>
      )}

      {hasStderr && (
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-red-400">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span className="text-[10px] text-red-400 uppercase tracking-wider font-mono">stderr</span>
          </div>
          <pre className="bg-red-950/20 border border-red-500/20 rounded p-3 font-mono text-xs text-red-300/90 overflow-x-auto max-h-48 whitespace-pre-wrap">
            {parsed.error_output.trimEnd()}
          </pre>
        </div>
      )}

      {!hasStdout && !hasStderr && (
        <div className="text-xs text-ouro-muted font-mono italic">No output produced</div>
      )}

      {parsed.output_hash && (
        <div className="flex items-center gap-2 flex-wrap">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-ouro-muted shrink-0">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0110 0v4" />
          </svg>
          <span className="text-[10px] text-ouro-muted uppercase tracking-wider">SHA-256</span>
          <code className="font-mono text-[11px] text-ouro-accent/80 break-all">
            {parsed.output_hash.slice(0, 16)}...{parsed.output_hash.slice(-16)}
          </code>
          <CopyButton text={parsed.output_hash} />
        </div>
      )}
    </div>
  );
}
