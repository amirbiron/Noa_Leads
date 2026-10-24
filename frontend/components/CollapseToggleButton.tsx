"use client";

import { ChevronDown, ChevronUp } from "lucide-react";

// כפתור chevron לקיפול בלוקי סיכום (יומי / שבועי). משותף ל-
// AiSummaryCard ול-DailySummaryBubble כדי שלא יהיה drift בין שתי
// הקומפוננטות (a11y, classes, אייקון).
//
// מוצג בכל ה-breakpoints — גם דסקטופ זקוק לקיפול אחרי שהוספנו את
// persistence: המשתמשת תרצה להחביא בלוק לפי הצורך בלי שיחזור פתוח
// בכל refresh.
export function CollapseToggleButton({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={collapsed ? "הרחב סיכום" : "קפל סיכום"}
      aria-expanded={!collapsed}
      className="p-1 -m-1 text-gray-500 hover:text-gray-800"
    >
      {collapsed ? (
        <ChevronDown size={16} aria-hidden />
      ) : (
        <ChevronUp size={16} aria-hidden />
      )}
    </button>
  );
}
