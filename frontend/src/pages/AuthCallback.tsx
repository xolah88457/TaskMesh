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
    if (token) {
      // Exchange JWT for HttpOnly cookie
      fetch('/api/auth/exchange', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, remember_me: true }),
      })
        .then(r => {
          if (!r.ok) throw r.status
          window.history.replaceState(null, '', '/auth/callback')
          return login()
        })
        .then(success => {
          if (success) {
            navigate('/', { replace: false })
          } else {
            navigate('/login?error=oauth_failed', { replace: true })
          }
        })
        .catch(() => {
          navigate('/login?error=oauth_failed', { replace: true })
        })
    } else {
      // No token — something went wrong with the OAuth flow
      navigate('/login?error=oauth_failed', { replace: true })
    }
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
