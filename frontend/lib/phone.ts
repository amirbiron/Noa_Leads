// המרה ל-E.164 לקישורי wa.me ו-tel:.
// תואם ל-app/utils/phone.py בבקאנד.
// ראה: docs/Skills/israeli-phone-formatter/SKILL.md
//
// wa.me דורש פורמט בינלאומי ללא + (לדוגמה: 972521234567).
// "052-1234567" → "972521234567"
// "+972521234567" → "972521234567"
// "+12125551234" → "12125551234" (חו"ל)
// "*2421" → null (אין E.164)

// פלט E.164 חייב להיות ספרות בלבד — wa.me דוחה כל דבר אחר
const E164_DIGITS_ONLY = /^\d+$/;

export function toWhatsAppDigits(phone: string | null): string | null {
  if (!phone) return null;
  const cleaned = phone.replace(/[\s\-().]/g, "");
  if (!cleaned || cleaned.startsWith("*")) return null;

  let candidate: string;
  if (cleaned.startsWith("+972")) {
    candidate = cleaned.slice(1);
  } else if (cleaned.startsWith("972")) {
    candidate = cleaned;
  } else if (cleaned.startsWith("0")) {
    // ישראלי עם 0 מוביל — להחליף ל-972
    candidate = "972" + cleaned.slice(1);
  } else if (cleaned.startsWith("1800") || cleaned.startsWith("1700")) {
    // לא ניתן לחיוג בינלאומי
    return null;
  } else if (cleaned.startsWith("+")) {
    // חו"ל עם +
    candidate = cleaned.slice(1);
  } else {
    // לא ברור — best effort, ייפסל אם יש תווים זרים
    candidate = cleaned;
  }

  // guard סופי: רק ספרות. מונע פלט שבור אם הקלט הכיל אותיות / סמלים אחרים
  // שעברו את הניקוי הראשוני (למשל phone שלא עבר את ה-backend validator).
  return E164_DIGITS_ONLY.test(candidate) ? candidate : null;
}
