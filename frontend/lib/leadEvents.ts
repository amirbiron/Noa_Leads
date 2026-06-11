// CustomEvent name משותף בין NewLeadModal (שמעלה את ה-event) ל-
// useDashboardPoll (שמאזין כדי לסנן toast "ליד חדש" על לידים שנועה
// יצרה בעצמה). שמירה בקובץ נפרד מונעת cyclic import.

export const LEAD_MANUALLY_CREATED_EVENT = "noa:lead-manually-created";

export interface LeadManuallyCreatedDetail {
  id: string;
}

// TTL לסטור של ה-IDs ב-hook: 5 דקות מספיק לכסות poll אחרון (60s) +
// safety margin. מעל זה — הליד כבר לא "טרי" בעיני ה-poll ממילא.
export const MANUALLY_CREATED_TTL_MS = 5 * 60 * 1000;
