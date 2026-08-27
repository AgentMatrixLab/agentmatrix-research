/** @type {import('tailwindcss').Config} */

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    container: {
      center: true,
    },
    extend: {
      colors: {
        ink: {
          950: "#0A0E14",
          900: "#0D1219",
          850: "#10161F",
          800: "#11161F",
          700: "#161D29",
          600: "#1C2534",
        },
        line: "rgba(148,163,184,0.10)",
        accent: "#22D3EE",
        up: "#F43F5E",
        down: "#10B981",
        fg: {
          DEFAULT: "#E2E8F0",
          soft: "#8B94A7",
          mute: "#566173",
        },
      },
      fontFamily: {
        sans: [
          "Manrope",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
      boxShadow: {
        glow: "0 0 24px rgba(34,211,238,0.10)",
        card: "0 8px 30px rgba(0,0,0,0.35)",
      },
      keyframes: {
        fadeUp: {
          from: { opacity: "0", transform: "translateY(14px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pulseDot: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        "fade-up": "fadeUp 0.55s cubic-bezier(0.22,1,0.36,1) both",
        "pulse-dot": "pulseDot 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
