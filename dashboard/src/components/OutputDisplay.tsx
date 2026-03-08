"use client";

import { useState, useMemo } from "react";

interface OutputDisplayProps {
  raw: string;
}

function parseOutput(raw: string): {
  stdout: string;
  stderr: string;
  hash: string | null;
} {
  try {
    const obj = JSON.parse(raw);
    if (typeof obj === "object" && obj !== null && "output" in obj) {
      return {
        stdout: obj.output || "",
        stderr: obj.error_output || "",
        hash: obj.output_hash || null,
      };
    }
  } catch {
    /* not JSON, fall through to legacy parsing */
  }

  const lines = raw.split("\n");
  const stderrStart = lines.findIndex(
    (l) => l.includes("--- stderr ---") || l.includes("STDERR:")
  );
  const stdout =
    stderrStart >= 0 ? lines.slice(0, stderrStart).join("\n") : raw;
  const stderr =
    stderrStart >= 0 ? lines.slice(stderrStart + 1).join("\n") : "";
  const hashMatch = raw.match(/sha256[:\s]+([a-f0-9]{64})/i);
  return { stdout, stderr, hash: hashMatch?.[1] ?? null };
}

export default function OutputDisplay({ raw }: OutputDisplayProps) {
  const [copied, setCopied] = useState(false);
  const [copiedErr, setCopiedErr] = useState(false);
  const { stdout, stderr, hash } = useMemo(() => parseOutput(raw), [raw]);

  const handleCopy = () => {
    navigator.clipboard.writeText(stdout);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopyErr = () => {
    navigator.clipboard.writeText(stderr);
    setCopiedErr(true);
    setTimeout(() => setCopiedErr(false), 2000);
  };

  return (
    <div className="space-y-3">
      {stdout && (
        <div>
          <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-2">STDOUT</div>
          <div className="relative">
            <pre className="bg-o-green/5 border border-o-green/20 rounded-lg p-3 pr-16 font-mono text-xs text-o-green overflow-x-auto max-h-48 whitespace-pre-wrap break-words leading-relaxed">
              {stdout}
            </pre>
            <button
              onClick={handleCopy}
              className="absolute top-2 right-2 px-2 py-1 text-xs border border-o-border rounded bg-o-surface/90 backdrop-blur-sm text-o-muted hover:text-o-text hover:border-o-borderHover transition-colors"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      )}

      {stderr && (
        <div>
          <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-2">STDERR</div>
          <div className="relative">
            <pre className="bg-o-red/5 border border-o-red/20 rounded-lg p-3 pr-16 font-mono text-xs text-o-red overflow-x-auto max-h-32 whitespace-pre-wrap break-words leading-relaxed">
              {stderr}
            </pre>
            <button
              onClick={handleCopyErr}
              className="absolute top-2 right-2 px-2 py-1 text-xs border border-o-border rounded bg-o-surface/90 backdrop-blur-sm text-o-muted hover:text-o-text hover:border-o-borderHover transition-colors"
            >
              {copiedErr ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      )}

      {hash && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-o-textSecondary">SHA-256:</span>
          <span className="font-mono text-o-blueText break-all">{hash}</span>
        </div>
      )}
    </div>
  );
}
