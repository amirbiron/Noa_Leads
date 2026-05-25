// ניהול JWT ב-localStorage. שני tokens — access ו-refresh.
// בעתיד נשקול cookies httpOnly לחיזוק האבטחה.

const ACCESS_KEY = "noa_access_token";
const REFRESH_KEY = "noa_refresh_token";

// event ייעודי שmustard ב-setTokens/clearTokens. מאזינים (כמו
// useDashboardPoll) מקבלים signal לreact ל-state change בלי
// page reload. `storage` event לא יורה באותו tab — הevent הזה
// משלים את החסר.
export const AUTH_CHANGED_EVENT = "noa:auth-changed";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
}

export function isLoggedIn(): boolean {
  return getAccessToken() !== null;
}
