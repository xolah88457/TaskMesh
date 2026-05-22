export interface ThemeVars {
  '--c-bg': string
  '--c-surface-1': string
  '--c-surface-2': string
  '--c-surface-3': string
  '--c-input-bg': string
  '--c-border': string
  '--c-text-1': string
  '--c-text-2': string
  '--c-text-3': string
  '--c-text-4': string
  '--c-accent': string
  '--c-accent-dim': string
  '--c-accent-border': string
  '--c-terminal': string
  '--rain-color': string
  '--rain-bg': string
  // TM dash elevation tokens (used by Dashboard)
  '--bg-elev': string
  '--bg-elev-2': string
  '--bg-hover': string
  '--border-strong': string
  '--accent-soft': string
  '--danger': string
  '--danger-soft': string
  '--warn': string
  '--info': string
  '--shadow': string
}

export interface Theme {
  id: string
  name: string
  previewBg: string
  previewAccent: string
  previewText: string
  vars: ThemeVars
}

export const THEMES: Theme[] = [
  {
    id: 'default',
    name: 'Black',
    previewBg: '#000000',
    previewAccent: '#4ade80',
    previewText: 'rgba(255,255,255,0.45)',
    vars: {
      '--c-bg':           '#000000',
      '--c-surface-1':    'rgba(14,14,14,0.9)',
      '--c-surface-2':    'rgba(10,10,10,0.7)',
      '--c-surface-3':    'rgba(255,255,255,0.035)',
      '--c-input-bg':     '#111111',
      '--c-border':       'rgba(255,255,255,0.08)',
      '--c-text-1':       'rgba(255,255,255,0.82)',
      '--c-text-2':       'rgba(255,255,255,0.55)',
      '--c-text-3':       'rgba(255,255,255,0.35)',
      '--c-text-4':       'rgba(255,255,255,0.18)',
      '--c-accent':       '#4ade80',
      '--c-accent-dim':   'rgba(74,222,128,0.1)',
      '--c-accent-border':'rgba(74,222,128,0.5)',
      '--c-terminal':     'rgba(0,0,0,0.65)',
      '--rain-color':     '#22c55e',
      '--rain-bg':        'rgba(0,0,0,0.12)',
      '--bg-elev':        '#111111',
      '--bg-elev-2':      '#161616',
      '--bg-hover':       '#1a1a1a',
      '--border-strong':  '#3a3a3a',
      '--accent-soft':    'rgba(74,222,128,0.12)',
      '--danger':         '#ef4444',
      '--danger-soft':    'rgba(239,68,68,0.12)',
      '--warn':           '#f59e0b',
      '--info':           '#60a5fa',
      '--shadow':         '0 8px 24px rgba(0,0,0,0.6)',
    },
  },
  {
    id: 'matrix',
    name: 'Matrix',
    previewBg: '#080c18',
    previewAccent: '#4ade80',
    previewText: 'rgba(255,255,255,0.5)',
    vars: {
      '--c-bg':           '#080c18',
      '--c-surface-1':    'rgba(0,0,0,0.5)',
      '--c-surface-2':    'rgba(0,0,0,0.3)',
      '--c-surface-3':    'rgba(255,255,255,0.04)',
      '--c-input-bg':     '#0d1117',
      '--c-border':       'rgba(255,255,255,0.1)',
      '--c-text-1':       'rgba(255,255,255,0.82)',
      '--c-text-2':       'rgba(255,255,255,0.55)',
      '--c-text-3':       'rgba(255,255,255,0.35)',
      '--c-text-4':       'rgba(255,255,255,0.2)',
      '--c-accent':       '#4ade80',
      '--c-accent-dim':   'rgba(74,222,128,0.1)',
      '--c-accent-border':'rgba(74,222,128,0.5)',
      '--c-terminal':     'rgba(0,0,0,0.4)',
      '--rain-color':     '#4ade80',
      '--rain-bg':        'rgba(8,12,24,0.07)',
      '--bg-elev':        '#111213',
      '--bg-elev-2':      '#171819',
      '--bg-hover':       '#1b1c1d',
      '--border-strong':  '#3a3c3e',
      '--accent-soft':    'rgba(74,222,128,0.12)',
      '--danger':         '#ef4444',
      '--danger-soft':    'rgba(239,68,68,0.12)',
      '--warn':           '#f59e0b',
      '--info':           '#60a5fa',
      '--shadow':         '0 8px 24px rgba(0,0,0,0.6)',
    },
  },
  {
    id: 'tokyo-night',
    name: 'Tokyo Night',
    previewBg: '#1a1b2e',
    previewAccent: '#7aa2f7',
    previewText: 'rgba(169,177,214,0.6)',
    vars: {
      '--c-bg':           '#1a1b2e',
      '--c-surface-1':    'rgba(22,33,62,0.9)',
      '--c-surface-2':    'rgba(22,33,62,0.6)',
      '--c-surface-3':    'rgba(122,162,247,0.04)',
      '--c-input-bg':     '#13141f',
      '--c-border':       'rgba(122,162,247,0.13)',
      '--c-text-1':       '#c0caf5',
      '--c-text-2':       '#a9b1d6',
      '--c-text-3':       '#565f89',
      '--c-text-4':       '#3b4261',
      '--c-accent':       '#7aa2f7',
      '--c-accent-dim':   'rgba(122,162,247,0.1)',
      '--c-accent-border':'rgba(122,162,247,0.45)',
      '--c-terminal':     'rgba(15,20,40,0.7)',
      '--rain-color':     '#7aa2f7',
      '--rain-bg':        'rgba(26,27,46,0.1)',
      '--bg-elev':        '#1f2137',
      '--bg-elev-2':      '#262844',
      '--bg-hover':       '#2a2c49',
      '--border-strong':  '#4a507f',
      '--accent-soft':    'rgba(122,162,247,0.12)',
      '--danger':         '#f7768e',
      '--danger-soft':    'rgba(247,118,142,0.12)',
      '--warn':           '#e0af68',
      '--info':           '#7dcfff',
      '--shadow':         '0 8px 24px rgba(0,0,0,0.5)',
    },
  },
  {
    id: 'light',
    name: 'Light',
    previewBg: '#f0f2f5',
    previewAccent: '#16a34a',
    previewText: 'rgba(0,0,0,0.4)',
    vars: {
      '--c-bg':           '#f0f2f5',
      '--c-surface-1':    'rgba(255,255,255,0.88)',
      '--c-surface-2':    'rgba(255,255,255,0.65)',
      '--c-surface-3':    'rgba(0,0,0,0.03)',
      '--c-input-bg':     '#ffffff',
      '--c-border':       'rgba(0,0,0,0.09)',
      '--c-text-1':       'rgba(0,0,0,0.82)',
      '--c-text-2':       'rgba(0,0,0,0.58)',
      '--c-text-3':       'rgba(0,0,0,0.38)',
      '--c-text-4':       'rgba(0,0,0,0.22)',
      '--c-accent':       '#16a34a',
      '--c-accent-dim':   'rgba(22,163,74,0.08)',
      '--c-accent-border':'rgba(22,163,74,0.45)',
      '--c-terminal':     'rgba(0,0,0,0.05)',
      '--rain-color':     'rgba(0,0,0,0.07)',
      '--rain-bg':        'rgba(240,242,245,0.18)',
      '--bg-elev':        '#f5f3f0',
      '--bg-elev-2':      '#eeebe6',
      '--bg-hover':       '#e8e4de',
      '--border-strong':  '#9c9c9c',
      '--accent-soft':    'rgba(21,128,61,0.08)',
      '--danger':         '#dc2626',
      '--danger-soft':    'rgba(220,38,38,0.08)',
      '--warn':           '#d97706',
      '--info':           '#2563eb',
      '--shadow':         '0 8px 24px rgba(0,0,0,0.1)',
    },
  },
  {
    id: 'solarized',
    name: 'Solarized',
    previewBg: '#fdf6e3',
    previewAccent: '#859900',
    previewText: 'rgba(101,123,131,0.5)',
    vars: {
      '--c-bg':           '#fdf6e3',
      '--c-surface-1':    'rgba(238,232,213,0.92)',
      '--c-surface-2':    'rgba(238,232,213,0.7)',
      '--c-surface-3':    'rgba(147,161,161,0.07)',
      '--c-input-bg':     '#eee8d5',
      '--c-border':       'rgba(147,161,161,0.28)',
      '--c-text-1':       '#586e75',
      '--c-text-2':       '#657b83',
      '--c-text-3':       '#93a1a1',
      '--c-text-4':       '#b0bcbe',
      '--c-accent':       '#859900',
      '--c-accent-dim':   'rgba(133,153,0,0.1)',
      '--c-accent-border':'rgba(133,153,0,0.45)',
      '--c-terminal':     'rgba(238,232,213,0.8)',
      '--rain-color':     'rgba(147,161,161,0.22)',
      '--rain-bg':        'rgba(253,246,227,0.22)',
      '--bg-elev':        '#fdf4df',
      '--bg-elev-2':      '#f8eecc',
      '--bg-hover':       '#f2e6c2',
      '--border-strong':  '#a39171',
      '--accent-soft':    'rgba(133,153,0,0.08)',
      '--danger':         '#dc322f',
      '--danger-soft':    'rgba(220,50,47,0.08)',
      '--warn':           '#b58900',
      '--info':           '#268bd2',
      '--shadow':         '0 8px 24px rgba(0,0,0,0.08)',
    },
  },
]

export const DEFAULT_THEME_ID = 'default'

export function getTheme(id: string): Theme {
  return THEMES.find(t => t.id === id) ?? THEMES[0]
}
