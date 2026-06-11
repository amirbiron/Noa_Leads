// CustomEvent names משותפים בין NewLeadModal ל-useDashboardPoll.
// 3 events ב-life-cycle של יצירת ליד ידנית:
//
//   1. `lead-creation-pending` — נורה *לפני* `await api.createLead`. מסמן
//      ל-hook להתחיל "creation in flight mode" — toast מ-poll נדחה
//      בתוך ה-window הזה (~2 שניות) כדי לתת ל-POST להחזיר ולהגיע ל-(3).
//      מטפל ב-race: poll שהיה in-flight מ-server_time ישן יותר יכול
//      להחזיר את הליד החדש *לפני* שה-POST resolve ו-(3) נורה.
//
//   2. `lead-creation-canceled` — נורה כשה-POST נכשל (network / 400 / וכו').
//      מבטל את "creation in flight mode" כדי שה-poll יחזור להתנהג רגיל.
//
//   3. `lead-manually-created` — נורה אחרי success עם ה-ID. ה-hook
//      מוסיף ל-Map (TTL 5 דק') ומסיים את "creation in flight mode".
//      ה-Map מסנן בודד את ה-ID הספציפי גם בpoll-ים הבאים.

export const LEAD_CREATION_PENDING_EVENT = "noa:lead-creation-pending";
export const LEAD_CREATION_CANCELED_EVENT = "noa:lead-creation-canceled";
export const LEAD_MANUALLY_CREATED_EVENT = "noa:lead-manually-created";

export interface LeadManuallyCreatedDetail {
  id: string;
}

// TTL לסטור של ה-IDs ב-hook: 5 דקות מספיק לכסות poll אחרון (60s) +
// safety margin. מעל זה — הליד כבר לא "טרי" בעיני ה-poll ממילא.
export const MANUALLY_CREATED_TTL_MS = 5 * 60 * 1000;

// כמה זמן לדחות toast מ-poll כש-creation in flight. רוב ה-POSTs יסיימו
// ב-<500ms; 2 שניות מכסה גם רשת איטית. אחרי זה אם אין סימן ל-event,
// ה-toast מוצג רגיל (sanity — לא רוצים לדחות לנצח אם משהו נתקע).
export const CREATION_PENDING_DEFER_MS = 2000;

// safety: ה-pending flag לא תקוע יותר מ-30s גם אם events לא נורים
// (browser closed mid-POST, JS error, וכו').
export const CREATION_PENDING_MAX_MS = 30 * 1000;
