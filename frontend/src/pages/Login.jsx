import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, CreditCard, Users } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { useBranding } from '../hooks/useBranding'
import api from '../api'

const inp = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-shield-500"

export default function Login() {
  const { login }    = useAuth()
  const { branding } = useBranding()
  const navigate     = useNavigate()

  // Auth provider state
  const [oidcProviders, setOidcProviders]   = useState([])
  const [saml, setSaml]                     = useState(null)   // {label} when enabled
  const [sip2Enabled,   setSip2Enabled]     = useState(false)
  const [loadingProviders, setLoadingProviders] = useState(true)

  // Tab: 'staff' | 'patron'
  const showStaff  = branding?.show_staff_tab  ?? true
  const showPatron = branding?.show_patron_tab ?? false
  const [tab, setTab] = useState(showStaff ? 'staff' : 'patron')

  // Form state
  const [email,    setEmail]    = useState('')
  const [password, setPw]       = useState('')
  const [barcode,  setBarcode]  = useState('')
  const [pin,      setPin]      = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)

  // First-run setup: if the install has zero accounts, show a "create the
  // administrator account" flow instead of a login form.
  const [needsSetup, setNeedsSetup] = useState(null)   // null = checking

  useEffect(() => {
    api.get('/auth/needs-setup')
      .then(r => setNeedsSetup(!!r.data.needs_setup))
      .catch(() => setNeedsSetup(false))
  }, [])

  useEffect(() => {
    api.get('/branding/auth-providers').then(r => {
      const ap = r.data
      setSip2Enabled(ap.sip2_enabled || false)
      setOidcProviders((ap.oidc_providers || []).filter(p => p.enabled))
      setSaml(ap.saml_enabled ? { label: ap.saml_label || 'Single sign-on' } : null)
    }).catch(() => {}).finally(() => setLoadingProviders(false))
  }, [])

  // Keep tab in sync if branding changes
  useEffect(() => {
    if (!showStaff && showPatron) setTab('patron')
    if (showStaff && !showPatron) setTab('staff')
  }, [showStaff, showPatron])

  const submitStaff = async e => {
    e.preventDefault(); setError(''); setLoading(true)
    try { await login(email, password); navigate('/') }
    catch { setError('Invalid email or password') }
    finally { setLoading(false) }
  }

  const submitPatron = async e => {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const { data } = await api.post('/auth/sip2/login', { barcode, pin })
      localStorage.setItem('token', data.access_token)
      window.location.href = '/'
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Library card authentication failed')
    } finally { setLoading(false) }
  }

  const oidcLogin = provider => { window.location.href = `/api/auth/oidc/${provider}/login` }

  // First-run: create the initial administrator, then log them straight in.
  const [setupName, setSetupName] = useState('')
  const [setupConfirm, setSetupConfirm] = useState('')
  const submitSetup = async e => {
    e.preventDefault(); setError('')
    if (password.length < 8) { setError('Use a password of at least 8 characters'); return }
    if (password !== setupConfirm) { setError('Passwords do not match'); return }
    setLoading(true)
    try {
      await api.post('/auth/register', { email, full_name: setupName, password })
      await login(email, password)   // first user is created as super_admin
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not create the administrator account')
    } finally { setLoading(false) }
  }

  const name         = branding?.system_name   || 'OpenOptOut'
  const tagline      = branding?.tagline        || 'Your personal data removal service'
  const staffLabel   = branding?.staff_tab_label  || 'Staff'
  const patronLabel  = branding?.patron_tab_label || 'Library Card'
  const staffWelcome = branding?.staff_welcome  || branding?.welcome_message
  const patronWelcome= branding?.patron_welcome || branding?.welcome_message

  const showTabs = showStaff && showPatron   // both enabled = show tabs

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">

        {/* Logo / name */}
        <div className="flex flex-col items-center mb-8">
          {branding?.logo_url ? (
            <img src={branding.logo_url} alt={name} className="h-12 object-contain mb-3" />
          ) : (
            <ShieldCheck size={28} className="text-shield-500 mb-2" />
          )}
          <h1 className="text-white font-semibold text-lg">{name}</h1>
          <p className="text-slate-500 text-xs mt-0.5 text-center">{tagline}</p>
        </div>

        <div className="bg-slate-900 rounded-2xl border border-slate-800 p-6">

          {/* First-run setup: create the administrator account */}
          {needsSetup === null ? (
            <div className="text-center text-slate-500 text-sm py-6">Loading…</div>
          ) : needsSetup ? (
            <div>
              <div className="mb-4">
                <h2 className="text-white font-semibold text-sm">Welcome — let's set up your system</h2>
                <p className="text-slate-500 text-xs mt-1">
                  No accounts exist yet. Create the administrator account below. This first account
                  has full super-admin access; you can add more users afterward.
                </p>
              </div>
              <form onSubmit={submitSetup} className="space-y-3">
                <input className={inp} placeholder="Your name" value={setupName}
                  onChange={e => setSetupName(e.target.value)} required />
                <input className={inp} type="email" placeholder="Admin email" value={email}
                  onChange={e => setEmail(e.target.value)} required />
                <input className={inp} type="password" placeholder="Password (min 8 characters)"
                  value={password} onChange={e => setPw(e.target.value)} required />
                <input className={inp} type="password" placeholder="Confirm password"
                  value={setupConfirm} onChange={e => setSetupConfirm(e.target.value)} required />
                {error && <p className="text-red-400 text-xs">{error}</p>}
                <button type="submit" disabled={loading}
                  className="w-full bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-sm rounded-lg py-2">
                  {loading ? 'Creating…' : 'Create administrator account'}
                </button>
              </form>
            </div>
          ) : (
          <div>

          {/* Staff / Patron tabs — only shown when both are enabled */}
          {showTabs && (
            <div className="flex gap-1 bg-slate-800 p-1 rounded-lg mb-5">
              <button
                onClick={() => { setTab('staff'); setError('') }}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-sm rounded transition-colors ${tab === 'staff' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
              >
                <Users size={13} /> {staffLabel}
              </button>
              <button
                onClick={() => { setTab('patron'); setError('') }}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-sm rounded transition-colors ${tab === 'patron' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
              >
                <CreditCard size={13} /> {patronLabel}
              </button>
            </div>
          )}

          {/* Welcome message */}
          {tab === 'staff'  && staffWelcome  && <p className="text-slate-400 text-xs mb-4 text-center">{staffWelcome}</p>}
          {tab === 'patron' && patronWelcome && <p className="text-slate-400 text-xs mb-4 text-center">{patronWelcome}</p>}

          {error && (
            <div className="mb-4 px-3 py-2 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          {/* ── Staff tab ── */}
          {tab === 'staff' && (
            <>
              {/* OIDC buttons */}
              {(oidcProviders.length > 0 || saml) && (
                <div className="space-y-2 mb-4">
                  {saml && (
                    <button onClick={() => { window.location.href = '/api/auth/saml/login' }}
                      className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-slate-700 rounded-lg text-slate-300 text-sm hover:bg-slate-800 transition-colors">
                      Sign in with {saml.label}
                    </button>
                  )}
                  {oidcProviders.map(p => (
                    <button key={p.key} onClick={() => oidcLogin(p.key)}
                      className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-slate-700 rounded-lg text-slate-300 text-sm hover:bg-slate-800 transition-colors">
                      Sign in with {p.label}
                    </button>
                  ))}
                  <div className="flex items-center gap-2 my-3">
                    <div className="flex-1 h-px bg-slate-800" />
                    <span className="text-slate-600 text-xs">or with email</span>
                    <div className="flex-1 h-px bg-slate-800" />
                  </div>
                </div>
              )}

              {/* Email/password form */}
              <form onSubmit={submitStaff} className="space-y-3">
                <div>
                  <label className="text-slate-400 text-xs mb-1 block">Email</label>
                  <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                    required className={inp} placeholder="you@example.com" autoFocus />
                </div>
                <div>
                  <label className="text-slate-400 text-xs mb-1 block">Password</label>
                  <input type="password" value={password} onChange={e => setPw(e.target.value)}
                    required className={inp} />
                </div>
                <button type="submit" disabled={loading}
                  className="w-full py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                  {loading ? 'Signing in…' : `Sign in`}
                </button>
              </form>
            </>
          )}

          {/* ── Patron tab ── */}
          {tab === 'patron' && (
            <form onSubmit={submitPatron} className="space-y-3">
              <div>
                <label className="text-slate-400 text-xs mb-1 block">Library card number</label>
                <input value={barcode} onChange={e => setBarcode(e.target.value)}
                  required className={inp} placeholder="Enter your barcode" autoFocus
                  inputMode="numeric" />
              </div>
              <div>
                <label className="text-slate-400 text-xs mb-1 block">PIN</label>
                <input type="password" value={pin} onChange={e => setPin(e.target.value)}
                  required className={inp} placeholder="Library PIN"
                  inputMode="numeric" />
              </div>
              <button type="submit" disabled={loading || !sip2Enabled}
                className="w-full py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                {loading ? 'Signing in…' : 'Sign in with library card'}
              </button>
              {!loadingProviders && !sip2Enabled && (
                <p className="text-amber-400 text-xs text-center">
                  Library card login is not yet configured. Contact your administrator.
                </p>
              )}
            </form>
          )}

          {/* Footer */}
          <div className="mt-4 flex items-center justify-between text-xs text-slate-600">
            {branding?.terms_url
              ? <a href={branding.terms_url} target="_blank" rel="noopener noreferrer" className="hover:text-slate-400">Terms</a>
              : <span />}
            {branding?.contact_email
              ? <a href={`mailto:${branding.contact_email}`} className="hover:text-slate-400">{branding.contact_email}</a>
              : <span>Contact your administrator for access</span>}
          </div>
          </div>
          )}
        </div>

        {branding?.show_powered_by && (
          <p className="text-center text-slate-700 text-xs mt-4">Powered by OpenOptOut</p>
        )}
      </div>
    </div>
  )
}
