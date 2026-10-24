"""בדיקות ל-services/followup_rules — list + update.

integration: דורש Postgres אמיתי (migration 0029 seeded 5 שורות).
מדלגות אם אין DB.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import NotFoundError
from app.schemas.followup_rule import FollowupRuleUpdate
from app.services.followup_rules import list_rules, update_rule


async def test_list_rules_returns_seeded_5(db):
    """migration 0029 seed-ת 5 כללים. הסדר תואם §17.1:
    first_response → lecture_inquiry → warm_followup → proposal_followup
    → dormant_check.
    """
    rules = await list_rules(db)
    assert len(rules) == 5
    assert [r.rule_key for r in rules] == [
        "first_response",
        "lecture_inquiry",
        "warm_followup",
        "proposal_followup",
        "dormant_check",
    ]
    # default repeat_count = 1 לכל הכללים (התנהגות נוכחית).
    assert all(r.repeat_count == 1 for r in rules)


async def test_update_rule_partial(db):
    """שדות שלא נשלחו נשארים — exclude_unset ב-service."""
    updated = await update_rule(
        db,
        "first_response",
        FollowupRuleUpdate(interval_value=12, repeat_count=3),
    )
    assert updated.interval_value == 12
    assert updated.repeat_count == 3
    # interval_unit לא נשלח → נשאר 'hours' (seed default).
    assert updated.interval_unit == "hours"
    # repeat_interval_value לא נשלח → נשאר 24 (seed default).
    assert updated.repeat_interval_value == 24

    # rollback של conftest מנקה — לא צריך לאפס ידנית.


async def test_update_rule_invalid_key_raises(db):
    """key לא קיים → NotFoundError. מונע insert דרך ה-API."""
    with pytest.raises(NotFoundError, match="לא נמצא"):
        await update_rule(
            db,
            "nonexistent_rule",
            FollowupRuleUpdate(interval_value=10),
        )


async def test_update_rule_check_constraints(db):
    """CHECK constraints ב-DB אוכפים גבולות הגיוניים.

    הולדציה ב-Pydantic (`gt=0`, `ge=1`) חוסמת קלט שלילי לפני שמגיע ל-DB,
    אבל אם מישהו עוקף (e.g., UPDATE ישיר), ה-DB עדיין מגן. כאן בודקים
    את ה-DB constraint ע"י עקיפת ה-schema והקצאה ישירה.
    """
    # קודם ניקוי - שולפים את הכלל הקיים ומשנים ישירות (לא דרך service).
    from app.models.followup_rule import FollowupRule

    rule = await db.get(FollowupRule, "first_response")
    assert rule is not None
    rule.interval_value = 0  # פוגע ב-CHECK
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()
