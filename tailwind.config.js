/** @type {import('tailwindcss').Config} */
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        "bg-deep": "rgb(var(--bg-deep) / <alpha-value>)",
        fg: "rgb(var(--text) / <alpha-value>)",
        "fg-soft": "rgb(var(--text-soft) / <alpha-value>)",
        "fg-muted": "rgb(var(--text-muted) / <alpha-value>)",
        "fg-subtle": "rgb(var(--text-subtle) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-hover": "rgb(var(--accent-hover) / <alpha-value>)",
        "accent-soft": "rgb(var(--accent-soft))",
        "on-accent": "rgb(var(--on-accent) / <alpha-value>)",
        border: "rgb(var(--border))",
        "border-strong": "rgb(var(--border-strong))",
        danger: "rgb(var(--danger) / <alpha-value>)",
        "danger-soft": "rgb(var(--danger-soft))",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      letterSpacing: {
        tightish: "-0.01em",
        tighter: "-0.02em",
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.25rem",
      },
    },
  },
  plugins: [],
};
