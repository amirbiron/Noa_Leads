// לוגיקת ההתאוששות מ-401, מופרדת מה-fetcher כדי שתהיה ניתנת לבדיקה.
//
// הרקע: מאז שהכניסה היא ללא סיסמה, תגובת 401 כבר לא מסתיימת בהפניה
// למסך התחברות — היא מנסה להיכנס מחדש אוטומטית. זה פותח מעגל שלא היה
// קודם: כניסה אוטומטית מצליחה ← ה-token עדיין נדחה ← 401 ← כניסה
// אוטומטית שוב. שלושה מצבים מייצרים בדיוק את זה, וכולם אמיתיים:
// שעון מכשיר שלא מסונכרן, `JWT_SECRET_KEY` שהוחלף ב-Render, ומשתמש
// ה-owner שנמחק.
//
// שתי ההגנות נפרדות ומטפלות בשתי בעיות שונות:
//   1. `decideAuthRecovery` — **ניסיון אחד לכל בקשה**. עוצר את המעגל.
//   2. `singleFlight`      — **קריאה אחת בו-זמנית**. עוצר מטח: דף
//      שטוען 6 endpoints במקביל ונופל ב-401 בכולם היה יורה 6 קריאות
//      כניסה, ונתקל במגבלת הקצב בשרת.

/** מה לעשות אחרי תגובה שהתקבלה. */
export type AuthRecoveryStep =
  /** לא 401, או שההתאוששות מנוטרלת לבקשה הזו — להמשיך כרגיל. */
  | "none"
  /** יש refresh token — לנסות לחדש ואז לשדר את הבקשה מחדש. */
  | "refresh"
  /** לנסות כניסה אוטומטית ואז לשדר את הבקשה מחדש. */
  | "public-access"
  /** מיצינו את כל הניסיונות — להיכשל עם השגיאה המקורית. */
  | "give-up";

export interface AuthRecoveryState {
  status: number;
  /** false ב-`/auth/refresh` ו-`/auth/public-access` עצמם, וב-endpoints ציבוריים. */
  retryAuth: boolean;
  /** האם כבר ניסינו refresh **בבקשה הזו**. */
  refreshAttempted: boolean;
  /** האם כבר ניסינו כניסה אוטומטית **בבקשה הזו**. */
  publicAccessAttempted: boolean;
  /** האם קיים refresh token שמור. */
  hasRefreshToken: boolean;
}

export function decideAuthRecovery(s: AuthRecoveryState): AuthRecoveryStep {
  if (s.status !== 401 || !s.retryAuth) return "none";
  // refresh קודם: הוא משמר את ה-session הקיים. כניסה אוטומטית היא
  // ה-fallback, ולכן גם בלי refresh token נופלים ישר אליה.
  if (s.hasRefreshToken && !s.refreshAttempted) return "refresh";
  if (!s.publicAccessAttempted) return "public-access";
  return "give-up";
}

/**
 * עוטף פונקציה אסינכרונית כך שקריאות שחופפות בזמן מתאחדות לאחת.
 *
 * הקריאה הראשונה מריצה בפועל; כל קריאה שמגיעה בזמן שהיא רצה מקבלת
 * את *אותו* Promise. ברגע שהיא מסתיימת (בהצלחה או בכישלון) המנעול
 * משוחרר, וקריאה חדשה תריץ מחדש — כלומר זה איחוד, לא cache.
 */
export function singleFlight<T>(fn: () => Promise<T>): () => Promise<T> {
  let inFlight: Promise<T> | null = null;
  return () => {
    if (inFlight) return inFlight;
    // ה-finally מנקה את המנעול גם בכישלון. בלעדיו כישלון אחד היה
    // מקפיא את כל הקריאות הבאות על אותו Promise דחוי.
    inFlight = fn().finally(() => {
      inFlight = null;
    });
    return inFlight;
  };
}
