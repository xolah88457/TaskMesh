/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'neon-green': '#00ff41',
        'neon-cyan': '#00d4ff',
        'neon-purple': '#b44fff',
        'neon-orange': '#ff8c00',
        'agent-bg': '#0a0e1a',
        'panel-bg': 'rgba(10,14,26,0.85)',
        'border-dim': 'rgba(255,255,255,0.08)',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}

