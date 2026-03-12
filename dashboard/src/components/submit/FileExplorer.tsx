"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import CodeEditor, { getLanguageForFile } from "./CodeEditor";
import type { WorkspaceFile } from "@/lib/types";

interface FileExplorerProps {
  files: WorkspaceFile[];
  onFilesChange: (files: WorkspaceFile[]) => void;
  defaultImage: string;
  height?: string;
}

interface TreeNode {
  name: string;
  path: string; // full path like "src/utils/helper.py"
  isFolder: boolean;
  children: TreeNode[];
  fileIndex?: number; // index into files[] (leaf only)
}

/* ─────────────────────── tree builder ────────────────────── */

function buildTree(files: WorkspaceFile[]): TreeNode[] {
  const root: TreeNode[] = [];

  for (let i = 0; i < files.length; i++) {
    const parts = (files[i].path ?? "").split("/").filter(Boolean);
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

  // Sort recursively: folders first, then alphabetical
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
  // Dockerfile gets a distinct container/whale-inspired icon
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
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      className="flex-shrink-0 text-o-muted"
    >
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

interface TreeItemProps {
  node: TreeNode;
  depth: number;
  activeIndex: number;
  expandedFolders: Set<string>;
  onToggleFolder: (path: string) => void;
  onSelectFile: (fileIndex: number) => void;
  onRemoveFile: (fileIndex: number) => void;
  onStartRename: (fileIndex: number) => void;
  onAddFileInFolder: (folderPath: string) => void;
  onRemoveFolder: (folderPath: string) => void;
  renamingIndex: number | null;
  renameValue: string;
  onRenameChange: (val: string) => void;
  onCommitRename: (fileIndex: number) => void;
  onCancelRename: (fileIndex: number) => void;
  duplicateError: boolean;
  fileCount: number;
}

function TreeItem({
  node,
  depth,
  activeIndex,
  expandedFolders,
  onToggleFolder,
  onSelectFile,
  onRemoveFile,
  onStartRename,
  onAddFileInFolder,
  onRemoveFolder,
  renamingIndex,
  renameValue,
  onRenameChange,
  onCommitRename,
  onCancelRename,
  duplicateError,
  fileCount,
}: TreeItemProps) {
  const isOpen = expandedFolders.has(node.path);

  if (node.isFolder) {
    return (
      <>
        <button
          className="group flex items-center gap-1 w-full px-1 py-1 md:py-[3px] text-xs text-o-textSecondary hover:bg-o-bg/50 hover:text-o-text transition-colors"
          style={{ paddingLeft: `${depth * 16 + 4}px`, paddingRight: "4px" }}
          onClick={() => onToggleFolder(node.path)}
        >
          <ChevronIcon open={isOpen} />
          <FolderIcon open={isOpen} />
          <span className="truncate font-mono">{node.name}</span>
          <div className="ml-auto flex items-center gap-0.5 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
            <span
              role="button"
              onClick={(e) => { e.stopPropagation(); onAddFileInFolder(node.path); }}
              className="text-o-muted hover:text-o-blueText p-1.5 md:p-0.5"
              title="New file"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M8 3v10M3 8h10" strokeLinecap="round" />
              </svg>
            </span>
            <span
              role="button"
              onClick={(e) => { e.stopPropagation(); onRemoveFolder(node.path); }}
              className="text-o-muted hover:text-o-red p-1.5 md:p-0.5"
              title="Delete folder"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
              </svg>
            </span>
          </div>
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
              onRemoveFile={onRemoveFile}
              onStartRename={onStartRename}
              onAddFileInFolder={onAddFileInFolder}
              onRemoveFolder={onRemoveFolder}
              renamingIndex={renamingIndex}
              renameValue={renameValue}
              onRenameChange={onRenameChange}
              onCommitRename={onCommitRename}
              onCancelRename={onCancelRename}
              duplicateError={duplicateError}
              fileCount={fileCount}
            />
          ))}
      </>
    );
  }

  // Leaf file node
  const idx = node.fileIndex!;
  const isActive = idx === activeIndex;
  const isRenaming = renamingIndex === idx;
  const isDockerfile = node.name.toLowerCase() === "dockerfile";

  return (
    <div
      className={`group flex items-center gap-1 w-full py-1 md:py-[3px] cursor-pointer transition-colors ${
        isActive
          ? "bg-o-bg text-o-text"
          : "text-o-textSecondary hover:bg-o-bg/50 hover:text-o-text"
      }`}
      style={{ paddingLeft: `${depth * 16 + 4}px`, paddingRight: "4px" }}
      onClick={() => {
        if (!isRenaming) onSelectFile(idx);
      }}
    >
      <FileIcon name={node.name} />

      {isRenaming ? (
        <input
          autoFocus
          value={renameValue}
          onChange={(e) => onRenameChange(e.target.value)}
          onBlur={() => onCommitRename(idx)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onCommitRename(idx);
            if (e.key === "Escape") onCancelRename(idx);
          }}
          className={`flex-1 min-w-0 bg-transparent text-xs font-mono focus:outline-none ${
            duplicateError
              ? "text-o-red border-b border-o-red"
              : "text-o-blueText"
          }`}
          placeholder="filename.py"
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span
          className="flex-1 min-w-0 truncate text-xs font-mono"
          onDoubleClick={(e) => {
            // Prevent renaming the Dockerfile
            if (isDockerfile) return;
            e.stopPropagation();
            onStartRename(idx);
          }}
        >
          {node.name}
        </span>
      )}

      {/* Hover actions */}
      {!isRenaming && !isDockerfile && (
        <div className={`ml-auto flex items-center gap-0.5 ${isActive ? "opacity-100" : "opacity-0"} md:opacity-0 md:group-hover:opacity-100 transition-opacity`}>
          <button
            onClick={(e) => { e.stopPropagation(); onStartRename(idx); }}
            className="text-o-muted hover:text-o-blueText p-1.5 md:p-0.5"
            title="Rename"
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M11.5 1.5l3 3L5 14H2v-3L11.5 1.5z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          {fileCount > 1 && (
            <button
              onClick={(e) => { e.stopPropagation(); onRemoveFile(idx); }}
              className="text-o-muted hover:text-o-red p-1.5 md:p-0.5"
              title="Delete"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
              </svg>
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════ FileExplorer (main) ═════════════════ */

export default function FileExplorer({
  files,
  onFilesChange,
  defaultImage,
  height = "400px",
}: FileExplorerProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [openTabs, setOpenTabs] = useState<number[]>([0]);
  const [renamingIndex, setRenamingIndex] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [duplicateError, setDuplicateError] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
    new Set(),
  );
  const [mobileTreeOpen, setMobileTreeOpen] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const tree = useMemo(() => buildTree(files), [files]);

  const activeFile = files[activeIndex] ?? files[0];
  const language = activeFile
    ? getLanguageForFile(activeFile.path, defaultImage)
    : "plaintext";

  /* ── tab management ── */

  const selectFile = useCallback(
    (index: number) => {
      setActiveIndex(index);
      setOpenTabs((prev) =>
        prev.includes(index) ? prev : [...prev, index],
      );
    },
    [],
  );

  const closeTab = useCallback(
    (index: number) => {
      setOpenTabs((prev) => {
        const next = prev.filter((t) => t !== index);
        if (next.length === 0 && files.length > 0) {
          // Always keep at least one tab open
          const fallback = index === 0 ? (files.length > 1 ? 1 : 0) : 0;
          setActiveIndex(fallback);
          return [fallback];
        }
        if (activeIndex === index) {
          // Switch to nearest tab
          const currentPos = prev.indexOf(index);
          const newActive =
            next[Math.min(currentPos, next.length - 1)] ?? next[0];
          setActiveIndex(newActive);
        }
        return next;
      });
    },
    [activeIndex, files.length],
  );

  /* ── folder expand/collapse ── */

  const toggleFolder = useCallback((path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  // Auto-expand folders when files change (for newly added nested files)
  const autoExpandForFile = useCallback((filePath: string) => {
    const parts = filePath.split("/").filter(Boolean);
    if (parts.length <= 1) return;
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      let pathSoFar = "";
      for (let i = 0; i < parts.length - 1; i++) {
        pathSoFar = pathSoFar ? `${pathSoFar}/${parts[i]}` : parts[i];
        next.add(pathSoFar);
      }
      return next;
    });
  }, []);

  /* ── file content editing ── */

  const updateFileContent = useCallback(
    (value: string) => {
      const updated = [...files];
      if (activeIndex >= 0 && activeIndex < updated.length) {
        updated[activeIndex] = { ...updated[activeIndex], content: value };
        onFilesChange(updated);
      }
    },
    [files, activeIndex, onFilesChange],
  );

  /* ── rename ── */

  const startRename = (index: number) => {
    setRenamingIndex(index);
    setRenameValue(files[index].path);
    setDuplicateError(false);
  };

  const commitRename = (index: number) => {
    const trimmed = renameValue.trim().replace(/^\/+|\/+$/g, ""); // strip leading/trailing slashes
    if (!trimmed) {
      // If the file was never named, remove it (same as cancel)
      if (!files[index].path) {
        removeFile(index);
      }
      setRenamingIndex(null);
      return;
    }
    const hasDuplicate = files.some(
      (f, i) => i !== index && f.path === trimmed,
    );
    if (hasDuplicate) {
      setDuplicateError(true);
      return;
    }
    const updated = [...files];
    updated[index] = { ...updated[index], path: trimmed };
    onFilesChange(updated);
    autoExpandForFile(trimmed);
    setRenamingIndex(null);
    setDuplicateError(false);
  };

  const cancelRename = (index: number) => {
    if (!files[index].path) {
      removeFile(index);
    }
    setRenamingIndex(null);
    setDuplicateError(false);
  };

  /* ── add/remove files ── */

  const addFile = () => {
    const newFiles = [...files, { path: "", content: "" }];
    onFilesChange(newFiles);
    const newIndex = newFiles.length - 1;
    setActiveIndex(newIndex);
    setOpenTabs((prev) => [...prev, newIndex]);
    setRenamingIndex(newIndex);
    setRenameValue("");
    setDuplicateError(false);
  };

  const removeFile = (index: number) => {
    if (files.length <= 1) return;
    const updated = files.filter((_, i) => i !== index);
    onFilesChange(updated);

    // Fix tab indices after removal
    setOpenTabs((prev) => {
      const next = prev
        .filter((t) => t !== index)
        .map((t) => (t > index ? t - 1 : t));
      return next.length > 0 ? next : [0];
    });

    if (activeIndex >= updated.length) {
      setActiveIndex(Math.max(0, updated.length - 1));
    } else if (activeIndex === index) {
      setActiveIndex(0);
    } else if (activeIndex > index) {
      setActiveIndex(activeIndex - 1);
    }
  };

  /* ── folder actions ── */

  const addFileInFolder = (folderPath: string) => {
    const newFiles = [...files, { path: "", content: "" }];
    onFilesChange(newFiles);
    const newIndex = newFiles.length - 1;
    setActiveIndex(newIndex);
    setOpenTabs((prev) => [...prev, newIndex]);
    setRenamingIndex(newIndex);
    setRenameValue(folderPath + "/");
    setDuplicateError(false);
    setExpandedFolders((prev) => new Set([...prev, folderPath]));
  };

  const removeFolder = (folderPath: string) => {
    const prefix = folderPath + "/";
    const updated = files.filter((f) => !(f.path ?? "").startsWith(prefix));
    if (updated.length === files.length) return;
    onFilesChange(updated);
    setActiveIndex(0);
    setOpenTabs([0]);
  };

  /* ── upload ── */

  const handleUpload = useCallback(
    (uploadedFiles: FileList) => {
      const readers: Promise<WorkspaceFile>[] = [];
      for (let i = 0; i < uploadedFiles.length; i++) {
        const file = uploadedFiles[i];
        readers.push(
          new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = (ev) => {
              resolve({
                path: file.name,
                content: (ev.target?.result as string) ?? "",
              });
            };
            reader.readAsText(file);
          }),
        );
      }
      Promise.all(readers).then((newFiles) => {
        const updated = [...files];
        for (const nf of newFiles) {
          const existingIdx = updated.findIndex((f) => f.path === nf.path);
          if (existingIdx >= 0) {
            updated[existingIdx] = nf;
          } else {
            updated.push(nf);
          }
        }
        onFilesChange(updated);
        setMobileTreeOpen(true);
      });
    },
    [files, onFilesChange],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer.files.length > 0) {
        handleUpload(e.dataTransfer.files);
      }
    },
    [handleUpload],
  );

  /* ── get filename from path ── */

  const fileName = (path: string) => {
    const parts = path.split("/");
    return parts[parts.length - 1] || path || "untitled";
  };

  /* ════════════════════════ render ═══════════════════════ */

  return (
    <div
      className="card !p-0 overflow-hidden"
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
    >
      {/* Mobile: collapsible tree panel */}
      <div className="md:hidden border-b border-o-border">
        <div className="px-3 py-2 flex items-center justify-between">
          <span className="text-xs text-o-muted uppercase tracking-widest font-semibold">Explorer</span>
          <div className="flex items-center gap-1">
            <button onClick={() => { addFile(); setMobileTreeOpen(true); }} className="text-o-muted hover:text-o-blueText transition-colors p-1" title="New File">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M8 3v10M3 8h10" strokeLinecap="round" />
              </svg>
            </button>
            <button onClick={() => { fileInputRef.current?.click(); }} className="text-o-muted hover:text-o-blueText transition-colors p-1" title="Upload">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M8 10V3M5 5l3-3 3 3M3 13h10" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <button onClick={() => setMobileTreeOpen((v) => !v)} className="text-o-muted hover:text-o-text transition-colors p-1" title={mobileTreeOpen ? "Collapse" : "Expand"}>
              <svg width="14" height="14" viewBox="0 0 16 16" className={`transition-transform ${mobileTreeOpen ? "" : "-rotate-90"}`}>
                <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
        {mobileTreeOpen && (
          <div className="max-h-52 overflow-y-auto select-none border-t border-o-border/50">
            {tree.map((node) => (
              <TreeItem
                key={node.path}
                node={node}
                depth={0}
                activeIndex={activeIndex}
                expandedFolders={expandedFolders}
                onToggleFolder={toggleFolder}
                onSelectFile={selectFile}
                onRemoveFile={removeFile}
                onStartRename={startRename}
                onAddFileInFolder={(folderPath) => { addFileInFolder(folderPath); setMobileTreeOpen(true); }}
                onRemoveFolder={removeFolder}
                renamingIndex={renamingIndex}
                renameValue={renameValue}
                onRenameChange={(val) => {
                  setRenameValue(val);
                  setDuplicateError(false);
                }}
                onCommitRename={commitRename}
                onCancelRename={cancelRename}
                duplicateError={duplicateError}
                fileCount={files.length}
              />
            ))}
            {/* Unnamed files at root */}
            {files.map(
              (f, i) =>
                !f.path && (
                  <div
                    key={`unnamed-${i}`}
                    className={`group flex items-center gap-1 w-full px-1 py-1 md:py-[3px] cursor-pointer transition-colors ${
                      i === activeIndex
                        ? "bg-o-bg text-o-text"
                        : "text-o-textSecondary hover:bg-o-bg/50 hover:text-o-text"
                    }`}
                    onClick={() => {
                      if (renamingIndex !== i) selectFile(i);
                    }}
                  >
                    <FileIcon name="untitled" />
                    {renamingIndex === i ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => {
                          setRenameValue(e.target.value);
                          setDuplicateError(false);
                        }}
                        onBlur={() => commitRename(i)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") commitRename(i);
                          if (e.key === "Escape") cancelRename(i);
                        }}
                        className={`flex-1 min-w-0 bg-transparent text-xs font-mono focus:outline-none ${
                          duplicateError
                            ? "text-o-red border-b border-o-red"
                            : "text-o-blueText"
                        }`}
                        placeholder="src/filename.py"
                        onClick={(e) => e.stopPropagation()}
                      />
                    ) : (
                      <>
                        <span
                          className="flex-1 min-w-0 text-xs font-mono text-o-muted italic"
                          onDoubleClick={(e) => {
                            e.stopPropagation();
                            startRename(i);
                          }}
                        >
                          untitled
                        </span>
                        <div className={`ml-auto flex items-center gap-0.5 ${i === activeIndex ? "opacity-100" : "opacity-0"} md:opacity-0 md:group-hover:opacity-100 transition-opacity`}>
                          <button
                            onClick={(e) => { e.stopPropagation(); startRename(i); }}
                            className="text-o-muted hover:text-o-blueText p-1.5 md:p-0.5"
                            title="Rename"
                          >
                            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                              <path d="M11.5 1.5l3 3L5 14H2v-3L11.5 1.5z" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </button>
                          {files.length > 1 && (
                            <button
                              onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                              className="text-o-muted hover:text-o-red p-1.5 md:p-0.5"
                              title="Delete"
                            >
                              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                                <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
                              </svg>
                            </button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ),
            )}
            {duplicateError && renamingIndex !== null && (
              <div className="px-3 py-1 text-xs text-o-red">
                Duplicate filename
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex">
        {/* Desktop: tree sidebar */}
        <div className="hidden md:flex flex-col w-[200px] border-r border-o-border flex-shrink-0">
          <div className="px-3 py-2 flex items-center justify-between">
            <span className="text-xs text-o-muted uppercase tracking-widest font-semibold">Explorer</span>
            <div className="flex items-center gap-1">
              <button onClick={addFile} className="text-o-muted hover:text-o-blueText transition-colors p-0.5" title="New File">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M8 3v10M3 8h10" strokeLinecap="round" />
                </svg>
              </button>
              <button onClick={() => fileInputRef.current?.click()} className="text-o-muted hover:text-o-blueText transition-colors p-0.5" title="Upload">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M8 10V3M5 5l3-3 3 3M3 13h10" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto select-none">
            {tree.map((node) => (
              <TreeItem
                key={node.path}
                node={node}
                depth={0}
                activeIndex={activeIndex}
                expandedFolders={expandedFolders}
                onToggleFolder={toggleFolder}
                onSelectFile={selectFile}
                onRemoveFile={removeFile}
                onStartRename={startRename}
                onAddFileInFolder={addFileInFolder}
                onRemoveFolder={removeFolder}
                renamingIndex={renamingIndex}
                renameValue={renameValue}
                onRenameChange={(val) => {
                  setRenameValue(val);
                  setDuplicateError(false);
                }}
                onCommitRename={commitRename}
                onCancelRename={cancelRename}
                duplicateError={duplicateError}
                fileCount={files.length}
              />
            ))}
            {/* Files without path (new unnamed) show at root */}
            {files.map(
              (f, i) =>
                !f.path && (
                  <div
                    key={`unnamed-${i}`}
                    className={`group flex items-center gap-1 w-full px-1 py-[3px] cursor-pointer transition-colors ${
                      i === activeIndex
                        ? "bg-o-bg text-o-text"
                        : "text-o-textSecondary hover:bg-o-bg/50 hover:text-o-text"
                    }`}
                    onClick={() => {
                      if (renamingIndex !== i) selectFile(i);
                    }}
                  >
                    <FileIcon name="untitled" />
                    {renamingIndex === i ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => {
                          setRenameValue(e.target.value);
                          setDuplicateError(false);
                        }}
                        onBlur={() => commitRename(i)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") commitRename(i);
                          if (e.key === "Escape") cancelRename(i);
                        }}
                        className={`flex-1 min-w-0 bg-transparent text-xs font-mono focus:outline-none ${
                          duplicateError
                            ? "text-o-red border-b border-o-red"
                            : "text-o-blueText"
                        }`}
                        placeholder="src/filename.py"
                        onClick={(e) => e.stopPropagation()}
                      />
                    ) : (
                      <>
                        <span
                          className="flex-1 min-w-0 text-xs font-mono text-o-muted italic"
                          onDoubleClick={(e) => {
                            e.stopPropagation();
                            startRename(i);
                          }}
                        >
                          untitled
                        </span>
                        {/* Hover actions */}
                        <div className="ml-auto flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={(e) => { e.stopPropagation(); startRename(i); }}
                            className="text-o-muted hover:text-o-blueText p-0.5"
                            title="Rename"
                          >
                            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                              <path d="M11.5 1.5l3 3L5 14H2v-3L11.5 1.5z" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </button>
                          {files.length > 1 && (
                            <button
                              onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                              className="text-o-muted hover:text-o-red p-0.5"
                              title="Delete"
                            >
                              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                                <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
                              </svg>
                            </button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ),
            )}
          </div>
          {duplicateError && renamingIndex !== null && (
            <div className="px-3 py-1 text-xs text-o-red">
              Duplicate filename
            </div>
          )}
        </div>

        {/* Editor area */}
        <div className="flex-1 min-w-0 flex flex-col">
          {/* Tab bar (desktop) */}
          <div className="hidden md:flex items-center border-b border-o-border">
            {/* Scrollable tabs */}
            <div className="flex-1 min-w-0 flex items-center overflow-x-auto">
              {openTabs.map((tabIdx) => {
                const file = files[tabIdx];
                if (!file) return null;
                const isActive = tabIdx === activeIndex;
                return (
                  <div
                    key={tabIdx}
                    className={`group flex items-center gap-1.5 px-3 py-2 text-xs font-mono cursor-pointer border-b-2 transition-colors flex-shrink-0 ${
                      isActive
                        ? "border-o-blueText text-o-text bg-o-bg/50"
                        : "border-transparent text-o-muted hover:text-o-textSecondary hover:bg-o-bg/30"
                    }`}
                    onClick={() => setActiveIndex(tabIdx)}
                  >
                    <FileIcon name={fileName(file.path)} />
                    <span>{fileName(file.path)}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        closeTab(tabIdx);
                      }}
                      className={`ml-1 text-o-muted hover:text-o-red transition-opacity ${
                        isActive
                          ? "opacity-60 hover:opacity-100"
                          : "opacity-0 group-hover:opacity-60 hover:!opacity-100"
                      }`}
                    >
                      ×
                    </button>
                  </div>
                );
              })}
            </div>
            {/* Pinned language indicator */}
            <div className="px-3 py-2 text-xs text-o-muted font-mono flex-shrink-0 border-l border-o-border">
              {language}
            </div>
          </div>

          {/* Mobile toolbar */}
          <div className="md:hidden flex items-center justify-end px-3 py-2 border-b border-o-border">
            <span className="text-xs text-o-muted font-mono">{language}</span>
          </div>

          {/* Monaco */}
          <CodeEditor
            value={activeFile?.content ?? ""}
            onChange={updateFileContent}
            language={language}
            height={height}
          />
        </div>
      </div>

      {/* Content size warning */}
      {activeFile && activeFile.content.length > 65536 && (
        <div className="px-3 py-1.5 border-t border-o-border">
          <span className="text-o-amber text-xs">
            Content exceeds 64KB limit
          </span>
        </div>
      )}

      {/* Hint */}
      <div className="px-4 py-2 border-t border-o-border">
        <span className="text-xs text-o-muted">
          Dockerfile defines the environment · double-click name to rename ·
          paths like <code className="text-o-textSecondary">src/main.py</code>{" "}
          create folders
        </span>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) {
            handleUpload(e.target.files);
          }
          e.target.value = "";
        }}
      />
    </div>
  );
}
