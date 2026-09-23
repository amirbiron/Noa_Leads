/**
 * שדה הטלפון בדפי הקביעה — חובה בשניהם.
 *
 * `maxLength={32}` תואם ל-`ContactPhone` בשרת (ול-VARCHAR(32) של
 * `bookings.contact_phone`). הוא נוחות בלבד: השרת הוא שמנרמל ודוחה,
 * עם הודעה בעברית שמסבירה מה לא תקין.
 */
export function BookingPhoneField({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <div className="text-xs text-gray-500 mb-1">
        טלפון ליצירת קשר <span className="text-state-red">*</span>
      </div>
      {/* dir="ltr" + textAlign start: מספר טלפון הוא רצף LTR בתוך דף
          RTL. בלי זה הסימנים בקצוות (+, מקף) קופצים לצד הלא נכון בזמן
          ההקלדה. inputMode="tel" פותח מקלדת ספרות בנייד, ו-autoComplete
          מאפשר מילוי אוטומטי. */}
      <input
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        dir="ltr"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        maxLength={32}
        placeholder="050-0000000"
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-start focus:outline-none focus:border-gray-900"
      />
      <div className="text-xs text-gray-500 mt-1">
        כדי שנועה תוכל ליצור קשר אם משהו משתנה.
      </div>
    </label>
  );
}
