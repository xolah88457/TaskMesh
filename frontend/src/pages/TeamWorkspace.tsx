import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuthFetch } from '../hooks/useAuthFetch'
import { useTeamSocket, type TeamMember, type TeamTask, type TeamMessage } from '../hooks/useTeamSocket'

interface TeamSnapshot {
  team:     { id: string; name: string; description: string | null; status: string; created_at: string | null; updated_at: string | null }
  members:  TeamMember[]
  tasks:    TeamTask[]
  messages: TeamMessage[]
}

const COLUMNS: { key: TeamTask['status']; label: string }[] = [
  { key: 'pending',     label: 'Pending'     },
  { key: 'in_progress', label: 'In progress' },
  { key: 'done',        label: 'Done'        },
]

export default function TeamWorkspace() {
  const { id } = useParams<{ id: string }>()
  const navigate  = useNavigate()
  const authFetch = useAuthFetch()
  const [snap, setSnap]   = useState<TeamSnapshot | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  // Task creation form state
  const [taskTitle, setTaskTitle]   = useState('')
  const [taskDesc,  setTaskDesc]    = useState('')
  const [taskDeps,  setTaskDeps]    = useState<string[]>([])
  const [taskAssignee, setTaskAssignee] = useState<string>('')

  // Member spawn form state
  const [memberOpen, setMemberOpen]       = useState(false)
  const [memberName, setMemberName]       = useState('')
  const [memberType, setMemberType]       = useState('generic')
  const [memberPrompt, setMemberPrompt]   = useState('')
  const [memberModel,  setMemberModel]    = useState('')

  // Message form
  const [msgFrom, setMsgFrom] = useState('user')
  const [msgTo,   setMsgTo]   = useState('all')
  const [msgText, setMsgText] = useState('')

  useEffect(() => {
    if (!id) return
    authFetch(`/api/teams/${id}`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then((d: TeamSnapshot) => setSnap(d))
      .catch(() => setError('Team not found'))
      .finally(() => setLoading(false))
  }, [id])

  useTeamSocket(id ?? null, {
    onTaskUpdate: (t) => setSnap(prev => prev ? {
      ...prev,
      tasks: upsertById(prev.tasks, t),
    } : prev),
    onMemberUpdate: (m) => setSnap(prev => prev ? {
      ...prev,
      members: upsertById(prev.members, m),
    } : prev),
    onMemberRemoved: (mid) => setSnap(prev => prev ? {
      ...prev,
      members: prev.members.filter(x => x.id !== mid),
    } : prev),
    onMessage: (m) => setSnap(prev => prev ? {
      ...prev,
      messages: [...prev.messages, m].slice(-200),
    } : prev),
    onTeamDeleted: () => { navigate('/teams', { replace: true }) },
  })

  const tasksByStatus = useMemo(() => {
    const out: Record<string, TeamTask[]> = { pending: [], in_progress: [], done: [], blocked: [], failed: [] }
    snap?.tasks.forEach(t => {
      ;(out[t.status] ||= []).push(t)
    })
    return out
  }, [snap?.tasks])

  if (loading) return <Frame><p className="text-xs">Loading team…</p></Frame>
  if (error || !snap) return <Frame><p className="text-xs" style={{ color: '#ef4444' }}>{error || 'Team not found'}</p></Frame>

  const team = snap.team
  const memberById = (id: string | null) => snap.members.find(m => m.id === id) || null

  const isBlocked = (t: TeamTask): boolean => {
    if (!t.depends_on?.length) return false
    return t.depends_on.some(depId => {
      const dep = snap.tasks.find(x => x.id === depId)
      return dep ? dep.status !== 'done' : true
    })
  }

  const createTask = async () => {
    if (taskTitle.trim().length < 2) return
    try {
      await authFetch(`/api/teams/${team.id}/tasks`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          title:       taskTitle.trim(),
          description: taskDesc.trim(),
          depends_on:  taskDeps,
          assigned_to: taskAssignee || null,
        }),
      })
      setTaskTitle('')
      setTaskDesc('')
      setTaskDeps([])
      setTaskAssignee('')
    } catch {
      setError('Failed to create task')
    }
  }

  const claimTask = async (taskId: string, memberId: string) => {
    if (!memberId) return
    const r = await authFetch(`/api/teams/${team.id}/tasks/${taskId}/claim`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ member_id: memberId }),
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      const code = (typeof d.detail === 'string' ? d.detail : d.detail?.error) || 'failed'
      setError(`Claim failed: ${code}`)
    }
  }

  const executeTask = async (taskId: string, memberId: string) => {
    if (!memberId) return
    const r = await authFetch(`/api/teams/${team.id}/tasks/${taskId}/execute`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ member_id: memberId }),
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      const code = (typeof d.detail === 'string' ? d.detail : d.detail?.error) || 'failed'
      setError(`Execute failed: ${code}`)
    }
  }

  const completeTask = async (taskId: string) => {
    const result = window.prompt('Result note (optional):', '') ?? ''
    await authFetch(`/api/teams/${team.id}/tasks/${taskId}/complete`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ result }),
    })
  }

  const spawnMember = async () => {
    if (memberName.trim().length < 1) return
    const r = await authFetch(`/api/teams/${team.id}/members`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        name:         memberName.trim(),
        agent_type:   memberType.trim() || 'generic',
        model:        memberModel.trim() || null,
        spawn_prompt: memberPrompt.trim(),
        is_lead:      false,
      }),
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      const code = (typeof d.detail === 'string' ? d.detail : d.detail?.error) || 'failed'
      setError(`Spawn failed: ${code}`)
      return
    }
    setMemberName(''); setMemberType('generic'); setMemberPrompt(''); setMemberModel('')
    setMemberOpen(false)
  }

  const shutdownMember = async (mid: string, nm: string) => {
    if (!window.confirm(`Shut down "${nm}"? In-progress tasks will be returned to pending.`)) return
    await authFetch(`/api/teams/${team.id}/members/${mid}`, { method: 'DELETE' })
  }

  const sendMessage = async () => {
    if (msgText.trim().length < 1) return
    await authFetch(`/api/teams/${team.id}/messages`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ from_member: msgFrom, to_member: msgTo, content: msgText.trim() }),
    })
    setMsgText('')
  }

  return (
    <Frame>
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 shrink-0 border-b" style={{ background: 'var(--c-surface-1)', borderColor: 'var(--c-border)' }}>
        <button
          onClick={() => navigate('/teams')}
          className="text-xs px-2 py-1 rounded"
          style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-3)' }}
        >
          ← Teams
        </button>
        <span className="text-[var(--c-accent)] font-bold tracking-widest text-xs">TASKMESH</span>
        <span className="text-[var(--c-text-4)] text-xs">›</span>
        <span className="text-xs">{team.name}</span>
        <span className="text-[9px] uppercase tracking-widest ml-2" style={{ color: 'var(--c-text-4)' }}>{team.status}</span>
        <div className="flex-1" />
        <button
          onClick={async () => {
            if (!window.confirm('Cleanup will permanently delete this team and all its data.')) return
            await authFetch(`/api/teams/${team.id}`, { method: 'DELETE' })
            navigate('/teams', { replace: true })
          }}
          className="text-xs px-2 py-1 rounded"
          style={{ border: '1px solid var(--c-border)', color: '#ef4444' }}
        >
          Cleanup
        </button>
      </div>

      {error && (
        <div className="px-4 py-1 text-[10px]" style={{ background: '#3a0000', color: '#ef4444', borderBottom: '1px solid var(--c-border)' }}>
          {error}
          <button className="ml-2 underline" onClick={() => setError('')}>dismiss</button>
        </div>
      )}

      <div className="flex-1 grid grid-cols-12 gap-3 p-3 overflow-hidden">

        {/* Left column: members */}
        <aside className="col-span-3 flex flex-col rounded border overflow-hidden" style={{ borderColor: 'var(--c-border)', background: 'var(--c-surface-1)' }}>
          <div className="px-3 py-2 flex items-center border-b" style={{ borderColor: 'var(--c-border)' }}>
            <span className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--c-text-3)' }}>Members ({snap.members.length})</span>
            <button
              className="ml-auto text-[10px] px-2 py-0.5 rounded"
              style={{ background: 'var(--c-accent)', color: '#000' }}
              onClick={() => setMemberOpen(o => !o)}
            >
              {memberOpen ? 'Cancel' : '+ Spawn'}
            </button>
          </div>

          {memberOpen && (
            <div className="px-3 py-2 border-b space-y-1" style={{ borderColor: 'var(--c-border)' }}>
              <input className="w-full text-xs px-2 py-1 rounded" placeholder="Name (e.g. researcher)" value={memberName} onChange={e => setMemberName(e.target.value)} style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }} />
              <input className="w-full text-xs px-2 py-1 rounded" placeholder="Role (e.g. researcher)" value={memberType} onChange={e => setMemberType(e.target.value)} style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }} />
              <input className="w-full text-xs px-2 py-1 rounded" placeholder="Model (optional)" value={memberModel} onChange={e => setMemberModel(e.target.value)} style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }} />
              <textarea className="w-full text-xs px-2 py-1 rounded" rows={2} placeholder="System prompt (optional)" value={memberPrompt} onChange={e => setMemberPrompt(e.target.value)} style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }} />
              <button className="w-full text-xs py-1 rounded font-bold" style={{ background: 'var(--c-accent)', color: '#000' }} onClick={spawnMember}>Spawn</button>
            </div>
          )}

          <ul className="flex-1 overflow-y-auto">
            {snap.members.length === 0 && (
              <li className="px-3 py-2 text-[11px]" style={{ color: 'var(--c-text-4)' }}>No members yet — spawn one to begin.</li>
            )}
            {snap.members.map(m => (
              <li key={m.id} className="px-3 py-2 border-b last:border-b-0" style={{ borderColor: 'var(--c-border)' }}>
                <div className="flex items-center gap-2">
                  <span
                    title={m.status}
                    style={{
                      width: 7, height: 7, borderRadius: 999,
                      background:
                        m.status === 'busy' ? '#f59e0b' :
                        m.status === 'idle' ? '#22c55e' :
                                              '#6b7280',
                    }}
                  />
                  <span className="text-xs font-bold" style={{ color: 'var(--c-text-1)' }}>{m.name}</span>
                  {m.is_lead && <span className="text-[9px] uppercase" style={{ color: 'var(--c-accent)' }}>LEAD</span>}
                  <button
                    title="Shut down"
                    className="ml-auto text-[10px] opacity-60 hover:opacity-100"
                    style={{ color: '#ef4444' }}
                    onClick={() => shutdownMember(m.id, m.name)}
                  >✕</button>
                </div>
                <div className="text-[10px]" style={{ color: 'var(--c-text-3)' }}>{m.agent_type}{m.model ? ` · ${m.model}` : ''}</div>
              </li>
            ))}
          </ul>
        </aside>

        {/* Middle: Kanban */}
        <section className="col-span-6 flex flex-col rounded border overflow-hidden" style={{ borderColor: 'var(--c-border)', background: 'var(--c-surface-1)' }}>
          <div className="px-3 py-2 border-b flex items-center gap-2" style={{ borderColor: 'var(--c-border)' }}>
            <span className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--c-text-3)' }}>Tasks ({snap.tasks.length})</span>
          </div>

          <div className="px-3 py-2 border-b grid grid-cols-1 gap-1" style={{ borderColor: 'var(--c-border)' }}>
            <input
              className="text-xs px-2 py-1 rounded"
              placeholder="New task title"
              value={taskTitle}
              onChange={e => setTaskTitle(e.target.value)}
              style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
            />
            <textarea
              className="text-xs px-2 py-1 rounded"
              rows={2}
              placeholder="Description (optional)"
              value={taskDesc}
              onChange={e => setTaskDesc(e.target.value)}
              style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
            />
            <div className="flex flex-wrap gap-2 items-center text-[10px]" style={{ color: 'var(--c-text-3)' }}>
              <span>Assignee:</span>
              <select
                value={taskAssignee}
                onChange={e => setTaskAssignee(e.target.value)}
                className="text-xs px-1.5 py-0.5 rounded"
                style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
              >
                <option value="">(unassigned)</option>
                {snap.members.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
              <span>Depends on:</span>
              <select
                multiple
                value={taskDeps}
                onChange={e => {
                  const opts = Array.from(e.currentTarget.selectedOptions).map(o => o.value)
                  setTaskDeps(opts)
                }}
                className="text-xs px-1.5 py-0.5 rounded"
                style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)', minWidth: 120 }}
              >
                {snap.tasks.map(t => <option key={t.id} value={t.id}>{t.title.slice(0, 30)}</option>)}
              </select>
              <button
                disabled={taskTitle.trim().length < 2}
                className="ml-auto text-xs px-2 py-1 rounded font-bold disabled:opacity-40"
                style={{ background: 'var(--c-accent)', color: '#000' }}
                onClick={createTask}
              >
                + Create task
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-x-auto overflow-y-auto p-2 grid grid-cols-3 gap-2 min-h-0">
            {COLUMNS.map(col => (
              <div key={col.key} className="flex flex-col rounded border overflow-hidden" style={{ borderColor: 'var(--c-border)' }}>
                <div className="px-2 py-1 text-[10px] uppercase tracking-widest border-b" style={{ color: 'var(--c-text-3)', background: 'var(--c-surface-2)', borderColor: 'var(--c-border)' }}>
                  {col.label} ({tasksByStatus[col.key]?.length ?? 0})
                </div>
                <ul className="flex-1 overflow-y-auto p-1.5 space-y-1.5">
                  {(tasksByStatus[col.key] ?? []).map(t => {
                    const blocked = col.key === 'pending' && isBlocked(t)
                    const assignee = memberById(t.assigned_to)
                    return (
                      <li
                        key={t.id}
                        className="rounded border p-2 text-[11px]"
                        style={{ borderColor: 'var(--c-border)', background: 'var(--c-surface-2)', opacity: blocked ? 0.55 : 1 }}
                      >
                        <div className="font-bold mb-1" style={{ color: 'var(--c-text-1)' }}>{t.title}</div>
                        {t.description && <div className="mb-1" style={{ color: 'var(--c-text-3)' }}>{t.description}</div>}
                        <div className="text-[9px]" style={{ color: 'var(--c-text-4)' }}>
                          {assignee ? `→ ${assignee.name}` : 'unassigned'}
                          {t.depends_on.length > 0 && ` · deps ${t.depends_on.length}`}
                          {blocked && ' · BLOCKED'}
                        </div>
                        {t.result && (
                          <pre className="mt-1 whitespace-pre-wrap text-[10px] p-1 rounded" style={{ background: 'var(--c-bg)', color: 'var(--c-text-2)', maxHeight: 80, overflow: 'auto' }}>{t.result}</pre>
                        )}
                        <TaskActions
                          task={t}
                          blocked={blocked}
                          members={snap.members}
                          onClaim={(mid) => claimTask(t.id, mid)}
                          onComplete={() => completeTask(t.id)}
                          onExecute={(mid) => executeTask(t.id, mid)}
                        />
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {/* Right: messages */}
        <aside className="col-span-3 flex flex-col rounded border overflow-hidden" style={{ borderColor: 'var(--c-border)', background: 'var(--c-surface-1)' }}>
          <div className="px-3 py-2 border-b" style={{ borderColor: 'var(--c-border)' }}>
            <span className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--c-text-3)' }}>Mailbox ({snap.messages.length})</span>
          </div>
          <ul className="flex-1 overflow-y-auto px-2 py-1">
            {snap.messages.length === 0 && (
              <li className="px-1 py-2 text-[11px]" style={{ color: 'var(--c-text-4)' }}>No messages yet.</li>
            )}
            {snap.messages.map(m => (
              <li key={m.id} className="text-[11px] mb-1 px-1">
                <div className="flex gap-1 items-baseline" style={{ color: 'var(--c-text-3)' }}>
                  <span style={{ color: 'var(--c-accent)' }}>{m.from_member}</span>
                  <span style={{ color: 'var(--c-text-4)' }}>→</span>
                  <span>{m.to_member}</span>
                </div>
                <div style={{ color: 'var(--c-text-2)' }}>{m.content}</div>
              </li>
            ))}
          </ul>

          <div className="border-t p-2 grid gap-1" style={{ borderColor: 'var(--c-border)' }}>
            <div className="flex gap-1">
              <select className="text-[10px] px-1 py-0.5 rounded flex-1" value={msgFrom} onChange={e => setMsgFrom(e.target.value)} style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}>
                <option value="user">user</option>
                {snap.members.map(m => <option key={m.id} value={m.name}>{m.name}</option>)}
              </select>
              <span className="text-[10px] self-center" style={{ color: 'var(--c-text-4)' }}>→</span>
              <select className="text-[10px] px-1 py-0.5 rounded flex-1" value={msgTo} onChange={e => setMsgTo(e.target.value)} style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}>
                <option value="all">all</option>
                {snap.members.map(m => <option key={m.id} value={m.name}>{m.name}</option>)}
              </select>
            </div>
            <textarea
              rows={2}
              value={msgText}
              onChange={e => setMsgText(e.target.value)}
              placeholder="Message…"
              className="text-xs px-2 py-1 rounded"
              style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
            />
            <button
              disabled={msgText.trim().length < 1}
              onClick={sendMessage}
              className="text-xs px-2 py-1 rounded font-bold disabled:opacity-40"
              style={{ background: 'var(--c-accent)', color: '#000' }}
            >
              Send
            </button>
          </div>
        </aside>
      </div>
    </Frame>
  )
}

function TaskActions({
  task, blocked, members, onClaim, onComplete, onExecute,
}: {
  task: TeamTask
  blocked: boolean
  members: TeamMember[]
  onClaim:    (mid: string) => void
  onComplete: () => void
  onExecute:  (mid: string) => void
}) {
  const [pick, setPick] = useState('')
  if (task.status === 'done' || task.status === 'failed') return null
  if (task.status === 'pending') {
    return (
      <div className="mt-1.5 flex gap-1 items-center">
        <select
          className="text-[10px] px-1 py-0.5 rounded flex-1"
          value={pick}
          onChange={e => setPick(e.target.value)}
          style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
          disabled={blocked}
        >
          <option value="">{blocked ? 'blocked' : 'pick member…'}</option>
          {members.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <button
          disabled={blocked || !pick}
          onClick={() => onClaim(pick)}
          className="text-[10px] px-1.5 py-0.5 rounded disabled:opacity-40"
          style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-2)' }}
        >Claim</button>
        <button
          disabled={blocked || !pick}
          onClick={() => onExecute(pick)}
          className="text-[10px] px-1.5 py-0.5 rounded disabled:opacity-40"
          style={{ background: 'var(--c-accent)', color: '#000' }}
        >Run</button>
      </div>
    )
  }
  // in_progress
  return (
    <div className="mt-1.5 flex justify-end">
      <button
        onClick={onComplete}
        className="text-[10px] px-1.5 py-0.5 rounded"
        style={{ background: 'var(--c-accent)', color: '#000' }}
      >Complete</button>
    </div>
  )
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full h-full flex flex-col overflow-hidden font-mono" style={{ background: 'var(--c-bg)', color: 'var(--c-text-1)' }}>
      {children}
    </div>
  )
}

function upsertById<T extends { id: string | number }>(arr: T[], item: T): T[] {
  const idx = arr.findIndex(x => String(x.id) === String(item.id))
  if (idx === -1) return [...arr, item]
  const next = arr.slice()
  next[idx] = item
  return next
}
