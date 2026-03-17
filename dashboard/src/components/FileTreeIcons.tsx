// Shared tree types and icons for file browsers

export interface TreeNode {
  name: string;
  path: string;
  isFolder: boolean;
  children: TreeNode[];
  fileIndex?: number;
}

export function buildTree<T extends { path: string }>(files: T[]): TreeNode[] {
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

export function collectFolderPaths(nodes: TreeNode[]): Set<string> {
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

export function FileIcon({ name }: { name: string }) {
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

export function FolderIcon({ open }: { open: boolean }) {
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

export function ChevronIcon({ open }: { open: boolean }) {
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
