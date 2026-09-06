"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { HelpCircle, X } from "lucide-react";
import {
  GLOSSARY,
  TERM_HINTS_ENABLED,
  type TermKey,
} from "@/lib/glossary";

// אייקון ⓘ קטן ליד מושג. tap → modal מרכזי עם הסבר.
//
// ## כיבוי
// כש-`TERM_HINTS_ENABLED=false` (env var `NEXT_PUBLIC_SHOW_TERM_HINTS=false`)
// הקומפוננטה מחזירה null — שום ⓘ לא מתרנדר. אין impact על ה-DOM/CSS.
//
// ## מימוש: modal מרכזי על מסך מלא (במקום popover צמוד)
// ה-ⓘ מופיע בתוך כרטיסים שיש להם `overflow: hidden` (TodayActionRow,
// LeadCardRow). popover רגיל `position: absolute` נחתך, ו-popover עם
// `position: fixed` בportal עלה מסובך + פגיע לשגיאות stacking context
// בדפדפנים מסוימים. modal מרכזי בportal ל-document.body פותר את שני
// הסיפורים: בכלל לא מנסה לחשב מיקום ביחס לכפתור, פשוט מוצג במרכז המסך
// מעל overlay מעומעם. עובד תמיד, בכל סוג כרטיס/דפדפן.
//
// ## נגישות
// - aria-label על הכפתור.
// - role="dialog" + aria-labelledby + aria-modal על ה-modal.
// - Escape סוגר. focus חוזר ל-button.
// - tap על backdrop סוגר.

interface Props {
  termKey: TermKey;
  // size אופציונלי — default 14px (`size-3.5`). באייקון בכותרת דף אולי
  // 16px עדיף.
  iconSize?: 14 | 16;
  // aria-label custom — אם לא, "הסבר על: {title}".
  ariaLabel?: string;
}

export function TermHint({ termKey, iconSize = 14, ariaLabel }: Props) {
  const [open, setOpen] = useState(false);
  // mounted guard ל-SSR — createPortal דורש document.body שלא קיים בשרת.
  const [mounted, setMounted] = useState(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  // unique id לקישור aria-labelledby.
  const idRef = useRef(`th-${Math.random().toString(36).slice(2, 9)}`);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Escape — סוגר. ה-effect חייב להיקרא **לפני** ה-return המותנה
  // (Rules of Hooks), גם אם הפיצ'ר כבוי.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // ה-component לא מתרנדר אם feature flag כבוי. ה-early return כאן
  // (אחרי כל ה-hooks) שומר על Rules of Hooks.
  if (!TERM_HINTS_ENABLED) return null;

  const entry = GLOSSARY[termKey];
  const titleId = `${idRef.current}-title`;

  return (
    <>
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
          setOpen(true);
        }}
        aria-label={ariaLabel ?? `הסבר על: ${entry.title}`}
        aria-haspopup="dialog"
        className="text-gray-400 hover:text-gray-600 active:text-gray-700 me-1 inline-flex items-center justify-center align-middle"
      >
        <HelpCircle size={iconSize} aria-hidden className="shrink-0" />
      </button>
      {/* Modal מרכזי ב-portal ל-document.body. מבטיח שה-overlay יוצא
          מכל ancestor עם overflow:hidden ו-stacking context. אותו pattern
          כמו NewLeadModal — overlay מעומעם + כרטיס במרכז. */}
      {open &&
        mounted &&
        createPortal(
          <div
            // backdrop: tap סוגר.
            onClick={(e) => {
              // אם המשתמש לחץ על ה-backdrop (לא על הכרטיס הפנימי) — סוגר.
              if (e.target === e.currentTarget) {
                e.stopPropagation();
                e.preventDefault();
                setOpen(false);
                // עקביות a11y עם Escape ו-X: focus חוזר לכפתור ⓘ. אחרת
                // screen reader נשאר בעץ של ה-dialog שכבר לא קיים.
                buttonRef.current?.focus();
              }
            }}
            className="fixed inset-0 z-[100] bg-black/40 flex items-center justify-center p-4"
            dir="rtl"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
          >
            <div
              // כרטיס: stopPropagation+preventDefault — לחיצה על הכרטיס
              // לא סוגרת, ולא מנווטת ל-anchor אב (TodayActionRow Link).
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
              }}
              className="bg-white rounded-2xl shadow-xl w-full max-w-sm px-4 py-4"
            >
              <div className="flex items-start justify-between gap-3 mb-2">
                <div
                  id={titleId}
                  className="text-base font-semibold text-gray-900"
                >
                  {entry.title}
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    setOpen(false);
                    buttonRef.current?.focus();
                  }}
                  aria-label="סגירה"
                  className="text-gray-400 hover:text-gray-700 shrink-0 -me-1 -mt-1 p-1"
                >
                  <X size={18} aria-hidden />
                </button>
              </div>
              <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">
                {entry.description}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
