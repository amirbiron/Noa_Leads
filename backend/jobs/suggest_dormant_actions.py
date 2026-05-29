"""
suggest_dormant_actions — רץ פעם ביום אחרי detect_dormant (§19 D.1).

לכל ליד רדום (בהגדרה המדויקת: IN_PROGRESS/PROPOSAL_SENT, עבר 60+ ימים מאז
ה-outbound האחרון, ואין inbound מאז) — מייצר/מעדכן משימת dormant_suggestion
עם המלצת פעולה. 60-119 ימים → קריאת AI (Opus). 120+ ימים → שורט-קאט archive
ללא AI (חוסך עלות, הסבירות לחזרה נמוכה).

"תמיד להציג, לא תמיד להקפיץ": ה-task נוצר תמיד עם ההמלצה (נשמרת בכרטיס), אבל
רק ai_action ∈ {gentle_followup, call} נשלפים ל-/today (סינון ב-dashboard).

idempotency (כלל 8): משימה יחידה פר ליד; refresh רק אם ההמלצה ישנה מ-7 ימים.
AIRateLimitError → לא יוצר task, משאיר לריצה הבאה (כלל 2). AIError → no_action
+ manual_review (fallback §20.13).
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ActivityType, LeadStatus, TaskStatus, TaskType
from app.db.session import AsyncSessionLocal
from app.models.activity import Activity
from app.models.lead import Lead
from app.models.task import Task
from app.services import ai
from app.services.ai import AIError, AIRateLimitError
from app.utils.service_translations import (
    category_to_hebrew,
    subtype_to_hebrew,
)
from jobs._runner import run_job

logger = logging.getLogger("jobs.suggest_dormant_actions")

DORMANT_THRESHOLD_DAYS = 60
SHORTCUT_DAYS = 120
REFRESH_DAYS = 7
# קלט ל-AI: מגבילים כדי לא לנפח טוקנים (היסטוריה ארוכה לא משפרת החלטה).
MAX_ACTIVITIES = 25
MAX_HISTORY_CHARS = 3000
# Guardrails עלות (Opus יקר): אזהרה מעל 5 קריאות חדשות בריצה, עצירה מעל 20.
AI_WARN_THRESHOLD = 5
AI_STOP_THRESHOLD = 20

_SHORTCUT_REASONING = "ליד שותק יותר מ-120 יום - הסבירות לחזרה נמוכה משמעותית"

# תווית עברית קצרה לכל סוג activity — לבניית ההיסטוריה ל-AI. content (אם קיים)
# מצורף אחרי התווית כי הוא האינפורמטיבי ביותר (טקסט הודעה נכנסת, סיכום שיחה).
_ACTIVITY_LABELS = {
    ActivityType.LEAD_CREATED.value: "נוצר ליד",
    ActivityType.LEAD_UPDATED.value: "עודכן ליד",
    ActivityType.TEMPLATE_MARKED_SENT.value: "נשלחה תבנית",
    ActivityType.MANUAL_MESSAGE_LOGGED.value: "תועדה הודעה יוצאת",
    ActivityType.CALL_COMPLETED.value: "שיחה התקיימה",
    ActivityType.CALL_NO_ANSWER.value: "שיחה - אין מענה",
    ActivityType.MEETING_REQUESTED.value: "התבקשה פגישה",
    ActivityType.MEETING_APPROVED.value: "פגישה אושרה",
    ActivityType.MEETING_REJECTED.value: "פגישה נדחתה",
    ActivityType.MEETING_RESCHEDULED.value: "פגישה תוזמנה מחדש",
    ActivityType.MEETING_CANCELED.value: "פגישה בוטלה",
    ActivityType.PROPOSAL_SENT.value: "נשלחה הצעת מחיר",
    ActivityType.FOLLOWUP_SCHEDULED.value: "תוזמן פולואפ",
    ActivityType.OWNER_CHANGED.value: "הועברה בעלות",
    ActivityType.INTERNAL_NOTE_ADDED.value: "נוספה הערה פנימית",
    ActivityType.STATUS_CHANGED.value: "שונה סטטוס",
    ActivityType.INBOUND_MESSAGE_LOGGED.value: "הליד הגיב",
    ActivityType.OUTBOUND_MESSAGE_LOGGED.value: "נשלחה הודעה",
    ActivityType.CHIP_APPLIED.value: "סומן צ'יפ",
}


async def _candidates(db: AsyncSession, now_utc: datetime) -> list[Lead]:
    """
    ההגדרה המדויקת של "ליד רדום" לפיצ'ר ההמלצות (§19 D.1):
    - status ∈ {IN_PROGRESS, PROPOSAL_SENT} (לא NEW/BOOKED/סגור).
    - last_outbound_at קיים ולפני 60+ ימים.
    - אין inbound מאז ה-outbound האחרון (הלקוח לא הגיב).
    """
    threshold = now_utc - timedelta(days=DORMANT_THRESHOLD_DAYS)
    stmt = select(Lead).where(
        Lead.status.in_(
            [LeadStatus.IN_PROGRESS.value, LeadStatus.PROPOSAL_SENT.value]
        ),
        Lead.last_outbound_at.is_not(None),
        Lead.last_outbound_at <= threshold,
        or_(
            Lead.last_inbound_at.is_(None),
            Lead.last_inbound_at <= Lead.last_outbound_at,
        ),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _existing_open_suggestion(db: AsyncSession, lead_id) -> Task | None:
    """ה-dormant_suggestion task הפתוח של הליד (לבדיקת refresh/idempotency)."""
    result = await db.execute(
        select(Task)
        .where(
            Task.lead_id == lead_id,
            Task.type == TaskType.DORMANT_SUGGESTION.value,
            Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]),
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _is_fresh(task: Task, now_utc: datetime) -> bool:
    """True אם ההמלצה הקיימת צעירה מ-7 ימים (אין צורך ב-refresh)."""
    meta = task.task_metadata or {}
    gen_at = meta.get("ai_generated_at")
    if not gen_at:
        return False
    try:
        gen_dt = datetime.fromisoformat(gen_at)
    except (ValueError, TypeError):
        return False
    return (now_utc - gen_dt) < timedelta(days=REFRESH_DAYS)


async def _format_history(
    db: AsyncSession, lead_id, now_utc: datetime
) -> str:
    """בונה רשימת bullet של ההיסטוריה ל-prompt. מוגבל ב-25 פעולות / 3000 תווים."""
    result = await db.execute(
        select(Activity)
        .where(Activity.lead_id == lead_id)
        .order_by(Activity.created_at.asc())
    )
    activities = list(result.scalars().all())
    # אם יש יותר מ-MAX — שומרים את האחרונות (הרלוונטיות ביותר להחלטה עכשיו).
    if len(activities) > MAX_ACTIVITIES:
        activities = activities[-MAX_ACTIVITIES:]

    lines: list[str] = []
    for act in activities:
        days_ago = max(0, (now_utc - act.created_at).days)
        label = _ACTIVITY_LABELS.get(act.type, act.type)
        if act.content:
            label = f"{label}: {act.content}"
        lines.append(f"- {days_ago} ימים אחורה: {label}")

    text = "\n".join(lines) if lines else "- (אין פעולות מתועדות)"
    if len(text) > MAX_HISTORY_CHARS:
        text = text[:MAX_HISTORY_CHARS] + "\n- [ההיסטוריה קוצרה]"
    return text


async def suggest_dormant_actions() -> None:
    now_utc = datetime.now(timezone.utc)
    model = ai.resolve_model("dormant_suggestion")

    async with AsyncSessionLocal() as db:
        from app.services.tasks import sync_lead_next_action_cache

        leads = await _candidates(db, now_utc)
        ai_calls = 0
        affected: list = []
        stopped = False

        for lead in leads:
            existing = await _existing_open_suggestion(db, lead.id)
            if existing is not None and _is_fresh(existing, now_utc):
                continue  # ההמלצה עדיין טרייה — לא מחדשים

            days_since = max(0, (now_utc - lead.last_outbound_at).days)

            if days_since >= SHORTCUT_DAYS:
                # שורט-קאט ללא AI.
                metadata = {
                    "ai_action": "archive",
                    "ai_reasoning": _SHORTCUT_REASONING,
                    "ai_generated_at": now_utc.isoformat(),
                    "model_used": "auto_shortcut_120d",
                }
            else:
                # מסלול AI — בכפוף ל-guardrails עלות.
                if ai_calls >= AI_STOP_THRESHOLD:
                    logger.error(
                        "Reached %d AI calls — stopping, %d dormant leads "
                        "left for next run",
                        AI_STOP_THRESHOLD,
                        len(leads) - len(affected),
                    )
                    stopped = True
                    break

                history = await _format_history(db, lead.id, now_utc)
                started = time.monotonic()
                try:
                    result = await ai.suggest_action_for_dormant(
                        lead_name=lead.full_name,
                        organization_name=lead.organization_name,
                        # עברית — עקבי עם ה-few-shot בעברית (§19.3).
                        service_subtype=subtype_to_hebrew(lead.service_subtype),
                        service_category=category_to_hebrew(lead.service_category),
                        days_since_last_activity=days_since,
                        activities_text=history,
                    )
                except AIRateLimitError:
                    # לא יוצרים task — נשאיר לריצה הבאה (כלל 2: לא להחמיר ספירה).
                    logger.warning(
                        "Rate limit on lead %s — leaving for next run", lead.id
                    )
                    continue
                except AIError as e:
                    # כשל אחרי 3 retries → fallback no_action + manual_review.
                    logger.warning("AI failed for lead %s: %s", lead.id, e)
                    metadata = {
                        "ai_action": "no_action",
                        "ai_reasoning": "לא ניתן היה להפיק המלצה אוטומטית — דורש בדיקה ידנית.",
                        "ai_generated_at": now_utc.isoformat(),
                        "model_used": "ai_failed",
                        "manual_review": True,
                    }
                else:
                    metadata = {
                        "ai_action": result.action,
                        "ai_reasoning": result.reasoning,
                        "ai_generated_at": now_utc.isoformat(),
                        "model_used": model,
                    }

                ai_calls += 1
                if ai_calls == AI_WARN_THRESHOLD + 1:
                    logger.warning(
                        "More than %d dormant AI calls in this run (Opus cost)",
                        AI_WARN_THRESHOLD,
                    )
                logger.info(
                    "dormant suggestion: lead=%s model=%s days=%d decision=%s "
                    "latency_ms=%d",
                    lead.id,
                    metadata["model_used"],
                    days_since,
                    metadata["ai_action"],
                    int((time.monotonic() - started) * 1000),
                )

            # UPSERT — משימה יחידה פר ליד (idempotent).
            if existing is not None:
                existing.task_metadata = metadata
                existing.due_at = now_utc
                existing.status = TaskStatus.OPEN.value
            else:
                db.add(
                    Task(
                        lead_id=lead.id,
                        type=TaskType.DORMANT_SUGGESTION.value,
                        assigned_to=lead.owner_id,
                        status=TaskStatus.OPEN.value,
                        due_at=now_utc,
                        origin_rule="auto_dormant_suggestion",
                        task_metadata=metadata,
                    )
                )
            affected.append(lead.id)

        if affected:
            await db.flush()
            for lead_id in affected:
                await sync_lead_next_action_cache(db, lead_id)

        await db.commit()

    logger.info(
        "Dormant suggestions: %d leads processed, %d AI calls%s",
        len(affected),
        ai_calls,
        " (stopped early on cost guardrail)" if stopped else "",
    )


if __name__ == "__main__":
    run_job("suggest_dormant_actions", suggest_dormant_actions)
