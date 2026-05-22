import { useEffect, useState } from 'react'

interface CheckStatus {
  status: 'ok' | 'degraded' | 'unconfigured'
  detail: string
}

interface HealthStatus {
  status: 'ok' | 'degraded'
  checks: {
    zen_api:     CheckStatus
    database:    CheckStatus
    project_dir: CheckStatus
  }
  timestamp: string
}

const LABEL: Record<keyof HealthStatus['checks'], string> = {
  zen_api:     'Provider API',
  database:    'Database',
  project_dir: 'Output dir',
}

export default function HealthBanner() {
  const [health, setHealth] = useState<HealthStatus | null>(null)

  useEffect(() => {
    let cancelled = false

    const poll = async () => {
      try {
        const r = await fetch('/api/health')
        if (!r.ok) {
          if (!cancelled) {
            setHealth({
              status: 'degraded',
              checks: {
                zen_api:     { status: 'degraded', detail: `HTTP ${r.status}` },
                database:    { status: 'degraded', detail: 'unknown' },
                project_dir: { status: 'degraded', detail: 'unknown' },
              },
              timestamp: new Date().toISOString(),
            })
          }
          return
        }
        const data = (await r.json()) as HealthStatus
        if (!cancelled) setHealth(data)
      } catch {
        if (!cancelled) {
          setHealth({
            status: 'degraded',
            checks: {
              zen_api:     { status: 'degraded', detail: 'backend unreachable' },
              database:    { status: 'degraded', detail: 'backend unreachable' },
              project_dir: { status: 'degraded', detail: 'backend unreachable' },
            },
            timestamp: new Date().toISOString(),
          })
        }
      }
    }

    poll()
    const id = setInterval(poll, 60_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  if (!health || health.status === 'ok') return null

  const failing: string[] = []
  for (const key of Object.keys(health.checks) as (keyof HealthStatus['checks'])[]) {
    if (health.checks[key].status === 'degraded') {
      failing.push(`${LABEL[key]}: ${health.checks[key].detail}`)
    }
  }
  if (failing.length === 0) return null

  return (
    <div
      className="shrink-0 px-4 py-1.5 font-mono text-[10px] flex items-center gap-2 z-30"
      style={{
        background: 'rgba(239,68,68,0.12)',
        borderBottom: '1px solid rgba(239,68,68,0.35)',
        color: '#fca5a5',
      }}
      title={failing.join(' · ')}
    >
      <span style={{ color: '#ef4444', fontWeight: 700 }}>⚠ Degraded</span>
      <span className="truncate" style={{ color: '#fecaca' }}>
        {failing.join(' · ')}
      </span>
    </div>
  )
}
