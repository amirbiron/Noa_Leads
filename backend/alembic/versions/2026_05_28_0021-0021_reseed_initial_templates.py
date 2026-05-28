"""reseed 10 initial templates idempotently (per-id)

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-28

רקע: migration 0009 זורע את 10 התבניות *רק אם הטבלה ריקה*. אם נועה
(או בדיקה) יצרה תבנית אחת דרך הממשק לפני ש-0009 רץ, ה-guard
`if COUNT(*) > 0: return` דילג על הזריעה — ו-10 התבניות לא נכנסו.

התיקון השורשי: זריעה מחדש per-id עם `ON CONFLICT (id) DO NOTHING`.
- ה-UUIDs קבועים (זהים ל-0009) → מכניס רק תבניות שחסרות.
- תבניות שנועה יצרה ידנית (UUID רנדומלי) לא מושפעות ולא משוכפלות.
- אידמפוטנטי: על DB שכבר נזרע ע"י 0009 → no-op מוחלט.

התוכן זהה 1:1 ל-0009 (שאומת מול SpecV2.1.md §9.5, תבניות 1-10).
תבנית 4: "ששלחתי" — תיקון דקדוקי שאושר וסונכרן ל-spec §614
(ראה Changelog v2.1).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# UUIDs קבועים — זהים ל-0009. כך ON CONFLICT (id) DO NOTHING מזהה
# תבניות שכבר קיימות מהסיד המקורי ולא משכפל אותן.
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
    זריעה מחדש per-id. ON CONFLICT (id) DO NOTHING מבטיח אידמפוטנטיות:
    - תבנית שכבר קיימת (מ-0009 או מהרצה קודמת) → לא נוגעים בה.
    - תבנית חסרה → מתווספת.
    אין guard של "טבלה ריקה" — זו בדיוק הסיבה ש-0009 דילג. ה-conflict
    על ה-PK הוא הגנת השכפול היחידה שצריך כאן.
    """
    import json

    bind = op.get_bind()
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
                ON CONFLICT (id) DO NOTHING
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
    no-op מכוון. downgrade *לא* מוחק את התבניות — לא ניתן לדעת אם תבנית
    עם ה-id הקבוע הוכנסה ע"י 0009 או ע"י 0021. מחיקה כאן הייתה עלולה
    להסיר תבניות שה-0009 "הבעלים" שלהן (downgrade ל-0020 ולא ל-0008).
    ה-downgrade של 0009 כבר מטפל בניקוי ה-ids הקבועים.
    """
    pass
