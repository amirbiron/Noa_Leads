"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
// ## מיקום: Portal ל-document.body
// ⓘ מופיע בתוך כרטיסים (TodayActionRow) שיש להם `overflow: hidden` (לטובת
// rounded corners + truncate). popover רגיל `position: absolute` היה
// נחתך ע"י ה-overflow של הכרטיס. הפתרון: רנדור ב-portal ל-document.body
// עם `position: fixed` + computed position from button rect. כך ה-popover
// יוצא מכל ancestor חותך.
//
// המיקום מחושב פעם אחת בפתיחה (`useLayoutEffect`) מ-`getBoundingClientRect`
// של הכפתור — אין סיבה לעקוב אחרי scroll/resize כי גם פעולה כזו סוגרת
// את ה-popover (pointerdown handler).

interface Props {
  termKey: TermKey;
  // size אופציונלי — default 14px (`size-3.5`). באייקון בכותרת דף אולי
  // 16px עדיף.
  iconSize?: 14 | 16;
  // aria-label custom — אם לא, "הסבר על: {title}".
  ariaLabel?: string;
}

interface PopoverPosition {
  top: number;
  // ב-RTL נצמד לקצה הימני של הכפתור (popover מתפשט שמאלה משם). מודד
  // distance מקצה ימני של viewport.
  right: number;
}

export function TermHint({ termKey, iconSize = 14, ariaLabel }: Props) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PopoverPosition | null>(null);
  // mounted — guard ל-SSR. createPortal דורש document.body שלא קיים בשרת.
  // נקבע ל-true ב-mount; עד אז ה-popover לא מנסה לרנדר.
  const [mounted, setMounted] = useState(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  // unique id לקישור aria-describedby + labelledby.
  const idRef = useRef(`th-${Math.random().toString(36).slice(2, 9)}`);

  useEffect(() => {
    setMounted(true);
  }, []);

  // מחשב מיקום ב-pre-render של ה-popover (פני ה-paint) — מונע "קפיצה"
  // אם נקבל מיקום ב-useEffect רגיל. ה-effect חייב להיקרא בכל render
  // (Rules of Hooks), משתקם כשלא פתוח.
  useLayoutEffect(() => {
    if (!open) return;
    if (!buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    setPosition({
      top: rect.bottom + 4, // mt-1 = 4px gap
      right: window.innerWidth - rect.right,
    });
  }, [open]);

  // tap בחוץ + Escape + scroll/resize — סוגרים. ה-effect חייב להיקרא
  // **לפני** ה-return המותנה (Rules of Hooks), גם אם הפיצ'ר כבוי.
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
    // scroll/resize — סוגרים. ה-popover מקובע למיקום חישוב חד-פעמי
    // (`position: fixed`); אם המשתמש גולל, הכפתור זז אך ה-popover נשאר
    // — מנותק. פשוט וצפוי לסגור.
    function onScrollOrResize() {
      setOpen(false);
    }
    // pointerdown ולא click — נסגר מיד עם תחילת הtap, לפני שייווצר אירוע
    // click שני שיפתח שוב. capture כדי לתפוס לפני handlers אחרים.
    window.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown, true);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
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
      // ה-span עוטף את הכפתור. ⓘ ממוקם בתוך כרטיסים שעטופים ב-<Link>
      // (TodayActionRow וכו'). כל אינטראקציה כאן חייבת לעצור גם את
      // ה-propagation וגם את ה-default action — אחרת קליק על ⓘ מנווט
      // ל-/leads/[id] במקום לפתוח popover.
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
      {/* Portal ל-document.body — מבטיח שה-popover לא נחתך ע"י ancestor
          עם overflow:hidden (TodayActionRow card). position:fixed +
          coordinates מ-rect → המיקום נשמר גם בלי context של ה-parent. */}
      {open &&
        mounted &&
        position &&
        createPortal(
          <div
            ref={popoverRef}
            id={popoverId}
            role="dialog"
            aria-labelledby={titleId}
            className="fixed z-50 max-w-[min(90vw,18rem)] w-72 rounded-lg
                       border border-gray-200 bg-white shadow-lg
                       px-3 py-2 text-start"
            style={{ top: position.top, right: position.right }}
            // קליק על ה-popover עצמו: אותה הגנה — לא להפעיל <Link> אב,
            // לא לסגור (pointerdown handler מסנן contains).
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
            }}
            dir="rtl"
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
          </div>,
          document.body,
        )}
    </span>
  );
}
