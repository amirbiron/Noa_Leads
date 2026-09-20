import type { MetadataRoute } from "next";

// `/robots.txt` — Next מייצר אותו מהקובץ הזה (App Router).
//
// מאז שהכניסה ללא סיסמה, כל מי שמגיע לכתובת נכנס כנועה — ולכן
// הדבר האחרון שרוצים הוא שהאפליקציה תופיע בתוצאות חיפוש. גם דף
// קביעת הפגישה (`/book/{token}`) לא אמור להיות מאונדקס: הטוקן הוא
// ה-credential היחיד שלו.
//
// זו אחת משלוש שכבות, כי כל אחת מכסה מה שהאחרת מפספסת:
// 1. הקובץ הזה — בקשה מנומסת לזחלנים; מי שמכבד robots.txt לא ייכנס.
// 2. `metadata.robots` ב-`app/layout.tsx` — תג בכל עמוד HTML, תקף גם
//    לזחלן שהגיע דרך קישור חיצוני ולא קרא robots.txt.
// 3. header `X-Robots-Tag` ב-`next.config.mjs` — מכסה גם תגובות
//    שאינן HTML.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      disallow: "/",
    },
  };
}
