// API client אחיד מול ה-backend. מטפל ב-auth headers, שגיאות בעברית,
// ו-refresh אוטומטי כשה-access pokens פג.

import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./auth";
import type {
  Activity,
  AvailabilityResponse,
  BookingPageInfo,
  BookingRead,
  CreateBookingResponse,
  DashboardPollResponse,
  EmailMessage,
  PendingBookingsResponse,
  HomeDashboard,
  QuickActionChip,
  QuickActionChipCreate,
  QuickActionChipUpdate,
  Lead,
  LeadCard,
  LeadCreate,
  LeadListItem,
  PaginatedResponse,
  ProposalCard,
  SnoozePreset,
  Task,
  Program,
  ProgramCreate,
  ProgramUpdate,
  ProgramWithLead,
  ServiceRate,
  ServiceRateUpdate,
  StuckTaskItem,
  Template,
  TemplateCreate,
  TemplateRenderResponse,
  TemplateUpdate,
  TodayActionItem,
  TokenResponse,
  User,
  WeeklyInsights,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

interface FetcherOpts extends Omit<RequestInit, "body"> {
  body?: unknown;
  // האם לנסות refresh אם מקבלים 401 (מנוטרל בקריאה ל-/auth/refresh כדי
  // למנוע לולאה אינסופית)
  retryAuth?: boolean;
}

async function fetcher<T>(path: string, opts: FetcherOpts = {}): Promise<T> {
  const { body, retryAuth = true, ...rest } = opts;
  const headers = new Headers(rest.headers);
  headers.set("Accept", "application/json");
  if (body !== undefined) headers.set("Content-Type", "application/json");

  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    // אין credentials כי אנחנו ב-cross-origin (subdomains שונים ב-Render).
    // auth ב-Bearer header, OAuth state ב-URL (לא cookies) — ראה
    // app/services/google_calendar.py:encode_oauth_state.
  });

  // 401 → ננסה refresh פעם אחת ואז retry
  if (res.status === 401 && retryAuth) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      return fetcher<T>(path, { ...opts, retryAuth: false });
    }
    clearTokens();
    // ה-refresh נכשל — מנווטים ל-login. בלי זה הדף נשאר במצב שבור
    // (כל קריאה הבאה תיכשל גם היא ב-401).
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }

  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const message =
      (data && (data.message || data.error)) || "אירעה שגיאה. נסה שוב.";
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

async function tryRefreshToken(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const data = await fetcher<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: { refresh_token: refresh },
      retryAuth: false,
    });
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

// ===== API surface =====

export const api = {
  // ----- Setup (deploy ראשון, ללא auth) -----
  getSetupStatus: () =>
    fetcher<{ setup_needed: boolean; users_count: number }>("/setup/status", {
      retryAuth: false,
    }),

  createInitialOwner: (payload: {
    email: string;
    name: string;
    password: string;
  }) =>
    fetcher<TokenResponse>("/setup/initial-owner", {
      method: "POST",
      body: payload,
      retryAuth: false,
    }),

  // ----- Auth -----
  login: (email: string, password: string) =>
    fetcher<TokenResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
      retryAuth: false,
    }),

  logout: () => fetcher<void>("/auth/logout", { method: "POST" }),

  // ----- Dashboard -----
  getHome: () => fetcher<HomeDashboard>("/dashboard/home"),

  getToday: () =>
    fetcher<{ items: TodayActionItem[] }>("/dashboard/today"),

  getPending: () =>
    fetcher<{ items: LeadCard[] }>("/dashboard/pending"),

  getProposals: () =>
    fetcher<{ items: ProposalCard[] }>("/dashboard/proposals"),

  getWeekly: () => fetcher<WeeklyInsights>("/dashboard/weekly"),

  // polling delta — לidim חדשים + תגובות לקוחות מאז `since`.
  // ה-hook useDashboardPoll קורא כל 60s (משתמש ב-server_time כanchor).
  pollDashboard: (since: string) =>
    fetcher<DashboardPollResponse>(
      `/dashboard/poll?since=${encodeURIComponent(since)}`,
    ),

  // ----- Leads -----
  listLeads: (params: Record<string, string | number | boolean> = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => qs.set(k, String(v)));
    const suffix = qs.toString() ? `?${qs}` : "";
    return fetcher<PaginatedResponse<LeadListItem>>(`/leads${suffix}`);
  },

  getLead: (id: string) => fetcher<Lead>(`/leads/${id}`),

  createLead: (payload: LeadCreate) =>
    fetcher<Lead>("/leads", { method: "POST", body: payload }),

  updateLead: (id: string, payload: Partial<Lead>) =>
    fetcher<Lead>(`/leads/${id}`, { method: "PATCH", body: payload }),

  getTimeline: (id: string) =>
    fetcher<Activity[]>(`/leads/${id}/timeline`),

  // מיילים נכנסים שקושרו לליד (Spec §20.10). מסודר מהחדש לישן.
  getLeadEmails: (id: string) =>
    fetcher<EmailMessage[]>(`/leads/${id}/emails`),

  performAction: (
    leadId: string,
    actionType: string,
    payload: { content?: string; metadata?: Record<string, unknown> } = {},
  ) =>
    fetcher<Lead>(`/leads/${leadId}/actions/${actionType}`, {
      method: "POST",
      body: payload,
    }),

  closeLead: (
    leadId: string,
    payload: {
      target_status: string;
      closure_reason?: string;
      note?: string;
      closed_value?: number | null;
      actual_hours?: number | null;
    },
  ) =>
    fetcher<Lead>(`/leads/${leadId}/close`, { method: "POST", body: payload }),

  reopenLead: (leadId: string) =>
    fetcher<Lead>(`/leads/${leadId}/reopen`, { method: "POST" }),

  transferLead: (
    leadId: string,
    payload: { target_user_id: string; handoff_note?: string },
  ) =>
    fetcher<Lead>(`/leads/${leadId}/transfer`, {
      method: "POST",
      body: payload,
    }),

  // ----- Users -----
  getMe: () => fetcher<User>("/users/me"),
  listUsers: () => fetcher<User[]>("/users"),

  // ----- Tasks -----
  listOpenTasks: () => fetcher<Task[]>("/tasks/open"),

  listStuckTasks: () => fetcher<StuckTaskItem[]>("/tasks/stuck"),

  // ----- Quick action chips (editable, מהגדרות) -----
  listChips: (activeOnly = false) =>
    fetcher<QuickActionChip[]>(`/chips?active_only=${activeOnly}`),

  createChip: (payload: QuickActionChipCreate) =>
    fetcher<QuickActionChip>("/chips", { method: "POST", body: payload }),

  updateChip: (id: string, payload: QuickActionChipUpdate) =>
    fetcher<QuickActionChip>(`/chips/${id}`, {
      method: "PATCH",
      body: payload,
    }),

  deleteChip: (id: string) =>
    fetcher<void>(`/chips/${id}`, { method: "DELETE" }),

  // הפעלת צ'יפ על ליד — Spec v2.1 §16.4. הendpoint מבצע אטומית את 4
  // הפעולות: status / waiting_on / יצירת task / activity. מחזיר את הליד
  // המעודכן. 400 על ליד סגור או צ'יפ לא מאוכלס.
  applyChip: (leadId: string, chipId: string) =>
    fetcher<Lead>(`/leads/${leadId}/apply-chip/${chipId}`, {
      method: "POST",
    }),

  snoozeTask: (taskId: string, preset: SnoozePreset, customUntil?: string) =>
    fetcher<Task>(`/tasks/${taskId}/snooze`, {
      method: "POST",
      body: { preset, custom_until: customUntil ?? null },
    }),

  completeTask: (taskId: string) =>
    fetcher<Task>(`/tasks/${taskId}/complete`, { method: "POST" }),

  // ----- Templates -----
  listTemplates: (activeOnly = false) =>
    fetcher<Template[]>(`/templates?active_only=${activeOnly}`),

  getTemplate: (id: string) => fetcher<Template>(`/templates/${id}`),

  createTemplate: (payload: TemplateCreate) =>
    fetcher<Template>("/templates", { method: "POST", body: payload }),

  updateTemplate: (id: string, payload: TemplateUpdate) =>
    fetcher<Template>(`/templates/${id}`, { method: "PATCH", body: payload }),

  deleteTemplate: (id: string) =>
    fetcher<void>(`/templates/${id}`, { method: "DELETE" }),

  renderTemplate: (templateId: string, leadId: string) =>
    fetcher<TemplateRenderResponse>(
      `/templates/${templateId}/render?lead_id=${leadId}`,
      { method: "POST" },
    ),

  // בחירה אוטומטית של תבנית קנונית לכפתור הראשי בכרטיס ליד.
  // role=opening (NEW) / proposal (IN_PROGRESS) / proposal_followup (PROPOSAL_SENT).
  // ApiError(404) = הקנונית בוטלה/נמחקה → ה-caller פותח TemplatePickerSheet
  // הרגיל (בחירה ידנית).
  getTemplateAuto: (
    leadId: string,
    role: "opening" | "proposal" | "proposal_followup",
  ) =>
    fetcher<Template>(
      `/templates/auto?lead_id=${leadId}&role=${role}`,
    ),

  // ----- Programs -----
  listActivePrograms: () =>
    fetcher<ProgramWithLead[]>("/programs/active"),

  listProgramsForLead: (leadId: string) =>
    fetcher<Program[]>(`/programs/lead/${leadId}`),

  createProgram: (payload: ProgramCreate) =>
    fetcher<Program>("/programs", { method: "POST", body: payload }),

  updateProgram: (id: string, payload: ProgramUpdate) =>
    fetcher<Program>(`/programs/${id}`, { method: "PATCH", body: payload }),

  cancelProgram: (id: string) =>
    fetcher<Program>(`/programs/${id}/cancel`, { method: "POST" }),

  // ----- Settings -----
  listServiceRates: () =>
    fetcher<ServiceRate[]>("/settings/service-rates"),

  // owner-only. PATCH partial — שלחי רק שדות שמשתנים.
  updateServiceRate: (subtype: string, payload: ServiceRateUpdate) =>
    fetcher<ServiceRate>(`/settings/service-rates/${subtype}`, {
      method: "PATCH",
      body: payload,
    }),

  // ----- Google Calendar -----
  getGoogleStatus: () =>
    fetcher<{
      connected: boolean;
      google_account_email?: string | null;
      calendar_id?: string | null;
      timezone?: string | null;
      connected_at?: string | null;
      auth_invalid: boolean;
    }>("/google/status"),

  startGoogleAuth: () =>
    fetcher<{ auth_url: string }>("/google/auth/start"),

  disconnectGoogle: () =>
    fetcher<void>("/google/disconnect", { method: "POST" }),

  // ----- Gmail (Phase 3 Stage 17) -----
  getGmailStatus: () =>
    fetcher<{
      connected: boolean;
      google_account_email?: string | null;
      history_id?: string | null;
      watch_expiration?: string | null;
      filter_label_name?: string | null;
      connected_at?: string | null;
      auth_invalid: boolean;
    }>("/google-gmail/status"),

  startGmailAuth: () =>
    fetcher<{ auth_url: string }>("/google-gmail/auth/start"),

  disconnectGmail: () =>
    fetcher<void>("/google-gmail/disconnect", { method: "POST" }),

  // ----- Booking page (ציבורי, ללא auth) -----
  getBookingPageInfo: (token: string) =>
    fetcher<BookingPageInfo>(`/booking/${token}`, { retryAuth: false }),

  getBookingAvailability: (
    token: string,
    dateFrom: string,
    dateTo: string,
  ) =>
    fetcher<AvailabilityResponse>(
      `/booking/${token}/availability?date_from=${dateFrom}&date_to=${dateTo}`,
      { retryAuth: false },
    ),

  createBooking: (
    token: string,
    payload: { slot_start: string; slot_end: string; notes?: string },
  ) =>
    fetcher<CreateBookingResponse>(`/booking/${token}`, {
      method: "POST",
      body: payload,
      retryAuth: false,
    }),

  // ----- Booking admin (אישור/דחייה ע"י נועה/עוזרת) -----
  listPendingBookings: () =>
    fetcher<PendingBookingsResponse>(`/bookings/pending`),

  getActiveBookingForLead: (leadId: string) =>
    fetcher<BookingRead | null>(`/bookings/lead/${leadId}/active`),

  approveBooking: (id: string) =>
    fetcher<BookingRead>(`/bookings/${id}/approve`, { method: "POST" }),

  rejectBooking: (id: string) =>
    fetcher<BookingRead>(`/bookings/${id}/reject`, { method: "POST" }),
};
