import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthContext } from '../context/auth'

/**
 * Landing page for Google OAuth redirect.
 * The backend redirects here as:   /auth/callback#<jwt>
 * We read the JWT from the URL hash, store it, then send the user home.
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
      login(token)
      window.history.replaceState(null, '', '/auth/callback')  // clear hash from URL
      navigate('/', { replace: true })
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
