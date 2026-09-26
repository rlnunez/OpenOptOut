import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Menu } from 'lucide-react'
import { AuthProvider, useAuth } from './hooks/useAuth'
import { BrandingProvider, useBranding } from './hooks/useBranding'
import AnnouncementBanner from './components/AnnouncementBanner'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Brokers from './pages/Brokers'
import BrokerSubmit from './pages/BrokerSubmit'
import Family from './pages/Family'
import IdentityVault from './pages/IdentityVault'
import AdminPanel from './pages/AdminPanel'
import Settings from './pages/Settings'
import Scheduled from './pages/Scheduled'
import Help from './pages/Help'
import EmailMonitor from './pages/EmailMonitor'
import Discovery from './pages/Discovery'
import Branding from './pages/Branding'
import Reporting from './pages/Reporting'
import DatabaseAdmin from './pages/DatabaseAdmin'
import Plugins from './pages/Plugins'
import PluginHelp from './pages/PluginHelp'
import BrokerHealth from './pages/BrokerHealth'
import BrokerPriority from './pages/BrokerPriority'
import ParentCompanies from './pages/ParentCompanies'
import Login from './pages/Login'
import SetupWizard from './pages/SetupWizard'

function RequireRole({ role, children }) {
  const { user } = useAuth()
  if (user?.role !== role) return <Navigate to="/" replace />
  return children
}

// Handle OIDC callback — token arrives in URL fragment
function OIDCCallback() {
  const { setUser } = useAuth()
  const navigate    = useNavigate()
  useEffect(() => {
    // Token arrives in the URL fragment (#token=...) — never sent to servers or logs.
    const hash   = window.location.hash.slice(1)
    const params = new URLSearchParams(hash.replace(/^\/?auth\/callback\?/, ''))
    const token  = params.get('token')
    // Clear the token from the address bar/history immediately.
    window.history.replaceState(null, '', window.location.pathname)
    if (token) {
      localStorage.setItem('token', token)
      import('./api').then(({ default: api }) => {
        api.get('/auth/me').then(r => { setUser(r.data); navigate('/') })
      })
    } else {
      navigate('/login')
    }
  }, [])
  return <div className="min-h-screen bg-slate-950 flex items-center justify-center"><p className="text-slate-500">Completing sign in…</p></div>
}

function Layout() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()
  const { branding } = useBranding()
  const systemName = branding?.system_name || 'PrivacyShield'

  // Close the drawer whenever the route changes (belt-and-suspenders alongside
  // the per-NavItem onClose, e.g. for programmatic navigation).
  useEffect(() => { setDrawerOpen(false) }, [location.pathname])

  return (
    <div className="flex min-h-screen bg-slate-950">
      <Sidebar open={drawerOpen} onClose={() => setDrawerOpen(false)} />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Mobile top bar with hamburger — hidden on md and up */}
        <div className="md:hidden flex items-center gap-3 px-4 h-14 bg-slate-900 border-b border-slate-800 shrink-0">
          <button onClick={() => setDrawerOpen(true)} className="text-slate-300 hover:text-white p-1 -ml-1" aria-label="Open menu">
            <Menu size={22} />
          </button>
          <span className="text-white font-semibold text-sm truncate">{systemName}</span>
        </div>
        <AnnouncementBanner />
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/"            element={<Dashboard />} />
            <Route path="/brokers"     element={<Brokers />} />
            <Route path="/brokers/add" element={<RequireRole role="super_admin"><BrokerSubmit /></RequireRole>} />
            <Route path="/email"       element={<EmailMonitor />} />
            <Route path="/scheduled"   element={<Scheduled />} />
            <Route path="/discovery"   element={<Discovery />} />
            <Route path="/family"      element={<Family />} />
            <Route path="/identity"    element={<IdentityVault />} />
            <Route path="/settings"    element={<Settings />} />
            <Route path="/help"        element={<Help />} />
            <Route path="/admin"       element={<RequireRole role="super_admin"><AdminPanel /></RequireRole>} />
            <Route path="/branding"    element={<RequireRole role="super_admin"><Branding /></RequireRole>} />
            <Route path="/reporting"   element={<RequireRole role="super_admin"><Reporting /></RequireRole>} />
            <Route path="/database"    element={<RequireRole role="super_admin"><DatabaseAdmin /></RequireRole>} />
            <Route path="/plugins"     element={<RequireRole role="super_admin"><Plugins /></RequireRole>} />
            <Route path="/plugin-help" element={<RequireRole role="super_admin"><PluginHelp /></RequireRole>} />
            <Route path="/broker-health" element={<RequireRole role="super_admin"><BrokerHealth /></RequireRole>} />
            <Route path="/broker-priority" element={<RequireRole role="super_admin"><BrokerPriority /></RequireRole>} />
            <Route path="/parent-companies" element={<RequireRole role="super_admin"><ParentCompanies /></RequireRole>} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  const [wizard, setWizard] = useState(undefined)  // undefined=checking, null=n/a, obj=state

  useEffect(() => {
    if (user?.role === 'super_admin') {
      import('./api').then(({ default: api }) => {
        api.get('/wizard/state')
          .then(r => setWizard(r.data))
          .catch(() => setWizard(null))
      })
    } else if (user) {
      setWizard(null)
    }
  }, [user])

  if (loading) return <div className="min-h-screen bg-slate-950 flex items-center justify-center"><p className="text-slate-500 text-sm">Loading…</p></div>
  if (!user)   return <Navigate to="/login" replace />
  // Fresh install: super admin hasn't finished the setup wizard yet.
  if (user.role === 'super_admin' && wizard === undefined)
    return <div className="min-h-screen bg-slate-950 flex items-center justify-center"><p className="text-slate-500 text-sm">Loading…</p></div>
  if (wizard && !wizard.completed)
    return <SetupWizard onDone={() => setWizard({ ...wizard, completed: true })} />
  return children
}

export default function App() {
  return (
    <BrandingProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login"                element={<Login />} />
            <Route path="/auth/callback"        element={<OIDCCallback />} />
            <Route path="/*"                    element={<RequireAuth><Layout /></RequireAuth>} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </BrandingProvider>
  )
}
