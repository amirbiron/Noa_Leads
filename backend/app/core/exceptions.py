"""
שגיאות אפליקציה — to_dict() מחזיר תשובה בטוחה בעברית,
בלי לחשוף stack traces, internal IDs או DB errors (כלל 3 ב-CLAUDE.md).
"""


class AppException(Exception):
    """בסיס לכל שגיאות האפליקציה. תמיד עם הודעה גנרית בעברית."""

    status_code: int = 400
    code: str = "error"
    user_message: str = "אירעה שגיאה. נסה שוב מאוחר יותר."

    def __init__(self, user_message: str | None = None) -> None:
        super().__init__(user_message or self.user_message)
        if user_message:
            self.user_message = user_message

    def to_dict(self) -> dict[str, str]:
        # התשובה החוצה — בלי מידע פנימי
        return {"error": self.code, "message": self.user_message}


class NotFoundError(AppException):
    status_code = 404
    code = "not_found"
    user_message = "המשאב המבוקש לא נמצא."


class AuthError(AppException):
    status_code = 401
    code = "unauthorized"
    user_message = "אימות נכשל. יש להתחבר מחדש."


class ForbiddenError(AppException):
    status_code = 403
    code = "forbidden"
    user_message = "אין הרשאה לפעולה זו."


class ValidationError(AppException):
    status_code = 422
    code = "validation_error"
    user_message = "נתונים לא תקינים."


class InvalidStateTransitionError(AppException):
    status_code = 409
    code = "invalid_state_transition"
    user_message = "לא ניתן לבצע את הפעולה במצב הנוכחי של הליד."


class ConflictError(AppException):
    status_code = 409
    code = "conflict"
    user_message = "הפעולה לא ניתנת לביצוע — ייתכן שמישהו אחר עדכן את המשאב."
