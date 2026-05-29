/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}',
  ],
  theme: {
    extend: {
      colors: {
        // Palette Steve Krug specs — slate dark sidebar + blue-600 accent
        primary: {
          DEFAULT: '#2563eb', // blue-600 — WCAG 4.5:1 sur blanc, reconnu "action"
          dark:    '#1d4ed8', // blue-700
          light:   '#dbeafe', // blue-100
        },
        sidebar: {
          bg:     '#1e293b', // slate-800
          text:   '#94a3b8', // slate-400
          hover:  '#f1f5f9', // slate-100
          active: '#334155', // slate-700
          accent: '#3b82f6', // blue-500
        },
      },
      fontFamily: {
        // System stack — aucune dépendance Google Fonts (outil interne, Pi5 potentiellement hors-ligne)
        sans: [
          'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont',
          '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif',
        ],
      },
    },
  },
  plugins: [],
};
