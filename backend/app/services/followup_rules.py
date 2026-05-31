"""Service של הגדרות פולואפ (§17.1).

list_rules / update_rule בלבד. אין create/delete — הכללים מוגדרים בקוד
(TaskType) ו-seeded ב-migration 0029.

flush בלבד; commit באחריות ה-route (כלל 15).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.followup_rule import FollowupRule
from app.schemas.followup_rule import FollowupRuleUpdate

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
