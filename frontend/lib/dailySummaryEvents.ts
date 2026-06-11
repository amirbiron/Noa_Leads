// CustomEvent name לתקשורת בין ה-badge "סיכום יומי" ב-AppShell header
// (פותח) לבין AiSummaryCard (מאזין ומפעיל setCollapsed(false)).
//
// הברירה ב-event ולא ב-state lift: AiSummaryCard מחזיק את ה-collapse state
// ב-useLocalStorageState המקומי (persist בין renders). לרים את ה-state
// היה דורש להעביר setter דרך 2 רמות; event פשוט יותר ותואם לpattern
// של noa:lead-manually-created הקיים.

export const EXPAND_DAILY_SUMMARY_EVENT = "noa:expand-daily-summary";
