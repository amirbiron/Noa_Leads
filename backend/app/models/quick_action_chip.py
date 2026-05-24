"""
QuickActionChip — צ'יפים editable לסיכום שיחה מהיר.

לפי Spec v2.1 §5.7 + §16.4: declarative model. כל צ'יפ אומר ישירות מה
סטטוס היעד, מי ה-waiting_on, איזה סוג task של פולואפ ליצור, ובעוד כמה
ימים. אין יותר action_type מקושר ל-state_machine — קליק על צ'יפ מבצע
4 פעולות אטומיות (status update + waiting_on + create task + activity).

נועה יכולה לערוך / להוסיף / להסיר דרך /settings/chips. 6 צ'יפי ברירת
מחדל נטענים ב-migration 0013.
"""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class QuickActionChip(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quick_action_chips"

    # טקסט שמופיע ל-נועה (ניתן לערוך). למשל: "אין מענה", "רוצה הצעה".
    label: Mapped[str] = mapped_column(String(100), nullable=False)

    # ===== 4 השדות הסמנטיים מ-§5.7 v2.1 =====
    # nullable כדי לתמוך בצ'יפים שנועה הוסיפה ידנית לפני שמילאה את כולם.
    # ה-frontend מציג רק צ'יפים שכל ה-4 מאוכלסים (אחרת קליק יהיה no-op).

    # סטטוס היעד אחרי הלחיצה. ערכי LeadStatus enum (בעיקר IN_PROGRESS לפי §16.4).
    target_status: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    # NOAH / CLIENT / ASSISTANT / ASSISTANT_PENDING_NOAH / SYSTEM / NONE.
    waiting_on: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    # סוג ה-task שייווצר אוטומטית. ערכי TaskType enum
    # (retry_call / followup / send_proposal / dormant_check / וכו').
    followup_task_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    # כמה ימים מהיום ל-due_at של ה-task החדש.
    auto_followup_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # ===== מטא =====
    # סדר תצוגה — נמוך מופיע ראשון.
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
