"use client";

import { useMemo, useState } from "react";
import type { WorkspaceFile } from "@/lib/types";
import CodeEditor, { getLanguageForFile } from "@/components/submit/CodeEditor";
import {
  type TreeNode,
  buildTree,
  collectFolderPaths,
  FileIcon,
  FolderIcon,
  ChevronIcon,
} from "@/components/FileTreeIcons";

interface FileBrowserProps {
  files: WorkspaceFile[];
  hideLabel?: boolean;
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
