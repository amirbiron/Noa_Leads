// מיפוי state_color → Tailwind classes.
// האדום בגוון עדין ולא צועק לפי האפיון (==**הבהרה:**==).

import type { StateColor } from "./types";

interface ColorClasses {
  dot: string;       // נקודה צבעונית קטנה
  badge: string;     // תווית מלאה (רקע + טקסט)
  border: string;    // פס צד או border-inline-start
  text: string;      // טקסט בלבד
}

export const STATE_COLORS: Record<StateColor, ColorClasses> = {
  red: {
    dot: "bg-state-red",
    badge: "bg-state-red/15 text-state-red border-state-red/40",
    border: "border-state-red",
    text: "text-state-red",
  },
  orange: {
    dot: "bg-state-orange",
    badge: "bg-state-orange/15 text-state-orange border-state-orange/40",
    border: "border-state-orange",
    text: "text-state-orange",
  },
  green: {
    dot: "bg-state-green",
    badge: "bg-state-green/15 text-state-green border-state-green/40",
    border: "border-state-green",
    text: "text-state-green",
  },
  gray: {
    dot: "bg-state-gray",
    badge: "bg-state-gray/15 text-state-gray border-state-gray/40",
    border: "border-state-gray",
    text: "text-state-gray",
  },
};

// תוויות מילוליות לצבעי מצב (Spec §12.9).
// `red` שמור לתרחישים קריטיים עתידיים — אין branch בקוד שמייצר אותו כעת
// (ראה derive_state_color ב-backend ו-inferStateColor ב-frontend).
// אם הוא מופיע בUI = באג, לא תרחיש לגיטימי.
export const STATE_LABELS: Record<StateColor, string> = {
  red: "דחוף", // reserved — לא בשימוש כעת
  orange: "לא טופל בזמן",
  green: "תקין",
  gray: "סגור",
};
