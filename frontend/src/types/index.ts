export type AgentStatus = 'idle' | 'thinking' | 'coding' | 'delegating' | 'waiting' | 'done'

export interface Agent {
  id: string
  name: string
  role: string
  status: AgentStatus
  color: string
  icon: string
  model?: string
  lastActivity?: number   // timestamp for heartbeat idle detection
}

export interface AcceptanceCriterion {
  id: string
  criterion: string
  met: boolean
  note?: string
}

export interface Task {
  id: string
  title: string
  assignee: string
  tag: string
  done: boolean
  acceptance?: AcceptanceCriterion[]
}

export interface LogEntry {
  time: string
  agentId: string
  message: string
}

export interface NetMessage {
  id: string
  from: string
  to: string
  at: number
}

// ── coordination types ────────────────────────────────────────────────────────

export type StageName = 'idle' | 'research' | 'plan' | 'production' | 'validation'

export interface ResearchReport {
  agentId: string
  report: string
}

export interface PlanReport {
  agentId: string
  spec: string
}

export interface ValidationVerdict {
  agentId: string
  approved: boolean
  summary: string
  issues: { severity: string; description: string }[]
  criteria_results?: Record<string, { met: boolean; note?: string }>
}

export interface ValidationResult {
  overallApproved: boolean
  verdicts: ValidationVerdict[]
}

export interface ReworkNotice {
  issues: { severity: string; description: string }[]
  reworkTaskCount: number
}

export interface ReviewerIssue {
  file: string
  issue: string
  severity: 'Blocker' | 'Major' | 'Minor' | 'Nit'
  agent: string
}

export interface ReviewerResult {
  approved: boolean
  summary: string
  issues: ReviewerIssue[]
}

export interface CoordLogEntry {
  type: string
  content: string
  timestamp: string
  metadata: Record<string, string>
}

export interface MailboxMessage {
  id: string
  from: string
  to: string
  content: string
  type: 'message' | 'blocker' | 'feedback' | 'approval'
  timestamp: string
  read: boolean
}

export interface FileLock {
  path: string
  agentId: string
}

// ── full app state ─────────────────────────────────────────────────────────────

export interface ProjectState {
  project: string
  sprint: string
  feature: string
  progress: number
  elapsedSeconds: number
  agents: Agent[]
  tasks: Task[]
  log: LogEntry[]
  changedFiles: number
  changedFileNames: string[]
  terminalLines: string[]
  running: boolean
  messages: NetMessage[]
  selectedAgentIds: string[] | null
  // stage tracking
  currentStage: StageName
  stageParticipants: string[]
  // coordination state
  reviewerResult: ReviewerResult | null
  reviewerActive: boolean
  coordLog: CoordLogEntry[]
  fileLocks: Record<string, string>   // path -> agentId
  mailbox: MailboxMessage[]
  // stage artifacts
  researchReports: ResearchReport[]
  planReports: PlanReport[]
  validationVerdicts: ValidationVerdict[]
  validationResult: ValidationResult | null
  reworkNotice: ReworkNotice | null
}
