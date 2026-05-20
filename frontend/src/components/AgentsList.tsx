import { motion, AnimatePresence } from 'framer-motion'
import type { Agent } from '../types'

function statusInfo(s: Agent['status']): { label: string; dot: string } {
  if (s === 'done') return { label: 'Done',    dot: '#3b82f6' }
  if (s === 'idle') return { label: 'Idle',    dot: '#4b5563' }
  return              { label: 'Working', dot: '#22c55e' }
}

export default function AgentsList({ agents, count }: { agents: Agent[]; count: number }) {
  return (
    <div>
      <div className="flex justify-between items-center mb-2">
        <span className="text-[10px] tracking-widest font-mono uppercase" style={{ color: 'var(--c-text-3)' }}>Agents</span>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--c-surface-3)', color: 'var(--c-text-2)' }}>{count}</span>
      </div>
      <div className="space-y-1.5">
        {agents.map(agent => (
          <div
            key={agent.id}
            className="flex items-center justify-between px-2 py-1.5 rounded"
            style={{ background: 'var(--c-surface-3)', border: '1px solid var(--c-border)' }}
          >
            <div className="flex items-center gap-2">
              <div
                className="w-6 h-6 rounded flex items-center justify-center text-xs"
                style={{ background: `${agent.color}33` }}
              >
                {agent.icon}
              </div>
              <span className="text-xs font-mono" style={{ color: 'var(--c-text-1)' }}>{agent.name}</span>
            </div>
            <AnimatePresence mode="wait">
              {(() => {
                const { label, dot } = statusInfo(agent.status)
                const pulsing = agent.status !== 'idle' && agent.status !== 'done'
                return (
                  <motion.div
                    key={label}
                    initial={{ opacity: 0, x: 4 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -4 }}
                    className="flex items-center gap-1.5"
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${pulsing ? 'animate-pulse' : ''}`} style={{ background: dot }} />
                    <span className="text-[10px] font-mono" style={{ color: 'var(--c-text-2)' }}>{label}</span>
                  </motion.div>
                )
              })()}
            </AnimatePresence>
          </div>
        ))}
      </div>
    </div>
  )
}
