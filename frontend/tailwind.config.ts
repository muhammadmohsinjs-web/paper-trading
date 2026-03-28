import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        panel: "#F3F5F7",
        line: "#E3E8EF",
        rise: "#1F8F5F",
        fall: "#C4554A",
        gold: "#9A6B16",
        accent: "#3E63DD"
      },
      boxShadow: {
        bloom: "0 8px 24px rgba(16, 24, 40, 0.06)"
      },
      backgroundImage: {
        grain:
          "radial-gradient(circle at 0% 0%, rgba(62, 99, 221, 0.06), transparent 24%), linear-gradient(180deg, rgba(255,255,255,0.65), rgba(255,255,255,0.35))"
      }
    }
  },
  plugins: []
};

export default config;
