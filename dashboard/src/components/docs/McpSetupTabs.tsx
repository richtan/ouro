"use client";

import { useState } from "react";
import CopyButton from "./CopyButton";

interface ClientConfig {
  name: string;
  file: string;
  language: string;
  code: string;
}

export default function McpSetupTabs({ configs }: { configs: ClientConfig[] }) {
  const [active, setActive] = useState(0);
  const config = configs[active];

  return (
    <div>
      {/* Tabs */}
      <div className="flex flex-wrap gap-1 mb-3">
        {configs.map((c, i) => (
          <button
            key={c.name}
            onClick={() => setActive(i)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              i === active
                ? "bg-o-blue/10 text-o-blueText"
                : "text-o-textSecondary hover:text-o-text hover:bg-o-surfaceHover"
            }`}
          >
            {c.name}
          </button>
        ))}
      </div>

      {/* Code block */}
      <div className="bg-o-surface border border-o-border rounded-xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-o-border">
          <div className="flex gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
            <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
            <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
          </div>
          <span className="text-xs text-o-muted ml-1 select-none">
            {config.file}
          </span>
          <CopyButton text={config.code} />
        </div>
        <pre className="px-5 py-5 font-mono text-xs leading-[1.7] overflow-x-auto text-o-textSecondary">
          {config.code}
        </pre>
      </div>
    </div>
  );
}
