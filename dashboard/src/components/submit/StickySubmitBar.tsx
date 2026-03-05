"use client";

import { ConnectButton } from "@rainbow-me/rainbowkit";

type JobStatus = "idle" | "submitting" | "paying" | "error";

interface StickySubmitBarProps {
  fromImage: string | null;
  entrypointDisplay: string | null;
  cpus: number;
  timeLimit: number;
  priceEstimate: string | null;
  priceLoading: boolean;
  canSubmit: boolean;
  isConnected: boolean;
  status: JobStatus;
  onSubmit: () => void;
  error: string | null;
}

export default function StickySubmitBar({
  fromImage,
  entrypointDisplay,
  cpus,
  timeLimit,
  priceEstimate,
  priceLoading,
  canSubmit,
  isConnected,
  status,
  onSubmit,
  error,
}: StickySubmitBarProps) {
  const isSubmitting = status === "submitting" || status === "paying";

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-o-border bg-o-surface/95 backdrop-blur-sm">
      {/* Error row */}
      {error && (
        <div className="max-w-4xl mx-auto px-4 md:px-8 lg:px-12 py-2 border-b border-o-red/20">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-o-red flex-shrink-0" />
            <span className="text-xs text-o-red truncate">
              Submission Failed: {error}
            </span>
          </div>
        </div>
      )}

      {/* Main bar */}
      <div className="max-w-4xl mx-auto px-4 md:px-8 lg:px-12 py-3">
        <div className="flex items-center justify-between gap-4">
          {/* Config summary — hidden on mobile */}
          <div className="hidden md:block text-sm text-o-textSecondary truncate">
            <span className="text-o-text">{fromImage ?? "no image"}</span>
            {entrypointDisplay && (
              <>
                <span className="text-o-muted mx-1.5">·</span>
                <span className="font-mono text-xs text-o-muted">{entrypointDisplay}</span>
              </>
            )}
            <span className="text-o-muted mx-1.5">·</span>
            {cpus} CPU{cpus > 1 ? "s" : ""}
            <span className="text-o-muted mx-1.5">·</span>
            {timeLimit} min
          </div>

          <div className="flex items-center gap-4 w-full md:w-auto justify-end">
            {/* Price */}
            <div className="flex-shrink-0">
              {priceLoading ? (
                <div className="w-4 h-4 border-2 border-o-border border-t-o-blueText rounded-full animate-spin" />
              ) : priceEstimate ? (
                <span className="font-mono text-sm text-o-green whitespace-nowrap">
                  {priceEstimate}
                </span>
              ) : null}
            </div>

            {/* Submit button or connect wallet */}
            {isConnected ? (
              <button
                onClick={onSubmit}
                disabled={!canSubmit || isSubmitting}
                className="px-6 py-3 bg-o-blue text-white font-display font-semibold text-sm rounded-lg hover:bg-o-blueHover transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
              >
                {status === "submitting"
                  ? "Preparing..."
                  : status === "paying"
                    ? "Sign Payment..."
                    : "Submit & Pay"}
              </button>
            ) : (
              <ConnectButton />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
