"""seed 10 initial templates for Noa

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-24

10 תבניות התחלתיות שנועה תקבל ביום הראשון (לפי phase-2.5-plan.md §5).
המשתמש סיפק את התוכן הסופי בהודעה למימוש פאזה 2.5.

הסיד רץ *רק* אם הטבלה ריקה — לא דורס תבניות שנועה יצרה ידנית.
שדות:
- name: שם התבנית (לחיפוש/בחירה)
- channel: whatsapp / email
- target_audience: private / organization / dormant — לפיצ'ר "פתיחה
  חכמה לפי סוג ליד" (האפיון ה.). NULL = any.
- body: תוכן עם {placeholders}
- variables: רשימת המשתנים שמותר להחליף (קונבנציה אצלנו)
- is_active: כברירת מחדל true
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# UUIDs קבועים לסיד: דטרמיניסטיים כדי שדאונגרייד ימחק *רק* את התבניות
# שהמיגרציה הזו יצרה. בלי id קבוע, downgrade שמסתמך על שם בלבד יכול
# למחוק תבניות שנועה יצרה ידנית עם שם תואם.
_TEMPLATES = [
    {
        "id": "00000000-0000-0009-0000-000000000001",
        "name": "פתיחה - קליניקה",
        "channel": "whatsapp",
        "target_audience": "private",
        "body": """היי {customer_name},
תודה שפנית אליי 🌸

ראיתי שאת/ה מעוניין/ת ב{service_subtype}. אשמח להכיר ולשמוע יותר על מה שמעניין אותך.

מתי נוח לך לשיחה קצרה כדי להבין מה הצורך ולתאם פגישת היכרות?

נועה""",
        "variables": ["customer_name", "service_subtype"],
    },
    {
        "id": "00000000-0000-0009-0000-000000000002",
        "name": "פתיחה - ארגון",
        "channel": "email",
        "target_audience": "organization",
        "body": """שלום {customer_name},

תודה רבה על הפנייה. אשמח לבחון יחד התאמה של {service_subtype} ל{organization}.

מציעה לקבוע שיחה קצרה (15-20 דק') כדי שאוכל להבין את הצורך המדויק - גודל הקבוצה, תאריך משוער, מטרות הסדנה - ולשלוח הצעה מותאמת.

מתי נוח לך?

בברכה,
נועה""",
        "variables": ["customer_name", "service_subtype", "organization"],
    },
    {
        "id": "00000000-0000-0009-0000-000000000003",
        "name": "פולואפ אחרי שיחה - קליניקה",
        "channel": "whatsapp",
        "target_audience": "private",
        "body": """היי {customer_name},
היה נעים לדבר איתך 🌸

מצרפת תקציר של מה שדיברנו ומה שהצענו:
[להוסיף תקציר ידני]

אשמח לדעת אם זה מתאים לך, ולתאם פגישה ראשונה.

נועה""",
        "variables": ["customer_name"],
    },
    {
        "id": "00000000-0000-0009-0000-000000000004",
        "name": "פולואפ אחרי הצעה",
        "channel": "whatsapp",
        "target_audience": None,
        "body": """היי {customer_name},

מקווה שאת/ה בסדר. רציתי לוודא שההצעה ל{service_subtype} ששלחתי לך הגיעה ושהיא ברורה.

יש לך שאלות? אשמח לעזור 🌸

נועה""",
        "variables": ["customer_name", "service_subtype"],
    },
    {
        "id": "00000000-0000-0009-0000-000000000005",
        "name": "חידוש קשר עדין",
        "channel": "whatsapp",
        "target_audience": "dormant",
        "body": """היי {customer_name},

עבר זמן מאז שדיברנו, רציתי רק לבדוק איתך - האם עדיין רלוונטי בשבילך {service_subtype}?

אם כן, אשמח לעדכן אותך באפשרויות החדשות שיש לי. אם לא - אין בעיה כמובן 🌸

נועה""",
        "variables": ["customer_name", "service_subtype"],
    },
    {
        "id": "00000000-0000-0009-0000-000000000006",
        "name": "אישור פגישה",
        "channel": "whatsapp",
        "target_audience": None,
        "body": """היי {customer_name},

מאשרת את הפגישה שלנו. מצפה לראותך 🌸

לתשומת ליבך:
- במידה ולא תוכל/י להגיע, אשמח לעדכון לפחות 24 שעות מראש
- מומלץ להגיע 5 דקות לפני

נועה""",
        "variables": ["customer_name"],
    },
    {
        "id": "00000000-0000-0009-0000-000000000007",
        "name": "מענה אחרי שעות / סוף שבוע",
        "channel": "whatsapp",
        "target_audience": None,
        "body": """היי {customer_name},
תודה שפנית אליי 🌸

אני כרגע לא זמינה. אחזור אליך ביום העבודה הקרוב בין 9:00-11:00.

שבת שלום / חג שמח,
נועה""",
        "variables": ["customer_name"],
    },
    {
        "id": "00000000-0000-0009-0000-000000000008",
        "name": "הצעת מחיר - סדנה",
        "channel": "email",
        "target_audience": "organization",
        "body": """שלום {customer_name},

תודה רבה על השיחה ועל ההזדמנות להציע ל{organization}.

הצעה ל{service_subtype}:
- משך: שעתיים
- מספר משתתפים: עד 20
- מחיר: 2,000 ₪ כולל מע"מ
- מיקום: לפי תיאום

הסדנה כוללת:
[להוסיף פירוט תוכן ספציפי]

אשמח לאשר את התיאום ולקבוע תאריך.

בברכה,
נועה""",
        "variables": ["customer_name", "service_subtype", "organization"],
    },
    {
        "id": "00000000-0000-0009-0000-000000000009",
        "name": "הצעת תוכנית - שיקום/עמידה מול קהל",
        "channel": "whatsapp",
        "target_audience": "private",
        "body": """היי {customer_name},

על בסיס מה שדיברנו, ממליצה לך על תוכנית של 8 מפגשים ל{service_subtype}.

פרטים:
- 8 מפגשים בני שעה
- 300 ₪ למפגש (סה"כ 2,400 ₪)
- תיאום גמיש לפי הזמינות שלך

זה מאפשר לבסס את העבודה ולראות תוצאות אמיתיות.

מה דעתך?

נועה""",
        "variables": ["customer_name", "service_subtype"],
    },
    {
        "id": "00000000-0000-0009-0000-000000000010",
        "name": "סיום תוכנית - הצעת המשך",
        "channel": "whatsapp",
        "target_audience": "private",
        "body": """היי {customer_name},

המפגש הבא הוא האחרון בתוכנית שלנו 🌸

לפני שנסיים, חשוב לי לעצור ולחשוב יחד - איך את/ה מרגיש/ה? מה השגנו? מה היית/ה רוצה להמשיך לעבוד עליו?

אשמח לחשוב יחד על המשך התהליך.

נועה""",
        "variables": ["customer_name"],
    },
]


def upgrade() -> None:
    """
    seed תבניות *רק* אם הטבלה ריקה. אחרת מדלגים — לא דורסים מה שנועה
    יצרה ידנית.

    Race: alembic תופס lock גלובלי לפני הרצת migrations (alembic_version
    table), אז 2 הרצות בו-זמנית לא יכולות לקרות. ה-check-then-insert
    כאן בטוח.
    """
    import json

    bind = op.get_bind()
    existing = bind.execute(
        sa.text("SELECT COUNT(*) FROM templates")
    ).scalar_one()
    if existing > 0:
        return

    for tpl in _TEMPLATES:
        bind.execute(
            sa.text(
                """
                INSERT INTO templates
                    (id, name, channel, target_audience, body, variables,
                     is_active, created_by, created_at, updated_at)
                VALUES
                    (:id, :name, :channel, :target_audience,
                     :body, CAST(:variables AS JSONB), TRUE, NULL,
                     NOW(), NOW())
                """
            ),
            {
                "id": tpl["id"],
                "name": tpl["name"],
                "channel": tpl["channel"],
                "target_audience": tpl["target_audience"],
                "body": tpl["body"],
                "variables": json.dumps(tpl["variables"]),
            },
        )


def downgrade() -> None:
    """
    downgrade מוחק *רק* תבניות עם ה-ids הקבועים של הסיד. תבניות שנועה
    יצרה ידנית (ב-UUIDs רנדומליים אחרים) נשארות. זה בטוח גם אם נועה
    יצרה תבנית עם שם זהה לאחת המקוריות.
    """
    bind = op.get_bind()
    ids = [tpl["id"] for tpl in _TEMPLATES]
    bind.execute(
        sa.text(
            "DELETE FROM templates WHERE id::text = ANY(:ids)"
        ),
        {"ids": ids},
    )
