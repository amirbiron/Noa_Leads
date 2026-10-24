"""
תווי BiDi בלתי נראים בקוד — בדיקה, לא משמעת.

הריפו הזה מוער כולו בעברית (`CLAUDE.md` מחייב את זה), והערות בעברית
שנכתבו במעבד תמלילים, הועתקו מדפדפן או עברו דרך צ'אט עלולות לגרור
איתן תווי בקרה **בלתי נראים בשום עורך**: RLM, LRM, embedding,
override, isolate.

למה זה חשוב, ולמה זה לא נראה:

- תו BiDi יכול לגרום לקוד להיראות אחרת ממה שהמהדר קורא — זו טכניקת
  התקפה אמיתית (Trojan Source, CVE-2021-42574). בהערות עברית זה תמים
  לגמרי, אבל אין דרך להבחין אוטומטית.
- **הבדיקה רחבה מהלינטר, ולא חופפת לו.** נמדד: `ruff` (`PLE2502`)
  פוסל את U+200F אבל **לא** את U+061C, ו-`bandit` (`B613`) אינו
  בתלויות הפרויקט כלל. כלומר על חלק מהתווים כאן אין שום כיסוי אחר.
  הרשימה היא 12 התווים שלהם Unicode מייחס `Bidi_Control` — כולם
  בקטגוריה `Cf`, כלומר בלתי נראים בכל עורך.
- ההודעה שמתקבלת היא לרוב מספר בלי שמות ("3 issues"), ולכן החיפוש
  הולך לכיוון הלא נכון.

**למה בדיקה ולא סריקה חד-פעמית:** תיקון ידני מחזיק עד ההערה העברית
הבאה. זה בדיוק הדפוס — הוא חזר שלוש פעמים באותו פרויקט אחרי שכבר
תוקן פעם אחת.

**מגבלה שצריך לומר:** אין `.github/workflows` בריפו, ולכן הבדיקה
נתפסת רק כשמריצים `pytest` מקומית. הפיכתה לאוטומטית דורשת workflow
(עם Postgres ב-job, אחרת רוב החבילה מדלגת) — מתועד ב-PR ולא מומש כאן.
"""

from pathlib import Path

import pytest

# התווים נבנים ב-`chr()` ולא נכתבים כליטרלים — קובץ הבדיקה הוא גם
# קוד בהיקף הנסרק, ולכן תו אמיתי כאן היה מפיל את הבדיקה על עצמה.
#
# גם `\u200f` בתוך מחרוזת אינו בטוח מספיק: הוא נראה כמו escape בקוד,
# אבל כל שכבה שמעבירה את הקובץ דרך JSON או דרך עורך שמפענח escapes
# הופכת אותו לתו אמיתי — וזה בדיוק מה שקרה בניסיון הראשון לכתוב את
# הקובץ הזה, והבדיקה תפסה את עצמה. `chr(0x200F)` אינו ניתן לפענוח
# בטעות על ידי אף שכבה.
BIDI_CONTROLS: dict[str, str] = {
    chr(0x061C): "ARABIC LETTER MARK",
    chr(0x200E): "LEFT-TO-RIGHT MARK",
    chr(0x200F): "RIGHT-TO-LEFT MARK",
    chr(0x202A): "LEFT-TO-RIGHT EMBEDDING",
    chr(0x202B): "RIGHT-TO-LEFT EMBEDDING",
    chr(0x202C): "POP DIRECTIONAL FORMATTING",
    chr(0x202D): "LEFT-TO-RIGHT OVERRIDE",
    chr(0x202E): "RIGHT-TO-LEFT OVERRIDE",
    chr(0x2066): "LEFT-TO-RIGHT ISOLATE",
    chr(0x2067): "RIGHT-TO-LEFT ISOLATE",
    chr(0x2068): "FIRST STRONG ISOLATE",
    chr(0x2069): "POP DIRECTIONAL ISOLATE",
}

# ההיקף חייב לכסות את מה שהלינטר סורק. סריקה של `app/` בלבד עוברת
# בשעה ש-bandit סורק גם את `tests/` ומפיל את ה-CI — פער שנראה כמו
# בדיקה שעובדת.
_BACKEND = Path(__file__).resolve().parent.parent
SCANNED_ROOTS = ("app", "jobs", "scripts", "tests", "alembic")


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCANNED_ROOTS:
        directory = _BACKEND / root
        if not directory.is_dir():
            continue
        files.extend(
            p
            for p in directory.rglob("*.py")
            if "__pycache__" not in p.parts
        )
    return files


def test_scan_actually_covers_files():
    """שומר על הבדיקה עצמה: היקף ריק היה עובר תמיד ולא בודק כלום."""
    files = _python_files()
    assert len(files) > 50, f"נסרקו רק {len(files)} קבצים — ההיקף כנראה שגוי"


@pytest.mark.parametrize("char,name", sorted(BIDI_CONTROLS.items()))
def test_no_bidi_control_characters(char: str, name: str):
    """אף קובץ `.py` בהיקף לא מכיל תו BiDi."""
    offenders: list[str] = []
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        if char not in text:
            continue
        line_no = next(
            i for i, line in enumerate(text.splitlines(), 1) if char in line
        )
        offenders.append(f"{path.relative_to(_BACKEND)}:{line_no}")

    assert not offenders, (
        f"נמצא {name} (U+{ord(char):04X}) ב: {', '.join(offenders)}. "
        "התו בלתי נראה בעורך — יש למחוק אותו מההערה."
    )
