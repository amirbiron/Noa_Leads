"""בדיקות services.leads.list_leads — סינון לפי `closed`.

Regression guard ל-cursor bugbot: ה-default (closed=None) חייב להחריג
לידים סגורים מרשימת /leads הראשית. closed=True שומר על התנהגות טאב
הארכיון (§12.12). closed=False נופל לאותה ברירת מחדל כמו None.

integration מול Postgres אמיתי — מדלגות אם אין DB (fixture `db`).
"""

from datetime import datetime, timezone

from app.constants import LeadStatus, SourceChannel
from app.schemas.lead import LeadCreate
from app.services.leads import create_lead, list_leads


async def _mk_lead_with_status(db, full_name: str, status: str):
    """יוצר ליד דרך create_lead ואז מציב סטטוס סופי. מתאים לבדיקות בלבד —
    בקוד אמיתי לידים סגורים עוברים דרך close_lead שמטפל ב-side-effects
    (closed_at, ביטול tasks, וכו'). כאן מקצרים כי הסטטוס בלבד רלוונטי."""
    payload = LeadCreate(
        full_name=full_name,
        source_channel=SourceChannel.MANUAL,
    )
    lead = await create_lead(
        db,
        payload,
        current_user_id=None,
        create_first_response_task=False,
        commit=False,
    )
    lead.status = status
    if status in {
        LeadStatus.WON.value,
        LeadStatus.LOST.value,
        LeadStatus.ARCHIVED.value,
    }:
        # closed_at נדרש כדי ש-ORDER BY ב-list_leads(closed=True) לא יקרוס.
        lead.closed_at = datetime.now(timezone.utc)
    await db.flush()
    return lead


async def test_list_leads_default_excludes_closed(db):
    """closed=None (default) → רק לידים פתוחים. סגורים מוסתרים.

    זה ה-fix העיקרי של ה-bug: לפני התיקון, default היה מחזיר הכל.
    """
    await _mk_lead_with_status(db, "פתוח NEW", LeadStatus.NEW.value)
    await _mk_lead_with_status(db, "פתוח IN_PROGRESS", LeadStatus.IN_PROGRESS.value)
    await _mk_lead_with_status(db, "סגור WON", LeadStatus.WON.value)
    await _mk_lead_with_status(db, "סגור LOST", LeadStatus.LOST.value)
    await _mk_lead_with_status(db, "סגור ARCHIVED", LeadStatus.ARCHIVED.value)

    items, _ = await list_leads(db, page=1, page_size=100)
    names = [lead.full_name for lead in items]

    assert "פתוח NEW" in names
    assert "פתוח IN_PROGRESS" in names
    assert "סגור WON" not in names
    assert "סגור LOST" not in names
    assert "סגור ARCHIVED" not in names


async def test_list_leads_closed_true_returns_only_closed(db):
    """closed=True → רק WON/LOST/ARCHIVED. regression של טאב הארכיון."""
    await _mk_lead_with_status(db, "פתוח", LeadStatus.IN_PROGRESS.value)
    await _mk_lead_with_status(db, "סגור WON", LeadStatus.WON.value)
    await _mk_lead_with_status(db, "סגור LOST", LeadStatus.LOST.value)
    await _mk_lead_with_status(db, "סגור ARCHIVED", LeadStatus.ARCHIVED.value)

    items, _ = await list_leads(db, page=1, page_size=100, closed=True)
    names = [lead.full_name for lead in items]

    assert "פתוח" not in names
    assert "סגור WON" in names
    assert "סגור LOST" in names
    assert "סגור ARCHIVED" in names


async def test_list_leads_closed_false_equivalent_to_none(db):
    """closed=False זהה ל-None — שתיהן מציגות פתוחים בלבד.

    מאמת שה-`is True` check ב-backend לא מערבב False עם None (היה
    bug אפשרי אם השתמשנו ב-`if closed:` החזיר את אותו ערך).
    """
    await _mk_lead_with_status(db, "פתוח א", LeadStatus.NEW.value)
    await _mk_lead_with_status(db, "פתוח ב", LeadStatus.PROPOSAL_SENT.value)
    await _mk_lead_with_status(db, "סגור", LeadStatus.WON.value)

    items_default, _ = await list_leads(db, page=1, page_size=100)
    items_false, _ = await list_leads(db, page=1, page_size=100, closed=False)

    assert [lead.id for lead in items_default] == [lead.id for lead in items_false]
    # ומתוכן — רק פתוחים.
    names_default = [lead.full_name for lead in items_default]
    assert "פתוח א" in names_default
    assert "פתוח ב" in names_default
    assert "סגור" not in names_default
