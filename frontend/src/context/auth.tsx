import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react'

const TOKEN_KEY = 'agentteam_token'

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
  login: (token: string) => void
  logout: () => void
}

function parseToken(token: string): AuthUser | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    if (payload.exp && payload.exp * 1000 < Date.now()) return null
    return { id: payload.sub, email: payload.email ?? '', name: payload.name ?? '' }
  } catch {
    return null
  }
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  token: null,
  getToken: async () => null,
  login: () => {},
  logout: () => {},
})

export const useAuthContext = () => useContext(AuthContext)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => {
    if (AUTH_DISABLED) return 'dev-token'
    return localStorage.getItem(TOKEN_KEY)
  })

  const [user, setUser] = useState<AuthUser | null>(() => {
    if (AUTH_DISABLED) return { id: 'dev-user', email: 'dev@local', name: 'Dev User' }
    const stored = localStorage.getItem(TOKEN_KEY)
    return stored ? parseToken(stored) : null
  })

  // Clear expired tokens on mount
  useEffect(() => {
    if (AUTH_DISABLED) return
    const stored = localStorage.getItem(TOKEN_KEY)
    if (stored && !parseToken(stored)) {
      localStorage.removeItem(TOKEN_KEY)
      setToken(null)
      setUser(null)
    }
  }, [])

  const login = useCallback((newToken: string) => {
    const parsed = parseToken(newToken)
    if (!parsed) return
    localStorage.setItem(TOKEN_KEY, newToken)
    setToken(newToken)
    setUser(parsed)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
  }, [])

  const getToken = useCallback(async (): Promise<string | null> => {
    if (AUTH_DISABLED) return 'dev-token'
    return token
  }, [token])

  return (
    <AuthContext.Provider value={{ user, token, getToken, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
