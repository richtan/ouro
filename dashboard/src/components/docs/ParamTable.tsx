interface Param {
  name: string;
  type: string;
  description: string;
  required?: boolean;
}

interface ParamTableProps {
  params: Param[];
}

export default function ParamTable({ params }: ParamTableProps) {
  return (
    <div className="bg-o-surface border border-o-border rounded-xl overflow-hidden overflow-x-auto">
      <table className="w-full min-w-[480px]">
        <thead>
          <tr className="text-xs text-o-muted uppercase tracking-wider border-b border-o-border bg-o-bg">
            <th className="text-left px-4 py-2.5">Parameter</th>
            <th className="text-left px-4 py-2.5">Type</th>
            <th className="text-left px-4 py-2.5">Description</th>
          </tr>
        </thead>
        <tbody>
          {params.map((p) => (
            <tr key={p.name} className="text-sm border-t border-o-border">
              <td className="px-4 py-2.5 font-mono text-xs text-o-text">
                {p.name}
                {p.required && <span className="text-o-red ml-1">*</span>}
              </td>
              <td className="px-4 py-2.5 text-xs text-o-textSecondary">{p.type}</td>
              <td className="px-4 py-2.5 text-xs text-o-textSecondary">{p.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
