"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { isLoggedIn, setTokens } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isLoggedIn()) {
      router.replace("/");
      return;
    }
    // בדיקה אם המערכת דורשת setup ראשוני (אין משתמשים) — מפנים ל-/setup.
    // אם backend לא זמין, פשוט נשאר ב-login (המשתמשת תקבל שגיאה ידידותית בשליחה).
    api
      .getSetupStatus()
      .then((s) => {
        if (s.setup_needed) router.replace("/setup");
      })
      .catch(() => {});
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const tokens = await api.login(email, password);
      setTokens(tokens.access_token, tokens.refresh_token);
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "אימות נכשל. בדקי את הפרטים.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 w-full max-w-sm p-6">
        <h1 className="text-xl font-semibold mb-1">כניסה למערכת</h1>
        <p className="text-sm text-gray-500 mb-5">ניהול לידים</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block">
            <div className="text-sm font-medium text-gray-700 mb-1.5">מייל</div>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              dir="ltr"
              autoComplete="email"
            />
          </label>

          <label className="block">
            <div className="text-sm font-medium text-gray-700 mb-1.5">סיסמה</div>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              dir="ltr"
              autoComplete="current-password"
            />
          </label>

          {error && (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !email || !password}
            className="w-full rounded-lg bg-gray-900 text-white py-3 font-medium disabled:opacity-50"
          >
            {submitting ? "מתחברת…" : "כניסה"}
          </button>
        </form>
      </div>
    </main>
  );
}
