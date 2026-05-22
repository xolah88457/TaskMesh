import { useMemo } from 'react'
import AgentsList from './AgentsList'
import TasksList from './TasksList'
import Terminal from './Terminal'
import ReviewerPanel from './ReviewerPanel'
import StageProgress from './StageProgress'
import type {
  Agent, Task, ReviewerResult, AcceptanceCriterion,
  StageName, ValidationVerdict, ValidationResult, ReworkNotice,
} from '../types'

function flattenAcceptance(tasks: Task[]): AcceptanceCriterion[] {
  const out: AcceptanceCriterion[] = []
  for (const t of tasks) {
    if (t.acceptance) out.push(...t.acceptance)
  }
  return out
}

interface Props {
  agents: Agent[]
  tasks: Task[]
  changedFiles: number
  changedFileNames: string[]
  terminalLines: string[]
  running: boolean
  currentStage: StageName
  reviewerActive?: boolean
  reviewerResult?: ReviewerResult | null
  validationVerdicts?: ValidationVerdict[]
  validationResult?: ValidationResult | null
  reworkNotice?: ReworkNotice | null
  onAddAgents?: () => void
}

export default function Sidebar({
  agents, tasks, changedFiles, changedFileNames, terminalLines,
  running, currentStage,
  reviewerActive = false, reviewerResult = null,
  validationVerdicts = [], validationResult = null, reworkNotice = null,
  onAddAgents,
}: Props) {
  const mergedVerdicts: ValidationVerdict[] = useMemo(
    () => [
      ...validationVerdicts,
      ...(validationResult?.verdicts ?? []),
    ].filter((v, i, arr) => arr.findIndex(x => x.agentId === v.agentId) === i),
    [validationVerdicts, validationResult],
  )

  // Flatten acceptance criteria once per task-list change rather than on every render.
  const acceptance = useMemo(() => flattenAcceptance(tasks), [tasks])

  return (
    <div
      className="flex flex-col gap-3 p-3 overflow-y-auto w-full h-full backdrop-blur-sm"
      style={{ borderLeft: '1px solid var(--c-border)', background: 'var(--c-surface-2)' }}
    >
      <StageProgress currentStage={currentStage} running={running} />

      <AgentsList agents={agents} count={agents.length} onAddAgents={onAddAgents} />

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

      {/* Multi-agent validation verdicts */}
      {mergedVerdicts.length > 0 && (
        <div className="pt-3" style={{ borderTop: '1px solid var(--c-border)' }}>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-[10px] tracking-widest font-mono uppercase" style={{ color: 'var(--c-text-3)' }}>Validation</span>
            {validationResult && (
              <span
                className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded"
                style={{
                  background: validationResult.overallApproved ? '#22c55e20' : '#ef444420',
                  color: validationResult.overallApproved ? '#22c55e' : '#ef4444',
                }}
              >
                {validationResult.overallApproved ? '✓ APPROVED' : '✗ REJECTED'}
              </span>
            )}
          </div>
          <div className="space-y-1">
            {mergedVerdicts.slice(0, 4).map((v) => (
              <div
                key={v.agentId}
                className="text-[9px] font-mono px-2 py-1 rounded"
                style={{ background: 'var(--c-surface-3)' }}
              >
                <div className="flex items-center gap-1.5">
                  <span
                    className="font-bold"
                    style={{ color: v.approved ? '#22c55e' : '#ef4444' }}
                  >
                    {v.approved ? '✓' : '✗'}
                  </span>
                  <span style={{ color: 'var(--c-text-2)' }}>{v.agentId}</span>
                </div>
                <div className="truncate" style={{ color: 'var(--c-text-4)' }}>
                  {v.summary.slice(0, 100)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {reworkNotice && (
        <div className="pt-3" style={{ borderTop: '1px solid var(--c-border)', color: '#f97316' }}>
          <span className="text-[10px] tracking-widest font-mono uppercase">Rework needed</span>
          <div className="text-[9px] font-mono mt-1" style={{ color: 'var(--c-text-2)' }}>
            {reworkNotice.issues.length} issue(s) — {reworkNotice.reworkTaskCount} fix tasks created
          </div>
        </div>
      )}

      <ReviewerPanel active={reviewerActive} result={reviewerResult} acceptance={acceptance} />

      <div className="pt-3" style={{ borderTop: '1px solid var(--c-border)' }}>
        <Terminal lines={terminalLines} />
      </div>
    </div>
  )
}
