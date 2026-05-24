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

export type WaitingOn = "NOAH" | "CLIENT" | "ASSISTANT" | "SYSTEM" | "NONE";

export type ServiceCategory = "clinic" | "workshops" | "production" | "digital_course";

export type PriorityLevel = "normal" | "hot" | "vip";

export type PreferredContact = "phone" | "whatsapp" | "email";

export type StateColor = "red" | "orange" | "green" | "gray";

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
  last_inbound_at: string | null;
  last_outbound_at: string | null;
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
  personal_note?: string | null;
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
  followup_task_type: string | null;  // TaskType-string (אין צורך ב-enum כי שמות חדשים יכולים להופיע)
  auto_followup_days: number | null;
  sort_order: number;
  is_active: boolean;
}

export interface QuickActionChipCreate {
  label: string;
  target_status?: LeadStatus | null;
  waiting_on?: WaitingOn | null;
  followup_task_type?: string | null;
  auto_followup_days?: number | null;
  sort_order?: number;
  is_active?: boolean;
}

export interface QuickActionChipUpdate {
  label?: string;
  target_status?: LeadStatus | null;
  waiting_on?: WaitingOn | null;
  followup_task_type?: string | null;
  auto_followup_days?: number | null;
  sort_order?: number;
  is_active?: boolean;
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

export interface ServiceRate {
  subtype: string;
  label: string;
  category: string;
  default_price: string | null;
  default_hours: string | null;
  hourly_rate: string | null;
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

export interface HomeDashboard {
  today_actions: TodayActionItem[];
  new_leads: LeadCard[];
  pending: LeadCard[];
  weekly_insights: WeeklyInsights;
  daily_summary: DailySummary | null;
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
