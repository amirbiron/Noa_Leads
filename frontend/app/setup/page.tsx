"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { isLoggedIn, setTokens } from "@/lib/auth";

// דף הגדרה ראשונית — מוצג רק כשאין משתמשים במערכת.
// אחרי deploy ראשון של ה-backend, המשתמשת נכנסת ל-/, ה-AuthGuard לא מוצא token,
// מפנה ל-/login, ו-login רואה ש-setup_needed=true ושולח לכאן.
export default function SetupPage() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // אם המערכת כבר הוגדרה (יש משתמש) — מפנים מיד ל-login.
  // אם backend לא זמין — נותנים למשתמשת לנסות בכל זאת.
  useEffect(() => {
    if (isLoggedIn()) {
      router.replace("/");
      return;
    }
    api
      .getSetupStatus()
      .then((s) => {
        if (!s.setup_needed) {
          router.replace("/login");
        } else {
          setChecking(false);
        }
      })
      .catch(() => setChecking(false));
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== passwordConfirm) {
      setError("הסיסמאות לא תואמות");
      return;
    }
    if (password.length < 8) {
      setError("סיסמה חייבת להיות לפחות 8 תווים");
      return;
    }
    setSubmitting(true);
    try {
      const tokens = await api.createInitialOwner({
        email: email.trim(),
        name: name.trim(),
        password,
      });
      setTokens(tokens.access_token, tokens.refresh_token);
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "שגיאה ביצירת המשתמש",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (checking) {
    return (
      <main className="min-h-screen flex items-center justify-center text-sm text-gray-400">
        טוען…
      </main>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 w-full max-w-sm p-6">
        <h1 className="text-xl font-semibold mb-1">הגדרה ראשונית</h1>
        <p className="text-sm text-gray-500 mb-5">
          נראה שזה ה-deploy הראשון. צרי את משתמש הבעלים של המערכת — תוכלי
          להתחבר איתו מיד.
        </p>

        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <div className="text-sm font-medium text-gray-700 mb-1.5">שם</div>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              placeholder="נועה"
              autoFocus
            />
          </label>

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
            <div className="text-sm font-medium text-gray-700 mb-1.5">
              סיסמה (לפחות 8 תווים)
            </div>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              dir="ltr"
              autoComplete="new-password"
            />
          </label>

          <label className="block">
            <div className="text-sm font-medium text-gray-700 mb-1.5">
              אישור סיסמה
            </div>
            <input
              type="password"
              required
              minLength={8}
              value={passwordConfirm}
              onChange={(e) => setPasswordConfirm(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              dir="ltr"
              autoComplete="new-password"
            />
          </label>

          {error && (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !email || !name || !password}
            className="w-full rounded-lg bg-gray-900 text-white py-3 font-medium disabled:opacity-50"
          >
            {submitting ? "יוצרת משתמש…" : "יצירה והתחברות"}
          </button>
        </form>
      </div>
    </main>
  );
}
