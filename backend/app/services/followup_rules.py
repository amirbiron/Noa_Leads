"""Service של הגדרות פולואפ (§17.1).

list_rules / update_rule + helper rule_interval_seconds. אין create/delete
— הכללים מוגדרים בקוד (TaskType) ו-seeded ב-migration 0029.

flush בלבד; commit באחריות ה-route (כלל 15).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.followup_rule import FollowupRule
from app.schemas.followup_rule import FollowupRuleUpdate


def rule_interval_seconds(value: int, unit: str) -> int:
    """ערך + יחידה ('hours' / 'days') → שניות. helper ל-cron
    `mark_overdue` שמתזמן את החזרה הבאה אחרי iteration. ה-CHECK
    constraints במודל מבטיחים unit חוקי, אבל ValueError defensive
    אם מישהו עוקף את ה-validation."""
    if unit == "hours":
        return value * 3600
    if unit == "days":
        return value * 86400
    raise ValueError(f"Unknown followup rule unit: {unit!r}")

# סדר תצוגה ל-UI: לפי הסדר ב-§17.1. שמירה על list מקובע מונעת
# drift אם פעם נוסיף/נסיר כלל ולא נעדכן את ה-UI.
_DISPLAY_ORDER = (
    "first_response",
    "lecture_inquiry",
    "warm_followup",
    "proposal_followup",
    "dormant_check",
)


async def list_rules(db: AsyncSession) -> list[FollowupRule]:
    """5 הכללים, ממוינים לסדר תצוגה קבוע (§17.1)."""
    result = await db.execute(select(FollowupRule))
    rules = list(result.scalars().all())
    rules.sort(
        key=lambda r: (
            _DISPLAY_ORDER.index(r.rule_key)
            if r.rule_key in _DISPLAY_ORDER
            else len(_DISPLAY_ORDER)
        )
    )
    return rules


async def update_rule(
    db: AsyncSession,
    rule_key: str,
    payload: FollowupRuleUpdate,
) -> FollowupRule:
    """עדכון partial של כלל. NotFoundError אם key לא קיים — מונע יצירת
    שורה חדשה דרך ה-API."""
    rule = await db.get(FollowupRule, rule_key)
    if rule is None:
        raise NotFoundError("כלל פולואף לא נמצא.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(rule, field, value)
    await db.flush()
    return rule


async def get_rule_interval_seconds(
    db: AsyncSession,
    rule_key: str,
    default_seconds: int,
) -> int:
    """Live lookup של interval_value × interval_unit לשניות.

    משמש בכל אתר יצירת task פולואף (first-response, warm, proposal,
    dormant, lecture-inquiry) — כדי שעריכת נועה ב-UI תשפיע מיידית על
    תזכורות שייווצרו מעכשיו.

    fallback ל-`default_seconds` אם ה-rule לא נמצא (e.g., migration
    0029 לא רץ, או row נמחק בטעות). זה defensive: לא לשבור יצירת
    task בגלל row חסר.
    """
    rule = await db.get(FollowupRule, rule_key)
    if rule is None:
        return default_seconds
    return rule_interval_seconds(rule.interval_value, rule.interval_unit)
