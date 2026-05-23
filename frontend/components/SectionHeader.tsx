interface Props {
  title: string;
  count?: number;
  hint?: string;
}

export function SectionHeader({ title, count, hint }: Props) {
  return (
    <div className="flex items-baseline justify-between mb-2 mt-5">
      <h2 className="text-sm font-semibold text-gray-700">
        {title}
        {count !== undefined && (
          <span className="text-gray-400 font-normal me-1">({count})</span>
        )}
      </h2>
      {hint && <span className="text-xs text-gray-400">{hint}</span>}
    </div>
  );
}
