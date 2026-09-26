/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        shield: {
          50:  '#eef2ff',
          100: '#e0e7ff',
          // 200/300/400/800 were missing entirely — not "wrong", just absent.
          // Tailwind only generates CSS for shades actually listed here; any
          // class using an undefined shade (text-shield-200, text-shield-300,
          // text-shield-400, bg-shield-800, etc.) silently produces NO rule at
          // all, so the element falls back to unstyled/inherited color (often
          // rendering as plain black text) instead of erroring or warning.
          // That's what caused active-tab text to disappear on plugin docs
          // and broker health, and was very likely already doing the same,
          // invisibly, everywhere else these shades were used (Branding,
          // Family, Settings, Discovery, and others). Filled in with the
          // same real values as Tailwind's own stock `indigo` palette, which
          // 50/100/500/600/700 below already match exactly (900 is the one
          // deliberately custom, darker value used throughout for background
          // tints — left as-is).
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#1e1b4b',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      }
    }
  },
  plugins: []
}
