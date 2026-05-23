import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthFetch } from '../hooks/useAuthFetch'
import { useAuthContext } from '../context/auth'

// ── Data types ──────────────────────────────────────────────────────────────────

interface Project {
  id: string
  name: string
  desc: string
  path?: string
  icon: string
  color: string
  status: 'running' | 'ready' | 'idle' | 'error' | 'done' | 'paused'
  progress: number
  agents: number
  files: number
  lastActive: string
  lastActiveSort: number
  created: string
  tokens: string
}

interface Usage {
  plan: 'none' | 'starter' | 'pro'
  balance_cents: number
  updated_at?: string | null
}

// ── Constants ───────────────────────────────────────────────────────────────────

const STATUSES = ['running', 'ready', 'paused', 'done', 'error', 'idle'] as const
const ALL_AGENTS: { id: string; name: string; role: string; color: string; required?: boolean }[] = [
  { id: 'manager', name: 'Manager', role: 'Coord', color: 'var(--c-purple)', required: true },
  { id: 'webdev', name: 'WebDev', role: 'Arch', color: 'var(--c-purple)' },
  { id: 'researcher', name: 'Researcher', role: 'Lead', color: 'var(--c-cyan)' },
  { id: 'backend', name: 'Backend', role: 'API', color: 'var(--c-orange)' },
  { id: 'frontend', name: 'Frontend', role: 'UI', color: 'var(--c-green)' },
  { id: 'tester', name: 'Tester', role: 'QA', color: 'var(--c-red)' },
  { id: 'docs', name: 'Docs', role: 'Writer', color: 'var(--c-green)' },
  { id: 'logger', name: 'Logger', role: 'Chron', color: 'var(--c-brown)' },
  { id: 'reviewer', name: 'Reviewer', role: 'Review', color: 'var(--c-magenta)' },
]

// ── Sub-components ──────────────────────────────────────────────────────────────

function CreditWidget({ usage }: { usage: Usage | null }) {
  const balance = usage?.balance_cents ?? 0
  const plan = usage?.plan ?? 'none'
  const planAlloc: Record<string, number> = { starter: 1500, pro: 4800, none: 1 }
  const allocated = planAlloc[plan] || 1
  const pct = Math.min(100, Math.round((balance / allocated) * 100))
  const updated = usage?.updated_at
    ? new Date(usage.updated_at).toLocaleDateString()
    : null
  return (
    <div className="widget">
      <div className="widget-label">
        <span>Credit balance</span>
        <span className="badge">{plan === 'none' ? 'no plan' : plan}</span>
      </div>
      <div className="widget-big">{pct}<span style={{ fontSize: 16, color: 'var(--text-mute)' }}>%</span></div>
      <div className="credit-bar">
        <div className="credit-bar-fill" style={{ width: pct + '%' }} />
      </div>
      <div className="credit-meta">
        <span>{plan === 'pro' ? 'Pro' : plan === 'starter' ? 'Starter' : 'No'} plan · ${(balance / 100).toFixed(0)} credits</span>
        {updated && (
          <span style={{ color: 'var(--text-dim)', marginLeft: 'auto' }}>{updated}</span>
        )}
      </div>
    </div>
  )
}

function ProjectCountWidget({ count, activeCount }: { count: number; activeCount: number }) {
  return (
    <div className="widget">
      <div className="widget-label">
        <span>Total projects</span>
        <span className="badge">all time</span>
      </div>
      <div className="widget-big">{count}</div>
      <div className="widget-sub">
        <span style={{ color: 'var(--text-dim)' }}>{activeCount} active</span>
      </div>
      <div style={{ display: 'flex', gap: 4, marginTop: 'auto' }}>
        {['running', 'ready', 'paused', 'done', 'idle'].map((s, i) => (
          <div key={s} style={{ flex: 1, height: 3, background: 'var(--accent)', opacity: [0.9, 0.55, 0.3, 0.45, 0.18][i], borderRadius: 1 }} />
        ))}
      </div>
    </div>
  )
}

function TasksWidget({ totalMessages }: { totalMessages: number }) {
  const tasks = [4, 7, 9, 3, 6, 11, 14, 8, 10, 16, 18, 7, 9, 15, 12, 5, 8, 14, 13, 11, 4, 12, 15, 18, 9, 7, 13, 16, 14]
  const max = Math.max(...tasks)
  return (
    <div className="widget">
      <div className="widget-label">
        <span>Tasks completed</span>
        <span className="badge">May</span>
      </div>
      <div className="widget-big">{totalMessages}</div>
      <div className="spend-chart">
        {tasks.map((v, i) => (
          <div key={i} className={'bar' + (i === tasks.length - 1 ? ' today' : '')} style={{ height: (v / max * 100) + '%' }} title={`Day ${i + 1}: ${v} tasks`} />
        ))}
      </div>
      <div className="widget-sub" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>total messages</span>
        <span style={{ color: 'var(--text-faint)' }}>all time</span>
      </div>
    </div>
  )
}

function QuickActionsWidget({ onAction, lastProjectName }: { onAction: (id: string) => void; lastProjectName?: string }) {
  const actions = [
    { id: 'last', label: lastProjectName ? `Last: ${lastProjectName}` : 'Last Project', ic: '↗' },
    { id: 'duplicate', label: 'Duplicate Last', ic: '⎘' },
    { id: 'billing', label: 'Billing & Credits', ic: '💳' },
  ]
  return (
    <div className="widget">
      <div className="widget-label">
        <span>Quick actions</span>
        <span className="badge">⌘K</span>
      </div>
      <div className="qa-list">
        {actions.map(a => (
          <button key={a.id} className="qa-btn" onClick={() => onAction(a.id)}>
            <span className="ic">{a.ic}</span>
            <span>{a.label}</span>
            <span className="arr">→</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function ProjectCard({ project, active, onOpen, onDelete, onChangeStatus }: {
  project: Project; active: boolean; onOpen: () => void;
  onDelete: (e: React.MouseEvent) => void; onChangeStatus: (p: Project, s: string) => void;
}) {
  const p = project
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className={'proj-card' + (active ? ' active' : '')} onClick={onOpen}>
      <div className="proj-head">
        <div className="proj-icon" style={{
          background: `color-mix(in oklab, ${p.color} 14%, var(--bg-elev-2))`,
          borderColor: `color-mix(in oklab, ${p.color} 30%, var(--border))`,
        }}>
          {p.icon}
        </div>
        <div className="proj-meta">
          <div className="proj-name">{p.name}</div>
          <div className="proj-path">{p.path || `/project/${p.id}`}</div>
        </div>
        <div className="proj-actions">
          <button className="proj-action" title="Open" onClick={(e) => { e.stopPropagation(); onOpen() }}>↗</button>
          <button className="proj-action danger" title="Delete" onClick={onDelete}>✕</button>
        </div>
      </div>
      <div className="proj-desc">{p.desc}</div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 10, color: 'var(--text-faint)' }}>
        <div style={{ flex: 1, height: 3, background: 'var(--bg-elev-2)', borderRadius: 2, overflow: 'hidden', border: '1px solid var(--border)' }}>
          <div style={{ height: '100%', width: p.progress + '%', background: p.status === 'error' ? 'var(--danger)' : p.status === 'paused' ? 'var(--warn)' : 'var(--accent)' }} />
        </div>
        <span style={{ color: 'var(--text-dim)', minWidth: 30, textAlign: 'right' }}>{p.progress}%</span>
      </div>

      <div className="proj-foot">
        <div className="stats">
          <div className="status-chip-wrap" style={{ position: 'relative' }}>
            <button className="status-chip" title="Click to change status"
              onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen) }}>
              <span className={'status-dot ' + p.status} />
              <span className={'status-label ' + p.status}>{p.status}</span>
              <span className="caret">▾</span>
            </button>
            {menuOpen && (
              <>
                <div style={{ position: 'fixed', inset: 0, zIndex: 40 }}
                  onClick={(e) => { e.stopPropagation(); setMenuOpen(false) }} />
                <div className="status-menu" onClick={(e) => e.stopPropagation()}>
                  <div className="status-menu-head">set status</div>
                  {STATUSES.map(s => (
                    <button key={s}
                      className={'status-menu-row' + (s === p.status ? ' on' : '')}
                      onClick={(e) => { e.stopPropagation(); onChangeStatus(p, s); setMenuOpen(false) }}>
                      <span className={'status-dot ' + s} />
                      <span className={'status-label ' + s}>{s}</span>
                      {s === p.status && <span className="check">✓</span>}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
          <span className="stat">{p.agents} agents</span>
          <span className="stat">{p.files} files</span>
        </div>
        <span>{p.lastActive}</span>
      </div>
    </div>
  )
}

function ProjectsTab({ projects, activeId, onOpen, onDelete, onChangeStatus, query, setQuery, filter, setFilter, onCreateNew }: {
  projects: Project[]; activeId: string | null; onOpen: (p: Project) => void;
  onDelete: (p: Project) => void; onChangeStatus: (p: Project, s: string) => void;
  query: string; setQuery: (q: string) => void; filter: string; setFilter: (f: string) => void;
  onCreateNew: () => void;
}) {
  const filtered = useMemo(() => {
    let arr = projects
    if (filter !== 'all') arr = arr.filter(p => p.status === filter)
    if (query.trim()) {
      const q = query.toLowerCase()
      arr = arr.filter(p => p.name.toLowerCase().includes(q) || p.desc.toLowerCase().includes(q))
    }
    return arr
  }, [projects, query, filter])

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: projects.length, running: 0, ready: 0, paused: 0, error: 0, done: 0, idle: 0 }
    projects.forEach(p => { c[p.status] = (c[p.status] || 0) + 1 })
    return c
  }, [projects])

  return (
    <div className="fadein">
      <div className="search-row">
        <div className="search">
          <span style={{ color: 'var(--text-faint)' }}>⌕</span>
          <input placeholder="Search projects, paths, descriptions…" value={query} onChange={e => setQuery(e.target.value)} />
          <span className="kbd">⌘F</span>
        </div>
        <div className="filter-pills">
          {[
            ['all', 'all'],
            ['running', 'running'],
            ['ready', 'ready'],
            ['paused', 'paused'],
            ['done', 'done'],
            ['error', 'error'],
          ].map(([k, label]) => (
            <button key={k} className={'pill' + (filter === k ? ' active' : '')} onClick={() => setFilter(k)}>
              {label} <span style={{ opacity: 0.5, marginLeft: 4 }}>{counts[k] ?? 0}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="section-head">
        <h2>// past projects</h2>
        <span className="meta">{filtered.length} shown · click to resume in agent dashboard</span>
      </div>

      <div className="projects-grid">
        {filtered.map(p => (
          <ProjectCard key={p.id} project={p} active={p.id === activeId}
            onOpen={() => onOpen(p)}
            onDelete={(e) => { e.stopPropagation(); onDelete(p) }}
            onChangeStatus={onChangeStatus} />
        ))}
        {filtered.length === 0 && (
          <div style={{ gridColumn: '1 / -1', padding: 40, textAlign: 'center', color: 'var(--text-faint)', border: '1px dashed var(--border)', borderRadius: 8 }}>
            no matching projects · adjust filters or <span style={{ color: 'var(--accent)', cursor: 'pointer' }} onClick={onCreateNew}>create one</span>
          </div>
        )}
      </div>
    </div>
  )
}

function CreateTab({ onLaunch }: { onLaunch: (cfg: { name: string; desc: string; icon: string; agents: string[]; autoStart: boolean }) => void }) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [agents, setAgents] = useState(new Set(['manager', 'webdev', 'backend', 'frontend', 'tester']))

  const toggleAgent = (id: string) => {
    if (id === 'manager') return
    const next = new Set(agents)
    next.has(id) ? next.delete(id) : next.add(id)
    setAgents(next)
  }

  const canSubmit = name.trim().length >= 2 && desc.trim().length >= 8 && agents.size >= 2

  const submit = () => {
    if (!canSubmit) return
    onLaunch({
      name: name.trim(), desc: desc.trim(), icon: '⚡',
      agents: Array.from(agents), autoStart: false,
    })
  }

  return (
    <div className="fadein">
      <div className="section-head">
        <h2>// new project</h2>
        <span className="meta">configure agents, then launch into the network</span>
      </div>

      <div className="create-wrap">
        <div className="form-card">
          <div className="field">
            <label>
              Project name
              <span className="opt">required · kebab-case suggested</span>
            </label>
            <input type="text" placeholder="e.g. auth-service-rewrite" value={name} onChange={e => setName(e.target.value)} />
          </div>

          <div className="field">
            <label>
              Goal / Brief
              <span className="opt">the manager will plan from this</span>
            </label>
            <textarea
              placeholder="Describe the project goal. e.g. 'Rewrite our authentication service to use JWT + WebAuthn. Replace passport-based middleware. Keep existing OAuth providers.'"
              value={desc} onChange={e => setDesc(e.target.value)} />
          </div>

          <div className="field" style={{ marginBottom: 0 }}>
            <label>
              Agent network
              <span className="opt">{agents.size} of {ALL_AGENTS.length} enabled · Manager required</span>
            </label>
            <div className="agent-picker">
              {ALL_AGENTS.map(a => (
                <button key={a.id}
                  className={'agent-chip' + (agents.has(a.id) ? ' on' : '')}
                  style={{ '--accent-color': a.color } as React.CSSProperties}
                  onClick={() => toggleAgent(a.id)} disabled={a.required}>
                  <span className="dot" />
                  <span className="name">{a.name}</span>
                  <span className="role">{a.role}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="create-summary">
          <h3>// summary</h3>
          <div className="summary-row">
            <span className="k">name</span>
            <span className="v">{name || <em style={{ color: 'var(--text-faint)' }}>untitled</em>}</span>
          </div>
          <div className="summary-row">
            <span className="k">agents</span>
            <span className="v">{agents.size} of {ALL_AGENTS.length}</span>
          </div>
          <div className="summary-row">
            <span className="k">brief</span>
            <span className="v">{desc ? desc.length + ' chars' : <em style={{ color: 'var(--text-faint)' }}>empty</em>}</span>
          </div>

          <div className="cta-row">
            <button className="btn ghost" onClick={() => { setName(''); setDesc('') }}>Reset</button>
            <button className="btn primary" disabled={!canSubmit} onClick={submit}
              style={{ flex: 1, justifyContent: 'center', opacity: canSubmit ? 1 : 0.5 }}>
              ▶ Launch project
            </button>
          </div>
          <div style={{ fontSize: 9, color: 'var(--text-faint)', marginTop: 12, textAlign: 'center', letterSpacing: '0.04em' }}>
            ⏎ to launch · ⎋ to clear
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Activity Feed ───────────────────────────────────────────────────────────────

function ActivityFeed({ items }: { items: { time: string; who: string; proj: string; verb: string; target: string; detail: string; kind: string }[] }) {
  return (
    <div className="activity">
      <div className="section-head">
        <h2>// recent activity</h2>
        <span className="meta">across all projects · past runs</span>
      </div>
      <div className="activity-list">
        {items.map((it, i) => (
          <div key={i} className="activity-item">
            <span className={'status-dot ' + (it.kind === 'ok' ? 'done' : it.kind === 'fail' ? 'error' : it.kind === 'warn' ? 'paused' : it.kind === 'route' ? 'running' : 'idle')} />
            <span className="time">{it.time}</span>
            <span className="msg">
              <span className="strong">{it.who}</span>
              {' '}{it.verb}{' '}
              <span className="accent">{it.target}</span>
              {' · '}
              <span style={{ color: 'var(--text-faint)' }}>{it.detail}</span>
            </span>
            <span className="who">{it.proj}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Status Bar ──────────────────────────────────────────────────────────────────

function StatusBar({ tab, projectCount, creditPct }: { tab: string; projectCount: number; creditPct: number }) {
  return (
    <div className="statusbar">
      <span className="sb-item accent"><span className="status-dot running" /> connected</span>
      <span className="sb-item">tm@v0.42.1</span>
      <span className="sb-item">us-east-1</span>
      <span className="spacer" />
      <span className="sb-item">tab: {tab}</span>
      <span className="sb-item">{projectCount} projects</span>
      <span className="sb-item">credits ${(creditPct / 100).toFixed(0)}</span>
      <span className="sb-item" style={{ color: 'var(--text-mute)' }}>⌘K cmds</span>
    </div>
  )
}

// ── Dashboard ───────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const authFetch = useAuthFetch()
  const navigate = useNavigate()
  const { user } = useAuthContext()
  const [tab, setTab] = useState<'create' | 'projects'>('create')
  const [projects, setProjects] = useState<Project[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null)
  const [accountOpen, setAccountOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [alertsOpen, setAlertsOpen] = useState(false)
  const [usage, setUsage] = useState<Usage | null>(null)

  useEffect(() => {
    authFetch('/api/projects')
      .then(r => r.json())
      .then((d: { projects?: Project[] }) => setProjects(d.projects ?? []))
      .catch(() => {})
    authFetch('/api/billing/usage')
      .then(r => r.json())
      .then(setUsage)
      .catch(() => {})
  }, [])

  // Set data-theme from localStorage
  useEffect(() => {
    const themeId = localStorage.getItem('agentteam-theme') ?? 'default'
    const dataTheme = themeId === 'default' ? 'black' : themeId === 'matrix' ? 'matrix' : themeId === 'tokyo-night' ? 'tokyo' : themeId
    document.documentElement.setAttribute('data-theme', dataTheme)
  }, [])

  const openInAgent = (p: Project) => {
    setActiveId(p.id)
    navigate(`/project/${p.id}`)
  }

  const launchNew = (cfg: { name: string; desc: string; icon: string; agents: string[]; autoStart: boolean }) => {
    const newProj: Project = {
      id: 'p_' + Math.random().toString(36).slice(2, 8),
      name: cfg.name,
      desc: cfg.desc,
      path: '~/projects/' + cfg.name,
      icon: cfg.icon,
      color: 'var(--c-cyan)',
      status: cfg.autoStart ? 'running' : 'ready',
      progress: 0,
      agents: cfg.agents.length,
      files: 0,
      lastActive: 'just now',
      lastActiveSort: 0,
      created: 'just now',
      tokens: '0K',
    }
    setProjects([newProj, ...projects])
    setActiveId(newProj.id)
    navigate(`/project/${newProj.id}`)
  }

  const confirmDelete = (p: Project) => setDeleteTarget(p)
  const doDelete = () => {
    if (!deleteTarget) return
    setProjects(projects.filter(p => p.id !== deleteTarget.id))
    setToast(`deleted ${deleteTarget.name}`)
    setDeleteTarget(null)
  }

  const changeStatus = (proj: Project, status: string) => {
    setProjects(projects.map(p => p.id === proj.id ? { ...p, status: status as Project['status'] } : p))
    setToast(`${proj.name} → ${status}`)
  }

  const handleQuickAction = (id: string) => {
    if (id === 'last') {
      const last = projects[0]
      if (last) navigate(`/project/${last.id}`)
    } else if (id === 'duplicate') {
      const last = projects[0]
      if (last) {
        const dup: Project = {
          ...last,
          id: 'p_' + Math.random().toString(36).slice(2, 8),
          name: last.name + '-copy',
          status: 'ready',
          progress: 0,
          lastActive: 'just now',
          lastActiveSort: 0,
          created: 'just now',
        }
        setProjects([dup, ...projects])
        setToast(`duplicated ${last.name}`)
      }
    } else if (id === 'billing') {
      navigate('/billing')
    }
  }

  const creditPct = usage ? usage.balance_cents : 0

  // Build alerts from running projects
  const alerts = useMemo(() => {
    const a: { text: string; time: string; kind: string }[] = []
    projects.filter(p => p.status === 'running').forEach(p => {
      a.push({
        text: `${p.name} · build running`,
        time: p.lastActive,
        kind: 'running',
      })
    })
    projects.filter(p => p.status === 'error').forEach(p => {
      a.push({
        text: `${p.name} · build failed`,
        time: p.lastActive,
        kind: 'error',
      })
    })
    if (a.length === 0) {
      a.push({ text: 'no active alerts', time: '', kind: 'idle' })
    }
    return a
  }, [projects])

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (deleteTarget) setDeleteTarget(null)
        else if (accountOpen) setAccountOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [deleteTarget, accountOpen])

  // Toast auto-dismiss
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 2400)
      return () => clearTimeout(t)
    }
  }, [toast])

  // Close account popover on outside click
  useEffect(() => {
    if (!accountOpen) return
    const onDoc = (e: MouseEvent) => {
      const el = document.querySelector('.account-pop-wrap')
      if (el && !el.contains(e.target as Node)) setAccountOpen(false)
    }
    setTimeout(() => document.addEventListener('click', onDoc), 0)
    return () => document.removeEventListener('click', onDoc)
  }, [accountOpen])

  const userName = user?.name || user?.email?.split('@')[0] || 'User'
  const userInitials = userName.slice(0, 2).toUpperCase()

  // Sample activities (eventually from API)
  const activities = projects.slice(0, 8).map(p => ({
    time: p.lastActive, who: 'Agent', proj: p.name,
    verb: 'worked on', target: p.name, detail: `${p.files} files · ${p.tokens}`,
    kind: p.status === 'running' ? 'route' : p.status === 'error' ? 'fail' : 'ok',
  }))

  return (
    <div className="app no-rail-mode">
      <div className="topbar">
        <div className="crumbs">
          <div className="logo">tm</div>
          <span className="seg">src</span>
          <span className="sep">›</span>
          <span className="seg active">dashboard</span>
          <span className="sep">›</span>
          <span className="seg" style={{ color: 'var(--accent)' }}>{tab === 'create' ? 'create' : 'projects'}</span>
        </div>

        <div className="tabs">
          <button className={tab === 'create' ? 'active' : ''} onClick={() => setTab('create')}>＋ Create</button>
          <button className={tab === 'projects' ? 'active' : ''} onClick={() => setTab('projects')}>
            ▦ Projects <span style={{ marginLeft: 4, opacity: 0.6 }}>{projects.length}</span>
          </button>
        </div>

        <div className="spacer" />

        {/* Alerts dropdown */}
        <div style={{ position: 'relative' }}>
          <button className="iconbtn" onClick={() => setAlertsOpen(!alertsOpen)}
            title="Alerts">
            ⌖ {alerts.filter(a => a.kind !== 'idle').length || 0} alerts
          </button>
          {alertsOpen && (
            <>
              <div style={{ position: 'fixed', inset: 0, zIndex: 40 }}
                onClick={() => setAlertsOpen(false)} />
              <div className="status-menu" style={{ position: 'absolute', top: '100%', right: 0, marginTop: 4, width: 280, zIndex: 50 }}
                onClick={e => e.stopPropagation()}>
                <div className="status-menu-head">alerts</div>
                {alerts.map((a, i) => (
                  <div key={i} className="status-menu-row" style={{ cursor: 'default' }}>
                    <span className={'status-dot ' + a.kind} />
                    <span style={{ fontSize: 10, color: 'var(--text)' }}>{a.text}</span>
                    {a.time && <span style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--text-faint)' }}>{a.time}</span>}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="account-pop-wrap" style={{ position: 'relative' }}>
          <button className="iconbtn" onClick={() => setAccountOpen(!accountOpen)}
            style={{ padding: '3px 8px 3px 4px' }}>
            <div className="avatar">{userInitials}</div>
            <span style={{ color: 'var(--text-dim)' }}>{userName}</span>
            <span style={{ color: 'var(--text-faint)' }}>▾</span>
          </button>
          {accountOpen && (
            <div className="account-pop fadein">
              <div className="ap-head">
                <div className="avatar" style={{ width: 30, height: 30, fontSize: 11 }}>{userInitials}</div>
                <div className="info">
                  <div className="nm">{user?.name || 'User'}</div>
                  <div className="em">{user?.email || ''}</div>
                </div>
              </div>
              <div className="ap-row" onClick={() => { setAccountOpen(false); navigate('/settings') }}>
                <span className="ic">⚙</span> Account settings
              </div>
              <div className="ap-row" onClick={() => { setAccountOpen(false); navigate('/billing') }}>
                <span className="ic">💳</span> Billing & credits
              </div>
              <div className="ap-row" onClick={() => { setAccountOpen(false); setToast('api keys — coming soon') }}>
                <span className="ic">🔑</span> API keys
              </div>
              <div className="ap-sep" />
              <div className="ap-row" onClick={() => { setAccountOpen(false); setToast('docs — coming soon') }}>
                <span className="ic">📖</span> Docs
              </div>
              <div className="ap-sep" />
              <div className="ap-row" style={{ color: 'var(--danger)' }} onClick={() => { setAccountOpen(false); setToast('sign out — placeholder') }}>
                <span className="ic">↗</span> Sign out
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="main no-rail">
        <div className="canvas">
          <div className="widgets">
            <CreditWidget usage={usage} />
            <ProjectCountWidget count={projects.length} activeCount={projects.filter(p => p.status === 'running' || p.status === 'ready').length} />
            <TasksWidget totalMessages={283} />
            <QuickActionsWidget onAction={handleQuickAction} lastProjectName={projects[0]?.name} />
          </div>

          {tab === 'create' ? (
            <CreateTab onLaunch={launchNew} />
          ) : (
            <ProjectsTab
              projects={projects} activeId={activeId} onOpen={openInAgent}
              onDelete={confirmDelete} onChangeStatus={changeStatus}
              query={query} setQuery={setQuery} filter={filter} setFilter={setFilter}
              onCreateNew={() => setTab('create')}
            />
          )}

          {activities.length > 0 && <ActivityFeed items={activities} />}
        </div>
      </div>

      <StatusBar tab={tab} projectCount={projects.length} creditPct={creditPct} />

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <div className="modal-mask fadein" onClick={() => setDeleteTarget(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>// delete project</h3>
            <p>You're about to permanently delete <span className="danger-target">{deleteTarget.name}</span>. This removes all agent transcripts, logged outputs, and changed file history. This cannot be undone.</p>
            <div className="modal-cta">
              <button className="btn ghost" onClick={() => setDeleteTarget(null)}>Cancel</button>
              <button className="btn danger" onClick={doDelete}>Delete project</button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="fadein toast-bar" style={{
          position: 'fixed', bottom: 36, left: '50%', transform: 'translateX(-50%)',
          background: 'var(--bg-elev)', border: '1px solid var(--border-strong)',
          padding: '8px 14px', borderRadius: 6, fontSize: 11, color: 'var(--text)',
          boxShadow: 'var(--shadow)', zIndex: 100,
        }}>
          <span style={{ color: 'var(--accent)', marginRight: 6 }}>▌</span>
          {toast}
        </div>
      )}
    </div>
  )
}
