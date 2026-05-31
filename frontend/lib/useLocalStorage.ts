"use client";

import { useCallback, useEffect, useState } from "react";

// useLocalStorageState — useState + persistence ל-localStorage.
//
// **SSR-safe:** initial render מחזיר את ה-defaultValue (כי localStorage
// לא קיים ב-SSR). hydration מ-localStorage קורה ב-useEffect, מה שיכול
// לגרום ל-flash קצר של default→stored ב-first paint. עבור MVP מקובל;
// אם בעתיד יעצבן, אפשר לעבור ל-suppressHydrationWarning + lazy initial.
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
  const [value, setValue] = useState<T>(defaultValue);

  // hydrate אחרי mount — `window` לא קיים ב-SSR.

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
