interface Props {
  title: string;
  hint?: string;
  icon?: React.ReactNode;
}

export function EmptyState({ title, hint, icon }: Props) {
  return (
    <div className="bg-white rounded-xl border border-dashed border-gray-200 px-4 py-8 text-center">
      {icon && <div className="text-gray-300 mb-2 flex justify-center">{icon}</div>}
      <div className="text-sm font-medium text-gray-600">{title}</div>
      {hint && <div className="mt-1 text-xs text-gray-400">{hint}</div>}
    </div>
  );
}
