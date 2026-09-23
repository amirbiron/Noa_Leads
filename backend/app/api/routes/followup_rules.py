"""Routes ל-`/settings/followup-rules` (§17.1).

GET: כל user מאומת. PATCH: owner בלבד — נועה היחידה משנה כללי פולואפ.
אין POST/DELETE — הכללים מוגדרים בקוד (TaskType) ו-seeded ב-migration.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, OwnerOnly
from app.schemas.followup_rule import FollowupRuleRead, FollowupRuleUpdate
from app.services import followup_rules as rules_service

router = APIRouter(prefix="/settings/followup-rules", tags=["settings"])


@router.get("", response_model=list[FollowupRuleRead])
async def list_followup_rules(
    db: DbSession, user: CurrentUser
) -> list[FollowupRuleRead]:
    """5 הכללים. כל user מאומת — assistant רואה את הערכים readonly."""
    rules = await rules_service.list_rules(db)
    return [FollowupRuleRead.model_validate(r) for r in rules]


@router.patch("/{rule_key}", response_model=FollowupRuleRead)
async def update_followup_rule(
    rule_key: str,
    payload: FollowupRuleUpdate,
    db: DbSession,
    user: OwnerOnly,
) -> FollowupRuleRead:
    """עריכת כלל בודד. owner-only. NotFoundError → 404 דרך global handler."""
    rule = await rules_service.update_rule(db, rule_key, payload)
    # ה-service עושה flush; ה-route בעל הסשן והוא ה-commit (כלל 15).
    await db.commit()
    return FollowupRuleRead.model_validate(rule)
