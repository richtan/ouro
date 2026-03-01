"use client";

import { useState } from "react";

interface OutputDisplayProps {
  raw: string;
}

export default function OutputDisplay({ raw }: OutputDisplayProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(raw);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const lines = raw.split("\n");
  const stderrStart = lines.findIndex(
    (l) => l.includes("--- stderr ---") || l.includes("STDERR:")
  );
  const stdout = stderrStart >= 0 ? lines.slice(0, stderrStart).join("\n") : raw;
  const stderr = stderrStart >= 0 ? lines.slice(stderrStart + 1).join("\n") : "";

  const hashMatch = raw.match(/sha256[:\s]+([a-f0-9]{64})/i);

  return (
    <div className="space-y-3">
      <div className="relative">
        <pre className="bg-o-green/5 border border-o-green/20 rounded-lg p-3 font-mono text-xs text-o-green overflow-x-auto max-h-48 whitespace-pre-wrap leading-relaxed">
          {stdout || "(no stdout)"}
        </pre>
        <button
          onClick={handleCopy}
          className="absolute top-2 right-2 px-2 py-1 text-xs font-mono border border-o-border rounded text-o-muted hover:text-o-text hover:border-o-borderHover transition-colors"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      {stderr && (
        <pre className="bg-o-red/5 border border-o-red/20 rounded-lg p-3 font-mono text-xs text-o-red overflow-x-auto max-h-32 whitespace-pre-wrap leading-relaxed">
          {stderr}
        </pre>
      )}

      {hashMatch && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-o-textSecondary">SHA-256:</span>
          <span className="font-mono text-o-blueText break-all">{hashMatch[1]}</span>
        </div>
      )}
    </div>
  );
}
