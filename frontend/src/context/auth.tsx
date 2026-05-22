import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react'

// VITE_AUTH_DISABLED=true skips login redirect and sends a dummy token.
// Backend must also have AUTH_DISABLED=true for this to work end-to-end.
const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === 'true'

interface AuthUser {
  id: string
  email: string
  name: string
}

interface AuthContextValue {
  user: AuthUser | null
  token: string | null
  getToken: () => Promise<string | null>
  login: () => void
  logout: () => void
}

// Auth token lives in an HttpOnly cookie (XSS-safe). The frontend never
// reads the raw JWT — it fetches /api/auth/me to get the current user.
// getToken() returns null because the token is only in the cookie.

const AuthContext = createContext<AuthContextValue>({
  user: null,
  token: null,
  getToken: async () => null,
  login: () => {},
  logout: () => {},
})

export const useAuthContext = () => useContext(AuthContext)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    if (AUTH_DISABLED) return { id: 'dev-user', email: 'dev@local', name: 'Dev User' }
    return null
  })

  const [token, setToken] = useState<string | null>(() => {
    if (AUTH_DISABLED) return 'dev-token'
    return null
  })

  // Fetch authenticated user from server on mount
  useEffect(() => {
    if (AUTH_DISABLED) return
    fetch('/api/auth/me')
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(u => setUser({ id: u.id, email: u.email ?? '', name: u.name ?? '' }))
      .catch(() => setUser(null))
  }, [])

  const login = useCallback(() => {
    // Token is in HttpOnly cookie. After login/register/OAuth, the cookie
    // is set server-side. We refresh the user state from /api/auth/me.
    if (AUTH_DISABLED) return
    fetch('/api/auth/me')
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(u => setUser({ id: u.id, email: u.email ?? '', name: u.name ?? '' }))
      .catch(() => {})
  }, [])

  const logout = useCallback(async () => {
    if (AUTH_DISABLED) return
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {})
    setUser(null)
    setToken(null)
  }, [])

  const getToken = useCallback(async (): Promise<string | null> => {
    if (AUTH_DISABLED) return 'dev-token'
    return null  // token lives in HttpOnly cookie, not JS-accessible
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, getToken, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
