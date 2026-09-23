"""0033 — קישור פתוח לקביעת פגישה, בלי ליד

הלקוחה מפרסמת קישור אחד וקבוע. מי שפותח אותו ממלא שם וטלפון, בוחר
מועד פנוי, והפגישה נכנסת ליומן Google שלה. **זה הכל** — אין יצירת
ליד, אין activity, אין משימה, ואין הופעה בשום מסך.

שני שינויים, ולכל אחד סיבה אחת:

1. **`bookings.lead_id` הופך ל-nullable.**

   ההגנה מפני ששני אנשים יתפסו את אותו מועד יושבת **כולה** בטבלה
   הזו, בשתי שכבות: `_fetch_db_busy` שמסתירה מועדים תפוסים מהרשת,
   ו-`ck_bookings_no_overlap` שדוחה אטומית שתי קביעות חופפות. בלי
   שורה, שתיהן נעלמות: שני אנשים שלוחצים באותה שנייה עוברים שניהם
   את בדיקת ה-busy מול Google — שעוד לא הספיק לאנדקס את האירוע
   הראשון — ונוצרות שתי פגישות באותה שעה ביומן.

   תנאי ה-EXCLUDE הוא `status IN ('pending_approval','approved')`
   ו**אינו מזכיר `lead_id` כלל**, ולכן שורה בלי ליד נהנית מההגנה
   אוטומטית ובלי שינוי באילוץ עצמו.

   השורה אינה מופיעה בממשק מפני שכל תצוגות הליד מסננות לפי
   `lead_id`, ו-`NULL` אינו שווה לשום ערך.

2. **`bookings.contact_name`** — בזרימת הליד השם לאירוע נלקח מכרטיס
   הליד. כאן אין כרטיס, ולכן הלקוח מזין אותו בעצמו. `VARCHAR(200)`
   ולא מספר אחר: זו המידה שכבר קבועה במערכת ל-`leads.full_name`,
   כלומר התשובה הקיימת לשאלה "כמה ארוך שם". הוא nullable כי שורות
   של לידים לא משתמשות בו.

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "bookings",
        "lead_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        "bookings",
        sa.Column("contact_name", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    # שורות הקישור הפתוח אינן ניתנות לשיוך לליד, ולכן ה-downgrade
    # מוחק אותן לפני החזרת ה-NOT NULL. אין דרך אחרת: הן נוצרו בדיוק
    # מפני שאין להן ליד. האירועים המקבילים נשארים ביומן של הלקוחה —
    # מחיקה מ-Google אינה חלק מ-downgrade של סכמה.
    op.execute("DELETE FROM bookings WHERE lead_id IS NULL")
    op.drop_column("bookings", "contact_name")
    op.alter_column(
        "bookings",
        "lead_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
