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
        ink: "#101312",
        mist: "#dbe6df",
        sand: "#f0ebde",
        panel: "#17201d",
        line: "#2a3934",
        rise: "#b8ff67",
        fall: "#ff7b5a",
        gold: "#f3c96b"
      },
      boxShadow: {
        bloom: "0 24px 80px rgba(0, 0, 0, 0.28)"
      },
      backgroundImage: {
        grain:
          "radial-gradient(circle at 15% 15%, rgba(243, 201, 107, 0.08), transparent 28%), radial-gradient(circle at 85% 10%, rgba(184, 255, 103, 0.08), transparent 20%), linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0))"
      }
    }
  },
  plugins: []
};

export default config;
