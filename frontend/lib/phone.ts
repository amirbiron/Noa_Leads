// המרה ל-E.164 לקישורי wa.me ו-tel:.
// תואם ל-app/utils/phone.py בבקאנד.
// ראה: docs/Skills/israeli-phone-formatter/SKILL.md
//
// wa.me דורש פורמט בינלאומי ללא + (לדוגמה: 972521234567).
// "052-1234567" → "972521234567"
// "+972521234567" → "972521234567"
// "+12125551234" → "12125551234" (חו"ל)
// "*2421" → null (אין E.164)

export function toWhatsAppDigits(phone: string | null): string | null {
  if (!phone) return null;
  const cleaned = phone.replace(/[\s\-().]/g, "");
  if (!cleaned || cleaned.startsWith("*")) return null;

  // ישראלי עם +972 או 972 בהתחלה
  if (cleaned.startsWith("+972")) return cleaned.slice(1);
  if (cleaned.startsWith("972")) return cleaned;

  // ישראלי עם 0 מוביל — להחליף ל-972
  if (cleaned.startsWith("0")) {
    return "972" + cleaned.slice(1);
  }

  // 1-800/1-700/קצרים — לא ניתן בינלאומי
  if (cleaned.startsWith("1800") || cleaned.startsWith("1700")) return null;

  // חו"ל עם +
  if (cleaned.startsWith("+")) return cleaned.slice(1);

  // לא ברור — מחזיר ספרות בלבד כ-best effort
  return cleaned;
}

export function toTelHref(phone: string | null): string | null {
  if (!phone) return null;
  // tel: מקבל גם פורמט מקומי וגם בינלאומי. נחזיר עם + לבינלאומי.
  const cleaned = phone.replace(/[\s\-().]/g, "");
  if (!cleaned) return null;
  return cleaned;
}
