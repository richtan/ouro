"use client";

import Editor, { type Monaco, type BeforeMount, type OnMount } from "@monaco-editor/react";
import { useCallback } from "react";
import { useTheme } from "next-themes";

// --- Language detection maps ---

const IMAGE_LANGUAGE: Record<string, string> = {
  "ouro-ubuntu": "shell",
  "ouro-python": "python",
  "ouro-nodejs": "javascript",
};

// Module-level caches, populated once in handleBeforeMount
let extToLang: Map<string, string> | null = null;
let nameToLang: Map<string, string> | null = null;

function buildLanguageMaps(monaco: Monaco): void {
  if (extToLang) return;
  extToLang = new Map();
  nameToLang = new Map();
  for (const lang of monaco.languages.getLanguages()) {
    for (const ext of lang.extensions ?? []) {
      if (!extToLang.has(ext)) extToLang.set(ext, lang.id);
    }
    for (const name of lang.filenames ?? []) {
      nameToLang.set(name.toLowerCase(), lang.id);
    }
  }
}

export function getLanguageForFile(filePath: string, fallbackImage: string): string {
  const fileName = filePath.split("/").pop() ?? "";
  // 1. Exact filename match (Dockerfile, Makefile, etc.)
  if (nameToLang) {
    const byName = nameToLang.get(fileName.toLowerCase());
    if (byName) return byName;
  }
  // 2. Extension match
  const dotIdx = fileName.lastIndexOf(".");
  if (dotIdx >= 0 && extToLang) {
    const ext = fileName.slice(dotIdx).toLowerCase();
    const byExt = extToLang.get(ext);
    if (byExt) return byExt;
  }
  // 3. Fallback by prebuilt image
  return IMAGE_LANGUAGE[fallbackImage] ?? "plaintext";
}

// --- Ouro themes (match Shiki CSS variables in globals.css) ---

const DARK_THEME = "ouro-dark";
const LIGHT_THEME = "ouro-light";

const handleBeforeMount: BeforeMount = (monaco) => {
  buildLanguageMaps(monaco);

  monaco.editor.defineTheme(DARK_THEME, {
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

  monaco.editor.defineTheme(LIGHT_THEME, {
    base: "vs",
    inherit: false,
    rules: [
      { token: "", foreground: "4b5563" },
      { token: "keyword", foreground: "7c3aed" },
      { token: "string", foreground: "15803d" },
      { token: "number", foreground: "b45309" },
      { token: "comment", foreground: "5b616e", fontStyle: "italic" },
      { token: "type", foreground: "111316" },
      { token: "identifier", foreground: "111316" },
      { token: "variable", foreground: "4b5563" },
      { token: "delimiter", foreground: "5b616e" },
    ],
    colors: {
      "editor.background": "#ffffff",
      "editor.foreground": "#4b5563",
      "editor.lineHighlightBackground": "#f7f7f8",
      "editorLineNumber.foreground": "#5b616e",
      "editorLineNumber.activeForeground": "#4b5563",
      "editorCursor.foreground": "#0052ff",
      "editor.selectionBackground": "#0052ff22",
      "editor.inactiveSelectionBackground": "#0052ff11",
      "editorWidget.background": "#ffffff",
      "editorWidget.border": "#d1d5db",
      "editorSuggestWidget.background": "#ffffff",
      "editorSuggestWidget.border": "#d1d5db",
      "editorSuggestWidget.selectedBackground": "#f0f1f3",
      "editorGutter.background": "#ffffff",
      "editorOverviewRuler.background": "#ffffff",
      "scrollbarSlider.background": "#b9bdc780",
      "scrollbarSlider.hoverBackground": "#5b616e80",
      "scrollbarSlider.activeBackground": "#5b616e",
    },
  });
};

// --- Loading skeleton ---

function EditorSkeleton({ height }: { height: string }) {
  return (
    <div className="bg-o-bg animate-pulse" style={{ height }} />
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
  const { resolvedTheme } = useTheme();
  const monacoTheme = resolvedTheme === "dark" ? DARK_THEME : LIGHT_THEME;

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
      theme={monacoTheme}
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
