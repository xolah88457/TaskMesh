import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthContext } from '../context/auth'

/**
 * Landing page for Google/GitHub OAuth redirect.
 *
 * The backend redirects here as: /auth/callback#<jwt>
 * We POST the JWT to /api/auth/exchange, which sets the HttpOnly
 * cookie on a regular JSON response (not a redirect, avoiding
 * Set-Cookie issues with Vercel proxy). Then we call login() to
 * refresh user state from /api/auth/me.
 */
export default function AuthCallback() {
  const { login }  = useAuthContext()
  const navigate   = useNavigate()
  const processed  = useRef(false)

  useEffect(() => {
    if (processed.current) return
    processed.current = true

    const token = window.location.hash.slice(1)  // strip leading '#'
    if (!token) {
      navigate('/login?error=oauth_failed', { replace: true })
      return
    }

    const run = async () => {
      try {
        const exchangeResp = await fetch('/api/auth/exchange', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token, remember_me: true }),
        })
        if (!exchangeResp.ok) throw exchangeResp.status
        // Strip the JWT from the URL so it never lands in server logs / referer.
        window.history.replaceState(null, '', '/auth/callback')
        const success = await login()
        if (!success) {
          navigate('/login?error=oauth_failed', { replace: true })
          return
        }

        // Plan-based routing. plan='none' must put /login as the history
        // back-target, not /auth/callback. We rewrite the current entry to
        // /login (browser-level) and then PUSH /billing — so back returns
        // to /login. Fail-closed: any error sends the user through /billing.
        let plan = 'none'
        try {
          const usageResp = await fetch('/api/billing/usage', { credentials: 'include' })
          if (usageResp.ok) {
            const usage = await usageResp.json()
            plan = usage.plan ?? 'none'
          }
        } catch {
          // keep plan='none'
        }
        if (plan === 'none') {
          window.history.replaceState({}, '', '/login')
          navigate('/billing')
        } else {
          navigate('/', { replace: true })
        }
      } catch {
        navigate('/login?error=oauth_failed', { replace: true })
      }
    }
    run()
  }, [login, navigate])

  return (
    <div
      className="min-h-screen flex items-center justify-center font-mono"
      style={{ background: 'var(--c-bg)', color: 'var(--c-text-4)' }}
    >
      <p className="text-xs">Completing sign-in…</p>
    </div>
  )
}
