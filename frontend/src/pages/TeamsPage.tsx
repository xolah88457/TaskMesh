import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthFetch } from '../hooks/useAuthFetch'

interface TeamSummary {
  id: string
  name: string
  description: string | null
  status: string
  created_at: string | null
  updated_at: string | null
}

interface RepoSummary {
  full_name:      string
  default_branch: string
  private:        boolean
}

type Gate = 'loading' | 'paywall' | 'github_required' | 'ready'

export default function TeamsPage() {
  const authFetch = useAuthFetch()
  const navigate  = useNavigate()
  const [teams, setTeams] = useState<TeamSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [gate, setGate] = useState<Gate>('loading')
  const [installUrl, setInstallUrl] = useState<string>('')
  const [repos,      setRepos]      = useState<RepoSummary[]>([])
  const [defaultRepo, setDefaultRepo] = useState<string>('')
  const [defaultBranch, setDefaultBranch] = useState<string>('main')
  const [creating, setCreating] = useState(false)
  const [name, setName]         = useState('')
  const [description, setDesc]  = useState('')
  const [error, setError]       = useState('')

  // Decide which view to show. Order: plan check → github check → ready.
  useEffect(() => {
    let cancelled = false
    const run = async () => {
      // Plan gate
      const usageResp = await authFetch('/api/billing/usage')
      if (cancelled) return
      if (!usageResp.ok) {
        setGate('paywall')
        return
      }
      const usage = await usageResp.json()
      if (usage.plan !== 'pro') {
        setGate('paywall')
        return
      }
      // GitHub gate
      const ghResp = await authFetch('/api/github/install/status')
      if (cancelled) return
      const gh = ghResp.ok ? await ghResp.json() : { installed: false }
      if (!gh.installed || !gh.default_repo) {
        // Fetch the install URL to render an Install button
        try {
          const urlResp = await authFetch('/api/github/install/url')
          if (urlResp.ok) {
            const u = await urlResp.json()
            if (!cancelled) setInstallUrl(u.install_url || '')
          }
        } catch { /* ignore */ }
        // If installed but no repo selected, load repos
        if (gh.installed) {
          try {
            const reposResp = await authFetch('/api/github/install/repos')
            if (reposResp.ok) {
              const data = await reposResp.json()
              if (!cancelled) setRepos(data.repositories ?? [])
            }
          } catch { /* ignore */ }
        }
        if (!cancelled) {
          setDefaultBranch(gh.default_branch || 'main')
          setGate('github_required')
        }
        return
      }
      if (!cancelled) setGate('ready')
    }
    run().catch(() => { if (!cancelled) setGate('paywall') })
    return () => { cancelled = true }
  }, [])

  const refresh = () => {
    setLoading(true)
    authFetch('/api/teams')
      .then(r => r.ok ? r.json() : { teams: [] })
      .then((d: { teams?: TeamSummary[] }) => setTeams(d.teams ?? []))
      .catch(() => setTeams([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (gate === 'ready') refresh()
  }, [gate])

  const saveRepo = async () => {
    if (!defaultRepo) return
    const r = await authFetch('/api/github/install/repo', {
      method:  'PUT',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ default_repo: defaultRepo, default_branch: defaultBranch || 'main' }),
    })
    if (r.ok) setGate('ready')
    else setError('Could not save repo selection')
  }

  const createTeam = async () => {
    if (name.trim().length < 2) {
      setError('Name must be at least 2 characters')
      return
    }
    setCreating(true)
    setError('')
    try {
      const r = await authFetch('/api/teams', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ name: name.trim(), description: description.trim() }),
      })
      const d = await r.json()
      if (!r.ok) {
        const code = (typeof d.detail === 'string' ? d.detail : d.detail?.error) || 'failed'
        setError(code)
        return
      }
      setName('')
      setDesc('')
      navigate(`/teams/${d.id}`)
    } catch {
      setError('Network error')
    } finally {
      setCreating(false)
    }
  }

  const deleteTeam = async (id: string, n: string) => {
    if (!window.confirm(`Delete team "${n}"? This removes all members, tasks, and messages.`)) return
    try {
      await authFetch(`/api/teams/${id}`, { method: 'DELETE' })
      setTeams(t => t.filter(x => x.id !== id))
    } catch {
      setError('Could not delete team')
    }
  }

  if (gate === 'loading') {
    return (
      <Frame onBack={() => navigate('/')}>
        <p className="text-xs px-6 py-8" style={{ color: 'var(--c-text-4)' }}>Loading Agent Teams…</p>
      </Frame>
    )
  }

  if (gate === 'paywall') {
    return (
      <Frame onBack={() => navigate('/')}>
        <div className="max-w-md mx-auto px-6 py-12 text-center">
          <h2 className="text-sm font-bold mb-2" style={{ color: 'var(--c-text-1)' }}>Agent Teams — Pro & Top-Up only</h2>
          <p className="text-xs mb-6" style={{ color: 'var(--c-text-3)' }}>
            Agent Teams runs are part of the Pro plan, or any one-time credit pack purchase.
            Upgrade your plan or buy a pack to unlock team workspaces.
          </p>
          <button
            onClick={() => navigate('/billing')}
            className="text-xs px-3 py-2 rounded font-bold"
            style={{ background: 'var(--c-accent)', color: '#000' }}
          >
            Go to Billing
          </button>
        </div>
      </Frame>
    )
  }

  if (gate === 'github_required') {
    return (
      <Frame onBack={() => navigate('/')}>
        <div className="max-w-md mx-auto px-6 py-12">
          <h2 className="text-sm font-bold mb-2" style={{ color: 'var(--c-text-1)' }}>Connect GitHub</h2>
          <p className="text-xs mb-4" style={{ color: 'var(--c-text-3)' }}>
            Agent Teams writes its output — generated code, configs, and run artifacts — to a repository in your own GitHub account.
            Install the TaskMesh GitHub App and choose a repo to continue.
          </p>
          {installUrl && (
            <a
              href={installUrl}
              className="inline-block text-xs px-3 py-2 rounded font-bold mb-6"
              style={{ background: 'var(--c-accent)', color: '#000' }}
            >
              Install TaskMesh on GitHub
            </a>
          )}
          {repos.length > 0 && (
            <div className="mt-4">
              <p className="text-[10px] uppercase tracking-widest mb-2" style={{ color: 'var(--c-text-3)' }}>Pick a repository</p>
              <select
                value={defaultRepo}
                onChange={e => setDefaultRepo(e.target.value)}
                className="w-full text-xs px-2 py-1 rounded mb-2"
                style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
              >
                <option value="">— select —</option>
                {repos.map(r => (
                  <option key={r.full_name} value={r.full_name}>
                    {r.full_name} ({r.private ? 'private' : 'public'})
                  </option>
                ))}
              </select>
              <input
                value={defaultBranch}
                onChange={e => setDefaultBranch(e.target.value)}
                placeholder="branch (default: main)"
                className="w-full text-xs px-2 py-1 rounded mb-2"
                style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
              />
              <button
                disabled={!defaultRepo}
                onClick={saveRepo}
                className="w-full text-xs px-3 py-2 rounded font-bold disabled:opacity-40"
                style={{ background: 'var(--c-accent)', color: '#000' }}
              >
                Save and continue
              </button>
              {error && <p className="text-[10px] mt-2" style={{ color: '#ef4444' }}>{error}</p>}
            </div>
          )}
        </div>
      </Frame>
    )
  }

  return (
    <Frame onBack={() => navigate('/')}>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-8">

          <div className="mb-8 rounded border p-4" style={{ borderColor: 'var(--c-border)', background: 'var(--c-surface-1)' }}>
            <h2 className="text-[10px] uppercase tracking-widest mb-3" style={{ color: 'var(--c-text-3)' }}>New team</h2>
            <input
              type="text"
              placeholder="Team name"
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full text-xs px-3 py-2 rounded mb-2"
              style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
            />
            <textarea
              placeholder="What is this team for?"
              value={description}
              onChange={e => setDesc(e.target.value)}
              rows={2}
              className="w-full text-xs px-3 py-2 rounded mb-2"
              style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
            />
            {error && <p className="text-[10px] mb-2" style={{ color: '#ef4444' }}>{error}</p>}
            <button
              onClick={createTeam}
              disabled={creating || name.trim().length < 2}
              className="text-xs px-3 py-1.5 rounded font-bold disabled:opacity-50"
              style={{ background: 'var(--c-accent)', color: '#000' }}
            >
              {creating ? 'Creating…' : '+ Create team'}
            </button>
          </div>

          <h2 className="text-[10px] uppercase tracking-widest mb-3" style={{ color: 'var(--c-text-3)' }}>
            Your teams {loading ? '…' : `(${teams.length})`}
          </h2>

          {!loading && teams.length === 0 && (
            <p className="text-xs" style={{ color: 'var(--c-text-4)' }}>
              No teams yet. Create one above to get started.
            </p>
          )}

          <ul className="grid gap-2">
            {teams.map(t => (
              <li
                key={t.id}
                className="rounded border p-3 flex items-center gap-3"
                style={{ borderColor: 'var(--c-border)', background: 'var(--c-surface-1)' }}
              >
                <div className="flex-1 min-w-0 cursor-pointer" onClick={() => navigate(`/teams/${t.id}`)}>
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-bold" style={{ color: 'var(--c-text-1)' }}>{t.name}</span>
                    <span className="text-[9px] uppercase tracking-widest" style={{ color: 'var(--c-text-4)' }}>{t.status}</span>
                  </div>
                  {t.description && (
                    <p className="text-[11px] mt-1 truncate" style={{ color: 'var(--c-text-3)' }}>{t.description}</p>
                  )}
                </div>
                <button
                  className="text-xs px-2 py-1 rounded"
                  style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-3)' }}
                  onClick={() => navigate(`/teams/${t.id}`)}
                >
                  Open →
                </button>
                <button
                  className="text-xs px-2 py-1 rounded"
                  style={{ border: '1px solid var(--c-border)', color: '#ef4444' }}
                  onClick={() => deleteTeam(t.id, t.name)}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>

        </div>
      </div>
    </Frame>
  )
}

function Frame({ children, onBack }: { children: React.ReactNode; onBack?: () => void }) {
  return (
    <div className="w-full h-full flex flex-col overflow-hidden font-mono" style={{ background: 'var(--c-bg)', color: 'var(--c-text-1)' }}>
      <div className="flex items-center gap-3 px-4 py-2 shrink-0 border-b" style={{ background: 'var(--c-surface-1)', borderColor: 'var(--c-border)' }}>
        {onBack && (
          <button
            onClick={onBack}
            className="text-xs px-2 py-1 rounded"
            style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-3)' }}
          >
            ← Dashboard
          </button>
        )}
        <span className="text-[var(--c-accent)] font-bold tracking-widest text-xs">TASKMESH</span>
        <span className="text-[var(--c-text-4)] text-xs">›</span>
        <span className="text-xs">Agent teams</span>
      </div>
      {children}
    </div>
  )
}
