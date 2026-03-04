interface StepCardProps {
  number: number;
  title: string;
  children: React.ReactNode;
  last?: boolean;
}

export default function StepCard({ number, title, children, last }: StepCardProps) {
  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <div className="w-8 h-8 rounded-full bg-o-blue/10 text-o-blueText text-sm font-semibold flex items-center justify-center shrink-0">
          {number}
        </div>
        {!last && <div className="w-px flex-1 bg-o-border mt-2" />}
      </div>
      <div className={`pb-8 ${last ? "pb-0" : ""}`}>
        <h3 className="font-display text-sm font-semibold text-o-text">{title}</h3>
        <div className="mt-2 text-sm text-o-textSecondary leading-relaxed">{children}</div>
      </div>
    </div>
  );
}
