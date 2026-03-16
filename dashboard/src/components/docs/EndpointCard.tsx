"use client";

import { useState } from "react";

interface EndpointCardProps {
  method: "GET" | "POST" | "DELETE";
  path: string;
  auth?: string;
  description: string;
  children?: React.ReactNode;
}

const METHOD_STYLES = {
  GET: "bg-o-green/10 text-o-green",
  POST: "bg-o-blue/10 text-o-blueText",
  DELETE: "bg-o-red/10 text-o-red",
};

export default function EndpointCard({
  method,
  path,
  auth,
  description,
  children,
}: EndpointCardProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="bg-o-surface border border-o-border rounded-xl overflow-hidden">
      <button
        onClick={() => children && setOpen((o) => !o)}
        className={`w-full flex items-center gap-3 px-4 py-3.5 text-left ${children ? "cursor-pointer hover:bg-o-surfaceHover" : "cursor-default"} transition-colors`}
      >
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold uppercase ${METHOD_STYLES[method]}`}
        >
          {method}
        </span>
        <span className="font-mono text-xs text-o-text">{path}</span>
        {auth && (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono bg-o-amber/10 text-o-amber">
            {auth}
          </span>
        )}
        <span className="ml-auto text-xs text-o-textSecondary hidden sm:inline">
          {description}
        </span>
        {children && (
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`text-o-muted transition-transform shrink-0 ${open ? "rotate-180" : ""}`}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        )}
      </button>
      <p className="px-4 pb-3 text-xs text-o-textSecondary sm:hidden">{description}</p>
      {open && children && (
        <div className="border-t border-o-border px-4 py-4">{children}</div>
      )}
    </div>
  );
}
