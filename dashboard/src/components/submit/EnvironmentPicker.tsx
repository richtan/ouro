"use client";

import { useState, useMemo, useRef, useEffect, useCallback } from "react";
import type { WorkspaceFile } from "@/lib/types";

/* ────────────────────────── data ────────────────────────── */

interface PrebuiltEnv {
  id: string;
  label: string;
  description: string;
  starterFile: string;
  starterContent: string;
  entrypoint: string;
}

const PREBUILT_ENVS: PrebuiltEnv[] = [
  {
    id: "python312",
    label: "Python 3.12",
    description: "General purpose scripting",
    starterFile: "main.py",
    starterContent: '#!/usr/bin/env python3\n# Your Python code here\nprint("Hello from Ouro!")\n',
    entrypoint: '["python", "main.py"]',
  },
  {
    id: "node20",
    label: "Node.js 20",
    description: "JavaScript runtime",
    starterFile: "index.js",
    starterContent: '// Your Node.js code here\nconsole.log("Hello from Ouro!");\n',
    entrypoint: '["node", "index.js"]',
  },
  {
    id: "pytorch",
    label: "PyTorch",
    description: "ML & deep learning",
    starterFile: "train.py",
    starterContent: '#!/usr/bin/env python3\nimport torch\nprint(f"PyTorch {torch.__version__}")\nprint(f"CUDA available: {torch.cuda.is_available()}")\n',
    entrypoint: '["python", "train.py"]',
  },
  {
    id: "r-base",
    label: "R",
    description: "Statistical computing",
    starterFile: "main.R",
    starterContent: '# Your R code here\ncat("Hello from Ouro!\\n")\nprint(sessionInfo())\n',
    entrypoint: '["Rscript", "main.R"]',
  },
  {
    id: "base",
    label: "Base",
    description: "Ubuntu shell environment",
    starterFile: "job.sh",
    starterContent: '#!/bin/bash\necho "Hello from Ouro HPC cluster!"\nhostname && uptime\n',
    entrypoint: '["bash", "job.sh"]',
  },
];


/* ───────────────────── helpers ──────────────────────────── */

function filesForEnv(env: PrebuiltEnv): WorkspaceFile[] {
  return [
    {
      path: "Dockerfile",
      content: `FROM ${env.id}\nENTRYPOINT ${env.entrypoint}`,
    },
    { path: env.starterFile, content: env.starterContent },
  ];
}

function inferStarterFromImage(image: string): { file: string; entrypoint: string } {
  const lower = image.toLowerCase();
  if (lower.includes("python") || lower.includes("pytorch") || lower.includes("tensorflow") || lower.includes("jupyter")) {
    return { file: "main.py", entrypoint: '["python", "main.py"]' };
  }
  if (lower.includes("node")) {
    return { file: "index.js", entrypoint: '["node", "index.js"]' };
  }
  if (lower.includes("golang") || lower.includes("go")) {
    return { file: "main.go", entrypoint: '["go", "run", "main.go"]' };
  }
  if (lower.includes("rust")) {
    return { file: "main.rs", entrypoint: '["rustc", "main.rs", "-o", "main"]' };
  }
  if (lower.includes("ruby")) {
    return { file: "main.rb", entrypoint: '["ruby", "main.rb"]' };
  }
  if (lower.includes("openjdk") || lower.includes("java")) {
    return { file: "Main.java", entrypoint: '["java", "Main.java"]' };
  }
  if (lower.includes("r-base") || lower === "r") {
    return { file: "main.R", entrypoint: '["Rscript", "main.R"]' };
  }
  return { file: "job.sh", entrypoint: '["bash", "job.sh"]' };
}

function filesForCustomImage(image: string): WorkspaceFile[] {
  const { file, entrypoint } = inferStarterFromImage(image);
  return [
    { path: "Dockerfile", content: `FROM ${image}\nENTRYPOINT ${entrypoint}` },
    { path: file, content: `# Your code here\n` },
  ];
}

function dockerHubUrl(image: string): string {
  const [base, tag] = image.split(":");
  const root = base.includes("/")
    ? `https://hub.docker.com/r/${base}`
    : `https://hub.docker.com/_/${base}`;
  return tag ? `${root}/tags?name=${tag}` : root;
}

/** Default files used on initial page load */
export const DEFAULT_FILES: WorkspaceFile[] = filesForEnv(PREBUILT_ENVS[0]);

/* ──────────────────── component ─────────────────────────── */

type DropdownItem =
  | { kind: "prebuilt"; env: PrebuiltEnv }
| { kind: "tag"; image: string }
  | { kind: "custom"; text: string };

interface EnvironmentPickerProps {
  onSelect: (files: WorkspaceFile[]) => void;
  currentFromImage: string | null;
}

export default function EnvironmentPicker({ onSelect, currentFromImage }: EnvironmentPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const [tagResults, setTagResults] = useState<string[]>([]);
  const [tagsLoading, setTagsLoading] = useState(false);
  const [tagsFetchedFor, setTagsFetchedFor] = useState<string | null>(null);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Current display label
  const activeLabel = useMemo(() => {
    if (!currentFromImage) return { label: "Python 3.12", desc: "General purpose scripting" };
    const env = PREBUILT_ENVS.find((e) => e.id === currentFromImage);
    if (env) return { label: env.label, desc: env.description };
    return { label: currentFromImage, desc: "Docker Hub" };
  }, [currentFromImage]);

  // Filtered items
  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    const prebuilt = q
      ? PREBUILT_ENVS.filter((e) => e.label.toLowerCase().includes(q) || e.id.includes(q))
      : PREBUILT_ENVS;
    return { prebuilt };
  }, [search]);

  // Parse search into base image and partial tag
  const { base, partialTag } = useMemo(() => {
    const colon = search.indexOf(":");
    if (colon === -1) return { base: search.trim(), partialTag: "" };
    return { base: search.slice(0, colon).trim(), partialTag: search.slice(colon + 1) };
  }, [search]);

  // Debounced fetch of Docker Hub tags
  useEffect(() => {
    if (!isOpen) return;
    if (base.length < 2) return;
    if (tagsFetchedFor === base) return;

    setTagsLoading(true);
    const timer = setTimeout(() => {
      fetch(`/api/docker-hub/tags?image=${encodeURIComponent(base)}`)
        .then((r) => r.json())
        .then((data: { tags: string[] }) => {
          setTagResults(data.tags ?? []);
          setTagsFetchedFor(base);
        })
        .catch(() => setTagResults([]))
        .finally(() => setTagsLoading(false));
    }, 300);

    return () => {
      clearTimeout(timer);
      setTagsLoading(false);
    };
  }, [isOpen, base, tagsFetchedFor]);

  // Reset fetched cache when dropdown closes
  useEffect(() => {
    if (!isOpen) {
      setTagsFetchedFor(null);
      setTagResults([]);
    }
  }, [isOpen]);

  // Computed tag items: show only when API results are available, pin "latest"
  const tagItems = useMemo(() => {
    if (base.length < 2) return [];
    if (tagsFetchedFor !== base) return [];

    // Ensure "latest" is always present
    const sourceTags = tagResults.includes("latest") ? tagResults : ["latest", ...tagResults];

    const filtered = partialTag
      ? sourceTags.filter((t) => t.includes(partialTag))
      : sourceTags;

    return filtered.slice(0, 10).map((tag) => `${base}:${tag}`);
  }, [base, partialTag, tagResults, tagsFetchedFor]);

  // Always include the selected prebuilt env, even when search doesn't match it
  const selectedPrebuilt = currentFromImage
    ? PREBUILT_ENVS.find((e) => e.id === currentFromImage) ?? null
    : null;

  const displayPrebuilt = useMemo(() => {
    if (!selectedPrebuilt) return filtered.prebuilt;
    if (filtered.prebuilt.some((e) => e.id === selectedPrebuilt.id)) return filtered.prebuilt;
    return [selectedPrebuilt, ...filtered.prebuilt];
  }, [filtered.prebuilt, selectedPrebuilt]);

  // Always include the selected Docker Hub image, even when search doesn't match it
  const selectedIsDockerHub = currentFromImage && !PREBUILT_ENVS.some((e) => e.id === currentFromImage);

  const displayTagItems = useMemo(() => {
    if (!selectedIsDockerHub || !currentFromImage) return tagItems;
    if (tagItems.includes(currentFromImage)) return tagItems;
    return [currentFromImage, ...tagItems];
  }, [tagItems, currentFromImage, selectedIsDockerHub]);

  // Flat list for keyboard navigation
  const flatItems = useMemo(() => {
    const items: DropdownItem[] = [];
    for (const env of displayPrebuilt) items.push({ kind: "prebuilt", env });
    for (const img of displayTagItems) items.push({ kind: "tag", image: img });
    // Custom fallback: show if search text doesn't exactly match any option
    const q = search.trim();
    if (q) {
      const matchesPrebuilt = PREBUILT_ENVS.some((e) => e.label.toLowerCase() === q.toLowerCase() || e.id === q.toLowerCase());
      const matchesTag = tagItems.some((t) => t === q);
      if (!matchesPrebuilt && !matchesTag) {
        items.push({ kind: "custom", text: q });
      }
    }
    return items;
  }, [displayPrebuilt, displayTagItems, search, tagItems]);

  // Derived: custom fallback presence and index
  const hasCustomFallback = flatItems.length > 0 && flatItems[flatItems.length - 1].kind === "custom";
  const customIdx = displayPrebuilt.length + displayTagItems.length;

  // Select handler
  const selectItem = useCallback(
    (item: DropdownItem) => {
      switch (item.kind) {
        case "prebuilt":
          onSelect(filesForEnv(item.env));
          break;
        case "tag":
          onSelect(filesForCustomImage(item.image));
          break;
        case "custom":
          onSelect(filesForCustomImage(item.text));
          break;
      }
      setIsOpen(false);
      setSearch("");
      setHighlightIndex(-1);
    },
    [onSelect],
  );

  // Click outside to close
  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setSearch("");
        setHighlightIndex(-1);
      }
    }
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, []);

  // Auto-focus input when opening
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightIndex < 0 || !listRef.current) return;
    const items = listRef.current.querySelectorAll("[data-item-index]");
    const el = items[highlightIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [highlightIndex]);

  // Reset highlight when search changes
  useEffect(() => {
    setHighlightIndex(-1);
  }, [search]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === "Enter" || e.key === "ArrowDown" || e.key === " ") {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightIndex((prev) => (prev < flatItems.length - 1 ? prev + 1 : prev));
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightIndex((prev) => (prev > 0 ? prev - 1 : prev));
        break;
      case "Enter":
        e.preventDefault();
        if (highlightIndex >= 0 && highlightIndex < flatItems.length) {
          selectItem(flatItems[highlightIndex]);
        } else if (search.trim()) {
          // No highlight + typed text → use as custom image
          selectItem({ kind: "custom", text: search.trim() });
        }
        break;
      case "Escape":
        e.preventDefault();
        setIsOpen(false);
        setSearch("");
        setHighlightIndex(-1);
        break;
    }
  };

  return (
    <div ref={wrapperRef}>
      {/* Section label */}
      <div className="text-xs text-o-textSecondary uppercase tracking-wider font-semibold mb-2">Environment</div>

      {/* Single card container */}
      <div className="w-full border border-o-border rounded-xl bg-o-bg overflow-hidden">
        {/* Trigger row */}
        <button
          onClick={() => setIsOpen((o) => !o)}
          onKeyDown={handleKeyDown}
          className="w-full px-4 py-3 flex items-center gap-1.5 text-left"
        >
          {isOpen ? (
            <>
              <svg className="w-4 h-4 text-o-muted shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
              </svg>
              <input
                ref={inputRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Search or enter a Docker Hub image..."
                className="flex-1 bg-transparent text-sm text-o-text placeholder-o-muted focus:outline-none"
                onClick={(e) => e.stopPropagation()}
              />
              <svg className="w-4 h-4 text-o-muted ml-auto shrink-0 rotate-180" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
              </svg>
            </>
          ) : (
            <>
              <span className="text-sm text-o-text">{activeLabel.label}</span>
              <span className="text-sm text-o-textSecondary hidden sm:inline">&mdash; {activeLabel.desc}</span>
              <svg className="w-4 h-4 text-o-muted ml-auto shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
              </svg>
            </>
          )}
        </button>

        {/* Expanding content */}
        <div
          className={`overflow-hidden transition-[max-height,opacity] duration-300 ease-in-out ${
            isOpen ? "max-h-[28rem] opacity-100" : "max-h-0 opacity-0"
          }`}
        >
          <div className="border-t border-o-border" />
          <div ref={listRef} className={isOpen ? "overflow-y-auto max-h-72 bg-o-surface" : "bg-o-surface"}>
        {/* Prebuilt section */}
        {displayPrebuilt.length > 0 && (
          <>
            <div className="text-xs text-o-muted uppercase tracking-wider px-4 py-2">Prebuilt</div>
            {displayPrebuilt.map((env, i) => {
              const idx = i;
              const isSelected = currentFromImage === env.id;
              return (
                <button
                  key={env.id}
                  data-item-index={idx}
                  onClick={() => selectItem({ kind: "prebuilt", env })}
                  onMouseEnter={() => setHighlightIndex(idx)}
                  className={`w-full px-4 py-2.5 text-sm cursor-pointer transition-colors flex items-center justify-between ${
                    highlightIndex === idx ? "bg-o-bg" : "hover:bg-o-bg"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-o-text">{env.label}</span>
                    <span className="text-o-textSecondary text-xs">{env.description}</span>
                  </div>
                  {isSelected && (
                    <svg className="w-4 h-4 text-o-blueText shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                    </svg>
                  )}
                </button>
              );
            })}
          </>
        )}

        {/* Docker Hub section */}
        {(displayTagItems.length > 0 || tagsLoading) && (
          <>
            {displayPrebuilt.length > 0 && (
              <div className="border-t border-o-border" />
            )}
            <div className="text-xs text-o-muted uppercase tracking-wider px-4 py-2 flex items-center gap-2">
              Docker Hub
              {tagsLoading && (
                <span className="inline-block w-3 h-3 border-2 border-o-muted border-t-transparent rounded-full animate-spin" />
              )}
            </div>
            {displayTagItems.map((img, i) => {
              const idx = displayPrebuilt.length + i;
              const isSelected = currentFromImage === img;
              return (
                <button
                  key={img}
                  data-item-index={idx}
                  onClick={() => selectItem({ kind: "tag", image: img })}
                  onMouseEnter={() => setHighlightIndex(idx)}
                  className={`w-full px-4 py-2.5 text-sm cursor-pointer transition-colors flex items-center gap-2 ${
                    highlightIndex === idx ? "bg-o-bg" : "hover:bg-o-bg"
                  }`}
                >
                  <span className="font-mono text-o-text">{img}</span>
                  <div className="flex items-center gap-2 ml-auto shrink-0">
                    {isSelected && (
                      <svg className="w-4 h-4 text-o-blueText" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                      </svg>
                    )}
                    <a
                      href={dockerHubUrl(img)}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="text-o-muted hover:text-o-textSecondary transition-colors"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                      </svg>
                    </a>
                  </div>
                </button>
              );
            })}
          </>
        )}

        {/* Custom fallback */}
        {hasCustomFallback && (
          <>
            {(displayPrebuilt.length > 0 || displayTagItems.length > 0) && (
              <div className="border-t border-o-border" />
            )}
            <button
              data-item-index={customIdx}
              onClick={() => selectItem(flatItems[flatItems.length - 1])}
              onMouseEnter={() => setHighlightIndex(customIdx)}
              className={`w-full px-4 py-2.5 text-sm cursor-pointer transition-colors flex items-center gap-1 ${
                highlightIndex === customIdx ? "bg-o-bg" : "hover:bg-o-bg"
              }`}
            >
              <span className="text-o-textSecondary">Use</span>
              <span className="font-mono text-o-blueText">{(flatItems[flatItems.length - 1] as Extract<DropdownItem, { kind: "custom" }>).text}</span>
              <span className="text-o-textSecondary">from Docker Hub</span>
              <span className="ml-auto text-o-muted text-xs">&#x23CE;</span>
            </button>
          </>
        )}

        {/* Docker Hub hint when dropdown open with empty search */}
        {!search.trim() && displayTagItems.length === 0 && !tagsLoading && (
          <div className="px-4 py-2.5 text-xs text-o-muted border-t border-o-border">
            Type any Docker Hub image — e.g. <span className="font-mono text-o-textSecondary">python:3.12-slim</span>
          </div>
        )}

        {/* Empty state */}
        {flatItems.length === 0 && (
          <div className="px-4 py-6 text-center text-xs text-o-muted">No matching environments</div>
        )}
        </div>
        </div>
      </div>

    </div>
  );
}
