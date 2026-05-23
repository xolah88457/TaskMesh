import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthFetch } from '../hooks/useAuthFetch'
import { useAuthContext } from '../context/auth'
import { THEMES, DEFAULT_THEME_ID, getTheme } from '../themes'

interface Profile {
  id: string
  name: string
  email: string
  has_password: boolean
  google_linked: boolean
  github_linked: boolean
  github_login: string | null
  created_at: string | null
}

interface ZenSummary {
  month_spent_cents: number
  lifetime_spent_cents: number
  balance_cents: number
  month_run_count: number
}

// ── Shared input style ─────────────────────────────────────────────────────────
const inputCls = 'w-full text-xs px-3 py-2 rounded focus:outline-none'
const inputStyle = {
  background: 'var(--c-input-bg)',
  border: '1px solid var(--c-border)',
  color: 'var(--c-text-1)',
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h2 className="text-[10px] uppercase tracking-widest mb-3 mt-6 first:mt-0" style={{ color: 'var(--c-text-3)' }}>
      {title}
    </h2>
  )
}

function StatusMsg({ msg, isError }: { msg: string; isError?: boolean }) {
  if (!msg) return null
  return (
    <p className="text-[10px] mt-2" style={{ color: isError ? '#ef4444' : 'var(--c-accent)' }}>
      {msg}
    </p>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function AccountPage() {
  const authFetch            = useAuthFetch()
  const { login, logout }    = useAuthContext()
  const navigate             = useNavigate()

  const [profile, setProfile]           = useState<Profile | null>(null)
  const [loading, setLoading]           = useState(true)

  // Profile form
  const [name, setName]                 = useState('')
  const [nameMsg, setNameMsg]           = useState('')
  const [nameErr, setNameErr]           = useState(false)
  const [nameSaving, setNameSaving]     = useState(false)

  // Email form
  const [newEmail, setNewEmail]         = useState('')
  const [emailPw, setEmailPw]           = useState('')
  const [emailMsg, setEmailMsg]         = useState('')
  const [emailErr, setEmailErr]         = useState(false)
  const [emailSaving, setEmailSaving]   = useState(false)

  // Password form
  const [curPw, setCurPw]               = useState('')
  const [newPw, setNewPw]               = useState('')
  const [pwMsg, setPwMsg]               = useState('')
  const [pwErr, setPwErr]               = useState(false)
  const [pwSaving, setPwSaving]         = useState(false)

  // Zen usage summary
  const [zenSummary, setZenSummary]         = useState<ZenSummary | null>(null)
  const [zenLoading, setZenLoading]         = useState(true)

  // Notifications
  const [notifications, setNotifications]   = useState<Record<string, boolean>>({
    subscription_started: false, credit_low: false,
  })

  // Delete
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [deleteMsg, setDeleteMsg]         = useState('')
  const [deleting, setDeleting]           = useState(false)

  // Theme
  const [themeId, setThemeId] = useState(() =>
    localStorage.getItem('agentteam-theme') ?? DEFAULT_THEME_ID
  )
  const applyTheme = (id: string) => {
    setThemeId(id)
    localStorage.setItem('agentteam-theme', id)
    const t = getTheme(id)
    if (!t) return
    const root = document.documentElement
    for (const [k, v] of Object.entries(t.vars)) {
      root.style.setProperty(k, v as string)
    }
  }

  useEffect(() => {
    authFetch('/api/account/profile')
      .then(r => r.json())
      .then((p: Profile) => {
        setProfile(p)
        setName(p.name)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
    authFetch('/api/account/zen-summary')
      .then(r => r.json())
      .then((d: ZenSummary) => setZenSummary(d))
      .catch(() => {})
      .finally(() => setZenLoading(false))
    authFetch('/api/account/notifications')
      .then(r => r.json())
      .then((d: { notifications: { type: string; enabled: boolean }[] }) => {
        const map: Record<string, boolean> = {}
        d.notifications.forEach(n => { map[n.type] = n.enabled })
        setNotifications(prev => ({ ...prev, ...map }))
      })
      .catch(() => {})
  }, [authFetch])

  const toggleNotif = (type: string, enabled: boolean) => {
    setNotifications(prev => ({ ...prev, [type]: enabled }))
    authFetch('/api/account/notifications', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, enabled }),
    }).catch(() => {})
  }

  // ── Save name ──────────────────────────────────────────────────────────────
  const saveName = async (e: FormEvent) => {
    e.preventDefault()
    setNameMsg(''); setNameErr(false); setNameSaving(true)
    try {
      const r = await authFetch('/api/account/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      const d = await r.json()
      if (!r.ok) { setNameMsg(d.detail ?? 'Failed'); setNameErr(true); return }
      if (d.token) login()
      setProfile(p => p ? { ...p, name: d.name } : p)
      setNameMsg('Name updated.')
    } catch { setNameMsg('Network error'); setNameErr(true) }
    finally { setNameSaving(false) }
  }

  // ── Change email ───────────────────────────────────────────────────────────
  const saveEmail = async (e: FormEvent) => {
    e.preventDefault()
    setEmailMsg(''); setEmailErr(false); setEmailSaving(true)
    try {
      const r = await authFetch('/api/account/email', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: newEmail, password: emailPw }),
      })
      const d = await r.json()
      if (!r.ok) { setEmailMsg(d.detail ?? 'Failed'); setEmailErr(true); return }
      if (d.token) login()
      setProfile(p => p ? { ...p, email: d.email } : p)
      setNewEmail(''); setEmailPw('')
      setEmailMsg('Email updated.')
    } catch { setEmailMsg('Network error'); setEmailErr(true) }
    finally { setEmailSaving(false) }
  }

  // ── Change password ────────────────────────────────────────────────────────
  const savePassword = async (e: FormEvent) => {
    e.preventDefault()
    setPwMsg(''); setPwErr(false); setPwSaving(true)
    try {
      const r = await authFetch('/api/account/password', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: curPw, new_password: newPw }),
      })
      const d = await r.json()
      if (!r.ok) { setPwMsg(d.detail ?? 'Failed'); setPwErr(true); return }
      setCurPw(''); setNewPw('')
      setPwMsg('Password updated.')
      setProfile(p => p ? { ...p, has_password: true } : p)
    } catch { setPwMsg('Network error'); setPwErr(true) }
    finally { setPwSaving(false) }
  }

  // ── Delete account ─────────────────────────────────────────────────────────
  const deleteAccount = async () => {
    if (deleteConfirm !== 'DELETE') {
      setDeleteMsg('Type DELETE to confirm.'); return
    }
    setDeleting(true)
    try {
      const r = await authFetch('/api/account', { method: 'DELETE' })
      if (!r.ok) {
        const d = await r.json()
        setDeleteMsg(d.detail ?? 'Failed to delete account')
        return
      }
      logout()
      navigate('/login', { replace: true })
    } catch { setDeleteMsg('Network error') }
    finally { setDeleting(false) }
  }

  const cardStyle = {
    background: 'var(--c-surface-2)',
    borderColor: 'var(--c-border)',
  }

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
          onClick={() => navigate(-1)}
          className="text-xs px-2 py-1 rounded transition-colors"
          style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-3)' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-text-1)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-3)')}
        >
          ← Back
        </button>
        <span className="text-[var(--c-accent)] font-bold tracking-widest text-xs uppercase">TASKMESH</span>
        <span className="text-[var(--c-text-4)] text-xs">›</span>
        <span className="text-[var(--c-text-1)] text-xs">Settings</span>
      </div>

      {loading && (
        <p className="px-6 py-8 text-xs" style={{ color: 'var(--c-text-4)' }}>Loading…</p>
      )}

      {!loading && profile && (
        <div className="flex-1 overflow-y-auto flex justify-center items-start">
        <div className="px-6 py-8 w-full" style={{ maxWidth: 780 }}>

          {/* ── Profile ── */}
          <SectionHeader title="Profile" />
          <div className="rounded border px-5 py-4 mb-1" style={cardStyle}>
            <p className="text-[10px] mb-3" style={{ color: 'var(--c-text-4)' }}>
              {profile.email}
              {profile.created_at && (
                <span className="ml-2">
                  · Member since {new Date(profile.created_at).toLocaleDateString()}
                </span>
              )}
            </p>
            <form onSubmit={saveName} className="flex gap-2 items-end">
              <div className="flex-1">
                <label className="block text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--c-text-3)' }}>
                  Display name
                </label>
                <input
                  className={inputCls}
                  style={inputStyle}
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="Your name"
                  required
                />
              </div>
              <button
                type="submit"
                disabled={nameSaving}
                className="text-xs px-3 py-2 rounded font-bold disabled:opacity-50 shrink-0"
                style={{ background: 'var(--c-accent)', color: '#000' }}
              >
                {nameSaving ? '…' : 'Save'}
              </button>
            </form>
            <StatusMsg msg={nameMsg} isError={nameErr} />
          </div>

          {/* ── Theme ── */}
          <SectionHeader title="Theme" />
          <div className="rounded border px-5 py-4 mb-1" style={cardStyle}>
            <div className="grid grid-cols-5 gap-2">
              {THEMES.map(t => (
                <button
                  key={t.id}
                  onClick={() => applyTheme(t.id)}
                  className="flex flex-col items-center gap-1.5 group"
                >
                  <div
                    className="w-full rounded overflow-hidden relative"
                    style={{
                      height: '44px',
                      background: t.previewBg,
                      border: themeId === t.id
                        ? `2px solid var(--c-accent)`
                        : `1px solid ${t.previewText}`,
                      boxShadow: themeId === t.id ? '0 0 0 1px var(--c-accent)' : 'none',
                    }}
                  >
                    <div className="absolute top-[8px] left-[6px] right-[14px] h-[2px] rounded" style={{ background: t.previewText, opacity: 0.5 }} />
                    <div className="absolute top-[13px] left-[6px] right-[18px] h-[2px] rounded" style={{ background: t.previewText, opacity: 0.3 }} />
                    <div className="absolute top-[18px] left-[6px] right-[10px] h-[2px] rounded" style={{ background: t.previewAccent, opacity: 0.8 }} />
                    <div className="absolute top-[23px] left-[6px] right-[16px] h-[2px] rounded" style={{ background: t.previewAccent, opacity: 0.5 }} />
                    <div className="absolute top-[28px] left-[6px] right-[12px] h-[2px] rounded" style={{ background: t.previewText, opacity: 0.25 }} />
                    {themeId === t.id && (
                      <div className="absolute bottom-0 left-0 right-0 h-[3px]" style={{ background: t.previewAccent }} />
                    )}
                  </div>
                  <span
                    className="text-[9px] font-mono leading-none"
                    style={{ color: themeId === t.id ? 'var(--c-accent)' : 'var(--c-text-3)' }}
                  >
                    {t.name}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* ── Change email ── */}
          <SectionHeader title="Email address" />
          <div className="rounded border px-5 py-4 mb-1" style={cardStyle}>
            <p className="text-xs mb-3" style={{ color: 'var(--c-text-2)' }}>
              Current: <span style={{ color: 'var(--c-text-1)' }}>{profile.email}</span>
            </p>
            {!profile.has_password && (
              <p className="text-[10px] mb-3" style={{ color: 'var(--c-text-4)' }}>
                Set a password first to change your email via this form.
              </p>
            )}
            {profile.has_password && (
              <form onSubmit={saveEmail} className="space-y-3">
                <div>
                  <label className="block text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--c-text-3)' }}>New email</label>
                  <input type="email" required className={inputCls} style={inputStyle}
                    value={newEmail} onChange={e => setNewEmail(e.target.value)} placeholder="new@example.com" />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--c-text-3)' }}>Confirm with password</label>
                  <input type="password" required className={inputCls} style={inputStyle}
                    value={emailPw} onChange={e => setEmailPw(e.target.value)} placeholder="Current password" />
                </div>
                <button type="submit" disabled={emailSaving}
                  className="text-xs px-3 py-2 rounded font-bold disabled:opacity-50"
                  style={{ background: 'var(--c-accent)', color: '#000' }}>
                  {emailSaving ? 'Saving…' : 'Update email'}
                </button>
              </form>
            )}
            <StatusMsg msg={emailMsg} isError={emailErr} />
          </div>

          {/* ── Password ── */}
          <SectionHeader title="Security" />
          <div className="rounded border px-5 py-4 mb-1" style={cardStyle}>
            <p className="text-xs mb-3" style={{ color: 'var(--c-text-2)' }}>
              {profile.has_password ? 'Change your password.' : 'Set a password to enable email/password login.'}
            </p>
            <form onSubmit={savePassword} className="space-y-3">
              {profile.has_password && (
                <div>
                  <label className="block text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--c-text-3)' }}>Current password</label>
                  <input type="password" required className={inputCls} style={inputStyle}
                    value={curPw} onChange={e => setCurPw(e.target.value)} placeholder="••••••••" />
                </div>
              )}
              <div>
                <label className="block text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--c-text-3)' }}>
                  {profile.has_password ? 'New password' : 'Password'}
                </label>
                <input type="password" required minLength={8} className={inputCls} style={inputStyle}
                  value={newPw} onChange={e => setNewPw(e.target.value)} placeholder="Min. 8 characters" />
              </div>
              <button type="submit" disabled={pwSaving}
                className="text-xs px-3 py-2 rounded font-bold disabled:opacity-50"
                style={{ background: 'var(--c-accent)', color: '#000' }}>
                {pwSaving ? 'Saving…' : (profile.has_password ? 'Change password' : 'Set password')}
              </button>
            </form>
            <StatusMsg msg={pwMsg} isError={pwErr} />
          </div>

          {/* ── Usage & Billing ── */}
          <SectionHeader title="Usage & Billing" />
          <div className="rounded border px-5 py-4 mb-1" style={cardStyle}>
            {zenLoading ? (
              <p className="text-xs" style={{ color: 'var(--c-text-4)' }}>Loading usage data…</p>
            ) : zenSummary ? (
              <div className="space-y-2">
                <div className="flex justify-between text-xs">
                  <span style={{ color: 'var(--c-text-3)' }}>Spent this month</span>
                  <span style={{ color: 'var(--c-text-1)' }}>${(zenSummary.month_spent_cents / 100).toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span style={{ color: 'var(--c-text-3)' }}>Runs this month</span>
                  <span style={{ color: 'var(--c-text-1)' }}>{zenSummary.month_run_count}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span style={{ color: 'var(--c-text-3)' }}>Lifetime spent</span>
                  <span style={{ color: 'var(--c-text-1)' }}>${(zenSummary.lifetime_spent_cents / 100).toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-xs pt-2" style={{ borderTop: '1px solid var(--c-border)' }}>
                  <span style={{ color: 'var(--c-text-3)' }}>Remaining balance</span>
                  <span className="font-bold" style={{ color: 'var(--c-accent)' }}>${(zenSummary.balance_cents / 100).toFixed(2)}</span>
                </div>
              </div>
            ) : null}
            {/* Manage subscription button */}
            <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--c-border)' }}>
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
            </div>
          </div>

          {/* ── Connected accounts ── */}
          <SectionHeader title="Connected accounts" />
          <div className="rounded border px-5 py-4 mb-1 space-y-3" style={cardStyle}>
            {/* Google */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="shrink-0">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                </svg>
                <span style={{ color: 'var(--c-text-1)' }}>Google</span>
              </div>
              <span
                className="text-[10px] px-2 py-0.5 rounded"
                style={profile.google_linked
                  ? { background: 'var(--c-accent-dim)', color: 'var(--c-accent)' }
                  : { color: 'var(--c-text-4)' }
                }
              >
                {profile.google_linked ? 'Connected' : 'Not connected'}
              </span>
            </div>

            {/* GitHub */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" className="shrink-0" style={{ color: 'var(--c-text-2)' }}>
                  <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
                </svg>
                <span style={{ color: 'var(--c-text-1)' }}>GitHub</span>
                {profile.github_login && (
                  <span style={{ color: 'var(--c-text-4)' }}>@{profile.github_login}</span>
                )}
              </div>
              <span
                className="text-[10px] px-2 py-0.5 rounded"
                style={profile.github_linked
                  ? { background: 'var(--c-accent-dim)', color: 'var(--c-accent)' }
                  : { color: 'var(--c-text-4)' }
                }
              >
                {profile.github_linked ? 'Connected' : 'Not connected'}
              </span>
            </div>
          </div>

          {/* ── Notifications ── */}
          <SectionHeader title="Notifications" />
          <div className="rounded border px-5 py-4 mb-1" style={cardStyle}>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs" style={{ color: 'var(--c-text-1)' }}>Subscription started</span>
                  <p className="text-[10px] mt-0.5" style={{ color: 'var(--c-text-4)' }}>Alert when a new subscription activates</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" className="sr-only peer"
                    checked={notifications.subscription_started}
                    onChange={e => toggleNotif('subscription_started', e.target.checked)} />
                  <div className="w-9 h-5 rounded-full border transition-colors
                    peer-checked:bg-[var(--c-accent)] peer-checked:border-[var(--c-accent)]
                    bg-[var(--c-surface-3)] border-[var(--c-border)]
                    after:content-[''] after:absolute after:top-[2px] after:left-[2px]
                    after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-transform
                    after:shadow-sm peer-checked:after:translate-x-4" />
                </label>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs" style={{ color: 'var(--c-text-1)' }}>Credit low</span>
                  <p className="text-[10px] mt-0.5" style={{ color: 'var(--c-text-4)' }}>Alert when balance drops below $2.50</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" className="sr-only peer"
                    checked={notifications.credit_low}
                    onChange={e => toggleNotif('credit_low', e.target.checked)} />
                  <div className="w-9 h-5 rounded-full border transition-colors
                    peer-checked:bg-[var(--c-accent)] peer-checked:border-[var(--c-accent)]
                    bg-[var(--c-surface-3)] border-[var(--c-border)]
                    after:content-[''] after:absolute after:top-[2px] after:left-[2px]
                    after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-transform
                    after:shadow-sm peer-checked:after:translate-x-4" />
                </label>
              </div>
            </div>
          </div>

          {/* ── Sign out ── */}
          <SectionHeader title="Session" />
          <div className="rounded border px-5 py-4 mb-1" style={cardStyle}>
            <button
              onClick={() => { logout(); navigate('/login', { replace: true }) }}
              className="text-xs px-3 py-2 rounded font-bold transition-colors"
              style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-2)' }}
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-text-1)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-2)')}
            >
              Sign out
            </button>
          </div>

          {/* ── Danger zone ── */}
          <SectionHeader title="Danger zone" />
          <div
            className="rounded border px-5 py-4"
            style={{ ...cardStyle, borderColor: 'rgba(239,68,68,0.3)' }}
          >
            <p className="text-xs mb-3" style={{ color: 'var(--c-text-2)' }}>
              Permanently delete your account and all data. This cannot be undone.
            </p>
            <div className="flex gap-2 items-center">
              <input
                className={inputCls + ' max-w-[160px]'}
                style={{ ...inputStyle, borderColor: 'rgba(239,68,68,0.4)' }}
                value={deleteConfirm}
                onChange={e => setDeleteConfirm(e.target.value)}
                placeholder='Type DELETE'
              />
              <button
                onClick={deleteAccount}
                disabled={deleting || deleteConfirm !== 'DELETE'}
                className="text-xs px-3 py-2 rounded font-bold disabled:opacity-40"
                style={{ border: '1px solid rgba(239,68,68,0.5)', color: '#ef4444' }}
                onMouseEnter={e => { if (deleteConfirm === 'DELETE') (e.currentTarget as HTMLButtonElement).style.background = 'rgba(239,68,68,0.1)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
              >
                {deleting ? 'Deleting…' : 'Delete account'}
              </button>
            </div>
            <StatusMsg msg={deleteMsg} isError />
          </div>

        </div>
        </div>
      )}
    </div>
  )
}
