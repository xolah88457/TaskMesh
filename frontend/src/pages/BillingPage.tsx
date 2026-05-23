import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthFetch } from '../hooks/useAuthFetch'

interface Usage {
  plan: 'none' | 'starter' | 'pro'
  balance_cents: number
  run_count: number
}

const PLANS = [
  {
    id:             'starter',
    name:           'Starter',
    price:          '$30',
    period:         '/mo',
    allocatedCents: 1500,
    bonusText:      undefined,
    features: [
      'Up to 3 agents per run',
      'All Balanced & Budget models',
      'File output to disk',
      'Run history + downloads',
      'Unlimited runs (credit permitting)',
    ],
    cta: 'Subscribe — $30/mo',
  },
  {
    id:             'pro',
    name:           'Pro',
    price:          '$80',
    period:         '/mo',
    allocatedCents: 4800,
    bonusText:      '+10% more credits',
    features: [
      'All agents per run',
      'All models including flagship',
      'File output to disk',
      'Run history + downloads',
      'Unlimited runs (credit permitting)',
      'Shared agent config',
      'GitHub push after run',
      'Priority support',
    ],
    cta: 'Subscribe — $80/mo',
  },
] as const

const PRO_FEATURES = [
  'All agents per run',
  'All models including flagship',
  'File output to disk',
  'Run history + downloads',
  'Unlimited runs (credit permitting)',
  'Shared agent config',
  'GitHub push after run',
  'Priority support',
] as const

const PACK_CARDS = [
  {
    id: 'pack_s',
    name: 'Pack S',
    price: '$20',
    period: 'one-time',
    features: [...PRO_FEATURES],
    cta: 'Buy — $20',
    bonusText: undefined,
  },
  {
    id: 'pack_m',
    name: 'Pack M',
    price: '$50',
    period: 'one-time',
    features: [...PRO_FEATURES],
    cta: 'Buy — $50',
    bonusText: '+5% more credits',
  },
  {
    id: 'pack_l',
    name: 'Pack L',
    price: '$100',
    period: 'one-time',
    features: [...PRO_FEATURES],
    cta: 'Buy — $100',
    bonusText: '+10% more credits',
  },
] as const

function BalanceBar({ balanceCents, allocatedCents }: { balanceCents: number; allocatedCents: number }) {
  const pct  = allocatedCents > 0 ? Math.min(100, Math.round((balanceCents / allocatedCents) * 100)) : 0
  const low  = pct < 10
  const warn = !low && pct < 25
  const color = low ? 'var(--c-danger, #ef4444)' : warn ? 'var(--c-warning, #f59e0b)' : 'var(--c-accent)'

  return (
    <div>
      <div className="flex justify-between items-baseline mb-2">
        <span className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--c-text-3)' }}>
          Credit balance
        </span>
        <span className="text-2xl font-bold tabular-nums" style={{ color }}>
          {pct}%
        </span>
      </div>
      <div className="w-full h-1.5 rounded-full overflow-hidden mb-1" style={{ background: 'var(--c-surface-3)' }}>
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      {(low || warn) && (
        <p className="text-[10px] mt-1" style={{ color }}>
          {low ? 'Credits critically low — top up to keep running agents.' : 'Credits running low — consider topping up.'}
        </p>
      )}
    </div>
  )
}

export default function BillingPage() {
  const authFetch                     = useAuthFetch()
  const navigate                      = useNavigate()
  const [usage, setUsage]             = useState<Usage | null>(null)
  const [loading, setLoading]         = useState(true)
  const [checkingOut, setCheckingOut] = useState<string | null>(null)
  const [adminOpen, setAdminOpen]     = useState(false)
  const [adminKey, setAdminKey]       = useState('')
  const [adminMsg, setAdminMsg]       = useState('')
  const [adminBusy, setAdminBusy]     = useState(false)

  const fetchUsage = () =>
    authFetch('/api/billing/usage')
      .then(r => r.json())
      .then(setUsage)
      .catch(() => {})
      .finally(() => setLoading(false))

  // Poll usage every 30s while this page is mounted. We used to gate the poll
  // on a Socket.IO `state.running` flag, but that required opening a duplicate
  // socket on the billing page solely to read one boolean — wasteful. A flat
  // 30s poll covers the same UX (credits update during/after a run).
  useEffect(() => {
    fetchUsage()
    const id = setInterval(fetchUsage, 30_000)
    return () => clearInterval(id)
    // fetchUsage is recreated each render but its identity does not matter here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authFetch])

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
        setAdminKey('')
        await fetchUsage()
        navigate('/')
      } else {
        setAdminMsg('Invalid key.')
      }
    } catch {
      setAdminMsg('Error — is the backend running?')
    } finally {
      setAdminBusy(false)
    }
  }

  const checkout = async (planId: string) => {
    setCheckingOut(planId)
    try {
      const r    = await authFetch('/api/billing/checkout', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ plan: planId }),
      })
      const data = await r.json()
      if (data.checkout_url) window.open(data.checkout_url, '_blank')
      else alert(data.detail ?? 'Failed to start checkout')
    } catch {
      alert('Failed to start checkout — is the backend running?')
    } finally {
      setCheckingOut(null)
    }
  }

  const currentPlan    = usage?.plan ?? 'none'
  const balanceCents   = usage?.balance_cents ?? 0
  const planDef        = PLANS.find(p => p.id === currentPlan)
  const allocatedCents = planDef?.allocatedCents ?? 0

  return (
    <div className="w-full h-full flex flex-col overflow-hidden font-mono" style={{ background: 'var(--c-bg)', color: 'var(--c-text-1)' }}>

      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-2 shrink-0 border-b" style={{ background: 'var(--c-surface-1)', borderColor: 'var(--c-border)' }}>
        <button
          onClick={() => navigate('/')}
          className="text-xs px-2 py-1 rounded transition-colors"
          style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-3)' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-text-1)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-3)')}
        >
          ← Back
        </button>
        <span className="text-[var(--c-accent)] font-bold tracking-widest text-xs">TASKMESH</span>
        <span className="text-[var(--c-text-4)] text-xs">›</span>
        <span className="text-xs" style={{ color: 'var(--c-text-1)' }}>Billing</span>
      </div>

      <div className="flex-1 overflow-y-auto flex justify-center items-start">
        <div className="px-6 py-8 w-full" style={{ maxWidth: 780 }}>

          {loading && <p className="text-xs mb-6" style={{ color: 'var(--c-text-4)' }}>Loading…</p>}

          {/* No-plan banner */}
          {!loading && currentPlan === 'none' && (
      <div className="mb-6 px-4 py-3 rounded border text-xs" style={{ background: 'var(--c-surface-2)', borderColor: 'var(--c-warning, #f59e0b30)', color: 'var(--c-warning, #f59e0b)' }}>
        No active plan — choose a plan below to start running agents.
            </div>
          )}

          {/* Balance card */}
          {!loading && currentPlan !== 'none' && (
            <div className="mb-8 rounded border overflow-hidden" style={{ borderColor: 'var(--c-border)' }}>
              <div className="flex items-center justify-between px-4 py-2.5 border-b" style={{ background: 'var(--c-surface-2)', borderColor: 'var(--c-border)' }}>
                <span className="text-[10px] uppercase tracking-widest font-bold" style={{ color: 'var(--c-accent)' }}>
                  {currentPlan === 'pro' ? 'Pro' : 'Starter'} Plan
                </span>
                <span className="text-[10px]" style={{ color: 'var(--c-text-4)' }}>
                  {usage?.run_count ?? 0} run{(usage?.run_count ?? 0) !== 1 ? 's' : ''} this month
                </span>
              </div>
              <div className="px-4 py-4" style={{ background: 'var(--c-surface-1)' }}>
                <BalanceBar balanceCents={balanceCents} allocatedCents={allocatedCents} />
              </div>
            </div>
          )}

          {/* Plan cards */}
          <h2 className="text-[10px] uppercase tracking-widest mb-3" style={{ color: 'var(--c-text-3)' }}>Plans</h2>
          <div className="grid gap-3 mb-8" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
            {PLANS.map(plan => {
              const isCurrent = currentPlan === plan.id
              return (
                <div
                  key={plan.id}
                  className="rounded border flex flex-col overflow-hidden"
                  style={{ borderColor: isCurrent ? 'var(--c-accent-border)' : 'var(--c-border)' }}
                >
                  {/* Card header */}
                  <div
                    className="flex items-baseline gap-2 px-4 py-3 border-b"
                    style={{ background: isCurrent ? 'var(--c-accent-dim)' : 'var(--c-surface-2)', borderColor: isCurrent ? 'var(--c-accent-border)' : 'var(--c-border)' }}
                  >
                    <span className="text-sm font-bold" style={{ color: 'var(--c-text-1)' }}>{plan.name}</span>
                    <span className="text-xl font-bold" style={{ color: 'var(--c-accent)' }}>{plan.price}</span>
                    <span className="text-xs" style={{ color: 'var(--c-text-4)' }}>{plan.period}</span>
                    {plan.bonusText && (
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: 'var(--c-accent-dim)', color: 'var(--c-accent)', border: '1px solid var(--c-accent-border)' }}>
                        {plan.bonusText}
                      </span>
                    )}
                    {isCurrent && (
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded ml-auto" style={{ background: 'var(--c-accent)', color: '#000' }}>
                        CURRENT
                      </span>
                    )}
                  </div>
                  {/* Features */}
                  <ul className="flex-1 px-4 py-3 space-y-1.5" style={{ background: 'var(--c-surface-1)' }}>
                    {plan.features.map(f => (
                      <li key={f} className="text-xs flex items-start gap-2" style={{ color: 'var(--c-text-2)' }}>
                        <span style={{ color: 'var(--c-accent)', flexShrink: 0, marginTop: 1 }}>✓</span>
                        {f}
                      </li>
                    ))}
                  </ul>
                  {/* CTA */}
                  <div className="px-4 py-3" style={{ background: 'var(--c-surface-1)', borderTop: '1px solid var(--c-border)' }}>
                    {isCurrent ? (
                      <button
                        onClick={() => {
                          authFetch('/api/billing/portal')
                            .then(r => r.json())
                            .then((d: { portal_url?: string; detail?: string }) => {
                              if (d.portal_url) window.open(d.portal_url, '_blank')
                              else alert(d.detail ?? 'Subscription portal not available — ensure Paddle is configured')
                            })
                            .catch(() => alert('Could not open subscription portal'))
                        }}
                        className="w-full text-xs py-2 rounded transition-colors"
                        style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-2)', background: 'var(--c-surface-2)' }}
                      >
                        ⚙ Manage Subscription
                      </button>
                    ) : (
                      <button
                        onClick={() => checkout(plan.id)}
                        disabled={!!checkingOut}
                        className="w-full text-xs py-2 rounded font-bold transition-opacity disabled:opacity-50"
                        style={{ background: 'var(--c-accent)', color: '#000' }}
                      >
                        {checkingOut === plan.id ? 'Opening checkout…' : plan.cta}
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Credit packs */}
          <h2 className="text-[10px] uppercase tracking-widest mb-3" style={{ color: 'var(--c-text-3)' }}>Top up credits</h2>
          <div className="grid gap-3 mb-8" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
            {PACK_CARDS.map(pack => (
              <div
                key={pack.id}
                className="rounded border flex flex-col overflow-hidden"
                style={{ borderColor: 'var(--c-border)' }}
              >
                {/* Card header */}
                <div
                  className="flex items-baseline gap-2 px-4 py-3 border-b"
                  style={{ background: 'var(--c-surface-2)', borderColor: 'var(--c-border)' }}
                >
                  <span className="text-sm font-bold" style={{ color: 'var(--c-text-1)' }}>{pack.name}</span>
                  <span className="text-xl font-bold" style={{ color: 'var(--c-accent)' }}>{pack.price}</span>
                  <span className="text-xs" style={{ color: 'var(--c-text-4)' }}>{pack.period}</span>
                  {pack.bonusText && (
                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: 'var(--c-accent-dim)', color: 'var(--c-accent)', border: '1px solid var(--c-accent-border)' }}>
                      {pack.bonusText}
                    </span>
                  )}
                </div>
                {/* Features */}
                <ul className="flex-1 px-4 py-3 space-y-1.5" style={{ background: 'var(--c-surface-1)' }}>
                  {pack.features.map(f => (
                    <li key={f} className="text-xs flex items-start gap-2" style={{ color: 'var(--c-text-2)' }}>
                      <span style={{ color: 'var(--c-accent)', flexShrink: 0, marginTop: 1 }}>✓</span>
                      {f}
                    </li>
                  ))}
                </ul>
                {/* CTA */}
                <div className="px-4 py-3" style={{ background: 'var(--c-surface-1)', borderTop: '1px solid var(--c-border)' }}>
                  <button
                    onClick={() => checkout(pack.id)}
                    disabled={!!checkingOut || currentPlan === 'none'}
                    className="w-full text-xs py-2 rounded font-bold transition-opacity disabled:opacity-40"
                    style={{ background: 'var(--c-accent)', color: '#000' }}
                    title={currentPlan === 'none' ? 'Requires an active subscription' : undefined}
                  >
                    {checkingOut === pack.id ? 'Opening checkout…' : pack.cta}
                  </button>
                </div>
              </div>
            ))}
          </div>
          {currentPlan === 'none' && !loading && (
            <p className="mt-2 text-[10px]" style={{ color: 'var(--c-text-4)' }}>An active subscription is required to top up credits.</p>
          )}

          {/* Admin bypass — invisible trigger */}
          <div className="mt-16 flex justify-end">
            <button
              onClick={() => { setAdminOpen(o => !o); setAdminMsg('') }}
              className="text-[9px] opacity-20 hover:opacity-40 transition-opacity"
              style={{ color: 'var(--c-text-4)' }}
            >·</button>
          </div>
          {adminOpen && (
            <div className="mt-2 p-3 rounded border" style={{ borderColor: 'var(--c-border)', background: 'var(--c-surface-2)' }}>
              <div className="flex gap-2">
                <input
                  type="password"
                  value={adminKey}
                  onChange={e => setAdminKey(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && submitAdminBypass()}
                  placeholder="Access key"
                  autoFocus
                  className="flex-1 text-xs font-mono rounded px-2 py-1 focus:outline-none"
                  style={{ background: 'var(--c-input-bg)', border: '1px solid var(--c-border)', color: 'var(--c-text-1)' }}
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
                <p className="mt-1.5 text-[10px]" style={{ color: '#ef4444' }}>{adminMsg}</p>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
