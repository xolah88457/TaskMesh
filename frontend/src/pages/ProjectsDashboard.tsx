import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthFetch } from '../hooks/useAuthFetch'

interface RunSummary {
  id: string
  brief: string
  status: 'running' | 'done' | 'cancelled' | 'error'
  agents_used: string[]
  started_at: string | null
  finished_at: string | null
  file_count: number
}

interface RunFile {
  path: string
  size: number
  content: string
}

interface RunDetail extends RunSummary {
  files: RunFile[]
}

function statusBadge(status: RunSummary['status']) {
  const map: Record<string, { label: string; color: string }> = {
    done:      { label: 'Done',      color: '#22c55e' },
    running:   { label: 'Running',   color: '#a855f7' },
    cancelled: { label: 'Cancelled', color: '#f59e0b' },
    error:     { label: 'Error',     color: '#ef4444' },
  }
  const { label, color } = map[status] ?? { label: status, color: '#6b7280' }
  return (
    <span
      className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded"
      style={{ background: `${color}22`, color }}
    >
      {label}
    </span>
  )
}

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function formatDuration(start: string | null, end: string | null) {
  if (!start || !end) return ''
  const ms = new Date(end).getTime() - new Date(start).getTime()
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

export default function ProjectsDashboard() {
  const authFetch = useAuthFetch()
  const navigate = useNavigate()
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<RunDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [activeFile, setActiveFile] = useState<RunFile | null>(null)
  const [ghConnected, setGhConnected] = useState<boolean | null>(null)
  const [ghRepo, setGhRepo]           = useState('')
  const [ghBranch, setGhBranch]       = useState('main')
  const [pushing, setPushing]         = useState(false)
  const [prUrl, setPrUrl]             = useState<string | null>(null)
  const [connectingGh, setConnectingGh] = useState(false)

  useEffect(() => {
    authFetch('/api/github/status')
      .then(r => r.json())
      .then(d => setGhConnected(d.connected ?? false))
      .catch(() => setGhConnected(false))
  }, [authFetch])

  useEffect(() => {
    authFetch('/api/runs')
      .then(r => r.json())
      .then(data => setRuns(Array.isArray(data) ? data : []))
      .catch(() => setRuns([]))
      .finally(() => setLoading(false))
  }, [authFetch])

  const pushToGitHub = useCallback(async () => {
    if (!selected || !ghRepo.trim()) return
    setPushing(true)
    setPrUrl(null)
    try {
      const r = await authFetch('/api/github/push', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: selected.id, repo: ghRepo.trim(), branch: ghBranch || 'main' }),
      })
      const data = await r.json()
      if (data.pr_url) {
        setPrUrl(data.pr_url)
      } else if (data.branch) {
        setPrUrl(`Branch pushed: ${data.branch}`)
      } else {
        alert(data.detail ?? 'Push failed')
      }
    } catch {
      alert('GitHub push failed')
    } finally {
      setPushing(false)
    }
  }, [authFetch, selected, ghRepo, ghBranch])

  const openRun = async (id: string) => {
    setLoadingDetail(true)
    setActiveFile(null)
    setPrUrl(null)
    try {
      const r = await authFetch(`/api/runs/${id}`)
      const data = await r.json()
      setSelected(data)
    } catch {
      setSelected(null)
    } finally {
      setLoadingDetail(false)
    }
  }

  const downloadFile = (file: RunFile) => {
    const blob = new Blob([file.content], { type: 'text/plain' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = file.path.split('/').pop() ?? 'file.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div
      className="w-full h-full flex flex-col overflow-hidden font-mono"
      style={{ background: 'var(--c-bg)', color: 'var(--c-text-1)' }}
    >
      {/* Topbar */}
      <div
        className="flex items-center gap-3 px-4 py-2 shrink-0 border-b"
        style={{ background: 'var(--c-surface-1)', borderColor: 'var(--c-border)' }}
      >
        <button
          onClick={() => navigate('/')}
          className="text-xs px-2 py-1 rounded transition-colors"
          style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-3)' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-text-1)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-3)')}
        >
          ← Back
        </button>
        <span className="text-[var(--c-accent)] font-bold tracking-widest text-xs uppercase">
          TASKMESH
        </span>
        <span className="text-[var(--c-text-4)] text-xs">›</span>
        <span className="text-[var(--c-text-1)] text-xs">Projects</span>
      </div>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Run list */}
        <div
          className="w-80 shrink-0 flex flex-col border-r overflow-hidden"
          style={{ borderColor: 'var(--c-border)' }}
        >
          <div className="px-4 pt-3 pb-2 shrink-0">
            <p className="text-[10px] tracking-widest uppercase" style={{ color: 'var(--c-text-3)' }}>
              Run History
            </p>
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading && (
              <p className="px-4 py-2 text-xs" style={{ color: 'var(--c-text-4)' }}>Loading…</p>
            )}
            {!loading && runs.length === 0 && (
              <p className="px-4 py-2 text-xs" style={{ color: 'var(--c-text-4)' }}>
                No runs yet. Start a project from the main page.
              </p>
            )}
            {runs.map(run => (
              <button
                key={run.id}
                onClick={() => openRun(run.id)}
                className="w-full text-left px-4 py-2.5 border-b transition-colors block"
                style={{
                  borderColor: 'var(--c-border)',
                  background: selected?.id === run.id ? 'var(--c-surface-2)' : 'transparent',
                }}
                onMouseEnter={e => { if (selected?.id !== run.id) (e.currentTarget as HTMLElement).style.background = 'var(--c-surface-2)' }}
                onMouseLeave={e => { if (selected?.id !== run.id) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  {statusBadge(run.status)}
                  <span className="text-[10px]" style={{ color: 'var(--c-text-4)' }}>
                    {formatDate(run.started_at)}
                  </span>
                </div>
                <p className="text-xs leading-snug" style={{ color: 'var(--c-text-1)' }}>
                  {run.brief}
                </p>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-[9px]" style={{ color: 'var(--c-text-4)' }}>
                    {run.file_count} file{run.file_count !== 1 ? 's' : ''}
                  </span>
                  {run.finished_at && (
                    <span className="text-[9px]" style={{ color: 'var(--c-text-4)' }}>
                      {formatDuration(run.started_at, run.finished_at)}
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Detail panel */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {!selected && !loadingDetail && (
            <div className="flex items-center justify-center h-full">
              <p className="text-xs" style={{ color: 'var(--c-text-4)' }}>
                Select a run to view details
              </p>
            </div>
          )}
          {loadingDetail && (
            <div className="flex items-center justify-center h-full">
              <p className="text-xs" style={{ color: 'var(--c-text-4)' }}>Loading…</p>
            </div>
          )}
          {selected && !loadingDetail && (
            <div className="flex flex-1 flex-col min-h-0 overflow-hidden">
              {/* GitHub push bar */}
              {selected.status === 'done' && selected.files.length > 0 && (
                <div
                  className="shrink-0 px-4 py-2 border-b flex items-center gap-2 flex-wrap"
                  style={{ borderColor: 'var(--c-border)', background: 'var(--c-surface-1)' }}
                >
                  {ghConnected === false && (
                    <button
                      onClick={async () => {
                        setConnectingGh(true)
                        try {
                          const r = await authFetch('/api/github/auth')
                          const { auth_url } = await r.json()
                          if (auth_url) window.location.href = auth_url
                        } catch { /* ignore */ } finally {
                          setConnectingGh(false)
                        }
                      }}
                      disabled={connectingGh}
                      className="text-[10px] px-2 py-1 rounded font-mono disabled:opacity-40"
                      style={{ border: '1px solid var(--c-border)', color: 'var(--c-accent)' }}
                    >
                      {connectingGh ? 'Connecting…' : 'Connect GitHub'}
                    </button>
                  )}
                  {ghConnected === true && (
                    <>
                      <input
                        type="text"
                        value={ghRepo}
                        onChange={e => setGhRepo(e.target.value)}
                        placeholder="owner/repo"
                        className="text-[10px] px-2 py-1 rounded font-mono w-36"
                        style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
                      />
                      <input
                        type="text"
                        value={ghBranch}
                        onChange={e => setGhBranch(e.target.value)}
                        placeholder="main"
                        className="text-[10px] px-2 py-1 rounded font-mono w-20"
                        style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
                      />
                      <button
                        onClick={pushToGitHub}
                        disabled={pushing || !ghRepo.trim()}
                        className="text-[10px] px-2 py-1 rounded font-mono font-bold disabled:opacity-40"
                        style={{ background: 'var(--c-accent)', color: '#000' }}
                      >
                        {pushing ? 'Pushing…' : '↑ Push to GitHub'}
                      </button>
                      {prUrl && (
                        prUrl.startsWith('http') ? (
                          <a
                            href={prUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[10px]"
                            style={{ color: 'var(--c-accent)' }}
                          >
                            View PR ↗
                          </a>
                        ) : (
                          <span className="text-[10px]" style={{ color: '#22c55e' }}>{prUrl}</span>
                        )
                      )}
                    </>
                  )}
                </div>
              )}
            <div className="flex flex-1 min-h-0 overflow-hidden">
              {/* File list */}
              <div
                className="w-56 shrink-0 border-r flex flex-col overflow-hidden"
                style={{ borderColor: 'var(--c-border)' }}
              >
                <div className="px-3 pt-3 pb-2 shrink-0">
                  <p className="text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--c-text-3)' }}>
                    Output Files
                  </p>
                  <div className="flex gap-2 items-center">
                    {statusBadge(selected.status)}
                    {selected.agents_used.length > 0 && (
                      <span className="text-[9px]" style={{ color: 'var(--c-text-4)' }}>
                        {selected.agents_used.length} agents
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto">
                  {selected.files.length === 0 && (
                    <p className="px-3 py-2 text-[10px]" style={{ color: 'var(--c-text-4)' }}>
                      No files written.
                    </p>
                  )}
                  {selected.files.map(f => (
                    <div
                      key={f.path}
                      className="flex items-center gap-1 px-3 py-1.5 border-b cursor-pointer transition-colors"
                      style={{
                        borderColor: 'var(--c-border)',
                        background: activeFile?.path === f.path ? 'var(--c-surface-2)' : 'transparent',
                      }}
                      onClick={() => setActiveFile(f)}
                    >
                      <span className="flex-1 text-[10px] truncate" style={{ color: 'var(--c-text-2)' }}>
                        {f.path}
                      </span>
                      <button
                        onClick={e => { e.stopPropagation(); downloadFile(f) }}
                        title="Download"
                        className="text-[10px] px-1 rounded shrink-0"
                        style={{ color: 'var(--c-text-4)' }}
                        onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-accent)')}
                        onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-4)')}
                      >
                        ↓
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* File content viewer */}
              <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                {!activeFile && (
                  <div className="flex items-center justify-center h-full">
                    <p className="text-xs" style={{ color: 'var(--c-text-4)' }}>
                      Select a file to preview
                    </p>
                  </div>
                )}
                {activeFile && (
                  <>
                    <div
                      className="flex items-center justify-between px-4 py-2 shrink-0 border-b"
                      style={{ borderColor: 'var(--c-border)', background: 'var(--c-surface-1)' }}
                    >
                      <span className="text-xs" style={{ color: 'var(--c-text-2)' }}>
                        {activeFile.path}
                      </span>
                      <button
                        onClick={() => downloadFile(activeFile)}
                        className="text-xs px-2 py-0.5 rounded transition-colors"
                        style={{ border: '1px solid var(--c-border)', color: 'var(--c-accent)' }}
                      >
                        Download
                      </button>
                    </div>
                    <pre
                      className="flex-1 overflow-auto px-4 py-3 text-[11px] leading-relaxed"
                      style={{ color: 'var(--c-text-2)', background: 'var(--c-surface-1)' }}
                    >
                      {activeFile.content}
                    </pre>
                  </>
                )}
              </div>
            </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
