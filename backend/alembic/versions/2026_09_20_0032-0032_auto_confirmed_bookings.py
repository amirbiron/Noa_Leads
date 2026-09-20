"""פגישות מאושרות אוטומטית: כמה פגישות לליד, טלפון והערה, ובחירת יומנים.

ארבעה שינויים, כולם נובעים מאותו שינוי מוצר — הליד קובע פגישה בעצמו
והיא מאושרת מיד, בלי שלב אישור של נועה:

1. **ביטול `idx_bookings_active_lead`.** האינדקס הזה (מיגרציה 0006) הוא
   UNIQUE על `lead_id` עבור bookings פעילים, כלומר "פגישה פעילה אחת לליד".
   זו בדיוק המגבלה שהתבקשנו להסיר: אותו ליד צריך להיות מסוגל לקבוע פגישה
   נוספת מאותו קישור. **`ck_bookings_no_overlap` נשאר** — הוא מונע שתי
   פגישות חופפות *בכלל* (גם בין לידים שונים), וזה עדיין נכון: נועה לא
   יכולה להיות בשתי פגישות באותו זמן.

   שים לב: `_expire_stale_bookings` ב-`app/services/booking.py` הסתמך
   בהערותיו על האינדקס הזה ("הindex מבטיח שאחרי שלב 2 אין תור פעיל"),
   ולכן ההנחה הזו הוחלפה שם בבדיקת `NOT EXISTS` מפורשת.

2. **`bookings.contact_phone`** — הטלפון שהליד מזין בדף קביעת הפגישה,
   כדי שנועה תוכל ליצור איתו קשר בביטול או עדכון. הוא מופיע בתיאור
   האירוע ביומן. nullable כי לשורות קיימות אין אותו; ברמת ה-API של הדף
   הציבורי הוא **חובה**.

   VARCHAR(32) ולא (20) כמו `leads.phone`: `app/utils/phone.py` מעביר
   מספר שאינו ישראלי as-is אחרי ניקוי, ומספר בינלאומי ארוך חורג מ-20.
   ב-`leads.phone` זו תקלה נדירה בטופס פנימי; כאן זה שדה חובה בדף ציבורי,
   ושגיאת DB הייתה מוצגת ללקוח כ-500.

3. **`bookings.notes`** — ההערה שהליד כותב. עד היום היא נשמרה רק ברשומת
   ה-activity ולא הגיעה ליומן (באג); מעכשיו היא נשמרת על הפגישה ונכנסת
   לתיאור האירוע.

4. **`google_calendar_credentials.busy_calendar_ids`** — רשימת מזהי
   היומנים הנוספים שנחשבים "תפוס" בחישוב הזמינות. העמודה `calendar_id`
   הקיימת (שנכתבה תמיד כ-"primary" ומעולם לא נקראה) הופכת למשמעותית:
   היא **יומן היעד** — היחיד שאליו נכתבים אירועים ושעליו רשום ה-watch.

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===== 1. הסרת המגבלה "פגישה פעילה אחת לליד" =====
    # IF EXISTS: ההרצה בטוחה גם אם האינדקס כבר הוסר ידנית בסביבה כלשהי.
    op.execute("DROP INDEX IF EXISTS idx_bookings_active_lead")

    # ===== 2+3. פרטי הקשר וההערה של הליד, על הפגישה =====
    op.add_column(
        "bookings",
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
    )
    op.add_column("bookings", sa.Column("notes", sa.Text(), nullable=True))

    # ===== 4. יומנים נוספים שנחשבים "תפוס" =====
    # server_default='[]' נדרש כדי שהשורה הקיימת (singleton) תקבל ערך
    # תקין ולא NULL — הקוד קורא את העמודה בכל חישוב זמינות.
    op.add_column(
        "google_calendar_credentials",
        sa.Column(
            "busy_calendar_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("google_calendar_credentials", "busy_calendar_ids")
    op.drop_column("bookings", "notes")
    op.drop_column("bookings", "contact_phone")

    # שחזור האינדקס. ייתכן שבינתיים נוצרו כמה פגישות פעילות לאותו ליד,
    # ואז ה-CREATE UNIQUE INDEX ייכשל. מבטלים קודם את העודפות בשיטה
    # דטרמיניסטית — הישנה ביותר נשארת — בדיוק כמו ב-migration 0006.
    op.execute(
        """
        UPDATE bookings SET status = 'canceled'
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY lead_id ORDER BY created_at, id
                ) AS rn
                FROM bookings
                WHERE status IN ('pending_approval', 'approved')
            ) sub
            WHERE rn > 1
        )
        """
    )
    op.create_index(
        "idx_bookings_active_lead",
        "bookings",
        ["lead_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_approval', 'approved')"),
    )
