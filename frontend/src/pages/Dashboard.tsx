import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthFetch } from '../hooks/useAuthFetch'
import { useAuthContext } from '../context/auth'

// ── Types ────────────────────────────────────────────────────────────────────────

interface Project {
  id: string
  name: string
  status: 'running' | 'ready' | 'idle' | 'error' | 'done' | 'paused'
  progress: number
  agents: number
  files: number
  last_active: string | null
  created_at: string | null
}

interface Usage {
  plan: 'none' | 'starter' | 'pro'
  balance_cents: number
}

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  running: { color: 'var(--accent)', label: 'running' },
  ready:   { color: 'var(--info)', label: 'ready' },
  idle:    { color: 'var(--text-faint)', label: 'idle' },
  error:   { color: 'var(--danger)', label: 'error' },
  done:    { color: 'var(--accent-dim)', label: 'done' },
  paused:  { color: 'var(--warn)', label: 'paused' },
}

// ── Helpers ──────────────────────────────────────────────────────────────────────

const timeAgo = (dateStr: string | null): string => {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

const EMOTES = ['🔐', '💬', '🧪', '💳', '⌨️', '📊', '📚', '📦', '🎫', '👔', '🏗️']

// ── Components ────────────────────────────────────────────────────────────────────

function WidgetCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border p-5" style={{ background: 'var(--bg-elev)', borderColor: 'var(--border)' }}>
      <div className="text-[10px] font-mono uppercase tracking-[0.08em] mb-3" style={{ color: 'var(--text-mute)' }}>
        {title}
      </div>
      {children}
    </div>
  )
}

function ProjectCard({ project, onClick }: { project: Project; onClick: () => void }) {
  const s = STATUS_CONFIG[project.status] || STATUS_CONFIG.idle
  const emote = EMOTES[project.id.length % EMOTES.length]
  return (
    <button
      onClick={onClick}
      className="text-left rounded-lg border p-4 transition-all duration-120 w-full group"
      style={{
        background: 'var(--bg-elev)',
        borderColor: 'var(--border)',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--border-strong)'
        e.currentTarget.style.background = 'var(--bg-elev-2)'
        e.currentTarget.style.transform = 'translateY(-1px)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.background = 'var(--bg-elev)'
        e.currentTarget.style.transform = 'none'
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <span className="shrink-0 w-8 h-8 rounded-md flex items-center justify-center text-sm"
          style={{ background: 'var(--accent-soft)', border: '1px solid var(--accent)' }}>
          {emote}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium truncate" style={{ color: 'var(--text)' }}>{project.name}</div>
          <div className="text-[10px] truncate" style={{ color: 'var(--text-faint)' }}>/project/{project.id}</div>
        </div>
        <span className="text-[10px] opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: 'var(--text-mute)' }}>
          ↗
        </span>
      </div>

      {/* Progress */}
      {project.progress > 0 && (
        <div className="h-[3px] rounded-full mb-3 overflow-hidden" style={{ background: 'var(--bg-hover)' }}>
          <div className="h-full rounded-full transition-all duration-500"
            style={{ width: `${project.progress}%`, background: s.color }} />
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center gap-3 pt-3" style={{ borderTop: '1px dashed var(--border)' }}>
        <div className="flex items-center gap-1.5">
          <span className="w-[6px] h-[6px] rounded-full"
            style={{ background: s.color, boxShadow: project.status === 'running' ? `0 0 6px ${s.color}` : 'none' }} />
          <span className="text-[11px]" style={{ color: s.color }}>{s.label}</span>
        </div>
        <span className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
          {project.agents} agents · {project.files} files
        </span>
        <span className="text-[10px] ml-auto" style={{ color: 'var(--text-faint)' }}>
          {timeAgo(project.last_active)}
        </span>
      </div>
    </button>
  )
}

function CreateForm({ onCreated }: { onCreated: (id: string) => void }) {
  const authFetch = useAuthFetch()
  const [name, setName] = useState('')
  const [brief, setBrief] = useState('')
  const [launching, setLaunching] = useState(false)
  const [error, setError] = useState('')

  const handleLaunch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !brief.trim()) return
    setLaunching(true)
    setError('')
    try {
      const r = await authFetch('/api/start-project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), brief: brief.trim() }),
      })
      const d = await r.json()
      if (!r.ok) { setError(d.detail ?? 'Failed'); return }
      onCreated(d.run_id ?? d.id)
    } catch {
      setError('Network error')
    } finally {
      setLaunching(false)
    }
  }

  return (
    <form onSubmit={handleLaunch} className="rounded-lg border p-8" style={{ background: 'var(--bg-elev)', borderColor: 'var(--border)' }}>
      <div className="text-sm font-medium mb-6" style={{ color: 'var(--text)' }}>// new project</div>

      <div className="mb-7">
        <label className="block text-[11px] uppercase tracking-[0.08em] mb-2" style={{ color: 'var(--text-mute)' }}>
          Project Name <span style={{ color: 'var(--text-faint)' }}>· required</span>
        </label>
        <input value={name} onChange={e => setName(e.target.value)}
          className="w-full text-[13px] px-4 py-2.5 rounded-md focus:outline-none font-mono"
          style={{ background: 'var(--c-input-bg)', border: '1px solid var(--border)', color: 'var(--text)' }}
          placeholder="e.g. auth-service-rewrite" required />
      </div>

      <div className="mb-7">
        <label className="block text-[11px] uppercase tracking-[0.08em] mb-2" style={{ color: 'var(--text-mute)' }}>
          Goal / Brief <span style={{ color: 'var(--text-faint)' }}>· the manager will plan from this</span>
        </label>
        <textarea value={brief} onChange={e => setBrief(e.target.value)}
          className="w-full text-[13px] px-4 py-2.5 rounded-md focus:outline-none font-mono resize-none"
          style={{ background: 'var(--c-input-bg)', border: '1px solid var(--border)', color: 'var(--text)', minHeight: 100 }}
          placeholder="e.g. Build a REST API for user authentication with JWT tokens, refresh token rotation, and OAuth2 social login support…"
          required />
      </div>

      {error && <p className="text-[11px] mb-4" style={{ color: 'var(--danger)' }}>{error}</p>}

      <button type="submit" disabled={launching || !name.trim() || !brief.trim()}
        className="w-full text-[13px] font-medium py-2.5 rounded-md transition-all disabled:opacity-40"
        style={{ background: 'var(--accent)', color: '#000' }}>
        {launching ? 'Launching…' : '▶ Launch Project'}
      </button>
      <p className="text-[10px] mt-2 text-center" style={{ color: 'var(--text-faint)' }}>
        ⏎ to launch · ⎋ to clear
      </p>
    </form>
  )
}

// ── Dashboard ────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const authFetch  = useAuthFetch()
  const navigate   = useNavigate()
  const { user }   = useAuthContext()
  const [projects, setProjects] = useState<Project[]>([])
  const [usage, setUsage]       = useState<Usage | null>(null)
  const [tab, setTab]           = useState<'projects' | 'create'>('projects')
  const [search, setSearch]     = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  const fetchProjects = () => {
    authFetch('/api/projects')
      .then(r => r.json())
      .then((d: { projects?: Project[] }) => setProjects(d.projects ?? []))
      .catch(() => {})
  }

  const fetchUsage = () => {
    authFetch('/api/billing/usage')
      .then(r => r.json())
      .then(setUsage)
      .catch(() => {})
  }

  useEffect(() => {
    fetchProjects()
    fetchUsage()
  }, [])

  const filtered = projects.filter(p => {
    if (statusFilter !== 'all' && p.status !== statusFilter) return false
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  const statusCounts: Record<string, number> = {}
  projects.forEach(p => {
    statusCounts[p.status] = (statusCounts[p.status] || 0) + 1
  })

  const statusLabels = ['all', 'running', 'ready', 'paused', 'done', 'error']

  return (
    <div className="w-full h-full flex flex-col overflow-hidden font-mono"
      style={{ background: 'var(--bg)', color: 'var(--text)' }}>
      {/* Topbar */}
      <div className="flex items-center gap-5 shrink-0 px-6 h-14"
        style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-elev)' }}>
        {/* Logo */}
        <button onClick={() => navigate('/')} className="shrink-0 w-[26px] h-[26px] rounded-[5px] flex items-center justify-center text-[11px] font-bold transition-colors"
          style={{ border: '1px solid var(--border)', color: 'var(--accent)' }}>
          tm
        </button>
        <span className="text-xs" style={{ color: 'var(--text-mute)' }}>›</span>

        {/* Tabs */}
        <div className="flex rounded-[7px] p-1 gap-[3px]" style={{ background: 'var(--bg-elev-2)' }}>
          {(['projects', 'create'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className="text-[13px] font-medium tracking-[0.02em] px-5 py-1.5 rounded-[5px] transition-all capitalize"
              style={{
                color: tab === t ? 'var(--accent)' : 'var(--text-dim)',
                background: tab === t ? 'var(--bg-hover)' : 'transparent',
                boxShadow: tab === t ? 'inset 0 0 0 1px rgba(255,255,255,0.06)' : 'none',
              }}>
              {t}
            </button>
          ))}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Billing */}
        {usage && usage.plan !== 'none' && (
          <div className="flex items-center gap-2 text-[12px]" style={{ color: 'var(--text-dim)' }}>
            <span style={{ color: 'var(--accent)' }}>
              ${(usage.balance_cents / 100).toFixed(0)}
            </span>
            <span className="text-[10px]" style={{ color: 'var(--text-mute)' }}>credits</span>
          </div>
        )}
        <button onClick={() => navigate('/billing')}
          className="text-[12px] px-3 py-1.5 rounded-md transition-colors"
          style={{ border: '1px solid var(--border)', color: 'var(--text-dim)', background: 'var(--bg-elev)' }}>
          ✦ Billing
        </button>

        {/* User pill */}
        <button onClick={() => navigate('/settings')}
          className="text-[12px] px-3 py-1.5 rounded-md transition-colors shrink-0 max-w-[120px] truncate"
          style={{ border: '1px solid var(--border)', color: 'var(--text-dim)', background: 'var(--bg-elev)' }}>
          {user?.name || user?.email?.split('@')[0] || 'User'}
        </button>
      </div>

      {/* Canvas */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[1440px] mx-auto px-12 pt-9 pb-16">

          {/* Widgets */}
          <div className="grid gap-5 mb-10" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <WidgetCard title="Credit Balance">
              {usage ? (
                <>
                  <div className="text-[28px] font-semibold tracking-[-0.02em]" style={{ color: 'var(--text)' }}>
                    {(usage.balance_cents / 100).toFixed(0)}%
                  </div>
                  <div className="h-2 rounded-full mt-2 overflow-hidden" style={{ background: 'var(--bg-hover)' }}>
                    <div className="h-full rounded-full transition-all" style={{ width: '72%', background: 'var(--accent)' }} />
                  </div>
                  <div className="text-[10px] mt-1.5" style={{ color: 'var(--text-mute)' }}>
                    ${(usage.balance_cents / 100).toFixed(0)} of credits
                  </div>
                </>
              ) : (
                <div className="text-[13px]" style={{ color: 'var(--text-mute)' }}>No active plan</div>
              )}
            </WidgetCard>

            <WidgetCard title="Total Projects">
              <div className="text-[28px] font-semibold tracking-[-0.02em]" style={{ color: 'var(--text)' }}>
                {projects.length}
              </div>
              <div className="flex gap-1 mt-2">
                {(['running', 'ready', 'paused', 'done'] as const).map(s => {
                  const count = statusCounts[s] || 0
                  if (!count) return null
                  return (
                    <div key={s}
                      className="h-1.5 rounded-full flex-1"
                      style={{ background: STATUS_CONFIG[s].color, opacity: 0.6 }} />
                  )
                })}
              </div>
              <div className="text-[10px] mt-1.5" style={{ color: 'var(--text-mute)' }}>
                {statusCounts.running || 0} active
              </div>
            </WidgetCard>

            <WidgetCard title="Quick Actions">
              <button onClick={() => setTab('create')}
                className="w-full text-left text-[12px] py-2 rounded-md transition-colors flex items-center gap-2 group px-3"
                style={{ color: 'var(--text-dim)' }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-dim)' }}>
                <span>⌖</span> New project
                <span className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">→</span>
              </button>
              <button onClick={() => navigate('/billing')}
                className="w-full text-left text-[12px] py-2 rounded-md transition-colors flex items-center gap-2 group px-3"
                style={{ color: 'var(--text-dim)' }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-dim)' }}>
                <span>✦</span> Manage billing
                <span className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">→</span>
              </button>
              <button onClick={() => navigate('/settings')}
                className="w-full text-left text-[12px] py-2 rounded-md transition-colors flex items-center gap-2 group px-3"
                style={{ color: 'var(--text-dim)' }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-dim)' }}>
                <span>⚙</span> Settings
                <span className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity text-[10px]">→</span>
              </button>
            </WidgetCard>
          </div>

          {/* Content area */}
          {tab === 'create' ? (
            <CreateForm onCreated={(id) => { fetchProjects(); navigate(`/project/${id}`) }} />
          ) : (
            <>
              {/* Search + filters */}
              <div className="flex items-center gap-4 mb-6">
                <div className="flex-1 relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[13px]" style={{ color: 'var(--text-faint)' }}>⌕</span>
                  <input value={search} onChange={e => setSearch(e.target.value)}
                    className="w-full text-[13px] pl-9 pr-4 py-2 rounded-md focus:outline-none font-mono"
                    style={{ background: 'var(--c-input-bg)', border: '1px solid var(--border)', color: 'var(--text)' }}
                    placeholder="Search projects…" />
                </div>
              </div>
              <div className="flex gap-2 mb-6">
                {statusLabels.map(s => {
                  const count = s === 'all' ? projects.length : (statusCounts[s] || 0)
                  return (
                    <button key={s} onClick={() => setStatusFilter(s)}
                      className="text-[11px] tracking-[0.04em] px-3 py-1 rounded-md transition-all capitalize flex items-center gap-1.5"
                      style={{
                        color: statusFilter === s ? 'var(--accent)' : 'var(--text-dim)',
                        background: statusFilter === s ? 'var(--accent-soft)' : 'var(--bg-elev)',
                        border: `1px solid ${statusFilter === s ? 'var(--accent)' : 'var(--border)'}`,
                      }}>
                      {s}
                      <span className="text-[9px]" style={{ color: 'var(--text-faint)' }}>{count}</span>
                    </button>
                  )
                })}
              </div>

              {/* Project grid */}
              {filtered.length === 0 ? (
                <div className="text-center py-12 rounded-lg border-dashed border"
                  style={{ borderColor: 'var(--border)', color: 'var(--text-mute)' }}>
                  <p className="text-[13px]">no matching projects</p>
                  <button onClick={() => setTab('create')} className="text-[12px] mt-2"
                    style={{ color: 'var(--accent)' }}>
                    create one →
                  </button>
                </div>
              ) : (
                <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))' }}>
                  {filtered.map(p => (
                    <ProjectCard key={p.id} project={p}
                      onClick={() => navigate(`/project/${p.id}`)} />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-4 shrink-0 h-6 px-3 text-[10px] tracking-[0.04em]"
        style={{ background: 'var(--bg-elev)', borderTop: '1px solid var(--border)', color: 'var(--text-faint)' }}>
        <span style={{ color: 'var(--accent)' }}>●</span> connected
        <span>tm@{import.meta.env.VITE_APP_VERSION || 'v0.4'}</span>
        <span className="ml-auto">{projects.length} projects</span>
      </div>
    </div>
  )
}
