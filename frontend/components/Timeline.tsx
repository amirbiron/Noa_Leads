"use client";

import { formatDateTimeHebrew, labelActivity } from "@/lib/hebrew";
import type { Activity } from "@/lib/types";

// timeline אנכי של activities — מסודר מהחדש לישן.
export function Timeline({ activities }: { activities: Activity[] }) {
  if (activities.length === 0) {
    return (
      <div className="text-sm text-gray-400 text-center py-4">
        אין פעילות מתועדת עדיין.
      </div>
    );
  }
  return (
    <ol className="relative space-y-3">
      {activities.map((a) => (
        <li
          key={a.id}
          className="bg-white rounded-lg border border-gray-200 px-3 py-2.5"
        >
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-sm font-medium">{labelActivity(a.type)}</span>
            <span className="text-xs text-gray-400 shrink-0">
              {formatDateTimeHebrew(a.created_at)}
            </span>
          </div>
          {a.content && (
            <div className="mt-1 text-sm text-gray-600 whitespace-pre-line">
              {a.content}
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}
