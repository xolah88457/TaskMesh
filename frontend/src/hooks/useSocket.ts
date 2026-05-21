import { useEffect, useReducer, useRef } from 'react'
import { io, Socket } from 'socket.io-client'
import type {
  ProjectState, Agent, Task, LogEntry, NetMessage,
  ReviewerResult, CoordLogEntry, MailboxMessage,
} from '../types'
import { useAuthContext } from '../context/auth'
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
  // coordination state
  reviewerResult: null,
  reviewerActive: false,
  coordLog: [],
  fileLocks: {},
  mailbox: [],
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
  | { type: 'REVIEWER_STARTED' }
  | { type: 'REVIEWER_RESULT'; result: ReviewerResult }
  | { type: 'COORD_LOG'; entry: CoordLogEntry }
  | { type: 'FILE_LOCKED'; path: string; agentId: string }
  | { type: 'FILE_UNLOCKED'; path: string }
  | { type: 'MAILBOX_MSG'; msg: MailboxMessage }

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
      const tasks: Task[] = action.tasks.map(t => ({
        id: t.id,
        title: t.title ?? '',
        tag: t.tag ?? '',
        assignee: t.tag ?? '',
        done: false,
      }))
      return { ...state, tasks }
    }

    case 'AGENT_UPDATE':
      return {
        ...state,
        agents: state.agents.map(a =>
          a.id === action.agentId ? { ...a, status: action.status } : a
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
      return { ...state, log: [...state.log, action.entry].slice(-60) }

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

    default:
      return state
  }
}

export function useSocket() {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const socketRef = useRef<Socket | null>(null)
  const authFetch = useAuthFetch()
  const { getToken } = useAuthContext()

  useEffect(() => {
    const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || undefined
    const socket = io(SOCKET_URL, { path: '/socket.io', transports: ['websocket', 'polling'] })
    socketRef.current = socket

    // Authenticate the socket so the backend joins this connection to the user's room.
    // Room-scoping ensures each user only receives events from their own runs.
    getToken().then(token => {
      if (token && token !== 'dev-token') {
        socket.emit('auth', { token })
      }
    }).catch(() => {})

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
    // NOTE: reviewer_started / reviewer_result / reviewer_retry are reserved for a
    // future Phase 4 reviewer gate. The orchestrator does not emit them yet; the
    // reviewer agent runs as a regular executor today. Re-add the listeners here
    // when the orchestrator gains a dedicated reviewer phase.

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
