import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Store, Mail, CalendarClock, Radar,
  Users, ShieldCheck, Settings, LogOut, ShieldAlert,
  ToggleLeft, ToggleRight, BookOpen, PlusCircle,
  Palette, BarChart2, HardDrive, Puzzle, X, Activity, ListOrdered, Building2, Upload
} from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { useBranding } from '../hooks/useBranding'
import api from '../api'
import { useState } from 'react'

const nav = [
  { label: 'Dashboard',     to: '/',           icon: LayoutDashboard },
  { label: 'Brokers',       to: '/brokers',    icon: Store },
  { label: 'Discovery',     to: '/discovery',  icon: Radar },
  { label: 'Email monitor', to: '/email',      icon: Mail },
  { label: 'Scheduled',     to: '/scheduled',  icon: CalendarClock },
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
  const [toggling, setToggling]   = useState(false)

  const toggleView = async () => {
    if (toggling) return
    setToggling(true)
    try {
      await api.patch(`/auth/me/unified-view?unified=${!user.unified_view}`)
      setUser({ ...user, unified_view: !user.unified_view })
    } finally { setToggling(false) }
  }

  const roleColor = { super_admin: 'text-purple-400', parent: 'text-teal-400', member: 'text-slate-400' }[user?.role] ?? 'text-slate-400'
  const systemName = branding?.system_name || 'PrivacyShield'

  const handleNavigate = () => onClose()

  return (
    <>
      {/* Backdrop — mobile only, shown when the drawer is open */}
      {open && (
        <div className="fixed inset-0 bg-black/60 z-30 md:hidden" onClick={onClose} aria-hidden="true" />
      )}

      <aside
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

        <nav className="flex flex-col gap-0.5 flex-1 overflow-y-auto">
          <p className="text-slate-600 text-xs px-4 mb-1 uppercase tracking-widest">Manage</p>
          {nav.map(n => <NavItem key={n.to} {...n} onNavigate={handleNavigate} />)}
          <p className="text-slate-600 text-xs px-4 mt-3 mb-1 uppercase tracking-widest">Setup</p>
          {setup.map(n => <NavItem key={n.to} {...n} onNavigate={handleNavigate} />)}
          {user?.role === 'super_admin' && (
            <>
              <p className="text-slate-600 text-xs px-4 mt-3 mb-1 uppercase tracking-widest">Admin</p>
              <NavItem to="/admin"     icon={ShieldAlert} label="Admin panel" onNavigate={handleNavigate} />
              <NavItem to="/broker-health" icon={Activity} label="Broker health" onNavigate={handleNavigate} />
              <NavItem to="/broker-priority" icon={ListOrdered} label="Broker priority" onNavigate={handleNavigate} />
              <NavItem to="/parent-companies" icon={Building2} label="Parent companies" onNavigate={handleNavigate} />
              <NavItem to="/branding"  icon={Palette}     label="Branding" onNavigate={handleNavigate} />
              <NavItem to="/reporting" icon={BarChart2}    label="Reporting" onNavigate={handleNavigate} />
              <NavItem to="/database"  icon={HardDrive}   label="Database" onNavigate={handleNavigate} />
              <NavItem to="/plugins"   icon={Puzzle}      label="Plugins" onNavigate={handleNavigate} />
              <NavItem to="/plugin-help" icon={BookOpen}  label="Plugin docs" onNavigate={handleNavigate} />
              <NavItem to="/brokers/add" icon={PlusCircle} label="Add brokers" onNavigate={handleNavigate} />
            </>
          )}
          {user?.role !== 'super_admin' && user?.can_upload_plugins && (
            <>
              <p className="text-slate-600 text-xs px-4 mt-3 mb-1 uppercase tracking-widest">Plugins</p>
              <NavItem to="/plugin-upload" icon={Upload} label="Upload plugin" onNavigate={handleNavigate} />
            </>
          )}
        </nav>

        {user?.role === 'parent' && (
          <div className="mx-2 mt-2 px-3 py-2.5 bg-slate-800 rounded-lg border border-slate-700/50">
            <p className="text-slate-500 text-xs mb-2">Dashboard view</p>
            <button onClick={toggleView} disabled={toggling} className="flex items-center gap-2 w-full text-left">
              {user.unified_view ? <ToggleRight size={16} className="text-shield-400 shrink-0" /> : <ToggleLeft size={16} className="text-slate-600 shrink-0" />}
              <span className="text-slate-300 text-xs">{user.unified_view ? 'All managed profiles' : 'My profile only'}</span>
            </button>
          </div>
        )}

        <div className="px-4 pt-4 border-t border-slate-800 mt-2">
          <p className={`text-xs mb-0.5 ${roleColor}`}>{user?.role}</p>
          <p className="text-white text-sm font-medium truncate">{user?.full_name}</p>
          <p className="text-slate-500 text-xs truncate">{user?.email}</p>
          {branding?.show_powered_by && (
            <p className="text-slate-700 text-xs mt-2">Powered by PrivacyShield</p>
          )}
          <button onClick={logout} className="mt-2 flex items-center gap-1.5 text-slate-500 hover:text-white text-xs transition-colors">
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </aside>
    </>
  )
}
