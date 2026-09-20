/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    // App Router הוא ברירת מחדל ב-Next 15 — כאן רק דגלים לעתיד
  },
  async headers() {
    return [
      {
        // כל הנתיבים.
        source: "/:path*",
        headers: [
          {
            // שכבה 3 מתוך 3 של ה-noindex (ראה `app/robots.ts`).
            // ה-header חל גם על תגובות שאינן HTML, שבהן אין איפה
            // לשים תג <meta>, ותקף גם לזחלן שהתעלם מ-robots.txt.
            key: "X-Robots-Tag",
            value: "noindex, nofollow",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
