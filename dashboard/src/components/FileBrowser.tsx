"use client";

import { useMemo, useState } from "react";
import type { WorkspaceFile } from "@/lib/types";
import CodeEditor, { getLanguageForFile } from "@/components/submit/CodeEditor";

interface FileBrowserProps {
  files: WorkspaceFile[];
  hideLabel?: boolean;
}

interface TreeNode {
  name: string;
  path: string;
  isFolder: boolean;
  children: TreeNode[];
  fileIndex?: number;
}

/* ─────────────────────── tree builder ────────────────────── */

function buildTree(files: WorkspaceFile[]): TreeNode[] {
  const root: TreeNode[] = [];

  for (let i = 0; i < files.length; i++) {
    const parts = files[i].path.split("/").filter(Boolean);
    let current = root;
    let pathSoFar = "";

    for (let j = 0; j < parts.length; j++) {
      pathSoFar = pathSoFar ? `${pathSoFar}/${parts[j]}` : parts[j];
      const isLast = j === parts.length - 1;
      let existing = current.find(
        (n) => n.name === parts[j] && n.isFolder === !isLast,
      );

      if (!existing) {
        existing = {
          name: parts[j],
          path: pathSoFar,
          isFolder: !isLast,
          children: [],
          fileIndex: isLast ? i : undefined,
        };
        current.push(existing);
      }
      current = existing.children;
    }
  }

  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.isFolder !== b.isFolder) return a.isFolder ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    for (const n of nodes) {
      if (n.children.length) sortNodes(n.children);
    }
  };
  sortNodes(root);
  return root;
}

function collectFolderPaths(nodes: TreeNode[]): Set<string> {
  const paths = new Set<string>();
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      if (n.isFolder) {
        paths.add(n.path);
        walk(n.children);
      }
    }
  };
  walk(nodes);
  return paths;
}

/* ──────────────────────── file icons ─────────────────────── */

const EXT_COLORS: Record<string, string> = {
  ".py": "#3572A5",
  ".js": "#f1e05a",
  ".mjs": "#f1e05a",
  ".ts": "#3178c6",
  ".tsx": "#3178c6",
  ".jsx": "#f1e05a",
  ".sh": "#89e051",
  ".bash": "#89e051",
  ".json": "#f59e0b",
  ".yaml": "#cb171e",
  ".yml": "#cb171e",
  ".toml": "#9c4221",
  ".md": "#083fa1",
  ".r": "#198CE7",
  ".R": "#198CE7",
};

function getExtColor(name: string): string {
  const dot = name.lastIndexOf(".");
  if (dot >= 0) {
    const ext = name.slice(dot);
    if (EXT_COLORS[ext]) return EXT_COLORS[ext];
  }
  return "#64748b";
}

function FileIcon({ name }: { name: string }) {
  if (name.toLowerCase() === "dockerfile") {
    return (
      <svg width="14" height="14" viewBox="0 0 16 16" className="flex-shrink-0">
        <rect x="2" y="6" width="12" height="8" rx="1" fill="none" stroke="#0db7ed" strokeWidth="1.2" />
        <rect x="4" y="3" width="2" height="3" rx="0.3" fill="#0db7ed" opacity="0.6" />
        <rect x="7" y="3" width="2" height="3" rx="0.3" fill="#0db7ed" opacity="0.6" />
        <rect x="10" y="3" width="2" height="3" rx="0.3" fill="#0db7ed" opacity="0.6" />
      </svg>
    );
  }

  const color = getExtColor(name);
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" className="flex-shrink-0">
      <path
        d="M3 1h7l4 4v10H3V1z"
        fill="none"
        stroke={color}
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path d="M10 1v4h4" fill="none" stroke={color} strokeWidth="1.2" />
    </svg>
  );
}

function FolderIcon({ open }: { open: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" className="flex-shrink-0 text-o-muted">
      {open ? (
        <path
          d="M1.5 3h5l1.5 2H14.5v9h-13V3z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
      ) : (
        <path
          d="M1.5 3h5l1.5 2H14.5v9h-13V3z"
          fill="currentColor"
          opacity="0.3"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
      )}
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 10 10"
      className={`flex-shrink-0 text-o-muted transition-transform ${open ? "rotate-90" : ""}`}
    >
      <path
        d="M3 1.5L7 5L3 8.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* ──────────────────── tree item component ────────────────── */

function TreeItem({
  node,
  depth,
  activeIndex,
  expandedFolders,
  onToggleFolder,
  onSelectFile,
}: {
  node: TreeNode;
  depth: number;
  activeIndex: number;
  expandedFolders: Set<string>;
  onToggleFolder: (path: string) => void;
  onSelectFile: (index: number) => void;
}) {
  const isOpen = expandedFolders.has(node.path);
  const isActive = !node.isFolder && node.fileIndex === activeIndex;

  if (node.isFolder) {
    return (
      <>
        <button
          onClick={() => onToggleFolder(node.path)}
          className="w-full flex items-center gap-1 py-1 px-1 text-xs font-mono text-o-textSecondary hover:bg-o-surface/50 rounded"
          style={{ paddingLeft: depth * 16 + 4 }}
        >
          <ChevronIcon open={isOpen} />
          <FolderIcon open={isOpen} />
          <span className="truncate">{node.name}</span>
        </button>
        {isOpen &&
          node.children.map((child) => (
            <TreeItem
              key={child.path}
              node={child}
              depth={depth + 1}
              activeIndex={activeIndex}
              expandedFolders={expandedFolders}
              onToggleFolder={onToggleFolder}
              onSelectFile={onSelectFile}
            />
          ))}
      </>
    );
  }

  return (
    <button
      onClick={() => node.fileIndex != null && onSelectFile(node.fileIndex)}
      className={`w-full flex items-center gap-1.5 py-1 px-1 text-xs font-mono rounded ${
        isActive
          ? "bg-o-surface text-o-text"
          : "text-o-textSecondary hover:bg-o-surface/50"
      }`}
      style={{ paddingLeft: depth * 16 + 4 }}
    >
      <FileIcon name={node.name} />
      <span className="truncate">{node.name}</span>
    </button>
  );
}

/* ──────────────────── main component ─────────────────────── */

export default function FileBrowser({ files, hideLabel }: FileBrowserProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [mobileTreeOpen, setMobileTreeOpen] = useState(true);
  const tree = useMemo(() => buildTree(files), [files]);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
    () => collectFolderPaths(tree),
  );

  if (files.length === 0) return null;

  const activeFile = files[activeIndex];

  const toggleFolder = (path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const isSingleFile = files.length === 1;

  return (
    <div>
      {!hideLabel && <div className="text-xs text-o-textSecondary uppercase tracking-wider mb-1">Files</div>}
      <div className="bg-o-bg border border-o-border rounded-lg overflow-hidden">
        {isSingleFile ? (
          /* Single file — no tree sidebar */
          <>
            <div className="text-xs font-mono text-o-textSecondary px-3 py-2 border-b border-o-border">
              {activeFile.path}
            </div>
            <CodeEditor
              value={activeFile.content}
              onChange={() => {}}
              language={getLanguageForFile(activeFile.path, "ouro-ubuntu")}
              height="256px"
              readOnly
            />
          </>
        ) : (
          <>
            {/* Mobile: collapsible tree + editor */}
            <div className="md:hidden">
              {/* Collapse toggle */}
              <div className="flex items-center justify-end px-3 py-1 border-b border-o-border">
                <button
                  onClick={() => setMobileTreeOpen((v) => !v)}
                  className="text-o-muted hover:text-o-text transition-colors p-1"
                  title={mobileTreeOpen ? "Collapse" : "Expand"}
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 16 16"
                    className={`transition-transform ${mobileTreeOpen ? "" : "-rotate-90"}`}
                  >
                    <path
                      d="M4 6l4 4 4-4"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              </div>
              {/* Collapsible tree */}
              {mobileTreeOpen && (
                <div className="max-h-52 overflow-y-auto select-none border-b border-o-border/50">
                  {tree.map((node) => (
                    <TreeItem
                      key={node.path}
                      node={node}
                      depth={0}
                      activeIndex={activeIndex}
                      expandedFolders={expandedFolders}
                      onToggleFolder={toggleFolder}
                      onSelectFile={setActiveIndex}
                    />
                  ))}
                </div>
              )}
              {/* File path + language bar */}
              <div className="flex items-center justify-between px-3 py-2 border-b border-o-border">
                <span className="text-xs font-mono text-o-textSecondary truncate">
                  {activeFile.path}
                </span>
                <span className="text-xs text-o-muted font-mono flex-shrink-0 ml-2">
                  {getLanguageForFile(activeFile.path, "ouro-ubuntu")}
                </span>
              </div>
              {/* Editor */}
              <CodeEditor
                value={activeFile.content}
                onChange={() => {}}
                language={getLanguageForFile(activeFile.path, "ouro-ubuntu")}
                height="256px"
                readOnly
              />
            </div>

            {/* Desktop: tree sidebar + content */}
            <div className="hidden md:flex">
              <div className="w-[200px] border-r border-o-border p-2 overflow-y-auto max-h-64">
                {tree.map((node) => (
                  <TreeItem
                    key={node.path}
                    node={node}
                    depth={0}
                    activeIndex={activeIndex}
                    expandedFolders={expandedFolders}
                    onToggleFolder={toggleFolder}
                    onSelectFile={setActiveIndex}
                  />
                ))}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-mono text-o-textSecondary px-3 py-2 border-b border-o-border">
                  {activeFile.path}
                </div>
                <CodeEditor
                  value={activeFile.content}
                  onChange={() => {}}
                  language={getLanguageForFile(activeFile.path, "ouro-ubuntu")}
                  height="256px"
                  readOnly
                />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
