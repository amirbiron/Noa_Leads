# מצב הפרויקט

מסמך חי שמסכם מה נבנה, מה פתוח, ואיך להמשיך.
**עדכון אחרון:** סוף שלב 14 (פאזה 2 — סנכרון הפוך Google→DB עם watch channels).

---

## איפה אנחנו

- **Branch פעיל:** `claude/focused-noether-h5H4d`
- **PR:** [#1](https://github.com/amirbiron/Noa_Leads/pull/1) — נסקר ע"י Cursor Bot ברצף, נדחפים תיקונים על אותו branch
- **Deploy ב-Render:** הוקם, עבר את חסמי הbuild הראשונים (Python 3.12.7, bcrypt 4.x). הflow הראשון (`/setup` → יצירת owner) עובד.

## פאזות

| פאזה | סטטוס | מה נכלל |
|---|---|---|
| **1 — ליבה (MVP)** | ✅ הושלמה | Auth, Leads CRUD + state machine, Intake, Templates, Tasks, Dashboard, Cron jobs, Telegram, Programs, Profitability, Frontend מלא |
| **2 — Google Calendar** | 🟡 בעבודה | שלבים 11-14 הושלמו (OAuth + booking page + approve/reject + סנכרון הפוך). חסר 15. |
| **3 — AI** | ⬜ עתיד | סיכומים, סינון מיילים, ניסוח הצעות |

### פאזה 2 — שלבים פנימיים

| שלב | סטטוס | הערות |
|---|---|---|
| **11 — OAuth + credentials** | ✅ | cookieless flow (JWT state), Fernet encryption, owner-only |
| **12 — דף קביעת תור ציבורי** | ✅ | `/book/{token}`, FreeBusy + DB busy, EXCLUDE constraint למניעת overlap |
| **13 — אישור/דחייה ע"י נועה** | ✅ | `PendingBookingCard` בדף הליד, `/bookings/{id}/approve\|reject`, אירוע נוצר ביומן עם `extendedProperties.private.bookingId` כעוגן לשלב 14. fail-safe ל-rollback אם Google נכשל. |
| **14 — סנכרון הפוך** | ✅ | Watch channels (auto על OAuth), `/webhooks/google-calendar`, syncToken + 410 resync, BackgroundTasks ל-ack מהיר, FOR UPDATE lock לסידור webhook מקבילים. ביטול ב-Google → ליד `IN_PROGRESS`+NOAH. שינוי זמן → עדכון שקט + activity log. cron `renew_calendar_watch` יומי. דורש `BACKEND_URL`. |
| **15 — Post-meeting update** | ⬜ הבא | התראה אחרי פגישה |

---

## מסמכי ייחוס חשובים

| מסמך | תפקיד |
|---|---|
| `CLAUDE.md` | כללי עבודה (7 כללים), הפניות לסקילים ול-references |
| `docs/product-spec.md` | האפיון של נועה — מקור האמת לדרישות |
| `docs/tech-spec.md` | החלטות ארכיטקטוניות + מבנה DB ראשוני |
| `docs/skills-review-plan.md` | סטטוס: כל ה-6 פריטים שזוהו ✅ הושלמו |
| `docs/google-calendar-setup.md` | מדריך לאדיר (המתאם) — GCP setup ל-פאזה 2 |
| `docs/references/google-calendar-blueprint.md` | blueprint חיצוני שאצלנו רק נשאב ממנו |

---

## מה צריך לעשות עכשיו (לא קוד)

### לפני שנועה נכנסת לראשונה
- [ ] **Render env vars לbackend:**
  - `CORS_ORIGINS` = `https://noa-leads-frontend.onrender.com`
  - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (מ-GCP Console)
  - `GOOGLE_REDIRECT_URI` = `https://noa-leads-backend.onrender.com/google/auth/callback`
  - `FRONTEND_URL` = `https://noa-leads-frontend.onrender.com`
  - `SECRETS_ENCRYPTION_KEY` = `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  - (אופציונלי) `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_CHAT_ID`
- [ ] **Render env vars לfrontend:**
  - `NEXT_PUBLIC_API_BASE_URL` = `https://noa-leads-backend.onrender.com`
- [ ] **GCP setup ל-Google Calendar** — `docs/google-calendar-setup.md` כצעד-צעד
- [ ] לוחצים `Deploy` → migrations רצות אוטומטית (`preDeployCommand: alembic upgrade head`)

### אחרי deploy ראשון
1. גולשים ל-`/login`
2. אם אין משתמשים → redirect אוטומטי ל-`/setup`
3. ממלאים שם/מייל/סיסמה → מחוברים אוטומטית
4. ב-`/settings` → "אינטגרציית Google Calendar" → התחברות

---

## החלטות ארכיטקטוניות חשובות

| תחום | החלטה | למה |
|---|---|---|
| Auth | JWT access (30 דק') + refresh (14 ימים), bcrypt ישיר (לא passlib) | passlib 1.7.4 לא תואם bcrypt 4.x |
| OAuth state | JWT חתום בURL state, **לא cookies** | `*.onrender.com` cross-site לפי PSL — cookies נחסמים |
| הצפנת tokens | Fernet (`SECRETS_ENCRYPTION_KEY`), fail-closed בפרודקשן | `generateValue: true` לא יוצר Fernet key תקין → user מגדיר ידני |
| Timezones | כל הדאטה ב-UTC ב-DB; UI ב-Asia/Jerusalem; חישובי שבוע/יום עם `datetime.combine` עצמאי | מניעת DST shift באביב/סתיו |
| מיגרציות | Alembic, אוטומטי דרך `preDeployCommand: alembic upgrade head` | אפס terminal לdeploy |
| Cron jobs | 5 jobs נפרדים (~$5/חודש ב-Render) | פתוחה אפשרות לconsolidation לscheduler אחד אם עלות מטרידה — תוכנית קיימת |
| Booking races | EXCLUDE USING gist + UNIQUE(lead_id) WHERE active | DB-level enforcement, לא הסתמכות על application logic |
| RTL | logical CSS bgmrt (`ms-`, `me-`, `border-s`), Tailwind v4 עם `@theme` | אומת בsweep — נקי לחלוטין |

---

## כללים מ-CLAUDE.md שיושמו לאורך הדרך (לא לשכוח בעתיד)

1. **await על כל async** — מבוצע
2. **race conditions אטומיים** — `UPDATE ... WHERE status = X` + rowcount בכל מעבר סטטוס; advisory lock ב-`/setup/initial-owner`; EXCLUDE constraint ב-bookings
3. **לא חושפים פנימי ב-API** — `AppException.to_dict()` בעברית; handler גלובלי ל-500; OAuth error allowlist
4. **NaN/Inf checks** — בולידציות מספריות (`Number.isFinite()`, `regex strict`)
5. **SQLAlchemy: `expire_on_commit=False` + `populate_existing=True`** — `get_lead_or_404`, `_get_lead`, `_get_task_or_404`, `get_program_or_404`
6. **Escape per-target** — `escape_telegram_html` בfork נפרד
7. **SSRF** — לא רלוונטי כיום (אין endpoints שמקבלים URLs מהמשתמש)

---

## באגבוט וסבבי תיקונים

PR #1 קיבל 12+ סבבי תיקונים מ-Cursor Bot, כולל באגי High severity:
- `_normalize_phone` ולידציה ישראלית
- ה-DST window bug (כפול: dashboard + daily_summary)
- ORM stale cache אחרי Core UPDATE
- bcrypt 4.x deploy crash
- OAuth cookies נחסמים ב-`*.onrender.com`
- DB double-booking races (2 highs)

הדפוס: Cursor מצביעה → אנחנו מתקנים את האמיתיים, מדלגים על over-engineering עם נימוק קצר. עבד טוב.

---

## פיצ'רים שדחינו / נשארו ל-pre-launch

- Cron consolidation (האם להריץ scheduler אחד במקום 5 services)
- a11y רחב (aria attributes מלאים; כרגע minimal)
- Multi-tenant (כיום singleton)
- RBAC מורחב (כיום owner-only על מספר routes, השאר כל user)
- Refresh token rotation עם DB revocation
- Settings UI מלא (chips customization, followup rules, service rates editing)
- Programs UI ב-/active list (קיים בback, חסר עמוד frontend)

---

## הפעלה לוקאלית (לdebug)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # למלא ערכים
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
cp .env.example .env.local  # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev  # port 3000
```

DB מקומי: כל Postgres 14+ עם הextension `btree_gist` (מותקן by default ברוב ההפצות).
