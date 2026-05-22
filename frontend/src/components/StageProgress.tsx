import type { StageName } from '../types'

const STAGES: { key: StageName; label: string; icon: string }[] = [
  { key: 'research',    label: 'Research',   icon: '🔬' },
  { key: 'plan',        label: 'Plan',       icon: '📋' },
  { key: 'production',  label: 'Production', icon: '⚙️' },
  { key: 'validation',  label: 'Approval',   icon: '✅' },
]

interface Props {
  currentStage: StageName
  running: boolean
}

const STAGE_ORDER: StageName[] = ['idle', 'research', 'plan', 'production', 'validation']

export default function StageProgress({ currentStage, running }: Props) {
  if (!running) return null

  const activeIdx = STAGE_ORDER.indexOf(currentStage)

  return (
    <div className="flex items-center gap-1 mb-2" style={{ borderBottom: '1px solid var(--c-border)', paddingBottom: 6 }}>
      {STAGES.map((s, i) => {
        const isActive = s.key === currentStage
        const isDone = activeIdx > i
        const isPending = activeIdx < i

        return (
          <div
            key={s.key}
            className="flex items-center gap-1 px-1.5 py-1 rounded text-[9px] font-mono"
            style={{
              background: isActive ? 'var(--c-accent, #3b82f6)20' : 'transparent',
              color: isActive ? 'var(--c-accent, #3b82f6)' : isDone ? 'var(--c-text-2)' : 'var(--c-text-4)',
              opacity: isPending ? 0.4 : 1,
              fontWeight: isActive ? 700 : 400,
            }}
          >
            <span>{isDone ? '✓' : s.icon}</span>
            <span className="hidden sm:inline">{s.label}</span>
            {i < STAGES.length - 1 && (
              <span className="mx-0.5" style={{ color: 'var(--c-text-4)' }}>→</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
