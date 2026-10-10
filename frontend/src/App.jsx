import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Menu } from 'lucide-react'
import { AuthProvider, useAuth, can } from './hooks/useAuth'
import { BrandingProvider, useBranding } from './hooks/useBranding'
import { LanguageProvider } from './i18n/LanguageContext'
import { AccessibilityProvider } from './context/AccessibilityContext'
import SkipLink from './components/SkipLink'
import Breadcrumbs from './components/Breadcrumbs'
import AnnouncementBanner from './components/AnnouncementBanner'
import UserWelcomeModal from './components/UserWelcomeModal'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Brokers from './pages/Brokers'
import BrokerSubmit from './pages/BrokerSubmit'
import Family from './pages/Family'
import IdentityVault from './pages/IdentityVault'
import AdminPanel from './pages/AdminPanel'
import Settings from './pages/Settings'
import Translations from './pages/Translations'
import Scheduled from './pages/Scheduled'
import Help from './pages/Help'
import EmailMonitor from './pages/EmailMonitor'
import Discovery from './pages/Discovery'
import Branding from './pages/Branding'
import Reporting from './pages/Reporting'
import DatabaseAdmin from './pages/DatabaseAdmin'
import Plugins from './pages/Plugins'
import PluginUpload from './pages/PluginUpload'
import PluginHelp from './pages/PluginHelp'
import SystemLogs from './pages/SystemLogs'
import BrokerHealth from './pages/BrokerHealth'
import BrokerPriority from './pages/BrokerPriority'
import ParentCompanies from './pages/ParentCompanies'
import CaptchaQueue from './pages/CaptchaQueue'
import WorkerFleet from './pages/WorkerFleet'
import Login from './pages/Login'
import SetupWizard from './pages/SetupWizard'

// Super admins, plus managers holding at least one of these permissions.
function RequirePermission({ perms, children }) {
  const { user } = useAuth()
  if (!can(user, ...perms)) return <Navigate to="/" replace />
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
  const systemName = branding?.system_name || 'OpenOptOut'

  // Close the drawer whenever the route changes (belt-and-suspenders alongside
  // the per-NavItem onClose, e.g. for programmatic navigation).
  useEffect(() => { setDrawerOpen(false) }, [location.pathname])

  return (
    <div className="flex min-h-screen bg-slate-950">
      <Sidebar open={drawerOpen} onClose={() => setDrawerOpen(false)} />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Mobile top bar with hamburger — hidden on md and up */}
        <header role="banner" className="md:hidden flex items-center gap-3 px-4 h-14 bg-slate-900 border-b border-slate-800 shrink-0">
          <button onClick={() => setDrawerOpen(true)} className="text-slate-300 hover:text-white p-1 -ml-1" aria-label="Open menu">
            <Menu size={22} />
          </button>
          <span className="text-white font-semibold text-sm truncate">{systemName}</span>
        </header>
        <AnnouncementBanner />
        <UserWelcomeModal />
        <main id="main-content" tabIndex="-1" role="main" className="flex-1 overflow-auto focus:outline-hidden">
          <Breadcrumbs />
          <Routes>
            <Route path="/"            element={<Dashboard />} />
            <Route path="/brokers"     element={<Brokers />} />
            <Route path="/brokers/add" element={<RequirePermission perms={['brokers.manage']}><BrokerSubmit /></RequirePermission>} />
            <Route path="/email"       element={<EmailMonitor />} />
            <Route path="/scheduled"   element={<Scheduled />} />
            <Route path="/discovery"   element={<Discovery />} />
            <Route path="/family"      element={<Family />} />
            <Route path="/identity"    element={<IdentityVault />} />
            <Route path="/settings"    element={<Settings />} />
            <Route path="/translations" element={<RequirePermission perms={['settings.manage']}><Translations /></RequirePermission>} />
            <Route path="/help"        element={<Help />} />
            <Route path="/admin"       element={<RequirePermission perms={['users.manage']}><AdminPanel /></RequirePermission>} />
            <Route path="/branding"    element={<RequirePermission perms={['branding.manage', 'users.registration', 'auth.providers']}><Branding /></RequirePermission>} />
            <Route path="/reporting"   element={<RequirePermission perms={['reporting.view']}><Reporting /></RequirePermission>} />
            <Route path="/database"    element={<RequirePermission perms={['database.view']}><DatabaseAdmin /></RequirePermission>} />
            <Route path="/plugins"     element={<RequirePermission perms={['plugins.view']}><Plugins /></RequirePermission>} />
            <Route path="/plugin-help" element={<RequirePermission perms={['plugins.view', 'plugins.upload']}><PluginHelp /></RequirePermission>} />
            <Route path="/plugin-upload" element={<RequirePermission perms={['plugins.upload']}><PluginUpload /></RequirePermission>} />
            <Route path="/broker-health" element={<RequirePermission perms={['brokers.manage']}><BrokerHealth /></RequirePermission>} />
            <Route path="/broker-priority" element={<RequirePermission perms={['brokers.manage']}><BrokerPriority /></RequirePermission>} />
            <Route path="/parent-companies" element={<RequirePermission perms={['brokers.manage']}><ParentCompanies /></RequirePermission>} />
            <Route path="/captcha" element={<CaptchaQueue />} />
            <Route path="/logs" element={<RequirePermission perms={['logs.view']}><SystemLogs /></RequirePermission>} />
            <Route path="/worker-fleet" element={<RequirePermission perms={['settings.system']}><WorkerFleet /></RequirePermission>} />
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
    <AccessibilityProvider>
      <BrandingProvider>
        <AuthProvider>
          <LanguageProvider>
            <SkipLink />
            <BrowserRouter>
              <Routes>
                <Route path="/login"                element={<Login />} />
                <Route path="/auth/callback"        element={<OIDCCallback />} />
                <Route path="/*"                    element={<RequireAuth><Layout /></RequireAuth>} />
              </Routes>
            </BrowserRouter>
          </LanguageProvider>
        </AuthProvider>
      </BrandingProvider>
    </AccessibilityProvider>
  )
}
