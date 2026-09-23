// טסטים ללוגיקת ההתאוששות מ-401.
//
// אין ב-frontend הזה runner טסטים (אין Vitest/Jest ב-package.json),
// ולא הוספתי אחד בשביל קובץ אחד. במקום זה הקובץ רץ ישירות תחת Node
// עם הסרת טיפוסים — בלי תלות חדשה ובלי שלב build:
//
//     node --experimental-strip-types lib/authRetry.test.ts
//
// זו הסיבה שהלוגיקה חולצה ל-`authRetry.ts` מלכתחילה: היא ניתנת
// לבדיקה בלי רשת, בלי דפדפן ובלי localStorage.

import assert from "node:assert/strict";
import { decideAuthRecovery, singleFlight } from "./authRetry.ts";

const base = {
  status: 401,
  retryAuth: true,
  refreshAttempted: false,
  publicAccessAttempted: false,
  hasRefreshToken: true,
};

let passed = 0;
function check(name: string, fn: () => void | Promise<void>) {
  const result = fn();
  if (result instanceof Promise) {
    return result.then(() => {
      passed++;
      console.log("  ✓", name);
    });
  }
  passed++;
  console.log("  ✓", name);
  return Promise.resolve();
}

const tests = async () => {
  await check("תגובה תקינה לא מפעילה שום התאוששות", () => {
    assert.equal(decideAuthRecovery({ ...base, status: 200 }), "none");
  });

  await check("retryAuth=false מנטרל התאוששות (מונע רקורסיה)", () => {
    assert.equal(decideAuthRecovery({ ...base, retryAuth: false }), "none");
  });

  await check("401 ראשון עם refresh token → refresh", () => {
    assert.equal(decideAuthRecovery(base), "refresh");
  });

  await check("401 בלי refresh token → ישר לכניסה אוטומטית", () => {
    assert.equal(
      decideAuthRecovery({ ...base, hasRefreshToken: false }),
      "public-access",
    );
  });

  await check("אחרי שה-refresh נוסה → כניסה אוטומטית", () => {
    assert.equal(
      decideAuthRecovery({ ...base, refreshAttempted: true }),
      "public-access",
    );
  });

  // הטסט המרכזי: זה מה שעוצר את המעגל refresh→כניסה→401→כניסה→...
  await check("אחרי ששניהם נוסו → כניעה, לא ניסיון נוסף", () => {
    assert.equal(
      decideAuthRecovery({
        ...base,
        refreshAttempted: true,
        publicAccessAttempted: true,
        hasRefreshToken: false,
      }),
      "give-up",
    );
  });

  await check("כניעה גם אם נשאר refresh token — ניסיון אחד לכל סוג", () => {
    assert.equal(
      decideAuthRecovery({
        ...base,
        refreshAttempted: true,
        publicAccessAttempted: true,
        hasRefreshToken: true,
      }),
      "give-up",
    );
  });

  await check("singleFlight: 6 קריאות במקביל → הרצה אחת בפועל", async () => {
    let calls = 0;
    let release!: (v: boolean) => void;
    const gate = new Promise<boolean>((r) => {
      release = r;
    });
    const wrapped = singleFlight(async () => {
      calls++;
      return gate;
    });

    const all = Promise.all([
      wrapped(), wrapped(), wrapped(), wrapped(), wrapped(), wrapped(),
    ]);
    release(true);
    const results = await all;

    assert.equal(calls, 1, "הפונקציה רצה יותר מפעם אחת");
    assert.deepEqual(results, [true, true, true, true, true, true]);
  });

  await check("singleFlight: קריאה אחרי שהסתיימה מריצה מחדש (לא cache)", async () => {
    let calls = 0;
    const wrapped = singleFlight(async () => {
      calls++;
      return calls;
    });
    assert.equal(await wrapped(), 1);
    assert.equal(await wrapped(), 2);
  });

  await check("singleFlight: כישלון משחרר את המנעול", async () => {
    let calls = 0;
    const wrapped = singleFlight(async () => {
      calls++;
      throw new Error("boom");
    });
    await assert.rejects(wrapped());
    await assert.rejects(wrapped());
    assert.equal(calls, 2, "המנעול נתקע אחרי כישלון");
  });
};

tests()
  .then(() => {
    console.log(`\n${passed} tests passed`);
  })
  .catch((err) => {
    // קוד יציאה מפורש: בלי זה הכישלון נשען על ברירת המחדל של Node
    // ל-unhandled rejection. היא אמנם מחזירה 1 היום, אבל טסט שהערך
    // שלו תלוי בדגל ריצה של סביבה אחרת הוא טסט שיכול להפוך בשקט
    // ל"תמיד ירוק".
    console.error(`\nנכשל אחרי ${passed} בדיקות:`);
    console.error(err);
    process.exitCode = 1;
  });
