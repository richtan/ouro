"use client";

import { Fragment } from "react";

const STEPS = ["Validating", "Submitting", "Running", "Proving", "Done"];

interface JobTimelineProps {
  stage: number;
  failed?: boolean;
  failedStage?: number;
}

export default function JobTimeline({ stage, failed, failedStage }: JobTimelineProps) {
  const effectiveFailStage = failed ? (failedStage ?? stage) : null;

  const nodeState = STEPS.map((label, i) => {
    const stepStage = i + 1;
    const isCompleted = effectiveFailStage
      ? stepStage < effectiveFailStage
      : (stage > stepStage || (stage === 5 && stepStage === 5));
    const isFailed = effectiveFailStage === stepStage;
    const isCurrent = !failed && stage === stepStage;
    return { label, stepStage, isCompleted, isFailed, isCurrent };
  });

  const lineColor = (i: number) => {
    const fromStage = i + 1;
    if (effectiveFailStage) {
      if (fromStage + 1 < effectiveFailStage) return "bg-o-green";
      if (fromStage + 1 === effectiveFailStage) return "bg-o-red";
      return "bg-o-border";
    }
    return stage > fromStage ? "bg-o-green" : "bg-o-border";
  };

  return (
    <div
      className="w-full grid items-center"
      style={{ gridTemplateColumns: "auto 1fr auto 1fr auto 1fr auto 1fr auto" }}
    >
      {/* Row 1: nodes + lines */}
      {nodeState.map((n, i) => (
        <Fragment key={n.label}>
          <div className="flex items-center self-center">
            <div className={`flex-1 h-0.5 ${i > 0 ? lineColor(i - 1) : ''}`} />
            <div
              className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center border-2 ${
                n.isFailed
                  ? "border-o-red bg-o-red/10"
                  : n.isCompleted
                    ? "border-o-green bg-o-green/10"
                    : n.isCurrent
                      ? "border-o-blue bg-o-blue/10 animate-pulse"
                      : "border-o-border bg-o-bg"
              }`}
            >
              {n.isFailed ? (
                <svg
                  width="10"
                  height="10"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                  strokeLinecap="round"
                  className="text-o-red"
                >
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              ) : n.isCompleted ? (
                <svg
                  width="10"
                  height="10"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-o-green"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              ) : n.isCurrent ? (
                <div className="w-2 h-2 rounded-full bg-o-blue" />
              ) : null}
            </div>
            <div className={`flex-1 h-0.5 ${i < STEPS.length - 1 ? lineColor(i) : ''}`} />
          </div>
          {i < STEPS.length - 1 && (
            <div className={`self-center h-0.5 ${lineColor(i)}`} />
          )}
        </Fragment>
      ))}

      {/* Row 2: labels */}
      {nodeState.map((n, i) => (
        <Fragment key={n.label}>
          <span
            className={`text-center whitespace-nowrap text-xs mt-1 ${
              n.isFailed
                ? "text-o-red"
                : n.isCompleted
                  ? "text-o-green"
                  : n.isCurrent
                    ? "text-o-blueText"
                    : "text-o-muted"
            }`}
          >
            {n.label}
          </span>
          {i < STEPS.length - 1 && <div />}
        </Fragment>
      ))}
    </div>
  );
}
