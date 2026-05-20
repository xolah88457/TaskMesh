import { motion } from 'framer-motion'
import type { Task } from '../types'

const TAG_COLORS: Record<string, string> = {
  MGR: '#6366f1',
  WEB: '#8b5cf6',
  FE:  '#22c55e',
  BE:  '#f97316',
  QA:  '#ef4444',
}

export default function TasksList({ tasks }: { tasks: Task[] }) {
  const done = tasks.filter(t => t.done).length

  return (
    <div>
      <div className="flex justify-between items-center mb-2">
        <span className="text-[10px] tracking-widest font-mono uppercase" style={{ color: 'var(--c-text-3)' }}>Tasks</span>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--c-surface-3)', color: 'var(--c-text-2)' }}>
          {done} / {tasks.length}
        </span>
      </div>
      <div className="space-y-1">
        {tasks.map(task => (
          <div key={task.id} className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <motion.div
                className="w-3.5 h-3.5 rounded flex items-center justify-center shrink-0"
                style={{
                  background: task.done ? 'rgba(59,130,246,0.3)' : 'transparent',
                  border: task.done ? '1px solid #3b82f6' : '1px solid var(--c-border)',
                }}
                animate={{ scale: task.done ? [1.3, 1] : 1 }}
              >
                {task.done && <span className="text-[8px]" style={{ color: '#60a5fa' }}>✓</span>}
              </motion.div>
              <span
                className={`text-[11px] font-mono truncate ${task.done ? 'line-through' : ''}`}
                style={{ color: task.done ? 'var(--c-text-4)' : 'var(--c-text-2)' }}
              >
                {task.title}
              </span>
            </div>
            <span
              className="text-[9px] font-mono px-1 py-0.5 rounded shrink-0"
              style={{
                background: `${TAG_COLORS[task.tag] ?? '#6b7280'}22`,
                color: TAG_COLORS[task.tag] ?? '#6b7280',
              }}
            >
              {task.tag}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
