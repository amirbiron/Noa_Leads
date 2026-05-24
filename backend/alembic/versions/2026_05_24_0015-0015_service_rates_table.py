"""service_rates table לפי SpecV2.1 §5.10

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-24

F-03 + F-12. מעביר תעריפי שירות מ-hardcoded dict ב-utils/service_rates.py
לטבלה ב-DB שנועה תוכל לערוך דרך /settings.

מבנה הטבלה לפי §5.10: per-session duration + sessions count + price.
total_hours ו-hourly_rate מחושבים ב-API response (לא נשמרים).

seed עם 10 ערכי ברירת המחדל מ-§15.2 (זהה ל-SERVICE_RATES הישן, רק
מומר ל-(duration_minutes × sessions_count) במקום total hours).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 10 התעריפים מ-§15.2 — מומרים ל-(minutes per session, sessions count).
# המקור: backend/app/utils/service_rates.py + תיאור באפיון.
# (category, subtype, label, price, duration_min, sessions, notes)
_DEFAULT_RATES = [
    ("clinic",      "voice_development",    "פיתוח קול",         300,  60,  1,  None),
    ("clinic",      "public_speaking",      "עמידה מול קהל",    2400, 60,  8,  None),
    ("clinic",      "voice_rehab",          "שיקום קול",         2400, 60,  8,  None),
    ("workshops",   "workshop_speaking",    "סדנת דיבור / הופעה", 2000, 120, 1,  None),
    ("workshops",   "stage_arts",           "אומניות הבמה",      7000, 60,  4,  "אפיון: 6,000–8,000 ל-3-4 מפגשים, midpoint"),
    ("workshops",   "lecture_organization", "הרצאה לארגון",       2000, 120, 1,  None),
    ("workshops",   "lecture_academic",     "הרצאה אקדמית",        2000, 120, 1,  None),
    ("production",  "production_guidance",  "ליווי הפקה אישית",   9600, 60,  28, "3.5 חודשים × 2 ש\"ש × 4 שב' ≈ 28 ש'"),
    ("production",  "production_directing", "בימוי הפקה",         None, None, None, "לבירור — מחיר משתנה"),
    ("digital_course", "digital_course",    "קורס דיגיטלי",        None, None, 12, "לבירור — נמכר כיחידה"),
]


def upgrade() -> None:
    op.create_table(
        "service_rates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("service_category", sa.String(length=50), nullable=False),
        sa.Column("service_subtype", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("default_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("default_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("default_sessions_count", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "service_category", "service_subtype", name="uq_service_rates_cat_subtype"
        ),
    )

    # seed — INSERT באמצעות raw SQL כדי לעבוד גם בלי ORM loaded.
    bind = op.get_bind()
    for cat, subtype, label, price, duration, sessions, notes in _DEFAULT_RATES:
        bind.execute(
            sa.text(
                """
                INSERT INTO service_rates (
                    service_category, service_subtype, label,
                    default_price, default_duration_minutes,
                    default_sessions_count, notes,
                    is_active, updated_at
                ) VALUES (
                    :cat, :subtype, :label,
                    :price, :duration, :sessions, :notes,
                    TRUE, NOW()
                ) ON CONFLICT (service_category, service_subtype) DO NOTHING
                """
            ),
            {
                "cat": cat,
                "subtype": subtype,
                "label": label,
                "price": price,
                "duration": duration,
                "sessions": sessions,
                "notes": notes,
            },
        )


def downgrade() -> None:
    op.drop_table("service_rates")
