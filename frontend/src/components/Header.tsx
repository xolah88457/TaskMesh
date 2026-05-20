import { useRef, useCallback } from 'react'
import logo from '../assets/logo.png'
import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { useAuthContext } from '../context/auth'

interface Props {
  project: string
  sprint: string
  feature: string
  progress: number
  elapsedSeconds: number
  running: boolean
  onStart: (brief: string) => void
  onStop: () => void
  onSettings: () => void
}

function pad(n: number) { return String(n).padStart(2, '0') }

const TEXTAREA_MAX_H = 140

export default function Header({ project, sprint, feature, progress, elapsedSeconds, running, onStart, onStop, onSettings }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { user }    = useAuthContext()
  const mm = pad(Math.floor(elapsedSeconds / 60))
  const ss = pad(elapsedSeconds % 60)
  const displayFeature = feature || (running ? '…' : 'Ready')

  const autoResize = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, TEXTAREA_MAX_H) + 'px'
    el.style.overflowY = el.scrollHeight > TEXTAREA_MAX_H ? 'auto' : 'hidden'
  }, [])

  const handleStart = () => {
    const val = textareaRef.current?.value.trim() ?? ''
    const brief = val || `Build the next feature for the ${project || 'project'}.`
    onStart(brief)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (running) onStop()
      else handleStart()
    }
  }

  return (
    <div className="flex items-start gap-3 px-4 py-2 border-b shrink-0 z-20 relative backdrop-blur-sm"
      style={{ background: 'var(--c-surface-1)', borderColor: 'var(--c-border)' }}>
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs font-mono shrink-0 h-7 self-center">
        <img src={logo} alt="TaskMesh" className="h-5 w-auto shrink-0" />
        {project && <>
          <span className="text-[var(--c-text-4)]">›</span>
          <span className="text-[var(--c-text-1)] whitespace-nowrap">{project}</span>
        </>}
        {sprint && <>
          <span className="text-[var(--c-text-4)]">›</span>
          <span className="text-[var(--c-text-2)] whitespace-nowrap">{sprint}</span>
        </>}
        <span className="text-[var(--c-text-4)]">›</span>
        <span className="text-[var(--c-text-1)] font-medium whitespace-nowrap">{displayFeature}</span>
      </div>

      {/* Expandable brief textarea + start */}
      <div className="flex items-start gap-2 flex-1 min-w-0">
        <textarea
          ref={textareaRef}
          rows={1}
          onInput={autoResize}
          onKeyDown={handleKeyDown}
          disabled={running}
          placeholder="Describe your project goal… (Enter to start, Shift+Enter for newline)"
          className="flex-1 min-w-0 text-xs font-mono rounded px-2 py-1.5 focus:outline-none disabled:opacity-40 resize-none leading-relaxed"
          style={{
            height: '30px',
            overflowY: 'hidden',
            maxHeight: TEXTAREA_MAX_H,
            background: 'var(--c-input-bg)',
            border: '1px solid var(--c-border)',
            color: 'var(--c-text-1)',
          }}
        />
        {running ? (
          <button
            onClick={onStop}
            className="text-xs font-mono px-3 py-1.5 rounded transition-colors shrink-0 h-7 self-start"
            style={{ border: '1px solid rgba(239,68,68,0.5)', color: '#ef4444' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'rgba(239,68,68,0.1)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            ■ Stop
          </button>
        ) : (
          <button
            onClick={handleStart}
            className="text-xs font-mono px-3 py-1.5 rounded transition-colors shrink-0 h-7 self-start"
            style={{ border: '1px solid var(--c-accent-border)', color: 'var(--c-accent)' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--c-accent-dim)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            ▶ Start
          </button>
        )}
      </div>

      {/* Progress + timer + settings */}
      <div className="flex items-center gap-3 shrink-0 self-center h-7">
        <div className="flex items-center gap-2 text-xs font-mono">
          <div className="w-20 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--c-surface-3)' }}>
            <motion.div
              className="h-full rounded-full"
              style={{ background: 'var(--c-accent)' }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.4 }}
            />
          </div>
          <span className="text-[var(--c-text-2)] w-7 text-right tabular-nums">{progress}%</span>
        </div>
        <span className="font-mono text-xs tabular-nums" style={{ color: 'var(--c-text-3)' }}>{mm}:{ss}</span>

        {/* Settings button */}
        <button
          onClick={onSettings}
          className="flex items-center gap-1 text-xs font-mono px-3 py-1 rounded transition-colors"
          style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-2)', height: 28 }}
          title="Settings"
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-text-1)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-2)')}
        >
          ⚙ Settings
        </button>

        <Link
          to="/projects"
          className="text-xs px-1.5 py-1 rounded transition-colors font-mono"
          style={{ color: 'var(--c-text-3)', border: '1px solid var(--c-border)' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-text-1)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-3)')}
          title="Projects"
        >
          📁
        </Link>
        <Link
          to="/billing"
          className="text-xs px-1.5 py-1 rounded transition-colors font-mono"
          style={{ color: 'var(--c-text-3)', border: '1px solid var(--c-border)' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-text-1)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-3)')}
          title="Billing"
        >
          ✦
        </Link>

        {/* Account pill — links to /account, never logs out */}
        {user && (
          <Link
            to="/account"
            className="text-[10px] font-mono px-2 py-1 rounded transition-colors max-w-[100px] truncate"
            style={{ color: 'var(--c-text-3)', border: '1px solid var(--c-border)' }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-text-1)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-3)')}
            title={user.email}
          >
            {user.name || user.email.split('@')[0]}
          </Link>
        )}
      </div>
    </div>
  )
}
