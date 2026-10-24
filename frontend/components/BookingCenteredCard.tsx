/** כרטיס ממורכז למצבי טעינה, שגיאה והצלחה בדפי הקביעה הציבוריים. */
export function BookingCenteredCard({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 w-full max-w-md p-6">
        {children}
      </div>
    </main>
  );
}
