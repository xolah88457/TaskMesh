import { useEffect, useMemo, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { LogEntry, Agent } from '../types'

interface Props {
  log: LogEntry[]
  agents: Agent[]
}

export default function LiveActivity({ log, agents }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const colorMap = useMemo(() => Object.fromEntries(agents.map(a => [a.id, a.color])), [agents])
  const getColor = (id: string) => colorMap[id] ?? '#6b7280'

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [log])

  return (
    <div className="w-full h-full flex flex-col overflow-hidden" style={{ borderTop: '1px solid var(--c-border)', background: 'var(--c-surface-2)' }}>
      <div className="px-4 pt-2 pb-1 shrink-0 flex items-center gap-2">
        <span className="text-[10px] tracking-widest font-mono uppercase" style={{ color: 'var(--c-text-3)' }}>Live Activity</span>
        <span className="text-[9px] font-mono" style={{ color: 'var(--c-text-4)' }}>{log.length} events</span>
      </div>
      <div ref={ref} className="flex-1 overflow-y-auto px-4 pb-2 min-h-0">
        <AnimatePresence initial={false}>
          {log.map((entry, i) => (
            <motion.div
              // Composite key — entries are append-only with .slice(-60),
              // so combining time + agent + position keeps stable identity
              // across re-renders without relying on positional index alone.
              key={`${entry.time}-${entry.agentId}-${i}`}
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-2 text-[10px] font-mono py-[1px]"
            >
              <span className="tabular-nums shrink-0 w-8" style={{ color: 'var(--c-text-4)' }}>{entry.time}</span>
              <span
                className="px-1 rounded text-[9px] font-bold shrink-0 leading-4"
                style={{
                  background: `${getColor(entry.agentId)}20`,
                  color: getColor(entry.agentId),
                  minWidth: '26px',
                  textAlign: 'center',
                }}
              >
                {entry.agentId.toUpperCase().slice(0, 3)}
              </span>
              <span className="leading-4 break-words min-w-0" style={{ color: 'var(--c-text-2)' }}>{entry.message}</span>
            </motion.div>
          ))}
        </AnimatePresence>
        {log.length === 0 && (
          <span className="text-[10px] font-mono" style={{ color: 'var(--c-text-4)' }}>Waiting for run to start…</span>
        )}
      </div>
    </div>
  )
}
