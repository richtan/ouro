"use client";

import Editor, { type BeforeMount, type OnMount } from "@monaco-editor/react";
import { useCallback } from "react";

// --- Language detection maps ---

export const IMAGE_LANGUAGE: Record<string, string> = {
  "ouro-ubuntu": "shell",
  "ouro-python": "python",
  "ouro-nodejs": "javascript",
};

export const EXT_LANGUAGE: Record<string, string> = {
  ".sh": "shell",
  ".bash": "shell",
  ".py": "python",
  ".js": "javascript",
  ".mjs": "javascript",
  ".ts": "typescript",
  ".r": "r",
  ".R": "r",
  ".jl": "julia",
  ".json": "json",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".toml": "ini",
  ".md": "markdown",
  ".txt": "plaintext",
  ".csv": "plaintext",
  ".tsv": "plaintext",
};

export function getLanguageForFile(filePath: string, fallbackImage: string): string {
  // Check exact filename first (e.g. Dockerfile)
  const fileName = filePath.split("/").pop() ?? "";
  if (fileName.toLowerCase() === "dockerfile") return "dockerfile";

  const ext = filePath.includes(".") ? "." + filePath.split(".").pop()! : "";
  return EXT_LANGUAGE[ext] ?? IMAGE_LANGUAGE[fallbackImage] ?? "plaintext";
}

// --- Ouro dark theme (matches Shiki CSS variables in globals.css) ---

const OURO_THEME_NAME = "ouro-dark";

const handleBeforeMount: BeforeMount = (monaco) => {
  monaco.editor.defineTheme(OURO_THEME_NAME, {
    base: "vs-dark",
    inherit: false,
    rules: [
      { token: "", foreground: "8a919e" },
      { token: "keyword", foreground: "c084fc" },
      { token: "string", foreground: "22c55e" },
      { token: "number", foreground: "eab308" },
      { token: "comment", foreground: "5b616e", fontStyle: "italic" },
      { token: "type", foreground: "f5f5f5" },
      { token: "identifier", foreground: "f5f5f5" },
      { token: "variable", foreground: "8a919e" },
      { token: "delimiter", foreground: "5b616e" },
    ],
    colors: {
      "editor.background": "#0a0b0d",
      "editor.foreground": "#8a919e",
      "editor.lineHighlightBackground": "#111316",
      "editorLineNumber.foreground": "#5b616e",
      "editorLineNumber.activeForeground": "#8a919e",
      "editorCursor.foreground": "#4C8FFF",
      "editor.selectionBackground": "#0052ff33",
      "editor.inactiveSelectionBackground": "#0052ff1a",
      "editorWidget.background": "#111316",
      "editorWidget.border": "#1e2025",
      "editorSuggestWidget.background": "#111316",
      "editorSuggestWidget.border": "#1e2025",
      "editorSuggestWidget.selectedBackground": "#191b1f",
      "editorGutter.background": "#0a0b0d",
      "editorOverviewRuler.background": "#0a0b0d",
      "scrollbarSlider.background": "#32353d80",
      "scrollbarSlider.hoverBackground": "#5b616e80",
      "scrollbarSlider.activeBackground": "#5b616e",
    },
  });
};

// --- Loading skeleton ---

function EditorSkeleton({ height }: { height: string }) {
  return (
    <div className="bg-[#0a0b0d] animate-pulse" style={{ height }} />
  );
}

// --- CodeEditor component ---

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  language: string;
  height?: string;
  readOnly?: boolean;
}

export default function CodeEditor({
  value,
  onChange,
  language,
  height = "400px",
  readOnly = false,
}: CodeEditorProps) {
  // On mount: hide the internal textarea (belt-and-suspenders for CSP/cascade
  // issues) and remeasure fonts once web fonts finish loading.
  const handleMount: OnMount = useCallback((editor, monaco) => {
    // Force-hide Monaco's internal textarea in case CDN CSS was blocked by CSP
    const container = editor.getDomNode();
    if (container) {
      const ta = container.querySelector("textarea");
      if (ta) {
        ta.style.setProperty("color", "transparent", "important");
        ta.style.setProperty("background-color", "transparent", "important");
        ta.style.setProperty("border", "none", "important");
        ta.style.setProperty("outline", "none", "important");
        ta.style.setProperty("resize", "none", "important");
        ta.style.setProperty("box-shadow", "none", "important");
        ta.style.setProperty("overflow", "hidden", "important");
        ta.style.setProperty("-webkit-appearance", "none", "important");
      }
    }
    document.fonts.ready.then(() => {
      monaco.editor.remeasureFonts();
    });
  }, []);

  return (
    <div style={{ height }}>
    <Editor
      height={height}
      language={language}
      value={value}
      onChange={(v) => onChange(v ?? "")}
      theme={OURO_THEME_NAME}
      beforeMount={handleBeforeMount}
      onMount={handleMount}
      loading={<EditorSkeleton height={height} />}
      options={{
        fontSize: 13,
        fixedOverflowWidgets: true,
        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        lineNumbers: "on",
        wordWrap: "on",
        automaticLayout: true,
        tabSize: 2,
        padding: { top: 12, bottom: 12 },
        readOnly,
        renderLineHighlight: "line",
        overviewRulerLanes: 0,
        hideCursorInOverviewRuler: true,
        overviewRulerBorder: false,
        scrollbar: {
          verticalScrollbarSize: 6,
          horizontalScrollbarSize: 6,
        },
      }}
    />
    </div>
  );
}
