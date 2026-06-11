// טיפוסים שמשקפים את ה-Pydantic schemas של ה-backend.
// אם משנים שדה ב-backend, חייבים לעדכן גם כאן.

export type LeadStatus =
  | "NEW"
  | "IN_PROGRESS"
  | "PROPOSAL_SENT"
  | "BOOKING_PENDING"
  | "BOOKED"
  | "WON"
  | "LOST"
  | "ARCHIVED";

export type WaitingOn =
  | "NOAH"
  | "CLIENT"
  | "ASSISTANT"
  | "ASSISTANT_PENDING_NOAH"  // Spec v2.1 §5.11 — F-09
  | "SYSTEM"
  | "NONE";

export type ServiceCategory = "clinic" | "workshops" | "production" | "digital_course";

export type PriorityLevel = "normal" | "hot" | "vip";

export type PreferredContact = "phone" | "whatsapp" | "email";

export type StateColor = "red" | "orange" | "green" | "gray";

// משקף את TaskType ב-backend/app/constants.py — Spec v2.1 §17.1 + §16.4.
// בהוספת ערך חדש לbackend, יש לעדכן גם כאן וגם ב-TASK_TYPE_LABELS.
export type TaskType =
  | "first_response"
  | "warm_followup"
  | "proposal_followup"
  | "dormant_check"
  | "dormant_suggestion"
  | "lecture_inquiry"
  | "followup"
  | "retry_call"
  | "send_proposal"
  | "post_meeting_update"
  | "program_end"
  | "after_hours_reply";

export type SourceChannel =
  | "form"
  | "email"
  | "manual"
  | "referral"
  | "facebook"
  | "instagram"
  | "whatsapp"
  | "other";

export type ClosureReason =
  | "no_response"
  | "not_relevant"
  | "price"
  | "timing"
  | "went_with_other"
  | "duplicate"
  | "other";

// ===== Auth =====

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// ===== Lead =====

export interface LeadListItem {
  id: string;
  full_name: string;
  organization_name: string | null;
  service_category: string | null;  // F-04: אופציונלי
  service_subtype: string | null;
  status: string;
  waiting_on: string;
  priority_level: string;
  preferred_contact: string;
  needs_attention: boolean;
  // לחישוב צבע real-time ב-list (Spec §12.9 — overdue → orange).
  next_action_due_at: string | null;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  last_activity_at: string | null;  // מקור ל-badge "גיל" (§12.1) — מכל מקור
  closed_at: string | null;  // לתצוגת "נסגר ב-" בארכיון
  created_at: string;  // fallback ל-badge "גיל" אם אין activities
  updated_at: string;
}

export interface Lead {
  id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  organization_name: string | null;
  service_category: string | null;  // F-04: אופציונלי
  service_subtype: string | null;
  status: string;
  waiting_on: string;
  priority_level: string;
  preferred_contact: string;
  owner_id: string | null;
  next_action_type: string | null;
  next_action_due_at: string | null;
  needs_attention: boolean;
  source_channel: string;
  source_detail: string | null;
  utm_source: string | null;
  utm_campaign: string | null;
  utm_content: string | null;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  last_activity_type: string | null;
  last_activity_at: string | null;  // מקור ל-badge "גיל" (§12.1) — מכל מקור
  reply_boost_until: string | null;
  proposal_sent_at: string | null;
  dormant_flag: boolean;
  is_duplicate_suspected: boolean;
  is_returning_customer: boolean;
  closure_reason: string | null;
  closed_at: string | null;
  closed_value: string | null;
  actual_hours: string | null;
  personal_note: string | null;
  lead_message: string | null;  // תוכן הפנייה
  booking_token: string;
  created_at: string;
  updated_at: string;
}

// ===== Booking page (ציבורי) =====

export interface BookingPageInfo {
  lead_name: string;
  service_category: string | null;  // F-04: אופציונלי
  service_subtype: string | null;
  default_duration_minutes: number;
  timezone: string;
  has_active_booking: boolean;
  active_booking_at: string | null;
  active_booking_end: string | null;
  active_booking_status: string | null;
}

export interface TimeSlot {
  start: string;
  end: string;
}

export interface DayAvailability {
  date: string;
  slots: TimeSlot[];
}

export interface AvailabilityResponse {
  days: DayAvailability[];
  includes_google_busy: boolean;
}

export interface CreateBookingResponse {
  booking_id: string;
  status: string;
  slot_start: string;
  slot_end: string;
}

// ===== Booking admin (אישור/דחייה ע"י נועה/עוזרת) =====

export type BookingStatus =
  | "pending_approval"
  | "approved"
  | "rejected"
  | "canceled";

export interface BookingRead {
  id: string;
  lead_id: string;
  requested_slot_start: string;
  requested_slot_end: string;
  status: BookingStatus;
  google_calendar_event_id: string | null;
  created_at: string;
  approved_at: string | null;
  rejected_at: string | null;
}

export interface PendingBookingItem {
  id: string;
  lead_id: string;
  lead_name: string;
  lead_phone: string | null;
  service_category: string | null;  // F-04: אופציונלי
  service_subtype: string | null;
  requested_slot_start: string;
  requested_slot_end: string;
  created_at: string;
}

export interface PendingBookingsResponse {
  items: PendingBookingItem[];
}

export interface LeadCreate {
  full_name: string;
  phone?: string | null;
  email?: string | null;
  organization_name?: string | null;
  service_category?: ServiceCategory | null;  // אופציונלי לפי Spec §7.1 (F-04)
  service_subtype?: string | null;
  source_channel: SourceChannel;
  source_detail?: string | null;
  preferred_contact?: PreferredContact;
  priority_level?: PriorityLevel;
  is_returning_customer?: boolean;  // §7.2 — default false ב-backend
  personal_note?: string | null;
  lead_message: string;  // תוכן הפנייה — חובה בטופס הידני
}

// ===== Activity =====

export interface Activity {
  id: string;
  type: string;
  content: string | null;
  activity_metadata: Record<string, unknown> | null;
  performed_by: string | null;
  created_at: string;
}

// מייל נכנס שקושר לליד (Spec §20.10). מקור: GET /leads/{id}/emails.
// שדות פנימיים (gmail_message_id, processing_status, classification_retry_count,
// cleaning_metadata, raw_html) לא נחשפים מה-backend — לא ב-MVP.
export interface EmailMessage {
  id: string;
  from_address: string | null;
  to_address: string | null;
  subject: string | null;
  cleaned_text: string | null;
  received_at: string | null;
  created_at: string;
}

// ===== Dashboard =====

export interface LeadCard {
  id: string;
  full_name: string;
  organization_name: string | null;
  service_category: string | null;  // F-04: אופציונלי
  service_subtype: string | null;
  status: string;
  waiting_on: string;
  priority_level: string;
  preferred_contact: string;
  state_color: StateColor;
  needs_attention: boolean;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  next_action_due_at: string | null;
  has_recent_reply: boolean;
  last_activity_type: string | null;
  last_activity_at: string | null;  // מקור ל-badge "גיל" (§12.1) — מכל מקור
  created_at: string;  // fallback ל-badge "גיל" אם אין activities
}

export interface ProposalCard extends LeadCard {
  proposal_sent_at: string | null;
  days_since_proposal: number | null;
}

// QuickActionChip לפי Spec v2.1 §5.7 + §16.4 — declarative.
// 4 השדות הסמנטיים nullable: צ'יפים שנועה הוסיפה ידנית בלי למלא הכל.
// ה-UI מציג רק chips ש-target_status שלהם לא null.
export interface QuickActionChip {
  id: string;
  label: string;
  target_status: LeadStatus | null;
  waiting_on: WaitingOn | null;
  followup_task_type: TaskType | null;
  auto_followup_days: number | null;
  sort_order: number;
  is_active: boolean;
}

export interface QuickActionChipCreate {
  label: string;
  target_status?: LeadStatus | null;
  waiting_on?: WaitingOn | null;
  followup_task_type?: TaskType | null;
  auto_followup_days?: number | null;
  sort_order?: number;
  is_active?: boolean;
}

export interface QuickActionChipUpdate {
  label?: string;
  target_status?: LeadStatus | null;
  waiting_on?: WaitingOn | null;
  followup_task_type?: TaskType | null;
  auto_followup_days?: number | null;
  sort_order?: number;
  is_active?: boolean;
}

// תוצאת POST /leads/{id}/apply-chip/{chip_id} — Spec v2.1 §16.4 +
// "אין סיגה אחורה" (ראה ApplyChipResponse ב-backend).
// status_preserved=True כש-chip ניסה להציב סטטוס מוקדם יותר בזרימה
// (PROPOSAL_SENT/BOOKING_PENDING/BOOKED → IN_PROGRESS). ה-frontend
// מציג toast רך ב-booking_pending/booked, ושקט ב-proposal_sent.
export type ChipPreservedReason =
  | "proposal_sent"
  | "booking_pending"
  | "booked";

export interface ApplyChipResponse {
  lead: Lead;
  status_preserved: boolean;
  preserved_reason: ChipPreservedReason | null;
}

export interface StuckTaskItem {
  task_id: string;
  task_type: string;
  due_at: string;
  days_stuck: number;
  lead_id: string;
  lead_name: string;
  lead_status: string;
  service_category: string | null;  // F-04: אופציונלי
  waiting_on: string;
}

export interface TodayActionItem {
  task_id: string;
  lead_id: string;
  lead_name: string;
  lead_organization: string | null;
  task_type: string;
  due_at: string;
  is_overdue: boolean;
  state_color: StateColor;
  priority_level: string;
  preferred_contact: string;
  service_category: string | null;  // F-04: אופציונלי
  // F-20: לכפתור פעולה ישיר ב-/today (tel: / wa.me / mailto:).
  lead_phone: string | null;
  lead_email: string | null;
  last_outbound_at: string | null;
  // ל-badge "גיל" (§12.1) — מקור: last_activity_at→created_at של הליד.
  last_activity_at: string | null;
  created_at: string;
  // §19 D.1 — לפריט dormant_suggestion בלבד: ההמלצה + הנימוק.
  ai_action: string | null;
  ai_reasoning: string | null;
}

// §19 D.1 — המלצת פעולה AI לליד רדום (מוצגת בכרטיס הליד).
export interface DormantSuggestion {
  action: "gentle_followup" | "archive" | "call" | "no_action";
  reasoning: string;
  generated_at: string | null;
  model_used: string | null;
}

export interface ProfitableServiceInsight {
  service_category: string | null;  // F-04: אופציונלי
  hourly_rate: string; // Decimal as string
  total_revenue: string;
  total_hours: string;
  deals_count: number;
}

export interface WeeklyInsights {
  week_start: string;
  week_end: string;
  new_leads_count: number;
  responded_in_time_count: number;
  stuck_count: number;
  total_open: number;
  most_profitable_service: ProfitableServiceInsight | null;
}

// תעריף שירות לפי Spec v2.1 §5.10. נטען מ-DB דרך GET /settings/service-rates.
// total_hours ו-hourly_rate מחושבים בbackend לפי duration*sessions/60.
export interface ServiceRate {
  id: string;
  service_category: string;
  service_subtype: string;
  label: string;
  default_price: string | null;
  default_duration_minutes: number | null;
  default_sessions_count: number | null;
  total_hours: string | null;
  hourly_rate: string | null;
  notes: string | null;
  is_active: boolean;
}

export interface ServiceRateUpdate {
  default_price?: number | null;
  default_duration_minutes?: number | null;
  default_sessions_count?: number | null;
  notes?: string | null;
  is_active?: boolean;
}

// F-07: ה-row האחרון מ-daily_summaries — מוצג כbubble בדשבורד.
// null אם cron עדיין לא רץ או הטבלה ריקה.
export interface DailySummary {
  summary_date: string; // YYYY-MM-DD
  new_leads_today: number;
  tasks_done_today: number;
  tasks_for_tomorrow: number;
  urgent_open: number;
  generated_at: string;
}

// C.1/C.2 §6.8: סיכומי AI נרטיביים. ה-output הוא JSON מבני עם סקציות
// קבועות + רשימת סקציות מושמטות (omitted_sections). לפי האפיון, סקציה
// שהושמטה לא מוצגת ב-UI.

export interface AiSummaryOutputDaily {
  bottom_line: string;
  today: string;
  highlights: string[];
  needs_attention: string[];
  tomorrow: string | null;
  omitted_sections: ("highlights" | "needs_attention" | "tomorrow")[];
}

export interface AiSummaryOutputWeekly {
  bottom_line: string;
  week_overview: string;
  trends_vs_last_week: string | null;
  what_worked: string[];
  what_stuck: string[];
  next_week_focus: string | null;
  omitted_sections: (
    | "trends_vs_last_week"
    | "what_worked"
    | "what_stuck"
    | "next_week_focus"
  )[];
}

export interface AiSummary {
  id: string;
  type: "daily" | "weekly";
  date_range_start: string; // YYYY-MM-DD
  date_range_end: string; // YYYY-MM-DD
  output: AiSummaryOutputDaily | AiSummaryOutputWeekly;
  inaccurate_count: number;
  created_at: string;
}

export interface HomeDashboard {
  today_actions: TodayActionItem[];
  new_leads: LeadCard[];
  pending: LeadCard[];
  weekly_insights: WeeklyInsights;
  daily_summary: DailySummary | null;
  // C.1/C.2 §6.8 — null אם ה-cron של אותו טווח עוד לא רץ או נכשל ב-AI.
  ai_daily_summary: AiSummary | null;
  ai_weekly_summary: AiSummary | null;
}

// תוצאת GET /dashboard/poll — delta מאז ה-poll הקודם.
// server_time = anchor ל-poll הבא (מבדיל clock skew של ה-client).
export interface DashboardPollResponse {
  new_leads: LeadCard[];
  leads_with_inbound_replies: LeadCard[];
  server_time: string;
}

// ===== Tasks =====

export interface Task {
  id: string;
  lead_id: string;
  type: string;
  assigned_to: string | null;
  due_at: string;
  status: string;
  snoozed_until: string | null;
  origin_rule: string | null;
  created_at: string;
  completed_at: string | null;
}

// ===== Programs =====

export type ProgramType =
  | "voice_rehab_8"
  | "public_speaking_8"
  | "stage_arts_4"
  | "production_3months"
  | "digital_course_12";

export interface Program {
  id: string;
  lead_id: string;
  program_type: string;
  total_sessions: number;
  completed_sessions: number;
  total_price: string | null; // Decimal as string
  actual_hours: string;
  started_at: string;
  estimated_end_at: string | null;
  status: string; // active | completed | canceled
}

export interface ProgramWithLead extends Program {
  lead_name: string;
  lead_organization: string | null;
}

export interface ProgramCreate {
  lead_id: string;
  program_type: ProgramType;
  total_sessions: number;
  total_price?: number | null;
  estimated_end_at?: string | null;
}

export interface ProgramUpdate {
  completed_sessions?: number;
  actual_hours?: number;
  total_price?: number;
  estimated_end_at?: string | null;
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  created_at: string;
}

export interface TemplateCreate {
  name: string;
  channel: "whatsapp" | "email";
  target_audience?: "private" | "organization" | "dormant" | null;
  body: string;
  variables?: string[] | null;
  is_active?: boolean;
}

export interface TemplateUpdate {
  name?: string;
  channel?: "whatsapp" | "email";
  target_audience?: "private" | "organization" | "dormant" | null;
  body?: string;
  variables?: string[] | null;
  is_active?: boolean;
}

export type SnoozePreset =
  | "today_afternoon"
  | "tomorrow_morning"
  | "sunday_morning"
  | "after_holiday"
  | "custom";

// ===== Templates =====

export interface Template {
  id: string;
  name: string;
  channel: string;
  target_audience: string | null;
  body: string;
  variables: string[] | null;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface TemplateRenderResponse {
  template_id: string;
  lead_id: string;
  rendered_body: string;
  channel: string;
  missing_variables: string[];
}

// ===== Common =====

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ===== Followup rules (§17.1) =====
// rule_key מתאים ל-TaskType value (first_response/lecture_inquiry/
// warm_followup/proposal_followup/dormant_check). הוספה/מחיקה אסורה
// דרך ה-API — רק עריכת ערכים.

export type FollowupTimeUnit = "hours" | "days";

export interface FollowupRule {
  rule_key: string;
  interval_value: number;
  interval_unit: FollowupTimeUnit;
  repeat_count: number;
  repeat_interval_value: number;
  repeat_interval_unit: FollowupTimeUnit;
}

export interface FollowupRuleUpdate {
  interval_value?: number;
  interval_unit?: FollowupTimeUnit;
  repeat_count?: number;
  repeat_interval_value?: number;
  repeat_interval_unit?: FollowupTimeUnit;
}
