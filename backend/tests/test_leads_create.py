"""בדיקות יצירת ליד דרך services.leads.create_lead — מיפוי שדות.

Regression guard ל-cursor bugbot על ad590f7: השדות מ-LeadCreate חייבים
לעבור 1:1 ל-Lead row. לפני התיקון, `is_returning_customer` עבר את ה-
schema אך לא מופה ב-`Lead(...)` constructor — הדאטה אובדה בשתיקה
וברירת המחדל של המודל (False) דרסה את ערך המשתמש.

integration מול Postgres אמיתי — מדלגות אם אין DB (fixture `db`).
"""

from app.constants import SourceChannel
from app.schemas.lead import LeadCreate
from app.services.leads import create_lead


async def test_create_lead_persists_is_returning_customer_true(db):
    """Regression: is_returning_customer=True נשמר ב-DB ולא נדרס ל-False.

    `db.refresh` קורא את הערך מ-DB אחרי flush — מאמת שהמיפוי הגיע באמת
    לעמודה ולא נשאר רק כ-Python attribute על ה-instance.
    """
    payload = LeadCreate(
        full_name="לקוח חוזר בדיקה",
        source_channel=SourceChannel.MANUAL,
        is_returning_customer=True,
    )
    lead = await create_lead(
        db,
        payload,
        current_user_id=None,
        create_first_response_task=False,
        commit=False,
    )
    await db.refresh(lead)
    assert lead.is_returning_customer is True


async def test_create_lead_default_is_returning_customer_false(db):
    """ברירת מחדל: ליד שנוצר בלי השדה → False (לא None, לא True)."""
    payload = LeadCreate(
        full_name="לקוח חדש בדיקה",
        source_channel=SourceChannel.MANUAL,
    )
    lead = await create_lead(
        db,
        payload,
        current_user_id=None,
        create_first_response_task=False,
        commit=False,
    )
    await db.refresh(lead)
    assert lead.is_returning_customer is False
