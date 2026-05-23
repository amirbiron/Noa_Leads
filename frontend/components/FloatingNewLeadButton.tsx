"use client";

import { Plus } from "lucide-react";
import { useState } from "react";
import { NewLeadModal } from "./NewLeadModal";

// כפתור צף בפינה — מאפשר יצירת ליד מ-3 שדות מכל מסך באפליקציה.
// ה-Inset-end-4 דואג למיקום נכון ב-RTL (פינה שמאלית-תחתונה).
export function FloatingNewLeadButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="ליד חדש"
        className="fixed bottom-20 inset-inline-end-4 z-30 bg-gray-900 text-white rounded-full w-14 h-14 shadow-lg active:bg-gray-700 flex items-center justify-center"
        style={{ insetInlineEnd: "1rem" }}
      >
        <Plus size={26} aria-hidden />
      </button>
      <NewLeadModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
