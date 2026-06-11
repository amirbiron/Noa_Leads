// מילון הסברים קצרים על מושגי המערכת — מוצגים כ-popovers ליד מושג בתוך
// ה-UI, לתקופת היכרות (חודש-חודשיים) עד שנועה מכירה את השפה.
//
// ## כיבוי
// ה-feature flag הוא env var `NEXT_PUBLIC_SHOW_TERM_HINTS`. ברירת המחדל
// (כשה-var ריק) — מופעל. לכיבוי גלובלי: ב-Render מגדירים
// `NEXT_PUBLIC_SHOW_TERM_HINTS=false` → redeploy. אין צורך לגעת בקוד.
//
// `NEXT_PUBLIC_` הוא prefix של Next.js שמחשיף את ה-var ל-client בזמן
// build. שינוי דורש rebuild.
//
// ## מבנה
// המפתחות הם stable IDs (snake_case) — לא בעברית — כדי שאפשר יהיה
// לעשות rename של ה-label בעברית בלי לשבור את ה-mapping.

export const TERM_HINTS_ENABLED: boolean =
  process.env.NEXT_PUBLIC_SHOW_TERM_HINTS !== "false";

export interface GlossaryEntry {
  // כותרת ה-popover (קצרה). לרוב זהה ל-label בממשק אבל לא חובה.
  title: string;
  // הסבר 1-2 משפטים. עברית פשוטה. אין מילים טכניות (PROPOSAL_SENT, etc).
  description: string;
}

export type TermKey =
  // ===== א. סוגי תזכורות / משימות (12) =====
  | "task_first_response"
  | "task_warm_followup"
  | "task_proposal_followup"
  | "task_followup"
  | "task_post_meeting_update"
  | "task_lecture_inquiry"
  | "task_dormant_check"
  | "task_dormant_suggestion"
  | "task_retry_call"
  | "task_send_proposal"
  | "task_after_hours_reply"
  | "task_program_end"
  // ===== ב. סטטוסים מבלבלים (4) =====
  | "status_in_progress"
  | "status_booking_pending"
  | "status_booked"
  | "status_closed"
  // ===== ג. אצל מי הכדור (3) =====
  | "waiting_noah"
  | "waiting_client"
  | "waiting_assistant"
  // ===== ד. AI / רדום (2) =====
  | "concept_dormant_lead"
  | "concept_ai_suggestion"
  // ===== ה. מושגים כלליים (4) =====
  | "concept_lead"
  | "concept_chip"
  | "concept_template"
  | "concept_log_inbound"
  // ===== ו. דפים (4) =====
  | "page_today"
  | "page_pending"
  | "page_leads"
  | "page_proposals"
  // ===== ז. הבחנות (1) =====
  | "distinction_template_vs_proposal";

export const GLOSSARY: Record<TermKey, GlossaryEntry> = {
  // ===== א. סוגי תזכורות / משימות =====
  task_first_response: {
    title: "תגובה ראשונה",
    description:
      "ליד חדש שעדיין לא יצרת איתו קשר. ההזדמנות הכי טרייה — לענות תוך 24 שעות.",
  },
  task_warm_followup: {
    title: "פולואפ חם",
    description:
      "שלחת הודעה ללקוח, עברו ~48 שעות והוא לא ענה. הוא מעורב אבל לא סגר — מותחים את החוט לפני שיתקרר.",
  },
  task_proposal_followup: {
    title: "פולואפ הצעה",
    description:
      "שלחת הצעת מחיר, עברו כמה ימים ואין תשובה. ההצעה 'באוויר' — לחזור ולוודא.",
  },
  task_followup: {
    title: "פולואפ",
    description:
      "תזכורת שאת בחרת לתזמן ידנית דרך צ'יפ (\"לחזור בעוד חודש\", \"מעוניין בשיחה\"). לא נגזרת מ-flow אוטומטי.",
  },
  task_post_meeting_update: {
    title: "עדכון אחרי פגישה",
    description:
      "הפגישה הסתיימה — לתעד מה היה ולקבוע צעד הבא, לפני שהפרטים נשכחים.",
  },
  task_lecture_inquiry: {
    title: "פנייה לארגון בנושא הרצאה",
    description:
      "כמו 'תגובה ראשונה', אבל ספציפית לליד ארגוני שביקש הרצאה (מאפשר התייחסות שונה).",
  },
  task_dormant_check: {
    title: "בדיקת חידוש קשר",
    description:
      "ליד ש'נרדם' — חלפו ~60 יום בלי תקשורת. תזכורת לבדוק אם שווה לחדש.",
  },
  task_dormant_suggestion: {
    title: "הצעת פעולה לליד רדום",
    description:
      "המלצה אוטומטית של ה-AI לליד רדום (לחדש קשר / להתקשר / לארכב).",
  },
  task_retry_call: {
    title: "ניסיון שיחה חוזר",
    description: "התקשרת ולא ענו — תזכורת לנסות שוב.",
  },
  task_send_proposal: {
    title: "שליחת הצעת מחיר",
    description: "תזכורת שצריך להכין ולשלוח הצעה.",
  },
  task_after_hours_reply: {
    title: "מענה אחרי שעות",
    description:
      "ליד שנכנס מחוץ לשעות העבודה — תזכורת לחזור אליו בבוקר.",
  },
  task_program_end: {
    title: "סיום תוכנית",
    description:
      "תוכנית מתמשכת (למשל 8 מפגשים) מתקרבת לסיום — תזכורת לסכם / להציע המשך.",
  },

  // ===== ב. סטטוסים =====
  status_in_progress: {
    title: "בטיפול",
    description: "כבר יצרת קשר, הליד פעיל אבל עוד לא נשלחה הצעה.",
  },
  status_booking_pending: {
    title: "ממתין לאישור תור",
    description:
      "הלקוח ביקש תור דרך דף ההזמנה, ואת צריכה לאשר או לדחות.",
  },
  status_booked: {
    title: "פגישה מאושרת",
    description: "התור אושר ונקבע ביומן.",
  },
  status_closed: {
    title: "סטטוסי סגירה",
    description:
      "הליד נסגר — 'נסגרה עסקה' (בהצלחה), 'סגור ללא עסקה' (לא הסתדר), או 'בארכיון'.",
  },

  // ===== ג. אצל מי הכדור =====
  waiting_noah: {
    title: "אצלי",
    description: "הכדור אצלך, את צריכה לעשות את הצעד הבא.",
  },
  waiting_client: {
    title: "אצל הלקוח",
    description:
      "שלחת משהו והכדור אצלו — מחכים שהוא יחזור.",
  },
  waiting_assistant: {
    title: "אצל העוזרת / ממתין לאישורי",
    description: "מצבים שקשורים למנגנון העוזרת.",
  },

  // ===== ד. AI / רדום =====
  concept_dormant_lead: {
    title: "ליד רדום",
    description:
      "ליד פתוח שאין בו תקשורת זמן רב (כ-60 יום). לא נסגר, אבל 'ישן'.",
  },
  concept_ai_suggestion: {
    title: "הצעת פעולה (AI)",
    description:
      "ה-AI מנתח ליד רדום וממליץ: חידוש קשר עדין / להתקשר / לארכב / אין פעולה כרגע.",
  },

  // ===== ה. מושגים כלליים =====
  concept_lead: {
    title: "ליד",
    description: "פנייה או לקוח פוטנציאלי. כל כרטיס במערכת הוא ליד.",
  },
  concept_chip: {
    title: "צ'יפ / סיכום מהיר",
    description:
      "כפתור מהיר לתיעוד מה קרה בשיחה (\"רוצה הצעה\", \"אין מענה\"). מעדכן סטטוס ויוצר תזכורת בלחיצה אחת.",
  },
  concept_template: {
    title: "תבנית",
    description:
      "נוסח הודעה מוכן מראש (פתיחה / הצעה / פולואפ) שאפשר לשלוח בלי להקליד מאפס.",
  },
  concept_log_inbound: {
    title: "תיעוד הודעה נכנסת",
    description:
      "לסמן שהלקוח חזר אלייך (וואטסאפ/טלפון). המערכת תדע שהכדור חזר אלייך ותסגור תזכורות מיותרות.",
  },

  // ===== ו. דפים =====
  page_today: {
    title: "עמוד 'היום'",
    description:
      "ה-to-do היומי שלך — תזכורות פתוחות שהזמן שלהן הגיע (כולל overdue קצר עד 7 ימים). 'מה לעשות עכשיו'.",
  },
  page_pending: {
    title: "עמוד 'ממתין לטיפול'",
    description:
      "רשת ביטחון — לידים תקועים 7+ ימים + בקשות תור שמחכות לאישור. לא ה-to-do השוטף, אלא ה'נופלים בין הכיסאות'.",
  },
  page_leads: {
    title: "עמוד 'לידים'",
    description:
      "המאגר המלא של הלידים הפתוחים שלך, ממוין לפי עדכון אחרון. סגורים מופיעים בארכיון בלבד.",
  },
  page_proposals: {
    title: "עמוד 'הצעות פתוחות'",
    description:
      "תצוגה ממוקדת רק על לידים ב-'נשלחה הצעה'. כל ההצעות הממתינות במקום אחד — לזהות מה מתחיל להעלות אבק.",
  },

  // ===== ז. הבחנות =====
  distinction_template_vs_proposal: {
    title: "תבנית מול הצעה",
    description:
      "תבנית = אמרת *משהו* ללקוח (פתיחה, מידע). הצעה = הנחת *מחיר* על השולחן. השני הוא נקודת מפנה עסקית — נכנס ל'הצעות פתוחות' ולמסלול מעקב נפרד.",
  },
};

// Mapping מ-`task_type` של ה-backend ל-TermKey של ה-glossary. נוח
// לקבל ב-component שיש לו רק את ה-task_type הגולמי.
// undefined → ה-task_type לא במילון (אין הסבר; ה-component לא מציג ⓘ).
export function taskTypeToTermKey(taskType: string): TermKey | undefined {
  switch (taskType) {
    case "first_response":
      return "task_first_response";
    case "warm_followup":
      return "task_warm_followup";
    case "proposal_followup":
      return "task_proposal_followup";
    case "followup":
      return "task_followup";
    case "post_meeting_update":
      return "task_post_meeting_update";
    case "lecture_inquiry":
      return "task_lecture_inquiry";
    case "dormant_check":
      return "task_dormant_check";
    case "dormant_suggestion":
      return "task_dormant_suggestion";
    case "retry_call":
      return "task_retry_call";
    case "send_proposal":
      return "task_send_proposal";
    case "after_hours_reply":
      return "task_after_hours_reply";
    case "program_end":
      return "task_program_end";
    default:
      return undefined;
  }
}

// Mapping מסטטוס Lead ל-TermKey. מחזיר רק לסטטוסים *מבלבלים* — אין
// טעם להסביר "חדש" ל-נועה. PROPOSAL_SENT → ההבחנה מ-"נשלחה תבנית"
// (הנקודה הכי חשובה ב-funnel).
export function statusToTermKey(status: string): TermKey | undefined {
  switch (status) {
    case "IN_PROGRESS":
      return "status_in_progress";
    case "PROPOSAL_SENT":
      return "distinction_template_vs_proposal";
    case "BOOKING_PENDING":
      return "status_booking_pending";
    case "BOOKED":
      return "status_booked";
    case "WON":
    case "LOST":
    case "ARCHIVED":
      return "status_closed";
    default:
      return undefined;
  }
}

// Mapping מ-waiting_on ל-TermKey.
export function waitingOnToTermKey(waitingOn: string): TermKey | undefined {
  switch (waitingOn) {
    case "NOAH":
      return "waiting_noah";
    case "CLIENT":
      return "waiting_client";
    case "ASSISTANT":
    case "ASSISTANT_PENDING_NOAH":
      return "waiting_assistant";
    default:
      return undefined;
  }
}
