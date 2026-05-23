// מילון תרגומים מסטטוסים/קטגוריות/וכו' לעברית להצגה למשתמשת.

export const STATUS_LABELS: Record<string, string> = {
  NEW: "חדש",
  IN_PROGRESS: "בטיפול",
  PROPOSAL_SENT: "נשלחה הצעה",
  BOOKING_PENDING: "ממתין לאישור תור",
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
  first_response: "תגובה ראשונה",
  followup: "פולואפ",
  proposal_followup: "פולואפ הצעה",
  post_meeting_update: "עדכון אחרי פגישה",
  dormant_reachout: "חידוש קשר",
  program_end: "סיום תוכנית",
  after_hours_reply: "מענה אחרי שעות",
};

export const ACTIVITY_TYPE_LABELS: Record<string, string> = {
  lead_created: "ליד נוצר",
  lead_updated: "ליד עודכן",
  template_marked_sent: "נשלחה תבנית",
  manual_message_logged: "תועדה הודעה ידנית",
  call_completed: "שיחה הסתיימה",
  call_no_answer: "אין מענה",
  meeting_requested: "נתבקש תור",
  meeting_approved: "פגישה אושרה",
  meeting_rejected: "פגישה נדחתה",
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
};

export function labelStatus(s: string): string {
  return STATUS_LABELS[s] ?? s;
}

export function labelCategory(s: string): string {
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

export function formatRelativeHebrew(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  // ISO לא חוקי → fallback בטוח במקום NaN בכל החישובים
  if (Number.isNaN(date.getTime())) return "";
  const diffMs = date.getTime() - Date.now();
  const diffMinutes = Math.round(diffMs / 60000);
  const diffHours = Math.round(diffMs / 3_600_000);
  const diffDays = Math.round(diffMs / 86_400_000);

  if (Math.abs(diffMinutes) < 60) {
    if (diffMinutes === 0) return "ממש עכשיו";
    if (diffMinutes < 0) return `לפני ${-diffMinutes} דקות`;
    return `בעוד ${diffMinutes} דקות`;
  }
  if (Math.abs(diffHours) < 24) {
    if (diffHours < 0) return `לפני ${-diffHours} שעות`;
    return `בעוד ${diffHours} שעות`;
  }
  if (diffDays < 0) return `לפני ${-diffDays} ימים`;
  if (diffDays === 1) return "מחר";
  if (diffDays === 0) return "היום";
  return `בעוד ${diffDays} ימים`;
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
