import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Store, Mail, CalendarClock, Radar,
  Users, ShieldCheck, Settings, LogOut, ShieldAlert,
  ToggleLeft, ToggleRight, BookOpen, PlusCircle,
  Palette, BarChart2, HardDrive, Puzzle, X, Activity, ListOrdered, Building2, Upload, Terminal,
  Globe, Compass, Server, Eye, Sun
} from 'lucide-react'
import { useAuth, can } from '../hooks/useAuth'
import { useBranding } from '../hooks/useBranding'
import { useLanguage } from '../i18n/LanguageContext'
import { useAccessibility } from '../context/AccessibilityContext'
import api from '../api'
import { useState } from 'react'

const nav = [
  { label: 'Dashboard',     to: '/',           icon: LayoutDashboard },
  { label: 'Brokers',       to: '/brokers',    icon: Store },
  { label: 'Discovery',     to: '/discovery',  icon: Radar },
  { label: 'Email monitor', to: '/email',      icon: Mail },
  { label: 'Scheduled',     to: '/scheduled',  icon: CalendarClock },
  { label: 'CAPTCHA queue', to: '/captcha',    icon: ShieldAlert },
]
const setup = [
  { label: 'Family members', to: '/family',   icon: Users },
  { label: 'Identity vault', to: '/identity', icon: ShieldCheck },
  { label: 'Settings',       to: '/settings', icon: Settings },
  { label: 'Help',           to: '/help',     icon: BookOpen },
]

function NavItem({ to, icon: Icon, label, onNavigate }) {
  return (
    <NavLink to={to} end={to === '/'} onClick={onNavigate}
      className={({ isActive }) =>
        `flex items-center gap-2.5 px-4 py-2 text-sm rounded-md mx-2 transition-colors ${
          isActive ? 'bg-shield-600 text-white font-medium' : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
        }`
      }
    >
      <Icon size={15} />{label}
    </NavLink>
  )
}

/**
 * Responsive sidebar.
 * - Desktop (md and up): static column, always visible.
 * - Mobile: off-canvas drawer that slides in when `open` is true, with a
 *   backdrop. `open`/`onClose` are controlled by the Layout so a hamburger
 *   button in the mobile top bar can open it, and navigating closes it.
 */
export default function Sidebar({ open = false, onClose = () => {} }) {
  const { user, logout, setUser } = useAuth()
  const { branding }              = useBranding()
  const { language, setLanguage, availableLanguages, setShowWelcomeTour, t } = useLanguage()
  const { theme, setTheme, highContrast, setHighContrast, dyslexicFont, setDyslexicFont } = useAccessibility()
  const [toggling, setToggling]   = useState(false)

  const toggleView = async () => {
    if (toggling) return
    setToggling(true)
    try {
      await api.patch(`/auth/me/unified-view?unified=${!user.unified_view}`)
      setUser({ ...user, unified_view: !user.unified_view })
    } finally { setToggling(false) }
  }

  // Admin links, each shown only to users holding its permission (super admins
  // hold them all). Upload plugin shows on its own for managers who can upload
  // but not see the Plugins page.
  const adminLinks = [
    { to: '/admin',            icon: ShieldAlert, label: 'Admin panel',      perms: ['users.manage'] },
    { to: '/broker-health',    icon: Activity,    label: 'Broker health',    perms: ['brokers.manage'] },
    { to: '/broker-priority',  icon: ListOrdered, label: 'Broker priority',  perms: ['brokers.manage'] },
    { to: '/parent-companies', icon: Building2,   label: 'Parent companies', perms: ['brokers.manage'] },
    { to: '/branding',         icon: Palette,     label: 'Branding',         perms: ['branding.manage', 'users.registration', 'auth.providers'] },
    { to: '/translations',     icon: Globe,       label: 'Translations',     perms: ['settings.manage'] },
    { to: '/reporting',        icon: BarChart2,   label: 'Reporting',        perms: ['reporting.view'] },
    { to: '/database',         icon: HardDrive,   label: 'Database',         perms: ['database.view'] },
    { to: '/worker-fleet',     icon: Server,      label: 'Worker fleet',     perms: ['settings.system'] },
    { to: '/logs',             icon: Terminal,    label: 'System logs',      perms: ['logs.view'] },
    { to: '/plugins',          icon: Puzzle,      label: 'Plugins',          perms: ['plugins.view'] },
    ...(!can(user, 'plugins.view') ? [{ to: '/plugin-upload', icon: Upload, label: 'Upload plugin', perms: ['plugins.upload'] }] : []),
    { to: '/plugin-help',      icon: BookOpen,    label: 'Plugin docs',      perms: ['plugins.view', 'plugins.upload'] },
    { to: '/brokers/add',      icon: PlusCircle,  label: 'Add brokers',      perms: ['brokers.manage'] },
  ].filter(n => can(user, ...n.perms)).map(({ perms, ...n }) => n)

  const roleColor = { super_admin: 'text-purple-400', manager: 'text-sky-400', parent: 'text-teal-400', member: 'text-slate-400' }[user?.role] ?? 'text-slate-400'
  const systemName = branding?.system_name || 'OpenOptOut'

  const handleNavigate = () => onClose()

  return (
    <>
      {/* Backdrop — mobile only, shown when the drawer is open */}
      {open && (
        <div className="fixed inset-0 bg-black/60 z-30 md:hidden" onClick={onClose} aria-hidden="true" />
      )}

      <aside
        aria-label="Main sidebar"
        className={`bg-slate-900 flex flex-col py-4 w-64 md:w-52 shrink-0 h-screen z-40
          fixed inset-y-0 left-0 transform transition-transform duration-200 ease-in-out
          md:sticky md:top-0 md:translate-x-0
          ${open ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="px-4 mb-6 flex items-start justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {branding?.logo_url ? (
                <img src={branding.logo_url} alt="Logo" className="h-6 object-contain" />
              ) : (
                <ShieldCheck size={18} className="text-shield-500" />
              )}
              <span className="text-white font-semibold text-sm truncate">{systemName}</span>
            </div>
            {branding?.tagline && <p className="text-slate-500 text-xs mt-0.5 truncate">{branding.tagline}</p>}
          </div>
          {/* Close button — mobile only */}
          <button onClick={onClose} className="md:hidden text-slate-500 hover:text-white p-1 -mr-1" aria-label="Close menu">
            <X size={18} />
          </button>
        </div>

        <nav aria-label="Primary navigation" className="flex flex-col gap-0.5 flex-1 overflow-y-auto">
          <p className="text-slate-600 text-xs px-4 mb-1 uppercase tracking-widest">Manage</p>
          {nav.map(n => <NavItem key={n.to} {...n} onNavigate={handleNavigate} />)}
          <p className="text-slate-600 text-xs px-4 mt-3 mb-1 uppercase tracking-widest">Setup</p>
          {setup.map(n => <NavItem key={n.to} {...n} onNavigate={handleNavigate} />)}
          {adminLinks.length > 0 && (
            <>
              <p className="text-slate-600 text-xs px-4 mt-3 mb-1 uppercase tracking-widest">Admin</p>
              {adminLinks.map(n => <NavItem key={n.to} {...n} onNavigate={handleNavigate} />)}
            </>
          )}
        </nav>

        {(user?.role === 'parent' || user?.role === 'manager') && (
          <div className="mx-2 mt-2 px-3 py-2.5 bg-slate-800 rounded-lg border border-slate-700/50">
            <p className="text-slate-500 text-xs mb-2">Dashboard view</p>
            <button onClick={toggleView} disabled={toggling} className="flex items-center gap-2 w-full text-left">
              {user.unified_view ? <ToggleRight size={16} className="text-shield-400 shrink-0" /> : <ToggleLeft size={16} className="text-slate-600 shrink-0" />}
              <span className="text-slate-300 text-xs">{user.unified_view ? 'All managed profiles' : 'My profile only'}</span>
            </button>
          </div>
        )}

        <div className="px-4 pt-4 border-t border-slate-800 mt-2 space-y-2.5">
          {/* On-the-fly Language Switcher */}
          <div className="flex items-center justify-between py-1 px-2 bg-slate-950/60 rounded-lg border border-slate-800">
            <div className="flex items-center gap-1.5 text-slate-400">
              <Globe size={13} className="text-blue-400" />
              <span className="text-xs">{t('nav.language', 'Language')}</span>
            </div>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="bg-transparent text-white text-xs border-0 focus:ring-0 cursor-pointer pr-1"
            >
              {availableLanguages.map(l => (
                <option key={l.code} value={l.code} className="bg-slate-900 text-white">
                  {l.native_name} {l.is_rtl ? '(RTL)' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Quick Theme Selector */}
          <div className="flex items-center justify-between py-1 px-2 bg-slate-950/60 rounded-lg border border-slate-800">
            <div className="flex items-center gap-1.5 text-slate-400">
              <Sun size={13} className="text-amber-400" />
              <span className="text-xs">{t('a11y.theme', 'Theme')}</span>
            </div>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              className="bg-transparent text-white text-xs border-0 focus:ring-0 cursor-pointer pr-1"
            >
              <option value="dark" className="bg-slate-900 text-white">{t('a11y.theme_dark', 'Dark')}</option>
              <option value="light" className="bg-slate-900 text-white">{t('a11y.theme_light', 'Light')}</option>
              <option value="gray" className="bg-slate-900 text-white">{t('a11y.theme_gray', 'Gray')}</option>
              <option value="system" className="bg-slate-900 text-white">{t('a11y.theme_system', 'System')}</option>
            </select>
          </div>

          {/* Quick High Contrast Mode Toggle */}
          <button
            onClick={() => setHighContrast(!highContrast)}
            className={`flex items-center justify-between w-full py-1.5 px-2 rounded-lg border text-xs transition-colors ${
              highContrast
                ? 'bg-yellow-400/20 text-yellow-300 border-yellow-400/50'
                : 'bg-slate-950/60 text-slate-400 border-slate-800 hover:text-white'
            }`}
            aria-pressed={highContrast}
            title={t('a11y.high_contrast', 'High Contrast Mode (WCAG 2.2 AAA)')}
          >
            <div className="flex items-center gap-1.5">
              <Eye size={13} className={highContrast ? 'text-yellow-400' : 'text-slate-400'} />
              <span>{t('a11y.high_contrast', 'High Contrast')}</span>
            </div>
            <span className="text-[10px] font-mono px-1 rounded bg-black/40">
              {highContrast ? 'ON' : 'OFF'}
            </span>
          </button>

          {/* Quick Dyslexia Font Toggle */}
          <button
            onClick={() => setDyslexicFont(!dyslexicFont)}
            className={`flex items-center justify-between w-full py-1.5 px-2 rounded-lg border text-xs transition-colors ${
              dyslexicFont
                ? 'bg-purple-500/20 text-purple-300 border-purple-500/50'
                : 'bg-slate-950/60 text-slate-400 border-slate-800 hover:text-white'
            }`}
            aria-pressed={dyslexicFont}
            title={t('a11y.dyslexic_font', 'Dyslexia-Friendly Font (OpenDyslexic)')}
          >
            <div className="flex items-center gap-1.5">
              <BookOpen size={13} className={dyslexicFont ? 'text-purple-400' : 'text-slate-400'} />
              <span>{t('a11y.dyslexic_font_short', 'Dyslexia Font')}</span>
            </div>
            <span className="text-[10px] font-mono px-1 rounded bg-black/40">
              {dyslexicFont ? 'ON' : 'OFF'}
            </span>
          </button>

          <div>
            <p className={`text-xs mb-0.5 ${roleColor}`}>{user?.role}</p>
            <p className="text-white text-sm font-medium truncate">{user?.full_name}</p>
            <p className="text-slate-500 text-xs truncate">{user?.email}</p>
          </div>

          <button
            onClick={() => { setShowWelcomeTour(true); onClose(); }}
            className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors pt-0.5"
          >
            <Compass size={13} /> {t('nav.welcome_tour', 'Welcome Tour')}
          </button>

          {branding?.show_powered_by && (
            <p className="text-slate-700 text-xs mt-1">Powered by OpenOptOut</p>
          )}
          <button onClick={logout} className="mt-1 flex items-center gap-1.5 text-slate-500 hover:text-white text-xs transition-colors">
            <LogOut size={13} /> {t('nav.logout', 'Sign out')}
          </button>
        </div>
      </aside>
    </>
  )
}
