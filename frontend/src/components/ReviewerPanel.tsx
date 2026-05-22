import { motion, AnimatePresence } from 'framer-motion'
import type { ReviewerResult, AcceptanceCriterion } from '../types'

interface Props {
  active: boolean
  result: ReviewerResult | null
  acceptance?: AcceptanceCriterion[]
}

const SEVERITY_COLOR: Record<string, string> = {
  Blocker: '#ef4444',
  Major:   '#f97316',
  Minor:   '#f59e0b',
  Nit:     '#6b7280',
}

export default function ReviewerPanel({ active, result, acceptance }: Props) {
  if (!active && !result) return null

  return (
    <div className="pt-3" style={{ borderTop: '1px solid var(--c-border)' }}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] tracking-widest font-mono uppercase" style={{ color: 'var(--c-text-3)' }}>
          Reviewer
        </span>
        {active && (
          <span
            className="text-[9px] font-mono px-1.5 py-0.5 rounded animate-pulse"
            style={{ background: '#a855f720', color: '#a855f7' }}
          >
            reviewing…
          </span>
        )}
        {result && (
          <span
            className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded"
            style={{
              background: result.approved ? '#22c55e20' : '#ef444420',
              color:      result.approved ? '#22c55e'   : '#ef4444',
            }}
          >
            {result.approved ? '✓ APPROVED' : '✗ REVISION'}
          </span>
        )}
      </div>

      {/* Acceptance criteria section */}
      {acceptance && acceptance.length > 0 && (
        <div className="mb-3 space-y-0.5">
          <span className="text-[8px] tracking-widest font-mono uppercase" style={{ color: 'var(--c-text-4)' }}>
            Acceptance Criteria
          </span>
          {acceptance.map((criterion) => (
            <div
              key={criterion.id}
              className="text-[9px] font-mono px-2 py-1 rounded flex items-start gap-1.5"
              style={{ background: 'var(--c-surface-3)' }}
            >
              <span
                className="shrink-0 font-bold"
                style={{ color: criterion.met ? '#22c55e' : '#ef4444' }}
              >
                {criterion.met ? '✓' : '✗'}
              </span>
              <div>
                <span style={{ color: 'var(--c-text-2)' }}>{criterion.criterion}</span>
                {criterion.note && (
                  <span className="block" style={{ color: 'var(--c-text-4)' }}>
                    {criterion.note}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <AnimatePresence>
        {result && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <p className="text-[9px] font-mono leading-relaxed mb-1.5" style={{ color: 'var(--c-text-2)' }}>
              {result.summary}
            </p>

            {result.issues.length > 0 && (
              <div className="space-y-1">
                {result.issues.slice(0, 5).map((issue, i) => (
                  <div
                    key={i}
                    className="text-[9px] font-mono px-2 py-1 rounded"
                    style={{ background: 'var(--c-surface-3)' }}
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span
                        className="font-bold"
                        style={{ color: SEVERITY_COLOR[issue.severity] ?? '#6b7280' }}
                      >
                        {issue.severity}
                      </span>
                      <span style={{ color: 'var(--c-text-4)' }}>{issue.agent}</span>
                    </div>
                    <div style={{ color: 'var(--c-text-3)' }} className="truncate">{issue.file}</div>
                    <div style={{ color: 'var(--c-text-2)' }}>{issue.issue}</div>
                  </div>
                ))}
                {result.issues.length > 5 && (
                  <p className="text-[9px] font-mono" style={{ color: 'var(--c-text-4)' }}>
                    +{result.issues.length - 5} more issue(s)
                  </p>
                )}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
