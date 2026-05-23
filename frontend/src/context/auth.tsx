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
  loading: boolean
  getToken: () => Promise<string | null>
  login: () => Promise<boolean>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  token: null,
  loading: false,
  getToken: async () => null,
  login: async () => false,
  logout: () => {},
})

export const useAuthContext = () => useContext(AuthContext)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    if (AUTH_DISABLED) return { id: 'dev-user', email: 'dev@local', name: 'Dev User' }
    return null
  })

  const [loading, setLoading] = useState(!AUTH_DISABLED)

  const [token, setToken] = useState<string | null>(() => {
    if (AUTH_DISABLED) return 'dev-token'
    return null
  })

  useEffect(() => {
    if (AUTH_DISABLED) return
    fetch('/api/auth/me')
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(u => setUser({ id: u.id, email: u.email ?? '', name: u.name ?? '' }))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (): Promise<boolean> => {
    // Token is in HttpOnly cookie. After login/register/OAuth, the cookie
    // is set server-side. We refresh the user state from /api/auth/me.
    if (AUTH_DISABLED) return true
    try {
      const r = await fetch('/api/auth/me')
      if (!r.ok) throw r.status
      const u = await r.json()
      setUser({ id: u.id, email: u.email ?? '', name: u.name ?? '' })
      return true
    } catch {
      return false
    }
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
    <AuthContext.Provider value={{ user, token, loading, getToken, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
