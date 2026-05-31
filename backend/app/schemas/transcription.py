"""תמלול קולי (§13.3) — schemas של ה-endpoint.

Response בלבד: ה-endpoint מקבל `multipart/form-data` עם UploadFile (לא
JSON schema לבקשה), ומחזיר את הטקסט המתומלל. ה-UI אחראי לשמור את
הטקסט ב-personal_note דרך PATCH /leads/{id} הרגיל.
"""

from pydantic import BaseModel


class TranscriptionResponse(BaseModel):
    """תוצאה של תמלול אודיו של נועה — טקסט עברי בלבד.

    אודיו לא נשמר ב-DB ולא ב-FS קבוע אצלנו (קובץ זמני נמחק מיד אחרי
    קריאה ל-OpenAI). רק הטקסט מוחזר ל-UI; אם נועה תרצה לשמור אותו
    כהערה — תאשר זאת ב-PATCH הרגיל של הליד.
    """

    text: str
