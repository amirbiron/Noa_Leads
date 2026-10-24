import { CheckCircle2 } from "lucide-react";
import { BookingCenteredCard } from "@/components/BookingCenteredCard";
import { fullSlotLabel } from "@/lib/bookingDates";

/**
 * מסך ההצלחה — משותף לשני דפי הקביעה.
 *
 * המועד מוצג **מתשובת השרת** ולא מהסלוט שנבחר בדף: זה המועד שבאמת
 * נשמר ונכנס ליומן, והלקוח צריך לראות בדיוק אותו.
 */
export function BookingSuccessCard({ start, end }: { start: string; end: string }) {
  return (
    <BookingCenteredCard>
      <div className="text-center space-y-3">
        <CheckCircle2 className="mx-auto text-state-green" size={56} aria-hidden />
        <div className="text-xl font-semibold">הפגישה נקבעה</div>
        <div className="text-base font-medium text-gray-900">
          {fullSlotLabel(start, end)}
        </div>
        <div className="text-sm text-gray-500 mt-4">
          הפגישה נכנסה ליומן של נועה. אם משהו משתנה, היא תיצור איתך
          קשר בטלפון שהשארת.
        </div>
      </div>
    </BookingCenteredCard>
  );
}
