import { ReactNode } from "react";
import { codeToHtml } from "shiki";
import { createCssVariablesTheme } from "shiki/core";
import CopyButton from "./CopyButton";

const theme = createCssVariablesTheme({
  name: "ouro",
  variablePrefix: "--shiki-",
});

interface CodeBlockProps {
  filename?: string;
  children: ReactNode;
  copyText?: string;
  language?: string;
}

export default async function CodeBlock({
  filename,
  children,
  copyText,
  language,
}: CodeBlockProps) {
  const html =
    language && typeof children === "string"
      ? await codeToHtml(children, { lang: language, theme })
      : null;

  return (
    <div className="bg-o-surface border border-o-border rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-o-border">
        <div className="flex gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
          <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
          <span className="w-2.5 h-2.5 rounded-full bg-o-border" />
        </div>
        {filename && (
          <span className="text-xs text-o-muted ml-1 select-none">
            {filename}
          </span>
        )}
        {copyText && <CopyButton text={copyText} />}
      </div>
      {html ? (
        <div
          className="px-5 py-5 font-mono text-xs leading-[1.7] overflow-x-auto [&_pre]:!bg-transparent [&_code]:!bg-transparent"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <pre className="px-5 py-5 font-mono text-xs leading-[1.7] overflow-x-auto text-o-textSecondary">
          {children}
        </pre>
      )}
    </div>
  );
}
