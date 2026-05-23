import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 4 צבעי מצב לפי האפיון — האדום בגוון עדין ולא צועק
        state: {
          red: "#d97a7a",
          orange: "#e8a55a",
          green: "#7ab87a",
          gray: "#9ca3af",
        },
      },
      fontFamily: {
        sans: ["var(--font-heebo)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
