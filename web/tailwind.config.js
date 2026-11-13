/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#070b10",
          900: "#0b1118",
          850: "#0f1620",
          800: "#141d28",
          700: "#1b2735",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      boxShadow: {
        panel:
          "inset 0 1px 0 0 rgba(255,255,255,0.04), 0 24px 60px -32px rgba(0,0,0,0.9)",
      },
    },
  },
  plugins: [],
};
