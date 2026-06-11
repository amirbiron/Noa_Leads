import { TermHint } from "./TermHint";
import type { TermKey } from "@/lib/glossary";

interface Props {
  title: string;
  count?: number;
  hint?: string;
  // ⓘ קופץ ליד הכותרת — להבהרת מושג חדש בתקופת ההיכרות.
  termKey?: TermKey;
}

export function SectionHeader({ title, count, hint, termKey }: Props) {
  return (
    <div className="flex items-baseline justify-between mb-2 mt-5">
      <h2 className="text-sm font-semibold text-gray-700 flex items-center">
        {title}
        {count !== undefined && (
          <span className="text-gray-400 font-normal me-1">({count})</span>
        )}
        {termKey && <TermHint termKey={termKey} />}
      </h2>
      {hint && <span className="text-xs text-gray-400">{hint}</span>}
    </div>
  );
}
