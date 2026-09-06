import type { ServiceCategory } from "./types";

// subtypes לכל קטגוריה — מקביל ל-SERVICE_CATEGORIES ב-backend/app/constants.py.
// שינוי שם של subtype או הוספה דורש עדכון בשני המקומות.
//
// משמש ב-NewLeadModal (expand section) וב-EditLeadModal לפילטור
// dropdown ה-subtype לפי הקטגוריה שנבחרה.
export const SUBTYPES_BY_CATEGORY: Record<ServiceCategory, string[]> = {
  clinic: ["voice_development", "public_speaking", "voice_rehab"],
  workshops: [
    "workshop_speaking",
    "stage_arts",
    "lecture_organization",
    "lecture_academic",
  ],
  production: ["production_guidance", "production_directing"],
  digital_course: ["digital_course"],
};
