import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        o: {
          bg: "rgb(var(--o-bg) / <alpha-value>)",
          surface: "rgb(var(--o-surface) / <alpha-value>)",
          surfaceHover: "rgb(var(--o-surfaceHover) / <alpha-value>)",
          border: "rgb(var(--o-border) / <alpha-value>)",
          borderHover: "rgb(var(--o-borderHover) / <alpha-value>)",
          blue: "rgb(var(--o-blue) / <alpha-value>)",
          blueHover: "rgb(var(--o-blueHover) / <alpha-value>)",
          blueText: "rgb(var(--o-blueText) / <alpha-value>)",
          text: "rgb(var(--o-text) / <alpha-value>)",
          textSecondary: "rgb(var(--o-textSecondary) / <alpha-value>)",
          muted: "rgb(var(--o-muted) / <alpha-value>)",
          green: "rgb(var(--o-green) / <alpha-value>)",
          red: "rgb(var(--o-red) / <alpha-value>)",
          amber: "rgb(var(--o-amber) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        body: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      animation: {
        "fade-in": "fade-in 0.5s ease-out",
        "fade-in-up": "fade-in-up 0.5s ease-out both",
        "slide-up": "slide-up 0.4s ease-out",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "fade-in-up": {
          from: { opacity: "0", transform: "translateY(12px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
