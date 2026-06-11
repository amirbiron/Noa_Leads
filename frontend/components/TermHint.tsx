"use client";

import { useEffect, useRef, useState } from "react";
import { HelpCircle } from "lucide-react";
import {
  GLOSSARY,
  TERM_HINTS_ENABLED,
  type TermKey,
} from "@/lib/glossary";

// אייקון ⓘ קטן ליד מושג. tap → popover עם הסבר. tap בחוץ / Esc → סוגר.
//
// ## כיבוי
// כש-`TERM_HINTS_ENABLED=false` (env var `NEXT_PUBLIC_SHOW_TERM_HINTS=false`)
// הקומפוננטה מחזירה null — שום ⓘ לא מתרנדר. אין impact על ה-DOM/CSS.
//
// ## נגישות
// - aria-describedby קושר את האייקון ל-popover.
// - role="dialog" + aria-labelledby על ה-popover.
// - Escape סוגר. focus חוזר ל-button.
//
// ## מיקום
// absolute מתחת לאייקון (translate-y). על מסכים קטנים — viewport-aware:
// אם ימני, נשלם משמאל; אם לא נכנס בגובה, נופל למעלה. לא ספריית popper כי
// המקרה פשוט (גודל קבוע ~280px).

interface Props {
  termKey: TermKey;
  // size אופציונלי — default 14px (`size-3.5`). באייקון בכותרת דף אולי
  // 16px עדיף.
  iconSize?: 14 | 16;
  // aria-label custom — אם לא, "הסבר על: {title}".
  ariaLabel?: string;
  // dir אופציונלי לאיזון מיקום ב-popover (default: end = שמאל ב-RTL).
}

export function TermHint({ termKey, iconSize = 14, ariaLabel }: Props) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  // unique id לקישור aria-describedby + labelledby.
  const idRef = useRef(`th-${Math.random().toString(36).slice(2, 9)}`);

  // tap בחוץ + Escape — סוגר. ה-effect חייב להיקרא **לפני** ה-return
  // המותנה (Rules of Hooks), גם אם הפיצ'ר כבוי.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      const target = e.target as Node | null;
      if (!target) return;
      if (
        popoverRef.current?.contains(target) ||
        buttonRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    // pointerdown ולא click — נסגר מיד עם תחילת הtap, לפני שייווצר אירוע
    // click שני שיפתח שוב. capture כדי לתפוס לפני handlers אחרים.
    window.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // ה-component לא מתרנדר אם feature flag כבוי. ה-early return כאן
  // (אחרי כל ה-hooks) שומר על Rules of Hooks.
  if (!TERM_HINTS_ENABLED) return null;

  const entry = GLOSSARY[termKey];
  const popoverId = `${idRef.current}-popover`;
  const titleId = `${idRef.current}-title`;

  return (
    <span
      className="relative inline-flex items-center align-middle"
      // ה-span עוטף את הכפתור והpopover. ⓘ ממוקם בתוך כרטיסים שעטופים
      // ב-<Link> (TodayActionRow וכו'). כל אינטראקציה כאן חייבת לעצור גם
      // את ה-propagation וגם את ה-default action — אחרת קליק על ⓘ מנווט
      // ל-/leads/[id] במקום לפתוח popover. ה-onClick על ה-span תופס גם
      // אזורים שאינם הכפתור (gap, popover background).
      onClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
      }}
    >
      <button
        ref={buttonRef}
        type="button"
        onClick={(e) => {
          // stopPropagation לבד לא מספיק כשהאב הוא <a>: ה-React event
          // אכן נעצר, אבל ה-DOM event ממשיך ל-default action של ה-anchor
          // (ניווט). preventDefault על אותו event מסמן defaultPrevented
          // → הדפדפן מדלג על הניווט.
          e.stopPropagation();
          e.preventDefault();
          setOpen((v) => !v);
        }}
        aria-label={ariaLabel ?? `הסבר על: ${entry.title}`}
        aria-describedby={open ? popoverId : undefined}
        aria-expanded={open}
        className="text-gray-400 hover:text-gray-600 active:text-gray-700 me-1 inline-flex items-center justify-center"
      >
        <HelpCircle
          size={iconSize}
          aria-hidden
          className="shrink-0"
        />
      </button>
      {open && (
        <div
          ref={popoverRef}
          id={popoverId}
          role="dialog"
          aria-labelledby={titleId}
          // top-full + mt-1 = מתחת לאייקון. inset-inline-end-0 ב-RTL =
          // היצמדות לקצה הימני של ה-anchor (טבעי שתופס שטח שמאלה).
          // max-w-[min(90vw,18rem)] = עד 288px או 90vw — מה שקטן.
          className="absolute top-full mt-1 z-50 max-w-[min(90vw,18rem)] w-72
                     rounded-lg border border-gray-200 bg-white shadow-lg
                     px-3 py-2 text-start"
          style={{ insetInlineEnd: 0 }}
        >
          <div
            id={titleId}
            className="text-sm font-semibold text-gray-900 mb-1"
          >
            {entry.title}
          </div>
          <div className="text-xs text-gray-700 leading-relaxed whitespace-pre-line">
            {entry.description}
          </div>
        </div>
      )}
    </span>
  );
}
