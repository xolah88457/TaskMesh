import AgentsList from './AgentsList'
import TasksList from './TasksList'
import Terminal from './Terminal'
import ReviewerPanel from './ReviewerPanel'
import type { Agent, Task, ReviewerResult } from '../types'

interface Props {
  agents: Agent[]
  tasks: Task[]
  changedFiles: number
  changedFileNames: string[]
  terminalLines: string[]
  reviewerActive?: boolean
  reviewerResult?: ReviewerResult | null
}

export default function Sidebar({
  agents, tasks, changedFiles, changedFileNames, terminalLines,
  reviewerActive = false, reviewerResult = null,
}: Props) {
  return (
    <div
      className="flex flex-col gap-3 p-3 overflow-y-auto w-full h-full backdrop-blur-sm"
      style={{ borderLeft: '1px solid var(--c-border)', background: 'var(--c-surface-2)' }}
    >
      <AgentsList agents={agents} count={agents.length} />

      {tasks.length > 0 && (
        <div className="pt-3" style={{ borderTop: '1px solid var(--c-border)' }}>
          <TasksList tasks={tasks} />
        </div>
      )}

      <div className="pt-3" style={{ borderTop: '1px solid var(--c-border)' }}>
        <div className="flex justify-between items-center mb-1">
          <span className="text-[10px] tracking-widest font-mono uppercase" style={{ color: 'var(--c-text-3)' }}>Changed Files</span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--c-surface-3)', color: 'var(--c-text-2)' }}>{changedFiles}</span>
        </div>
        {changedFileNames.slice(0, 6).map(f => (
          <div key={f} className="text-[9px] font-mono truncate pl-1 leading-4" style={{ color: 'var(--c-text-4)' }}>{f}</div>
        ))}
        {changedFileNames.length > 6 && (
          <div className="text-[9px] font-mono pl-1" style={{ color: 'var(--c-text-4)' }}>+{changedFileNames.length - 6} more</div>
        )}
      </div>

      <ReviewerPanel active={reviewerActive} result={reviewerResult} />

      <div className="pt-3" style={{ borderTop: '1px solid var(--c-border)' }}>
        <Terminal lines={terminalLines} />
      </div>
    </div>
  )
}
