"use client";

const STEPS = ["Validating", "Submitting", "Running", "Proving", "Done"];

interface JobTimelineProps {
  stage: number;
  failed?: boolean;
}

export default function JobTimeline({ stage, failed }: JobTimelineProps) {
  return (
    <div className="flex items-center justify-between w-full">
      {STEPS.map((label, i) => {
        const stepStage = i + 1; // stage value when this step is active
        const isCompleted = stage > stepStage || (stage === 5 && stepStage === 5);
        const isCurrent = stage === stepStage && !failed;
        const isFailed = failed && stage === stepStage;

        return (
          <div key={label} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center">
              {/* Circle */}
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center border-2 ${
                  isFailed
                    ? "border-o-red bg-o-red/10"
                    : isCompleted
                      ? "border-o-green bg-o-green/10"
                      : isCurrent
                        ? "border-o-blue bg-o-blue/10 animate-pulse"
                        : "border-o-border bg-o-bg"
                }`}
              >
                {isFailed ? (
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
                ) : isCompleted ? (
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
                ) : isCurrent ? (
                  <div className="w-2 h-2 rounded-full bg-o-blue" />
                ) : null}
              </div>
              {/* Label */}
              <span
                className={`text-xs mt-1 ${
                  isFailed
                    ? "text-o-red"
                    : isCompleted
                      ? "text-o-green"
                      : isCurrent
                        ? "text-o-blueText"
                        : "text-o-muted"
                }`}
              >
                {label}
              </span>
            </div>
            {/* Connecting line */}
            {i < STEPS.length - 1 && (
              <div
                className={`flex-1 h-0.5 mx-1.5 mt-[-1rem] ${
                  stage > stepStage
                    ? "bg-o-green"
                    : "bg-o-border"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
