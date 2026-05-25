import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useAuthContext } from '../context/auth'

export default function LoginPage() {
  const { login } = useAuthContext()
  const navigate  = useNavigate()
  const [searchParams] = useSearchParams()

  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [githubLoading, setGithubLoading] = useState(false)

  useEffect(() => {
    const err = searchParams.get('error')
    if (err) setError(decodeURIComponent(err))
  }, [searchParams])

  const handleOAuth = async (
    provider: 'google' | 'github',
    setLoading: (v: boolean) => void,
  ) => {
    setError('')
    setLoading(true)
    try {
      const r    = await fetch(`/api/auth/${provider}/url`)
      const data = await r.json()
      if (data.auth_url) {
        window.location.href = data.auth_url
      } else {
        setError(data.detail ?? `${provider} OAuth not configured`)
        setLoading(false)
      }
    } catch {
      setError('Could not reach backend')
      setLoading(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const r = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, remember_me: rememberMe }),
      })
      const data = await r.json()
      if (!r.ok) {
        setError(data.detail ?? 'Login failed')
        return
      }
      const success = await login()
      if (!success) { setError('Login failed — could not verify session'); return }

      // Route based on plan. For users without an active subscription we
      // PUSH /billing onto history (not replace) so the browser back button
      // lands on /login, never on the dashboard. The plan check defaults to
      // 'none' on network failure so we err on the side of routing through
      // billing — fail-closed for the gating decision.
      let plan = 'none'
      try {
        const usageResp = await fetch('/api/billing/usage', { credentials: 'include' })
        if (usageResp.ok) {
          const usage = await usageResp.json()
          plan = usage.plan ?? 'none'
        }
      } catch {
        // network error — keep plan='none', user gets routed to /billing
      }
      if (plan === 'none') {
        navigate('/billing')                 // push: back → /login
      } else {
        navigate('/', { replace: true })     // replace: /login → /
      }
    } catch {
      setError('Network error — is the backend running?')
    } finally {
      setLoading(false)
    }
  }


  return (
    <div
      className="min-h-screen flex items-center justify-center font-mono"
      style={{ background: 'var(--c-bg)', color: 'var(--c-text-1)' }}
    >
      <div
        className="w-full max-w-sm p-8 rounded border"
        style={{ background: 'var(--c-surface-1)', borderColor: 'var(--c-border)' }}
      >
        <h1
          className="text-xs font-bold tracking-widest uppercase mb-6"
          style={{ color: 'var(--c-accent)' }}
        >
          TaskMesh — Sign In
        </h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--c-text-3)' }}>
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoFocus
              className="w-full text-xs px-3 py-2 rounded"
              style={{
                background: 'var(--c-input-bg)',
                border: '1px solid var(--c-border)',
                color: 'var(--c-text-1)',
                outline: 'none',
              }}
            />
          </div>

          <div>
            <label className="block text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--c-text-3)' }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              className="w-full text-xs px-3 py-2 rounded"
              style={{
                background: 'var(--c-input-bg)',
                border: '1px solid var(--c-border)',
                color: 'var(--c-text-1)',
                outline: 'none',
              }}
            />
          </div>

          <div className="flex items-center gap-2 mt-1">
            <input
              type="checkbox"
              id="remember-me"
              checked={rememberMe}
              onChange={e => setRememberMe(e.target.checked)}
              className="w-3 h-3 rounded"
              style={{ accentColor: 'var(--c-accent)' }}
            />
            <label htmlFor="remember-me" className="text-[10px] cursor-pointer select-none" style={{ color: 'var(--c-text-3)' }}>
              Remember me for 7 days
            </label>
          </div>

          {error && (
            <p className="text-[10px]" style={{ color: '#ef4444' }}>{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full text-xs py-2 rounded font-bold disabled:opacity-50"
            style={{ background: 'var(--c-accent)', color: '#000' }}
          >
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        <div className="my-4 flex items-center gap-3">
          <div className="flex-1 h-px" style={{ background: 'var(--c-border)' }} />
          <span className="text-[10px]" style={{ color: 'var(--c-text-4)' }}>or</span>
          <div className="flex-1 h-px" style={{ background: 'var(--c-border)' }} />
        </div>

        <button
          onClick={() => handleOAuth('google', setGoogleLoading)}
          disabled={googleLoading}
          className="w-full text-xs py-2 rounded font-bold disabled:opacity-50 flex items-center justify-center gap-2"
          style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-1)', background: 'var(--c-surface-2)' }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
          </svg>
          {googleLoading ? 'Redirecting…' : 'Continue with Google'}
        </button>

        <button
          onClick={() => handleOAuth('github', setGithubLoading)}
          disabled={githubLoading}
          className="w-full text-xs py-2 rounded font-bold disabled:opacity-50 flex items-center justify-center gap-2 mt-2"
          style={{ border: '1px solid var(--c-border)', color: 'var(--c-text-1)', background: 'var(--c-surface-2)' }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
          </svg>
          {githubLoading ? 'Redirecting…' : 'Continue with GitHub'}
        </button>

        <p className="mt-6 text-center text-[10px]" style={{ color: 'var(--c-text-4)' }}>
          No account?{' '}
          <Link to="/register" style={{ color: 'var(--c-accent)' }}>
            Create one
          </Link>
        </p>
      </div>
    </div>
  )
}
