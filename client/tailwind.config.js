/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        /* Design tokens — the source of truth lives in globals.css :root,
           mirrored here so `bg-panel`, `text-ink-2`, etc. work in markup. */
        stage: "var(--mf-stage)",
        background: "var(--mf-bg)",
        panel: "var(--mf-panel)",
        "panel-2": "var(--mf-panel-2)",
        line: "var(--mf-line)",
        "line-strong": "var(--mf-line-strong)",

        ink: "var(--mf-ink)",
        "ink-2": "var(--mf-ink-2)",
        "ink-3": "var(--mf-ink-3)",
        "ink-4": "var(--mf-ink-4)",

        violet: "var(--mf-violet)",
        "violet-deep": "var(--mf-violet-deep)",
        "violet-soft": "var(--mf-violet-soft)",
        gold: "var(--mf-gold)",
        "gold-soft": "var(--mf-gold-soft)",

        /* Legacy aliases kept so untouched pages keep rendering. */
        surface: "var(--mf-panel)",
        "surface-2": "var(--mf-panel-2)",
        "surface-3": "var(--mf-line-strong)",
        accent: "var(--mf-violet)",
        "accent-light": "var(--mf-violet-soft)",
        "accent-glow": "rgba(139, 92, 246, 0.3)",
        muted: "var(--mf-ink-3)",
        "muted-2": "var(--mf-ink-4)",
      },
      fontSize: {
        /* Display scale for hero + section headings. */
        "display-sm": ["2.5rem", { lineHeight: "1", letterSpacing: "-0.03em" }],
        "display-md": ["3.5rem", { lineHeight: "0.98", letterSpacing: "-0.034em" }],
        "display-lg": ["4.75rem", { lineHeight: "0.94", letterSpacing: "-0.038em" }],
      },
      boxShadow: {
        glow: "var(--mf-glow)",
        lift: "var(--mf-lift)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        glow: "glow 2s ease-in-out infinite alternate",
        "slide-up": "slideUp 0.4s ease-out",
        "fade-in": "fadeIn 0.3s ease-out",
      },
      keyframes: {
        glow: {
          "0%": { boxShadow: "0 0 5px rgba(139, 92, 246, 0.3)" },
          "100%": { boxShadow: "0 0 20px rgba(139, 92, 246, 0.7), 0 0 40px rgba(139, 92, 246, 0.3)" },
        },
        slideUp: {
          "0%": { transform: "translateY(10px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
