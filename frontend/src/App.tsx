import { useState, useCallback, useEffect } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import MatrixRain from './components/MatrixRain'
import HealthBanner from './components/HealthBanner'
import Header from './components/Header'
import AgentNetwork from './components/AgentNetwork'
import Sidebar from './components/Sidebar'
import LiveActivity from './components/LiveActivity'
import SettingsPanel from './components/SettingsPanel'
import Dashboard, { StatusBar } from './pages/Dashboard'
import type { Usage } from './pages/Dashboard'
import BillingPage from './pages/BillingPage'
import AccountPage from './pages/AccountPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import AuthCallback from './pages/AuthCallback'
import { useSocket } from './hooks/useSocket'
import { useAuthContext } from './context/auth'
import { useAuthFetch } from './hooks/useAuthFetch'
import { getTheme, DEFAULT_THEME_ID } from './themes'

const SIDEBAR_MIN = 180
const SIDEBAR_MAX = 520
const SIDEBAR_DEFAULT = 240

const ACTIVITY_MIN = 50
const ACTIVITY_MAX = 360
const ACTIVITY_DEFAULT = 88

const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === 'true'

// ── Theme-aware wrapper with Matrix rain on all pages ──────────────────────

function ThemedLayout({ children }: { children: React.ReactNode }) {
  const themeId = localStorage.getItem('agentteam-theme') ?? DEFAULT_THEME_ID
  const theme = getTheme(themeId)

  useEffect(() => {
    const root = document.documentElement
    Object.entries(theme.vars).forEach(([key, value]) => {
      root.style.setProperty(key, value)
    })
  }, [theme])

  return <>{children}</>
}

// ── Route guards ───────────────────────────────────────────────────────────────

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuthContext()
  if (!AUTH_DISABLED && !user) return <Navigate to="/login" replace />
  return <>{children}</>
}

// ── Onboarding gate ────────────────────────────────────────────────────────────
// After login, if the user has no subscription, redirect to /billing so they
// can choose a plan before accessing the main app.
// Skipped entirely when AUTH_DISABLED=true (local dev).

function BillingGate({ children }: { children: React.ReactNode }) {
  const authFetch  = useAuthFetch()
  const navigate   = useNavigate()
  const [checked, setChecked] = useState(AUTH_DISABLED)  // skip check in dev

  useEffect(() => {
    if (AUTH_DISABLED) return
    authFetch('/api/billing/usage')
      .then(r => r.json())
      .then((data: { plan: string }) => {
        if (data.plan === 'none') {
          navigate('/billing', { replace: true })
        } else {
          setChecked(true)
        }
      })
      .catch(() => setChecked(true))   // on error, let the user in
  }, [authFetch, navigate])

  if (!checked) return null   // brief flash while the check runs
  return <>{children}</>
}

// ── Project workspace (was MainApp, now at /project/:id) ─────────────────────

function Workspace() {
  const { state, startProject, cancelProject } = useSocket()
  const [settingsOpen, setSettingsOpen]     = useState(false)
  const [sidebarWidth, setSidebarWidth]     = useState(SIDEBAR_DEFAULT)
  const [activityHeight, setActivityHeight] = useState(ACTIVITY_DEFAULT)
  const [usage, setUsage] = useState<Usage | null>(null)
  const authFetch = useAuthFetch()

  useEffect(() => {
    authFetch('/api/billing/usage')
      .then(r => r.json())
      .then(setUsage)
      .catch(() => {})
  }, [])

  const creditPct = usage
    ? Math.min(100, Math.round((usage.balance_cents / ((usage.plan === 'pro' ? 4800 : usage.plan === 'starter' ? 1500 : 1))) * 100))
    : 0

  const onSidebarDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    const startX = e.clientX
    const startW = sidebarWidth

    const onMove = (ev: MouseEvent) => {
      const delta = startX - ev.clientX
      setSidebarWidth(Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, startW + delta)))
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [sidebarWidth])

  const onActivityDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    const startY = e.clientY
    const startH = activityHeight

    const onMove = (ev: MouseEvent) => {
      const delta = startY - ev.clientY
      setActivityHeight(Math.max(ACTIVITY_MIN, Math.min(ACTIVITY_MAX, startH + delta)))
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [activityHeight])

  const themeId = localStorage.getItem('agentteam-theme') ?? DEFAULT_THEME_ID
  const theme = getTheme(themeId)

  return (
    <>
      {themeId === 'matrix' && <MatrixRain rainColor={theme.vars['--rain-color']} rainBg={theme.vars['--rain-bg']} />}
      <div className="relative w-full h-full flex flex-col overflow-hidden" style={{ background: 'var(--c-bg)' }}>
      <HealthBanner />

      <Header
        project={state.project}
        sprint={state.sprint}
        feature={state.feature}
        progress={state.progress}
        elapsedSeconds={state.elapsedSeconds}
        running={state.running}
        onStart={startProject}
        onStop={cancelProject}
        onSettings={() => { setSettingsOpen(true) }}
        onToggleSidebar={() => setSidebarWidth(w => w > 0 ? 0 : SIDEBAR_DEFAULT)}
        mode="workspace"
      />

      <div className="flex flex-1 overflow-hidden relative z-10 min-h-0">
        <div className="flex-1 relative min-w-0">
          <AgentNetwork agents={state.agents} running={state.running} messages={state.messages} selectedAgentIds={state.selectedAgentIds} />
        </div>

        <div className="relative shrink-0 hidden lg:flex" style={{ width: sidebarWidth }}>
          <div
            onMouseDown={onSidebarDragStart}
            className="absolute left-0 top-0 h-full w-1 cursor-col-resize z-10 hover:bg-white/20 active:bg-white/40 transition-colors"
          />
          <Sidebar
            agents={state.agents}
            tasks={state.tasks}
            changedFiles={state.changedFiles}
            changedFileNames={state.changedFileNames}
            terminalLines={state.terminalLines}
            running={state.running}
            currentStage={state.currentStage}
            reviewerActive={state.reviewerActive}
            reviewerResult={state.reviewerResult}
            validationVerdicts={state.validationVerdicts}
            validationResult={state.validationResult}
            reworkNotice={state.reworkNotice}
            onAddAgents={() => { setSettingsOpen(true) }}
          />
        </div>
      </div>

      <div className="relative shrink-0 z-10" style={{ height: activityHeight }}>
        <div
          onMouseDown={onActivityDragStart}
          className="absolute top-0 left-0 right-0 h-1 cursor-row-resize z-10 hover:bg-white/20 active:bg-white/40 transition-colors"
        />
        <LiveActivity log={state.log} agents={state.agents} />
      </div>

      <StatusBar projectCount={1} creditPct={creditPct} />

      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={() => {}}
      />
    </div>
    </>
  )
}

// ── Router ─────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <ThemedLayout>
    <Routes>
      {/* Public routes */}
      <Route path="/login"         element={<LoginPage />} />
      <Route path="/register"      element={<RegisterPage />} />
      <Route path="/auth/callback" element={<AuthCallback />} />

      {/* Protected routes */}
      <Route path="/project/:id" element={<ProtectedRoute><Workspace /></ProtectedRoute>} />
      <Route path="/billing"     element={<ProtectedRoute><BillingPage /></ProtectedRoute>} />
      <Route path="/settings"    element={<ProtectedRoute><AccountPage /></ProtectedRoute>} />
      <Route path="/"            element={
        <ProtectedRoute>
          <BillingGate>
            <Dashboard />
          </BillingGate>
        </ProtectedRoute>
      } />
    </Routes>
    </ThemedLayout>
  )
}
