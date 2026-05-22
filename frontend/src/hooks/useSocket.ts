import { useEffect, useReducer, useRef } from 'react'
import { io, Socket } from 'socket.io-client'
import type {
  ProjectState, Agent, Task, LogEntry, NetMessage,
  ReviewerResult, CoordLogEntry, MailboxMessage, AcceptanceCriterion,
  StageName, ValidationVerdict,
} from '../types'
import { useAuthFetch } from './useAuthFetch'

const INITIAL: ProjectState = {
  project: '',
  sprint: '',
  feature: '',
  progress: 0,
  elapsedSeconds: 0,
  agents: [],
  tasks: [],
  log: [],
  changedFiles: 0,
  changedFileNames: [],
  terminalLines: [],
  running: false,
  messages: [],
  selectedAgentIds: null,
  // stage tracking
  currentStage: 'idle',
  stageParticipants: [],
  // coordination state
  reviewerResult: null,
  reviewerActive: false,
  coordLog: [],
  fileLocks: {},
  mailbox: [],
  // stage artifacts
  researchReports: [],
  planReports: [],
  validationVerdicts: [],
  validationResult: null,
  reworkNotice: null,
}

type Action =
  | { type: 'INIT'; project: string; sprint: string; agents: Agent[] }
  | { type: 'UPDATE_AGENTS'; agents: Agent[] }
  | { type: 'START' }
  | { type: 'FEATURE_SET'; feature: string }
  | { type: 'TASKS_INIT'; tasks: Task[] }
  | { type: 'AGENT_UPDATE'; agentId: string; status: Agent['status'] }
  | { type: 'TASK_UPDATE'; taskId: string }
  | { type: 'LOG'; entry: LogEntry }
  | { type: 'MSG'; from: string; to: string }
  | { type: 'AGENTS_SELECTED'; agentIds: string[] }
  | { type: 'FILE_UPDATE'; count: number; files: string[] }
  | { type: 'TERMINAL'; line: string }
  | { type: 'TICK' }
  | { type: 'DONE' }
  // coordination actions
  | { type: 'STAGE_START'; stage: StageName; participants: string[] }
  | { type: 'REVIEWER_STARTED' }
  | { type: 'REVIEWER_RESULT'; result: ReviewerResult }
  | { type: 'REVIEWER_RETRY'; taskIds: string[] }
  | { type: 'RUN_RESUMABLE'; runId: string; brief: string; startedAt: string }
  | { type: 'COORD_LOG'; entry: CoordLogEntry }
  | { type: 'FILE_LOCKED'; path: string; agentId: string }
  | { type: 'FILE_UNLOCKED'; path: string }
  | { type: 'MAILBOX_MSG'; msg: MailboxMessage }
  // stage actions
  | { type: 'RESEARCH_REPORT'; agentId: string; report: string }
  | { type: 'PLAN_REPORT'; agentId: string; spec: string }
  | { type: 'VALIDATION_VERDICT'; agentId: string; approved: boolean;
      summary: string; issues: { severity: string; description: string }[] }
  | { type: 'VALIDATION_COMPLETE'; overallApproved: boolean; verdicts: ValidationVerdict[] }
  | { type: 'REWORK_NEEDED'; issues: { severity: string; description: string }[]; reworkTaskCount: number }
  | { type: 'THINKING_CONTENT'; agentId: string; content: string }
  | { type: 'RUN_TIMEOUT'; runId: string; elapsedSeconds: number }
  | { type: 'AGENT_ACTIVITY'; agentId: string }

function reducer(state: ProjectState, action: Action): ProjectState {
  switch (action.type) {
    case 'INIT':
      return {
        ...state,
        project: action.project,
        sprint: action.sprint,
        agents: action.agents.map(a => ({ ...a, status: 'idle' as const })),
      }

    case 'START':
      return {
        ...state,
        running: true,
        feature: '',
        tasks: [],
        progress: 0,
        elapsedSeconds: 0,
        log: [],
        terminalLines: [],
        changedFiles: 0,
        changedFileNames: [],
        messages: [],
        selectedAgentIds: null,
        agents: state.agents.map(a => ({ ...a, status: 'idle' as const })),
        // reset coordination state
        reviewerResult: null,
        reviewerActive: false,
        coordLog: [],
        fileLocks: {},
        mailbox: [],
      }

    case 'UPDATE_AGENTS':
      return { ...state, agents: action.agents.map(a => ({ ...a, status: 'idle' as const })) }

    case 'FEATURE_SET':
      return { ...state, feature: action.feature }

    case 'TASKS_INIT': {
      const tasks: Task[] = action.tasks.map(t => {
        const rawAcc: unknown[] = Array.isArray(t.acceptance) ? t.acceptance : []
        const acceptance: AcceptanceCriterion[] = rawAcc.map((c: unknown) => {
          const item = c as Record<string, unknown>
          return {
            id: String(item.id ?? ''),
            criterion: String(item.criterion ?? ''),
            met: Boolean(item.met),
            note: typeof item.checked_by === 'string' ? `by ${item.checked_by}` : undefined,
          }
        })
        return {
          id: t.id,
          title: t.title ?? '',
          tag: t.tag ?? '',
          assignee: t.tag ?? '',
          done: false,
          acceptance: acceptance.length > 0 ? acceptance : undefined,
        }
      })
      return { ...state, tasks }
    }

    case 'AGENT_UPDATE':
      return {
        ...state,
        agents: state.agents.map(a =>
          a.id === action.agentId
            ? { ...a, status: action.status, lastActivity: Date.now() }
            : a
        ),
      }

    case 'TASK_UPDATE': {
      const tasks = state.tasks.map(t =>
        t.id === action.taskId ? { ...t, done: true } : t
      )
      const done = tasks.filter(t => t.done).length
      return { ...state, tasks, progress: tasks.length ? Math.round((done / tasks.length) * 100) : 0 }
    }

    case 'LOG':
      return {
        ...state,
        log: [...state.log, action.entry].slice(-60),
        agents: state.agents.map(a =>
          a.id === action.entry.agentId
            ? { ...a, lastActivity: Date.now() }
            : a
        ),
      }

    case 'MSG': {
      const now = Date.now()
      const msg: NetMessage = { id: `${now}-${action.from}-${action.to}`, from: action.from, to: action.to, at: now }
      const messages = [...state.messages.filter(m => now - m.at < 3000), msg]
      return { ...state, messages }
    }

    case 'AGENTS_SELECTED':
      return { ...state, selectedAgentIds: action.agentIds }

    case 'FILE_UPDATE':
      return { ...state, changedFiles: action.count, changedFileNames: action.files }

    case 'TERMINAL':
      return { ...state, terminalLines: [...state.terminalLines, action.line].slice(-30) }

    case 'TICK':
      return { ...state, elapsedSeconds: state.elapsedSeconds + 1 }

    case 'DONE':
      return {
        ...state,
        running: false,
        messages: [],
        selectedAgentIds: null,
        reviewerActive: false,
        fileLocks: {},
      }

    // ── coordination actions ──────────────────────────────────────────────────

    case 'REVIEWER_STARTED':
      return { ...state, reviewerActive: true, reviewerResult: null }

    case 'REVIEWER_RESULT':
      return { ...state, reviewerActive: false, reviewerResult: action.result }

    case 'REVIEWER_RETRY':
      // Future: trigger retry of failed tasks. No-op for now.
      return state

    case 'RUN_RESUMABLE':
      // Future: surface a "Resume?" prompt. Logged to terminal for now.
      return {
        ...state,
        terminalLines: [
          ...state.terminalLines,
          `[resumable] Run ${action.runId.slice(0, 8)}… interrupted at ${action.startedAt.slice(11, 19)} — "${action.brief.slice(0, 60)}"`,
        ].slice(-30),
      }

    case 'COORD_LOG':
      return { ...state, coordLog: [...state.coordLog, action.entry].slice(-100) }

    case 'FILE_LOCKED': {
      const fileLocks = { ...state.fileLocks, [action.path]: action.agentId }
      return { ...state, fileLocks }
    }

    case 'FILE_UNLOCKED': {
      const { [action.path]: _, ...rest } = state.fileLocks
      return { ...state, fileLocks: rest }
    }

    case 'MAILBOX_MSG':
      return { ...state, mailbox: [...state.mailbox, action.msg].slice(-50) }

    // ── stage actions ──────────────────────────────────────────────────────

    case 'STAGE_START':
      return {
        ...state,
        currentStage: action.stage,
        stageParticipants: action.participants,
      }

    case 'RESEARCH_REPORT':
      return {
        ...state,
        researchReports: [
          ...state.researchReports.filter(r => r.agentId !== action.agentId),
          { agentId: action.agentId, report: action.report },
        ],
      }

    case 'PLAN_REPORT':
      return {
        ...state,
        planReports: [
          ...state.planReports.filter(r => r.agentId !== action.agentId),
          { agentId: action.agentId, spec: action.spec },
        ],
      }

    case 'VALIDATION_VERDICT':
      return {
        ...state,
        validationVerdicts: [
          ...state.validationVerdicts.filter(v => v.agentId !== action.agentId),
          {
            agentId: action.agentId,
            approved: action.approved,
            summary: action.summary,
            issues: action.issues,
          },
        ],
      }

    case 'VALIDATION_COMPLETE':
      return {
        ...state,
        validationResult: {
          overallApproved: action.overallApproved,
          verdicts: action.verdicts,
        },
      }

    case 'REWORK_NEEDED':
      return {
        ...state,
        reworkNotice: {
          issues: action.issues,
          reworkTaskCount: action.reworkTaskCount,
        },
        terminalLines: [
          ...state.terminalLines,
          `[rework] ${action.issues.length} issue(s) found — ${action.reworkTaskCount} rework tasks created`,
        ].slice(-30),
      }

    case 'THINKING_CONTENT':
      return {
        ...state,
        terminalLines: [
          ...state.terminalLines,
          `[think·${action.agentId}] ${action.content.slice(0, 120)}`,
        ].slice(-30),
      }

    case 'RUN_TIMEOUT':
      return {
        ...state,
        terminalLines: [
          ...state.terminalLines,
          `⏱ Run ${action.runId.slice(0, 8)} timed out after ${action.elapsedSeconds}s`,
        ].slice(-30),
        running: false,
      }

    case 'AGENT_ACTIVITY':
      return {
        ...state,
        agents: state.agents.map(a =>
          a.id === action.agentId
            ? { ...a, lastActivity: Date.now() }
            : a
        ),
      }

    default:
      return state
  }
}

export function useSocket() {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const socketRef = useRef<Socket | null>(null)
  const authFetch = useAuthFetch()

  useEffect(() => {
    const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || undefined
    const socket = io(SOCKET_URL, { path: '/socket.io', transports: ['websocket', 'polling'] })
    socketRef.current = socket

    socket.on('init', ({ project, sprint, agents }: { project: string; sprint: string; agents: Agent[] }) =>
      dispatch({ type: 'INIT', project, sprint, agents }))

    socket.on('feature_set', ({ feature }: { feature: string }) =>
      dispatch({ type: 'FEATURE_SET', feature }))

    socket.on('tasks_init', ({ tasks }: { tasks: Task[] }) =>
      dispatch({ type: 'TASKS_INIT', tasks }))

    socket.on('agent_update', ({ agentId, status }: { agentId: string; status: Agent['status'] }) =>
      dispatch({ type: 'AGENT_UPDATE', agentId, status }))

    socket.on('task_update', ({ taskId }: { taskId: string }) =>
      dispatch({ type: 'TASK_UPDATE', taskId }))

    socket.on('log_update', (entry: LogEntry) => {
      dispatch({ type: 'LOG', entry })
      const match = entry.message.match(/^→\s+(\S+?):/)
      if (match) dispatch({ type: 'MSG', from: entry.agentId, to: match[1] })
    })

    socket.on('file_update', ({ count, files }: { count: number; files: string[] }) =>
      dispatch({ type: 'FILE_UPDATE', count, files: files ?? [] }))

    socket.on('terminal_line', ({ line }: { line: string }) =>
      dispatch({ type: 'TERMINAL', line }))

    socket.on('agents_selected', ({ agentIds }: { agentIds: string[] }) =>
      dispatch({ type: 'AGENTS_SELECTED', agentIds }))

    socket.on('run_done', () => dispatch({ type: 'DONE' }))

    // ── coordination events ───────────────────────────────────────────────────

    socket.on('reviewer_started', () =>
      dispatch({ type: 'REVIEWER_STARTED' }))

    socket.on('reviewer_result', ({ result }: { result: ReviewerResult }) =>
      dispatch({ type: 'REVIEWER_RESULT', result }))

    socket.on('reviewer_retry', ({ taskIds }: { taskIds: string[] }) =>
      dispatch({ type: 'REVIEWER_RETRY', taskIds }))

    socket.on('run_resumable', ({ runId, brief, startedAt }: { runId: string; brief: string; startedAt: string }) =>
      dispatch({ type: 'RUN_RESUMABLE', runId, brief, startedAt }))

    socket.on('coordinator_log', ({ entry }: { entry: CoordLogEntry }) =>
      dispatch({ type: 'COORD_LOG', entry }))

    socket.on('file_locked', ({ path, agentId }: { path: string; agentId: string }) =>
      dispatch({ type: 'FILE_LOCKED', path, agentId }))

    socket.on('file_unlocked', ({ path }: { path: string }) =>
      dispatch({ type: 'FILE_UNLOCKED', path }))

    socket.on('file_conflict', ({ path, requestingAgent, holdingAgent }: {
      path: string; requestingAgent: string; holdingAgent: string
    }) => {
      dispatch({
        type: 'TERMINAL',
        line: `[conflict] ${path}: ${requestingAgent} overwrote ${holdingAgent}'s lock`,
      })
    })

    socket.on('mailbox_msg', (msg: MailboxMessage) =>
      dispatch({ type: 'MAILBOX_MSG', msg }))

    // ── stage events ───────────────────────────────────────────────────────

    socket.on('stage_start', ({ stage, participants }: { stage: StageName; participants: string[] }) =>
      dispatch({ type: 'STAGE_START', stage, participants }))

    socket.on('research_report', ({ agentId, report }: { agentId: string; report: string }) =>
      dispatch({ type: 'RESEARCH_REPORT', agentId, report }))

    socket.on('research_complete', ({ summary, agentCount }: { summary: string; agentCount: number }) => {
      dispatch({
        type: 'TERMINAL',
        line: `[research] ${agentCount} agent(s) completed research — ${summary.slice(0, 80)}`,
      })
    })

    socket.on('plan_report', ({ agentId, spec }: { agentId: string; spec: string }) =>
      dispatch({ type: 'PLAN_REPORT', agentId, spec }))

    socket.on('plan_complete', ({ feature, taskCount, agentCount }:
      { feature: string; taskCount: number; agentCount: number }) => {
      dispatch({
        type: 'TERMINAL',
        line: `[plan] ${agentCount} planner(s) created ${taskCount} task(s)${feature ? ` — ${feature}` : ''}`,
      })
    })

    socket.on('validation_verdict', (verdict: ValidationVerdict) =>
      dispatch({
        type: 'VALIDATION_VERDICT',
        agentId: verdict.agentId,
        approved: verdict.approved,
        summary: verdict.summary,
        issues: verdict.issues,
      }))

    socket.on('validation_complete', ({ overallApproved, verdicts }:
      { overallApproved: boolean; verdicts: ValidationVerdict[] }) =>
      dispatch({ type: 'VALIDATION_COMPLETE', overallApproved, verdicts }))

    socket.on('rework_needed', ({ issues, reworkTaskCount }:
      { issues: { severity: string; description: string }[]; reworkTaskCount: number }) =>
      dispatch({ type: 'REWORK_NEEDED', issues, reworkTaskCount }))

    socket.on('thinking_content', ({ agentId, content }:
      { agentId: string; content: string }) =>
      dispatch({ type: 'THINKING_CONTENT', agentId, content }))

    socket.on('run_timeout', ({ run_id, elapsed_seconds }:
      { run_id: string; elapsed_seconds: number }) =>
      dispatch({ type: 'RUN_TIMEOUT', runId: run_id, elapsedSeconds: elapsed_seconds }))

    return () => { socket.disconnect() }
  }, [])

  useEffect(() => {
    if (!state.running) return
    const id = setInterval(() => dispatch({ type: 'TICK' }), 1000)
    return () => clearInterval(id)
  }, [state.running])

  const startProject = (brief: string, uploadToken?: string) => {
    authFetch('/api/start-project', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brief, ...(uploadToken ? { upload_token: uploadToken } : {}) }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.status === 'started') {
          if (data.credit_warning) {
            const proceed = window.confirm(data.credit_warning + '\n\nStart anyway?')
            if (!proceed) return
          }
          dispatch({ type: 'START' })
        } else if (data.error === 'run_limit_reached') {
          alert('Monthly run limit reached. Upgrade at /billing to continue.')
        } else if (data.error) {
          alert(`Could not start: ${data.error}`)
        }
      })
      .catch(console.error)
  }

  const cancelProject = () => {
    authFetch('/api/cancel', { method: 'POST' }).catch(console.error)
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const updateAgents = (agents: any[]) =>
    dispatch({ type: 'UPDATE_AGENTS', agents: agents as Agent[] })

  return { state, startProject, cancelProject, updateAgents }
}
