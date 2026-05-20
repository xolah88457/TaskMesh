import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthFetch } from '../hooks/useAuthFetch'
import { useSocket } from '../hooks/useSocket'

interface Usage {
  plan: 'none' | 'starter' | 'pro'
  balance_cents: number
  run_count: number
}

// ── Plan definitions ───────────────────────────────────────────────────────────

const PLANS = [
  {
    id:    'starter',
    name:  'Starter',
    price: '$30',
    period: '/mo',
    allocatedCents: 1500,
    features: [
      'Up to 3 agents per run',
      '$15 API credits / month',
      'All standard models',
      'File output to disk',
      'Run history + downloads',
      'Unlimited runs (credit permitting)',
    ],
    locked: [],
    cta: 'Subscribe — $30/mo',
  },
  {
    id:    'pro',
    name:  'Pro',
    price: '$80',
    period: '/mo',
    allocatedCents: 4000,
    features: [
      'All 9 agents per run',
      '$40 API credits / month',
      'All models including flagship',
      'File output to disk',
      'Run history + downloads',
      'Unlimited runs (credit permitting)',
      'Shared agent config',
      'GitHub push after run',
      'Priority support',
    ],
    locked: [],
    cta: 'Subscribe — $80/mo',
  },
] as const

const PACKS = [
  { id: 'pack_s', label: 'Add $10',  subLabel: '$20 purchase',  cents: 1000 },
  { id: 'pack_m', label: 'Add $25',  subLabel: '$50 purchase',  cents: 2500 },
  { id: 'pack_l', label: 'Add $50',  subLabel: '$100 purchase', cents: 5000 },
] as const

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtDollars(cents: number): string {
  return '$' + (cents / 100).toFixed(2)
}

function BalanceBar({ balanceCents, allocatedCents }: { balanceCents: number; allocatedCents: number }) {
  const pct     = allocatedCents > 0 ? Math.min(100, (balanceCents / allocatedCents) * 100) : 0
  const low     = balanceCents < 50    // < $0.50
  const warn    = !low && balanceCents < 200  // < $2.00

  const barColor = low  ? '#ef4444'
                 : warn ? '#f59e0b'
                 :        'var(--c-accent)'

  return (
    <div>
      <div className="flex justify-between text-xs mb-1.5" style={{ color: 'var(--c-text-2)' }}>
        <span>Credit balance</span>
        <span style={{ color: low ? '#ef4444' : warn ? '#f59e0b' : 'var(--c-text-1)' }}>
          {fmtDollars(balanceCents)} remaining
        </span>
      </div>
      <div
        className="w-full h-2 rounded-full overflow-hidden"
        style={{ background: 'var(--c-surface-3)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: barColor }}
        />
      </div>
      {(low || warn) && (
        <p className="mt-1.5 text-[10px]" style={{ color: low ? '#ef4444' : '#f59e0b' }}>
          {low
            ? 'Balance critically low — add credits or renew your subscription to continue running agents.'
            : 'Balance low — consider topping up soon.'}
        </p>
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function BillingPage() {
  const authFetch                   = useAuthFetch()
  const navigate                    = useNavigate()
  const { state }                   = useSocket()
  const [usage, setUsage]           = useState<Usage | null>(null)
  const [loading, setLoading]       = useState(true)
  const [checkingOut, setCheckingOut] = useState<string | null>(null)
  const pollRef                     = useRef<ReturnType<typeof setInterval> | null>(null)
  const [adminOpen, setAdminOpen]   = useState(false)
  const [adminKey, setAdminKey]     = useState('')
  const [adminMsg, setAdminMsg]     = useState('')
  const [adminBusy, setAdminBusy]   = useState(false)

  const submitAdminBypass = async () => {
    if (!adminKey.trim()) return
    setAdminBusy(true)
    setAdminMsg('')
    try {
      const r = await authFetch('/api/billing/admin-bypass', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ key: adminKey.trim() }),
      })
      if (r.ok) {
        setAdminMsg('Access granted.')
        setAdminKey('')
        fetchUsage()
      } else {
        setAdminMsg('Invalid key.')
      }
    } catch {
      setAdminMsg('Error — is the backend running?')
    } finally {
      setAdminBusy(false)
    }
  }

  const fetchUsage = () =>
    authFetch('/api/billing/usage')
      .then(r => r.json())
      .then(setUsage)
      .catch(() => {})
      .finally(() => setLoading(false))

  useEffect(() => {
    fetchUsage()
  }, [authFetch])

  // Poll every 30 s while a run is active so balance updates live
  useEffect(() => {
    if (state.running) {
      if (!pollRef.current) {
        pollRef.current = setInterval(fetchUsage, 30_000)
      }
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
        fetchUsage()  // one final refresh when run ends
      }
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [state.running])

  const checkout = async (planId: string) => {
    setCheckingOut(planId)
    try {
      const r = await authFetch('/api/billing/checkout', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ plan: planId }),
      })
      const data = await r.json()
      if (data.checkout_url) {
        window.open(data.checkout_url, '_blank')
      } else {
        alert(data.detail ?? 'Failed to start checkout')
      }
    } catch {
      alert('Failed to start checkout — is the backend running?')
    } finally {
      setCheckingOut(null)
    }
  }

  const currentPlan   = usage?.plan ?? 'none'
  const balanceCents  = usage?.balance_cents ?? 0
  const allocatedCents = currentPlan === 'pro' ? 4000 : currentPlan === 'starter' ? 1500 : 0

  return (
    <div
      className="w-full h-full flex flex-col overflow-hidden font-mono"
      style={{ background: 'var(--c-bg)', color: 'var(--c-text-1)' }}
    >
      {/* ── Top bar ── */}
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
        <span className="text-[var(--c-text-1)] text-xs">Billing</span>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-8" style={{ maxWidth: 720 }}>

        {/* ── No-plan banner ── */}
        {!loading && currentPlan === 'none' && (
          <div
            className="mb-6 px-4 py-3 rounded border text-xs"
            style={{ background: 'rgba(234,179,8,0.08)', borderColor: 'rgba(234,179,8,0.35)', color: '#f59e0b' }}
          >
            No active plan — choose a plan below to start running agents.
          </div>
        )}

        {/* ── Credit balance (shown when on a plan) ── */}
        {!loading && currentPlan !== 'none' && (
          <div
            className="mb-8 px-4 py-4 rounded border"
            style={{ background: 'var(--c-surface-2)', borderColor: 'var(--c-border)' }}
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--c-text-3)' }}>
                {currentPlan === 'pro' ? 'Pro' : 'Starter'} Plan
              </span>
              <span className="text-[10px]" style={{ color: 'var(--c-text-3)' }}>
                {usage?.run_count ?? 0} run{(usage?.run_count ?? 0) !== 1 ? 's' : ''} this month
              </span>
            </div>
            <BalanceBar balanceCents={balanceCents} allocatedCents={allocatedCents} />
          </div>
        )}

        {loading && (
          <p className="text-xs mb-8" style={{ color: 'var(--c-text-4)' }}>Loading…</p>
        )}

        {/* ── Plan cards ── */}
        <h2 className="text-[10px] uppercase tracking-widest mb-4" style={{ color: 'var(--c-text-3)' }}>
          Plans
        </h2>
        <div className="grid grid-cols-1 gap-4 mb-8 sm:grid-cols-2">
          {PLANS.map(plan => {
            const isCurrent = currentPlan === plan.id
            return (
              <div
                key={plan.id}
                className="rounded border px-5 py-4 flex flex-col"
                style={{
                  borderColor: isCurrent ? 'var(--c-accent-border)' : 'var(--c-border)',
                  background:  isCurrent ? 'var(--c-accent-dim)'    : 'var(--c-surface-2)',
                }}
              >
                <div className="flex items-baseline gap-2 mb-3">
                  <span className="text-sm font-bold" style={{ color: 'var(--c-text-1)' }}>
                    {plan.name}
                  </span>
                  <span className="text-lg font-bold" style={{ color: 'var(--c-accent)' }}>
                    {plan.price}
                  </span>
                  <span className="text-xs" style={{ color: 'var(--c-text-4)' }}>
                    {plan.period}
                  </span>
                  {isCurrent && (
                    <span
                      className="text-[9px] font-bold px-1.5 py-0.5 rounded ml-auto"
                      style={{ background: 'var(--c-accent)', color: '#000' }}
                    >
                      CURRENT
                    </span>
                  )}
                </div>

                <ul className="flex-1 mb-4 space-y-1">
                  {plan.features.map(f => (
                    <li key={f} className="text-xs flex items-start gap-2" style={{ color: 'var(--c-text-2)' }}>
                      <span style={{ color: 'var(--c-accent)', flexShrink: 0, marginTop: 1 }}>✓</span>
                      {f}
                    </li>
                  ))}
                </ul>

                {!isCurrent && (
                  <button
                    onClick={() => checkout(plan.id)}
                    disabled={!!checkingOut}
                    className="w-full text-xs py-2 rounded font-bold transition-opacity disabled:opacity-50"
                    style={{ background: 'var(--c-accent)', color: '#000' }}
                  >
                    {checkingOut === plan.id ? 'Opening checkout…' : plan.cta}
                  </button>
                )}

                {isCurrent && (
                  <p className="text-[10px] text-center" style={{ color: 'var(--c-text-4)' }}>
                    Manage via Paddle customer portal
                  </p>
                )}
              </div>
            )
          })}
        </div>

        {/* ── Pay-as-you-go packs ── */}
        <h2 className="text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--c-text-3)' }}>
          Top up credits
        </h2>
        <p className="text-[10px] mb-4" style={{ color: 'var(--c-text-4)' }}>
          One-time purchases · no expiry · 50% goes to API credits
        </p>
        <div className="flex flex-wrap gap-3">
          {PACKS.map(pack => (
            <button
              key={pack.id}
              onClick={() => checkout(pack.id)}
              disabled={!!checkingOut || currentPlan === 'none'}
              className="flex flex-col items-center px-5 py-3 rounded border text-xs font-bold disabled:opacity-40 transition-colors"
              style={{ borderColor: 'var(--c-border)', background: 'var(--c-surface-2)', color: 'var(--c-text-1)' }}
              onMouseEnter={e => { if (!checkingOut) (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--c-accent-border)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--c-border)' }}
              title={currentPlan === 'none' ? 'Requires an active subscription' : undefined}
            >
              <span style={{ color: 'var(--c-accent)', fontSize: 14 }}>
                {checkingOut === pack.id ? '…' : pack.label}
              </span>
              <span className="text-[10px] font-normal mt-0.5" style={{ color: 'var(--c-text-4)' }}>
                {pack.subLabel}
              </span>
            </button>
          ))}
        </div>
        {currentPlan === 'none' && !loading && (
          <p className="mt-2 text-[10px]" style={{ color: 'var(--c-text-4)' }}>
            An active subscription is required to top up credits.
          </p>
        )}

        {/* ── Admin bypass — hidden, no label ── */}
        <div className="mt-16 flex justify-end">
          <button
            onClick={() => { setAdminOpen(o => !o); setAdminMsg('') }}
            className="text-[9px] opacity-20 hover:opacity-40 transition-opacity"
            style={{ color: 'var(--c-text-4)' }}
          >
            ·
          </button>
        </div>
        {adminOpen && (
          <div
            className="mt-2 p-3 rounded border"
            style={{ borderColor: 'var(--c-border)', background: 'var(--c-surface-2)' }}
          >
            <div className="flex gap-2">
              <input
                type="password"
                value={adminKey}
                onChange={e => setAdminKey(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && submitAdminBypass()}
                placeholder="Access key"
                className="flex-1 text-xs font-mono rounded px-2 py-1 focus:outline-none"
                style={{
                  background: 'var(--c-input-bg)',
                  border: '1px solid var(--c-border)',
                  color: 'var(--c-text-1)',
                }}
              />
              <button
                onClick={submitAdminBypass}
                disabled={adminBusy || !adminKey.trim()}
                className="text-xs px-3 py-1 rounded disabled:opacity-40"
                style={{ background: 'var(--c-accent)', color: '#000' }}
              >
                {adminBusy ? '…' : '→'}
              </button>
            </div>
            {adminMsg && (
              <p className="mt-1.5 text-[10px]" style={{ color: adminMsg === 'Access granted.' ? 'var(--c-accent)' : '#ef4444' }}>
                {adminMsg}
              </p>
            )}
          </div>
        )}

      </div>
    </div>
  )
}
