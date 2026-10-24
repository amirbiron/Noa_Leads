"use client";

import { useCallback, useEffect, useState } from "react";

// useLocalStorageState — useState + persistence ל-localStorage.
//
// **Lazy initial state:** הקריאה מ-localStorage קורית ב-initializer של
// useState (paint ראשון), לא post-mount. מונע flash של "default → stored"
// ל-משתמשים שכבר שמרו preference. ה-initializer רץ פעם אחת בלבד; שינוי
// `key` בהמשך מטופל ב-useEffect.
//
// **SSR:** typeof window guard ב-initializer. ב-server מחזיר defaultValue;
// בלקוח לקריאה ראשונה מנסה localStorage. אם הקומפוננטה משתמשת מאחורי
// boundary שלא server-renders (e.g. AuthGuard עם data fetch אחרי mount),
// אין SSR mismatch. *אם* הקומפוננטה כן server-renders, ייתכן hydration
// mismatch — מותר במקרה הזה כי הערך משתנה רק במקרי קצה (משתמש שבחר
// לכבות לפני שיעבור login).
//
// **Fail-safe:** try/catch כפול (read+write) — אם ה-storage חסום (Safari
// private browsing, iframe sandboxed, quota מלאה) ה-state נשאר ב-memory
// והקריאות לא קורסות.
//
// **Serialization:** JSON, אז עובד לכל type (boolean, number, אובייקטים).
//
// **לא tab-sync:** אין storage event listener — נועה משתמש יחיד, אין
// טעם בסנכרון בין טאבים.
export function useLocalStorageState<T>(
  key: string,
  defaultValue: T,
): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => {
    if (typeof window === "undefined") return defaultValue;
    try {
      const raw = window.localStorage.getItem(key);
      return raw !== null ? (JSON.parse(raw) as T) : defaultValue;
    } catch {
      return defaultValue;
    }
  });

  // re-sync אם ה-key משתנה (rare — `summary:daily` ↔ `summary:weekly`
  // למשל). ב-render הראשון יקרא בלי שינוי ערך → React bails out → אין
  // re-render מיותר.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(key);
      setValue(raw !== null ? (JSON.parse(raw) as T) : defaultValue);
    } catch {
      setValue(defaultValue);
    }
  }, [key, defaultValue]);

  const update = useCallback(
    (next: T) => {
      setValue(next);
      try {
        window.localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // best-effort — state ב-memory עדיין מעודכן, רק לא persistent
      }
    },
    [key],
  );

  return [value, update];
}
