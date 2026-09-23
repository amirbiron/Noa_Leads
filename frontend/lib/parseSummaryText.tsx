"use client";

import { Fragment } from "react";
import Link from "next/link";

// Parser ל-markers של היפר-קישור ללידים בסיכומים AI (§13.X).
//
// Marker syntax (יוצר ע"י Claude לפי instruction ב-daily_summary.py):
//   [[lead:<UUID>|<טקסט תצוגה>]]
//
// פלט: React.ReactNode — strings + <Link> components — מוכן ל-render
// בתוך <div>/<li>.
//
// **Fail-safe** (regression guard ל-prompt drift):
// - Marker עם UUID לא חוקי (regex לא תופס) → ה-syntax הגולמי עדיין בטקסט.
//   ניקוי שלב שני (FALLBACK_REGEX) מחליף marker syntax שדלף ב-display text
//   בלבד — נועה לא תראה לעולם `[[…]]` ב-DOM.
// - text ריק / null → מוחזר as-is.
//
// **דטרמיניסטי** ולא heuristic: ה-id מגיע ישירות מ-context שה-backend
// הזין. אם הליד נמחק, ה-Link עדיין יוצר; click → /leads/<id> → 404
// (לא קריסה).

// UUID v4 standard format (8-4-4-4-12 hex chars).
const UUID_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const MARKER_REGEX = new RegExp(`\\[\\[lead:(${UUID_PATTERN})\\|([^\\]]+)\\]\\]`, "gi");

// Fallback — תופס marker syntax עם UUID לא תקני / פגום. ה-display text
// בלבד נשמר; ה-syntax עצמו מנוקה. כך נועה לא רואה `[[lead:abc|דנה]]`
// גם אם Claude שגה בפורמט.
const FALLBACK_REGEX = /\[\[lead:[^|\]]*\|([^\]]+)\]\]/g;

function cleanSegment(text: string): string {
  return text.replace(FALLBACK_REGEX, "$1");
}

export function parseSummaryText(text: string | null | undefined): React.ReactNode {
  if (!text) return text ?? "";

  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;

  for (const m of text.matchAll(MARKER_REGEX)) {
    const [full, id, display] = m;
    const start = m.index ?? 0;
    if (start > lastIndex) {
      // text לפני ה-marker — מנקים marker syntax פגום אם דלף.
      parts.push(cleanSegment(text.slice(lastIndex, start)));
    }
    parts.push(
      <Link
        key={key++}
        href={`/leads/${id}`}
        className="text-indigo-700 hover:underline font-medium"
      >
        {display}
      </Link>,
    );
    lastIndex = start + full.length;
  }

  // אם לא היו markers בכלל — מחזירים text מנוקה (יכול לכלול marker syntax
  // עם UUID פגום).
  if (parts.length === 0) {
    const cleaned = cleanSegment(text);
    return cleaned;
  }

  if (lastIndex < text.length) {
    parts.push(cleanSegment(text.slice(lastIndex)));
  }

  return (
    <>
      {parts.map((p, i) => (
        <Fragment key={i}>{p}</Fragment>
      ))}
    </>
  );
}
