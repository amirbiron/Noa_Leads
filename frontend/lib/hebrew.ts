// מילון תרגומים מסטטוסים/קטגוריות/וכו' לעברית להצגה למשתמשת.

export const STATUS_LABELS: Record<string, string> = {
  NEW: "חדש",
  IN_PROGRESS: "בטיפול",
  PROPOSAL_SENT: "נשלחה הצעה",
  BOOKING_PENDING: "ממתין לאישור פגישה",
  BOOKED: "פגישה מאושרת",
  WON: "נסגרה עסקה",
  LOST: "סגור ללא עסקה",
  ARCHIVED: "בארכיון",
};

export const SERVICE_CATEGORY_LABELS: Record<string, string> = {
  clinic: "קליניקה",
  workshops: "סדנאות והרצאות",
  production: "ליווי והפקות",
  digital_course: "קורס דיגיטלי",
};

export const SERVICE_SUBTYPE_LABELS: Record<string, string> = {
  voice_development: "פיתוח קול",
  public_speaking: "עמידה מול קהל",
  voice_rehab: "שיקום קול",
  workshop_speaking: "סדנת דיבור/הופעה",
  stage_arts: "אומניות הבמה",
  lecture_organization: "הרצאה לארגון",
  lecture_academic: "הרצאה אקדמית",
  production_guidance: "ליווי הפקה אישית",
  production_directing: "בימוי הפקה",
  digital_course: "קורס דיגיטלי",
};

export const WAITING_ON_LABELS: Record<string, string> = {
  NOAH: "אצלי",
  CLIENT: "אצל הלקוח",
  ASSISTANT: "אצל העוזרת",
  ASSISTANT_PENDING_NOAH: "ממתין לאישורי",
  SYSTEM: "פעולה אוטומטית",
  NONE: "—",
};

export const PRIORITY_LABELS: Record<string, string> = {
  normal: "רגיל",
  hot: "חם",
  vip: "VIP",
};

export const PREFERRED_CONTACT_LABELS: Record<string, string> = {
  phone: "טלפון",
  whatsapp: "וואטסאפ",
  email: "מייל",
};

export const TASK_TYPE_LABELS: Record<string, string> = {
  // 5 כללי הפולואפ של Spec §17.1
  first_response: "תגובה ראשונה",
  warm_followup: "פולואפ חם",
  proposal_followup: "פולואפ הצעה",
  dormant_check: "בדיקת חידוש קשר",
  dormant_suggestion: "הצעת פעולה לליד רדום",
  lecture_inquiry: "פנייה לארגון בנושא הרצאה",
  // סוגים שצ'יפים יוצרים (Spec §16.4) ושאר המערכת
  followup: "פולואפ",
  retry_call: "ניסיון שיחה חוזר",
  send_proposal: "שליחת הצעת מחיר",
  post_meeting_update: "עדכון אחרי פגישה",
  program_end: "סיום תוכנית",
  after_hours_reply: "מענה אחרי שעות",
};

// §19 D.1 — תווית עברית לפעולה המומלצת ע"י ה-AI לליד רדום.
export const DORMANT_ACTION_LABELS: Record<string, string> = {
  gentle_followup: "חידוש קשר עדין",
  call: "להתקשר",
  archive: "לארכב",
  no_action: "אין פעולה כרגע",
};

export function labelDormantAction(s: string): string {
  return DORMANT_ACTION_LABELS[s] ?? s;
}

export const ACTIVITY_TYPE_LABELS: Record<string, string> = {
  lead_created: "ליד נוצר",
  lead_updated: "ליד עודכן",
  template_marked_sent: "נשלחה תבנית",
  manual_message_logged: "תועדה הודעה ידנית",
  call_completed: "שיחה הסתיימה",
  call_no_answer: "אין מענה",
  meeting_requested: "נתבקשה פגישה",
  meeting_approved: "פגישה אושרה",
  meeting_rejected: "פגישה נדחתה",
  meeting_rescheduled: "מועד הפגישה עודכן",
  meeting_canceled: "פגישה בוטלה",
  proposal_sent: "נשלחה הצעה",
  followup_scheduled: "תוזמן פולואפ",
  owner_changed: "הוחלפה בעלות",
  internal_note_added: "הוספה הערה",
  status_changed: "שינוי סטטוס",
  lead_won: "נסגרה עסקה",
  lead_lost: "ליד נסגר ללא עסקה",
  lead_archived: "ליד הועבר לארכיון",
  lead_reopened: "ליד נפתח מחדש",
  inbound_message_logged: "הודעה נכנסת",
  outbound_message_logged: "הודעה יוצאת",
  chip_applied: "סיכום מהיר",
  program_created: "תוכנית חדשה",
  program_session_done: "מפגש בוצע",
  program_completed: "תוכנית הסתיימה",
  program_canceled: "תוכנית בוטלה",
};

// ===== תרגומי תוכניות =====

export const PROGRAM_TYPE_LABELS: Record<string, string> = {
  voice_rehab_8: "שיקום קול (8 מפגשים)",
  public_speaking_8: "עמידה מול קהל (8 מפגשים)",
  stage_arts_4: "אומניות הבמה",
  production_3months: "ליווי הפקה",
  digital_course_12: "קורס דיגיטלי (12 מפגשים)",
};

export const PROGRAM_STATUS_LABELS: Record<string, string> = {
  active: "פעילה",
  completed: "הסתיימה",
  canceled: "בוטלה",
};

export function labelProgramType(s: string): string {
  return PROGRAM_TYPE_LABELS[s] ?? s;
}

export function labelProgramStatus(s: string): string {
  return PROGRAM_STATUS_LABELS[s] ?? s;
}

export function labelStatus(s: string): string {
  return STATUS_LABELS[s] ?? s;
}

export function labelCategory(s: string | null): string {
  if (!s) return "ללא קטגוריה";  // F-04: service_category אופציונלי
  return SERVICE_CATEGORY_LABELS[s] ?? s;
}

export function labelSubtype(s: string | null): string {
  if (!s) return "";
  return SERVICE_SUBTYPE_LABELS[s] ?? s;
}

export function labelWaiting(s: string): string {
  return WAITING_ON_LABELS[s] ?? s;
}

export function labelPriority(s: string): string {
  return PRIORITY_LABELS[s] ?? s;
}

export function labelContact(s: string): string {
  return PREFERRED_CONTACT_LABELS[s] ?? s;
}

export function labelTaskType(s: string): string {
  return TASK_TYPE_LABELS[s] ?? s;
}

export function labelActivity(s: string): string {
  return ACTIVITY_TYPE_LABELS[s] ?? s;
}

// ===== פורמטר תאריך יחסי =====

// פלורליזציה בעברית — קטגוריות CLDR: one (1) / two (2) / other (3+, decimals, 0).
// ראה: docs/Skills/hebrew-i18n/references/pluralization.md
// במקום "דקתיים" משתמשים ב"שתי דקות" — צורה תקנית יותר לפי הסקיל.
function pluralizeTimeUnit(
  n: number,
  one: string,
  two: string,
  other: string,
): string {
  if (n === 1) return one;
  if (n === 2) return two;
  return `${n} ${other}`;
}

// משך זמן בדקות — "דקה" / "שתי דקות" / "N דקות". משמש למשל בדף הbooking
// להצגת default_duration_minutes.
export function pluralizeMinutes(n: number): string {
  return pluralizeTimeUnit(n, "דקה", "שתי דקות", "דקות");
}

export function formatRelativeHebrew(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  // ISO לא חוקי → fallback בטוח במקום NaN בכל החישובים
  if (Number.isNaN(date.getTime())) return "";
  const diffMs = date.getTime() - Date.now();
  const diffMinutes = Math.round(diffMs / 60000);
  const diffHours = Math.round(diffMs / 3_600_000);
  const diffDays = Math.round(diffMs / 86_400_000);

  // עד שעה — דקות. הבאג הקודם: "לפני 1 דקות" / "בעוד 1 דקות".
  if (Math.abs(diffMinutes) < 60) {
    if (diffMinutes === 0) return "ממש עכשיו";
    const abs = Math.abs(diffMinutes);
    const unit = pluralizeTimeUnit(abs, "דקה", "שתי דקות", "דקות");
    return diffMinutes < 0 ? `לפני ${unit}` : `בעוד ${unit}`;
  }

  // עד 24 שעות — שעות
  if (Math.abs(diffHours) < 24) {
    const abs = Math.abs(diffHours);
    const unit = pluralizeTimeUnit(abs, "שעה", "שעתיים", "שעות");
    return diffHours < 0 ? `לפני ${unit}` : `בעוד ${unit}`;
  }

  // ימים — עם מילים מיוחדות לאתמול/היום/מחר. הבאג הקודם:
  // "לפני 1 ימים" במקום "אתמול".
  if (diffDays === 0) return "היום";
  if (diffDays === 1) return "מחר";
  if (diffDays === -1) return "אתמול";
  const abs = Math.abs(diffDays);
  const unit = pluralizeTimeUnit(abs, "יום", "יומיים", "ימים");
  return diffDays < 0 ? `לפני ${unit}` : `בעוד ${unit}`;
}

// ===== badge "גיל" לבועת ליד (§12.1) =====

// כמה זמן עבר מאז הפעולה האחרונה על הליד מכל מקור (לקוח/נועה). מקור:
// last_activity_at (MAX של ה-activity log), ובהיעדרו created_at (ליד שעוד אין לו
// activities). רזולוציה ייעודית לפי האפיון — שונה מ-formatRelativeHebrew
// (שאין לו שבוע/שבועיים/חודש ומטפל גם בעתיד).
export function formatLeadAge(
  primaryAt: string | null,
  createdAt: string,
): string {
  const iso = primaryAt ?? createdAt;
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";

  // gap במילישניות. clamp ל-0 — שעון client שמקדים את השרת לא יחזיר "עתיד".
  const diffMs = Math.max(0, Date.now() - date.getTime());
  const minutes = Math.floor(diffMs / 60000);
  const hours = Math.floor(diffMs / 3_600_000);
  const days = Math.floor(diffMs / 86_400_000);

  if (minutes < 5) return "עכשיו";
  if (minutes < 60) return "לפני זמן קצר";
  if (hours < 24) return `לפני ${pluralizeTimeUnit(hours, "שעה", "שעתיים", "שעות")}`;
  if (days === 1) return "אתמול";
  if (days < 7) return `לפני ${pluralizeTimeUnit(days, "יום", "יומיים", "ימים")}`;
  if (days < 14) return "לפני שבוע";
  if (days < 21) return "לפני שבועיים";
  if (days < 30) return "לפני 3 שבועות";
  return "לפני חודש";
}

export function formatDateTimeHebrew(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("he-IL", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Jerusalem",
  });
}

// תוויות UI ל-5 כללי הפולואף של §17.1. השמות המדויקים מהאפיון —
// למשתמש (נועה) יותר טבעי מאשר ה-rule_key הטכני (first_response וכו').
export const FOLLOWUP_RULE_LABELS: Record<string, string> = {
  first_response: "ליד חדש שלא טופל",
  lecture_inquiry: "ארגון שהתעניין בהרצאה",
  warm_followup: "לקוח חם שלא סגר",
  proposal_followup: "פולואפ אחרי הצעת מחיר",
  dormant_check: "לקוח שלא חזר",
};

export const FOLLOWUP_UNIT_LABELS: Record<string, string> = {
  hours: "שעות",
  days: "ימים",
};
