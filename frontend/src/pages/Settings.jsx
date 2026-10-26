import { useEffect, useState, useRef } from 'react'
import {
  Palette, Mail, CalendarClock, Database, AlertTriangle, Shield, Bot, Info, Globe, Lock,
  Check, X, RefreshCw, TestTube, Eye, EyeOff, ChevronDown,
  Download, Trash2, Upload, Sun, Moon, Monitor, Compass, Play, Pause,
  Clock, Zap, RotateCcw, Users, Puzzle, Ban, ShieldCheck, Star, Plus,
  Key, Smartphone, Fingerprint, ShieldAlert, Copy
} from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'
import { performWebAuthnRegister } from '../utils/webauthn'
import { tx, txn, txr } from '../i18n/tx'
import { fmtDate, fmtDateTime, fmtNumber, formatLocale, regional, setRegional } from '../i18n/format'
import { SecretKeyGeneratorPanel } from '../components/SecretKeyBanner'
import { detailText } from '../errorMessage'
import Field, { inputCls as inp, labelCls } from '../components/Field'

// ── Shared ────────────────────────────────────────────────────────────────────

// Sections unlock their admin controls when userRole is 'super_admin'. The
// Settings page passes that for managers too when they hold the section's
// permission (see sectionRole below).
function Section({ icon: Icon, title, description, children, adminOnly, userRole }) {
  const locked = adminOnly && userRole !== 'super_admin'
  return (
    <div className={`bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden mb-4 ${locked ? 'opacity-60' : ''}`}>
      <div className="px-5 py-4 border-b border-slate-700/50 flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          <Icon size={15} className="text-shield-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-slate-200 text-sm font-medium">{title}</p>
            {description && <p className="text-slate-500 text-xs mt-0.5">{description}</p>}
          </div>
        </div>
        {locked && <span className="text-xs text-slate-600 border border-slate-700 px-2 py-0.5 rounded-sm">{tx("admin only")}</span>}
      </div>
      <div className={`px-5 py-4 space-y-4 ${locked ? 'pointer-events-none select-none' : ''}`}>
        {children}
      </div>
    </div>
  )
}

function SaveButton({ saving, saved, onClick, disabled }) {
  return (
    <button onClick={onClick} disabled={saving || disabled}
      className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
        saved ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800'
              : 'bg-shield-600 hover:bg-shield-700 text-white disabled:opacity-40'
      }`}>
      {saving ? <RefreshCw size={12} className="animate-spin" /> : saved ? <Check size={12} /> : null}
      {saving ? tx("Saving…") : saved ? tx("Saved") : tx("Save")}
    </button>
  )
}

function PasswordField({ label, hint, value, onChange, isSet }) {
  const [show, setShow] = useState(false)
  return (
    <Field label={label} hint={hint}>
      <div className="relative">
        <input type={show ? 'text' : 'password'} value={value} onChange={e => onChange(e.target.value)}
          placeholder={isSet ? tx("••••••••  (blank = keep current)") : tx("Enter password…")}
          className={`${inp} pe-9`} />
        <button type="button" onClick={() => setShow(s => !s)}
          className="absolute end-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
          {show ? <EyeOff size={13} /> : <Eye size={13} />}
        </button>
      </div>
    </Field>
  )
}

// ── Appearance ────────────────────────────────────────────────────────────────
const THEMES = [
  { value: 'dark', label: tx("Dark"), icon: Moon },
  { value: 'dark-ada', label: tx("Dark (ADA Compliant)"), icon: Eye },
  { value: 'light', label: tx("Light"), icon: Sun },
  { value: 'light-ada', label: tx("Light (ADA Compliant)"), icon: Eye },
  { value: 'space', label: tx("Space Explorer"), icon: Compass },
  { value: 'space-ada', label: tx("Space Explorer (ADA Compliant)"), icon: Eye },
  { value: 'system', label: tx("System"), icon: Monitor },
]
const ACCENT_PRESETS = [
  { color: '#6366f1', label: tx("Indigo") }, { color: '#0ea5e9', label: tx("Sky") },
  { color: '#10b981', label: tx("Emerald") }, { color: '#f59e0b', label: tx("Amber") },
  { color: '#ef4444', label: tx("Red") }, { color: '#8b5cf6', label: tx("Violet") },
]

function AppearanceSection({ initial, onSaved, userRole }) {
  const [form, setForm] = useState(initial)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const iconRef = useRef()

  const save = async () => {
    setSaving(true)
    try {
      await api.patch('/settings/appearance', form)
      setSaved(true); setTimeout(() => setSaved(false), 2000); onSaved(form)
    } finally { setSaving(false) }
  }

  const handleIconUpload = e => {
    const file = e.target.files?.[0]; if (!file) return
    const reader = new FileReader()
    reader.onload = ev => setForm(f => ({ ...f, app_icon_url: ev.target.result }))
    reader.readAsDataURL(file)
  }

  return (
    <Section icon={Palette} title={tx("Appearance")} description={tx("Customize how the app looks for everyone")} adminOnly userRole={userRole}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label={tx("App name")}>
          <input value={form.app_name ?? ''} onChange={e => setForm(f => ({...f, app_name: e.target.value}))}
            placeholder="OpenOptOut" className={inp} />
        </Field>
        <Field label={tx("App icon")} hint={tx("PNG or SVG shown in sidebar")}>
          <div className="flex items-center gap-2">
            {form.app_icon_url && <img src={form.app_icon_url} alt="icon" className="w-8 h-8 rounded-sm object-cover border border-slate-600" />}
            <button onClick={() => iconRef.current?.click()}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors">
              <Upload size={11} />{" "}{tx("Upload")}
            </button>
            {form.app_icon_url && <button onClick={() => setForm(f => ({...f, app_icon_url: null}))} className="text-slate-600 hover:text-red-400"><X size={13} /></button>}
            <input ref={iconRef} type="file" accept="image/*" className="hidden" onChange={handleIconUpload} />
          </div>
        </Field>
      </div>
      <Field label={tx("Theme")}>
        <div className="flex gap-2 flex-wrap">
          {THEMES.map(t => (
            <button key={t.value} onClick={() => setForm(f => ({...f, theme: t.value}))}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border transition-colors ${
                form.theme === t.value ? 'bg-shield-600/20 border-shield-600 text-shield-300' : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-600'
              }`}>
              <t.icon size={13} />{t.label}
            </button>
          ))}
        </div>
      </Field>
      <Field label={tx("Accent color")}>
        <div className="flex items-center gap-2 flex-wrap">
          {ACCENT_PRESETS.map(p => (
            <button key={p.color} onClick={() => setForm(f => ({...f, accent_color: p.color}))} title={p.label}
              className={`w-7 h-7 rounded-full border-2 transition-all ${form.accent_color === p.color ? 'border-white scale-110' : 'border-transparent hover:scale-105'}`}
              style={{ background: p.color }} />
          ))}
          <div className="flex items-center gap-1.5 ms-1">
            <input type="color" value={form.accent_color ?? '#6366f1'} onChange={e => setForm(f => ({...f, accent_color: e.target.value}))}
              className="w-7 h-7 rounded-sm cursor-pointer bg-transparent border-0" />
            <span className="text-slate-500 text-xs font-mono">{form.accent_color}</span>
          </div>
        </div>
      </Field>
      <div className="flex justify-end pt-1"><SaveButton saving={saving} saved={saved} onClick={save} /></div>
    </Section>
  )
}

// ── Regional formats ──────────────────────────────────────────────────────────

// How dates, times and numbers look for everyone (default: United States).
// Each person still reads month and day names in their own language.
function RegionalSection({ userRole }) {
  const isAdmin = userRole === 'super_admin'
  const [form, setForm] = useState(null)
  const [regions, setRegions] = useState([])
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.get('/settings/regional').then(r => {
      const { regions: list, ...rest } = r.data
      setForm(rest); setRegions(list || [])
    }).catch(() => {})
  }, [])
  if (!form) return null

  let names = null
  try { names = new Intl.DisplayNames([formatLocale()], { type: 'region' }) } catch { /* codes only */ }
  const regionName = c => { try { return names?.of(c) || c } catch { return c } }
  let zones = []
  try { zones = Intl.supportedValuesOf('timeZone') } catch { /* free text */ }

  // Preview with the choices on screen, then put the saved ones back.
  const preview = (() => {
    const before = regional()
    setRegional(form)
    const sample = new Date(Date.UTC(2026, 9, 11, 20, 5))
    const out = { date: fmtDate(sample), dateTime: fmtDateTime(sample), number: fmtNumber(1234567.5) }
    setRegional(before)
    return out
  })()

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const save = async () => {
    setSaving(true); setMsg('')
    try {
      const { data } = await api.patch('/settings/regional', form)
      setRegional(data); setForm(data)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      setMsg(tx("Saved. Refresh the page to see it everywhere."))
    } catch (e) { setMsg(detailText(e) || tx("Couldn't save that.")) }
    finally { setSaving(false) }
  }
  const sel = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-hidden focus:border-shield-500"

  return (
    <Section icon={Globe} title={tx("Regional formats")}
      description={tx("How dates, times and numbers look for everyone. People still see month and day names in their own language.")}
      adminOnly userRole={userRole}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor="rf-region" className={labelCls}>{tx("Country or region")}</label>
          <select id="rf-region" className={sel} value={form.region} onChange={set('region')} disabled={!isAdmin}>
            {regions.map(c => <option key={c} value={c}>{regionName(c)}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="rf-clock" className={labelCls}>{tx("Clock")}</label>
          <select id="rf-clock" className={sel} value={form.hour_cycle} onChange={set('hour_cycle')} disabled={!isAdmin}>
            <option value="auto">{tx("Usual for the region")}</option>
            <option value="h12">{tx("12-hour (3:05 PM)")}</option>
            <option value="h23">{tx("24-hour (15:05)")}</option>
          </select>
        </div>
        <div>
          <label htmlFor="rf-week" className={labelCls}>{tx("Weeks start on")}</label>
          <select id="rf-week" className={sel} value={form.week_start} onChange={set('week_start')} disabled={!isAdmin}>
            <option value="auto">{tx("Usual for the region")}</option>
            <option value="sun">{tx("Sunday")}</option>
            <option value="mon">{tx("Monday")}</option>
            <option value="sat">{tx("Saturday")}</option>
          </select>
        </div>
        <div>
          <label htmlFor="rf-digits" className={labelCls}>{tx("Digits")}</label>
          <select id="rf-digits" className={sel} value={form.digits} onChange={set('digits')} disabled={!isAdmin}>
            <option value="latn">{tx("0–9 in every language")}</option>
            <option value="native">{tx("Each language's own digits")}</option>
          </select>
        </div>
        <div className="sm:col-span-2">
          <label htmlFor="rf-tz" className={labelCls}>{tx("Time zone for times on screen")}</label>
          <input id="rf-tz" className={inp} list="rf-tz-list" value={form.time_zone} onChange={set('time_zone')} disabled={!isAdmin}
            placeholder={tx("Leave empty to use each person's own device")} dir="ltr" />
          <datalist id="rf-tz-list">{zones.map(z => <option key={z} value={z} />)}</datalist>
          <p className="text-slate-500 text-xs mt-1">{tx("Leave empty to use each person's own device. Example: America/Chicago.")}</p>
        </div>
      </div>
      <div className="rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2.5 text-sm" aria-live="polite">
        <p className="text-slate-400 text-xs mb-1">{tx("Preview")}</p>
        <p className="text-slate-200">{preview.date} · {preview.dateTime} · {preview.number}</p>
      </div>
      {msg && <p role="status" className="text-slate-300 text-xs">{msg}</p>}
      {isAdmin && <div className="flex justify-end pt-1"><SaveButton saving={saving} saved={saved} onClick={save} /></div>}
    </Section>
  )
}

// ── Email ─────────────────────────────────────────────────────────────────────

// OAuth-connected accounts for the shared/admin email identity. One account is
// "active" (used for actual sends — core/optout_engine.py reads this instead
// of a hardcoded account_ref); the rest just sit connected, e.g. for testing
// sending from a second account without disconnecting the first.
function ConnectedAccounts({ currentProvider, onChanged }) {
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [addProvider, setAddProvider] = useState(currentProvider && currentProvider !== 'smtp' ? currentProvider : 'gmail')
  const [client, setClient] = useState({ client_id: '', client_secret: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = () => {
    setLoading(true)
    api.get('/email-oauth/accounts').then(r => setAccounts(r.data.accounts || []))
      .catch(() => setAccounts([])).finally(() => setLoading(false))
  }
  useEffect(load, [])

  const nextAccountRef = () => {
    let n = 2
    const used = new Set(accounts.map(a => a.account_ref))
    while (used.has(`account-${n}`)) n++
    return `account-${n}`
  }

  const activate = async (ref) => {
    setBusy(true); setError('')
    try { await api.post(`/email-oauth/accounts/${ref}/activate`); load(); onChanged?.() }
    catch (e) { setError(detailText(e) || tx("Could not switch accounts")) }
    finally { setBusy(false) }
  }

  const disconnect = async (ref) => {
    setBusy(true); setError('')
    try { await api.delete(`/email-oauth/accounts/${ref}`); load(); onChanged?.() }
    catch (e) { setError(detailText(e) || tx("Could not disconnect")) }
    finally { setBusy(false) }
  }

  const connect = async () => {
    setBusy(true); setError('')
    const ref = nextAccountRef()
    const defaultRedirect = typeof window !== 'undefined'
      ? `${window.location.origin}/api/email-oauth/callback` : ''
    try {
      // A provider only needs its client_id/secret registered once — one
      // Google/Microsoft OAuth client can authorize several accounts, so
      // leaving these blank just reuses whatever's already registered.
      if (client.client_id && client.client_secret) {
        await api.post('/email-oauth/client', {
          provider_key: addProvider, client_id: client.client_id,
          client_secret: client.client_secret, redirect_uri: defaultRedirect,
        })
      }
      const r = await api.post('/email-oauth/begin', { provider_key: addProvider, account_ref: ref })
      const popup = window.open(r.data.authorize_url, 'oauth', 'width=520,height=680')
      const iv = setInterval(async () => {
        try {
          const st = await api.get('/email-oauth/accounts')
          if ((st.data.accounts || []).some(a => a.account_ref === ref)) {
            clearInterval(iv)
            setAdding(false); setClient({ client_id: '', client_secret: '' })
            load(); onChanged?.()
            if (popup && !popup.closed) popup.close()
          }
        } catch { /* keep polling */ }
      }, 2500)
      setTimeout(() => clearInterval(iv), 300000)
    } catch (e) {
      setError(detailText(e) || tx("Could not start the connect flow"))
    } finally { setBusy(false) }
  }

  return (
    <div>
      <p className="text-slate-400 text-xs font-medium mb-2 uppercase tracking-wide">{tx("Accounts you've signed in with")}</p>
      {error && <div className="mb-2 px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs">{error}</div>}
      {loading ? (
        <p className="text-slate-500 text-xs">{tx("Loading…")}</p>
      ) : accounts.length === 0 ? (
        <p className="text-slate-500 text-xs mb-2">{tx("Nothing signed in yet. Signing in with Google or Microsoft below is the safest choice. You can also use a mail server and app password further down.")}</p>
      ) : (
        <div className="space-y-1.5 mb-2">
          {accounts.map(a => (
            <div key={a.account_ref} className={`flex items-center justify-between gap-2 px-3 py-2 rounded-lg border ${
              a.active ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700 bg-slate-900'}`}>
              <div className="flex items-center gap-2 min-w-0">
                {a.active
                  ? <Star size={13} className="text-shield-400 shrink-0" />
                  : <span className="w-[13px] shrink-0" />}
                <span className="text-slate-200 text-sm capitalize truncate">{a.provider_key}</span>
                <span className="text-slate-500 text-xs truncate">({a.account_ref})</span>
                {a.expired && <span className="text-amber-400 text-xs shrink-0">{tx("sign-in needs renewing (happens automatically next time)")}</span>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {!a.active && (
                  <button onClick={() => activate(a.account_ref)} disabled={busy}
                    className="text-xs text-slate-400 hover:text-shield-300 disabled:opacity-40">{tx("Make active")}</button>
                )}
                <button onClick={() => disconnect(a.account_ref)} disabled={busy}
                  className="text-slate-500 hover:text-red-400 disabled:opacity-40" title={tx("Disconnect")}>
                  <X size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {!adding ? (
        <button onClick={() => { setAdding(true); setError('') }} className="flex items-center gap-1.5 text-shield-400 hover:text-shield-300 text-xs">
          <Plus size={12} />{" "}{tx("Connect {v} account", { v: accounts.length ? 'another' : 'an' })}
        </button>
      ) : (
        <div className="px-3 py-2.5 rounded-lg border border-slate-700 bg-slate-800/40">
          <div className="flex items-center gap-2 mb-2">
            <select className={inp} value={addProvider} onChange={e => setAddProvider(e.target.value)}>
              <option value="gmail">{tx("Gmail / Google Workspace")}</option>
              <option value="outlook">{tx("Outlook / Microsoft 365")}</option>
              <option value="yahoo">{"Yahoo"}</option>
            </select>
          </div>
          <p className="text-slate-500 text-xs mb-2">
            {tx("If this provider already has a client registered, leave these blank to reuse it — one client can authorize several accounts. Otherwise, enter it (from the provider's developer console) to register one now.")}
          </p>
          <div className="space-y-2 mb-2">
            <input className={inp} placeholder={tx("Client ID (optional if already registered)")} value={client.client_id}
              onChange={e => setClient({ ...client, client_id: e.target.value })} />
            <input className={inp} type="password" placeholder={tx("Client secret (optional if already registered)")} value={client.client_secret}
              onChange={e => setClient({ ...client, client_secret: e.target.value })} />
          </div>
          <div className="flex items-center gap-2">
            <button onClick={connect} disabled={busy}
              className="px-3 py-1.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-xs rounded-lg">
              {busy ? tx("Connecting…") : tx("Connect")}
            </button>
            <button onClick={() => { setAdding(false); setError('') }} className="text-slate-500 hover:text-slate-300 text-xs">{tx("Cancel")}</button>
          </div>
        </div>
      )}
    </div>
  )
}

const EMAIL_PRESETS = [
  { key: 'gmail',      label: 'Gmail' },
  { key: 'outlook',    label: 'Outlook' },
  { key: 'fastmail',   label: 'Fastmail' },
  { key: 'protonmail', label: 'ProtonMail' },
  { key: 'custom',     label: tx("Custom") },
]

function EmailSection({ initial, userRole }) {
  const [form, setForm]     = useState({})
  const [imapPw, setImapPw] = useState('')
  const [smtpPw, setSmtpPw] = useState('')
  const [presets, setPresets] = useState({})
  const [note, setNote]     = useState('')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)
  const [gracePeriod, setGracePeriod] = useState(initial.grace_period || null)
  const isAdmin = userRole === 'super_admin'

  useEffect(() => {
    if (!isAdmin) return
    api.get('/settings/email/presets').then(r => setPresets(r.data))
    setGracePeriod(initial.grace_period || null)
    setForm({
      mode: initial.mode ?? 'shared',
      preset: initial.preset, imap_host: initial.imap_host ?? '',
      imap_port: initial.imap_port ?? 993, imap_user: initial.imap_user ?? '',
      imap_ssl: initial.imap_ssl ?? true, imap_folder: initial.imap_folder ?? 'INBOX',
      poll_interval_minutes: initial.poll_interval_minutes ?? 15,
      smtp_host: initial.smtp_host ?? '', smtp_port: initial.smtp_port ?? 587,
      smtp_user: initial.smtp_user ?? '', smtp_tls: initial.smtp_tls ?? true,
      from_name: initial.from_name ?? tx("OpenOptOut Removals"), from_email: initial.from_email ?? '',
    })
  }, [isAdmin, initial])

  const applyPreset = key => {
    const p = presets[key] ?? {}
    setNote(p.note ?? '')
    setForm(f => ({
      ...f, preset: key,
      ...(key !== 'custom' ? {
        imap_host: p.imap_host ?? f.imap_host, imap_port: p.imap_port ?? f.imap_port, imap_ssl: p.imap_ssl ?? f.imap_ssl,
        smtp_host: p.smtp_host ?? f.smtp_host, smtp_port: p.smtp_port ?? f.smtp_port, smtp_tls: p.smtp_tls ?? f.smtp_tls,
      } : {}),
    }))
  }

  const dismissGracePeriod = async () => {
    try {
      await api.post('/settings/email/grace-period/dismiss')
      setGracePeriod(prev => prev ? { ...prev, active: false } : null)
    } catch (e) {
      console.error(e)
    }
  }

  const extendGracePeriod = async () => {
    try {
      const { data } = await api.post('/settings/email/grace-period/extend?extra_days=30')
      setGracePeriod(prev => prev ? { ...prev, days_remaining: (prev.days_remaining || 0) + 30, active: true } : null)
    } catch (e) {
      console.error(e)
    }
  }

  const save = async () => {
    setSaving(true); setTestResult(null)
    try {
      await api.patch('/settings/email', { ...form, imap_password: imapPw || undefined, smtp_password: smtpPw || undefined })
      setSaved(true); setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }

  const test = async () => {
    setTesting(true); setTestResult(null)
    try {
      const { data } = await api.post('/settings/email/test')
      setTestResult(data)
    } catch (err) {
      setTestResult({ connected: false, errors: [detailText(err) ?? tx("Connection failed")] })
    } finally { setTesting(false) }
  }

  return (
    <Section icon={Mail} title={tx("Email configuration")}
      description={tx("One shared inbox for all opt-out requests and confirmation matching")}
      adminOnly userRole={userRole}>
      {!isAdmin ? (
        <p className="text-slate-500 text-sm">{tx("Email settings are managed by your administrator.")}</p>
      ) : (
        <>
          <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border ${
            initial.connected ? 'bg-emerald-900/20 text-emerald-400 border-emerald-800' : 'bg-slate-900 text-slate-500 border-slate-700'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${initial.connected ? 'bg-emerald-400' : 'bg-slate-600'}`} />
            {initial.connected
              ? (initial.provider_connected ? tx("Connected via {provider}", { provider: initial.provider }) : tx("Email connected"))
              : tx("Not configured")}
          </div>

          {gracePeriod?.active && (
            <div className="p-3.5 bg-indigo-950/40 border border-indigo-700/60 rounded-xl text-xs space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 text-indigo-300 font-medium">
                  <Clock size={14} className="text-indigo-400" />
                  <span>{tx("Dual-Inbox Grace Period Active (Item 11)")}</span>
                </div>
                <span className="bg-indigo-900/60 text-indigo-200 px-2 py-0.5 rounded-sm text-[11px] font-mono">
                  {tx("{days_remaining} days remaining", { days_remaining: gracePeriod.days_remaining })}
                </span>
              </div>
              <p className="text-slate-300 leading-relaxed">
                {tx("Background monitoring preserves dual-inbox checks during mode and mailbox transitions. Currently polling the previous mailbox (")}<strong>{gracePeriod.previous_inbox || tx("previous account")}</strong>{tx(") alongside the primary inbox to catch delayed broker confirmation replies.")}
              </p>
              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={extendGracePeriod}
                  className="px-2.5 py-1 bg-indigo-800/50 hover:bg-indigo-800 border border-indigo-600 rounded-sm text-indigo-200 transition-colors"
                >
                  {tx("Extend +30 Days")}
                </button>
                <button
                  type="button"
                  onClick={dismissGracePeriod}
                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-sm text-slate-300 transition-colors"
                >
                  {tx("Dismiss Grace Period")}
                </button>
              </div>
            </div>
          )}

          <div className="p-3 rounded-lg border border-slate-700 bg-slate-900/60 text-xs text-slate-300">
            <div className="font-medium text-slate-200 mb-0.5">{tx("This is the system inbox")}</div>
            {txr("It sends sign-in links, status updates and admin alerts only. Opt-outs are sent from each family's own inbox, connected under <0>Email inboxes</0>.", [<a href="/inboxes" className="text-shield-400 underline" />])}</div>

          <ConnectedAccounts currentProvider={initial.provider} onChanged={() => { /* status badge refreshes on next page load; accounts list refreshes itself */ }} />

          <Field label={tx("Provider")}>
            <div className="flex gap-1.5 flex-wrap">
              {EMAIL_PRESETS.map(p => (
                <button key={p.key} onClick={() => applyPreset(p.key)}
                  className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                    form.preset === p.key ? 'bg-shield-600/20 border-shield-600 text-shield-300' : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-600'
                  }`}>{p.label}</button>
              ))}
            </div>
            {note && <div className="mt-2 px-3 py-2 bg-amber-900/20 border border-amber-800 rounded-lg text-amber-300 text-xs">{note}</div>}
          </Field>

          {/* IMAP */}
          <div>
            <p className="text-slate-400 text-xs font-medium mb-2 uppercase tracking-wide">{tx("IMAP — incoming confirmations")}</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="col-span-2"><Field label={tx("Host")}><input value={form.imap_host ?? ''} onChange={e => setForm(f=>({...f,imap_host:e.target.value}))} placeholder="imap.gmail.com" className={inp}/></Field></div>
              <Field label={tx("Port")}><input type="number" value={form.imap_port ?? 993} onChange={e => setForm(f=>({...f,imap_port:parseInt(e.target.value)}))} className={inp}/></Field>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <Field label={tx("Username / email")}><input value={form.imap_user ?? ''} onChange={e => setForm(f=>({...f,imap_user:e.target.value}))} placeholder="removals@example.com" className={inp}/></Field>
              <PasswordField label={tx("Password / App Password")} value={imapPw} onChange={setImapPw} isSet={initial.imap_password_set}
                hint={form.preset === 'gmail' ? tx("Use a Gmail App Password") : undefined} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <Field label={tx("Folder")}><input value={form.imap_folder ?? 'INBOX'} onChange={e => setForm(f=>({...f,imap_folder:e.target.value}))} placeholder="INBOX" className={inp}/></Field>
              <Field label={tx("Poll every (minutes)")}><input type="number" min="5" max="60" value={form.poll_interval_minutes ?? 15} onChange={e => setForm(f=>({...f,poll_interval_minutes:parseInt(e.target.value)}))} className={inp}/></Field>
            </div>
            <label className="flex items-center gap-2 mt-2 cursor-pointer">
              <input type="checkbox" checked={form.imap_ssl ?? true} onChange={e => setForm(f=>({...f,imap_ssl:e.target.checked}))} className="w-3.5 h-3.5 rounded-sm accent-shield-500"/>
              <span className="text-slate-400 text-sm">{tx("Use SSL/TLS")}</span>
            </label>
          </div>

          {/* SMTP */}
          <div>
            <p className="text-slate-400 text-xs font-medium mb-2 uppercase tracking-wide">{tx("SMTP — outgoing opt-out emails")}</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="col-span-2"><Field label={tx("Host")}><input value={form.smtp_host ?? ''} onChange={e => setForm(f=>({...f,smtp_host:e.target.value}))} placeholder="smtp.gmail.com" className={inp}/></Field></div>
              <Field label={tx("Port")}><input type="number" value={form.smtp_port ?? 587} onChange={e => setForm(f=>({...f,smtp_port:parseInt(e.target.value)}))} className={inp}/></Field>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <Field label={tx("Username")}><input value={form.smtp_user ?? ''} onChange={e => setForm(f=>({...f,smtp_user:e.target.value}))} placeholder="removals@example.com" className={inp}/></Field>
              <PasswordField label={tx("Password / App Password")} value={smtpPw} onChange={setSmtpPw} isSet={initial.smtp_password_set}/>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <Field label={tx("\"From\" name")}><input value={form.from_name ?? ''} onChange={e => setForm(f=>({...f,from_name:e.target.value}))} placeholder={tx("OpenOptOut Removals")} className={inp}/></Field>
              <Field label={tx("\"From\" email")}><input type="email" value={form.from_email ?? ''} onChange={e => setForm(f=>({...f,from_email:e.target.value}))} placeholder="removals@example.com" className={inp}/></Field>
            </div>
            <label className="flex items-center gap-2 mt-2 cursor-pointer">
              <input type="checkbox" checked={form.smtp_tls ?? true} onChange={e => setForm(f=>({...f,smtp_tls:e.target.checked}))} className="w-3.5 h-3.5 rounded-sm accent-shield-500"/>
              <span className="text-slate-400 text-sm">{tx("Use STARTTLS")}</span>
            </label>
          </div>

          {testResult && (
            <div className={`px-3 py-2.5 rounded-lg border text-sm ${testResult.connected ? 'bg-emerald-900/20 border-emerald-800 text-emerald-300' : 'bg-red-900/20 border-red-800 text-red-300'}`}>
              {testResult.connected ? <span className="flex items-center gap-1.5"><Check size={13}/>{tx("IMAP and SMTP connected successfully")}</span> : (
                <div><p className="flex items-center gap-1.5 mb-1"><X size={13}/>{tx("Connection failed")}</p>
                  {testResult.errors?.map((e,i) => <p key={i} className="text-xs opacity-80 ms-4">{e}</p>)}</div>
              )}
            </div>
          )}

          <div className="flex items-center justify-between pt-1">
            <button onClick={test} disabled={testing || !initial.imap_password_set}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors disabled:opacity-40">
              {testing ? <RefreshCw size={12} className="animate-spin"/> : <TestTube size={12}/>}
              {testing ? tx("Testing…") : tx("Test connection")}
            </button>
            <SaveButton saving={saving} saved={saved} onClick={save}/>
          </div>
        </>
      )}
    </Section>
  )
}

// ── Scheduler ─────────────────────────────────────────────────────────────────
const TIMEZONES = [
  'America/New_York','America/Chicago','America/Denver','America/Los_Angeles',
  'America/Phoenix','America/Anchorage','Pacific/Honolulu',
  'Europe/London','Europe/Paris','Europe/Berlin','Asia/Tokyo','Asia/Shanghai',
  'Australia/Sydney','UTC',
]

function SchedulerSection({ initial, memberConfigs, onMemberConfigUpdate, userRole, onSaved }) {
  const [form, setForm]     = useState(initial)
  const [status, setStatus] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)
  const [triggering, setTriggering] = useState({})
  const isAdmin = userRole === 'super_admin'
  const isParent = userRole === 'parent' || userRole === 'manager' || isAdmin

  useEffect(() => {
    if (!isAdmin) return
    api.get('/scheduler/status').then(r => setStatus(r.data)).catch(() => {})
  }, [isAdmin])

  const save = async () => {
    setSaving(true)
    try {
      await api.patch('/settings/scheduler', form)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      onSaved(form)
      api.get('/scheduler/status').then(r => setStatus(r.data))
    } finally { setSaving(false) }
  }

  const trigger = async job => {
    setTriggering(t => ({...t, [job]: true}))
    try {
      await api.post(`/scheduler/trigger/${job}`)
    } finally {
      setTimeout(() => setTriggering(t => ({...t, [job]: false})), 1500)
    }
  }

  const updateMemberLimit = async (memberId, field, value) => {
    try {
      const { data } = await api.patch(`/scheduler/members/${memberId}`, { [field]: value })
      onMemberConfigUpdate(data)
    } catch (e) { console.error(e) }
  }

  return (
    <Section icon={CalendarClock} title={tx("Scheduler")}
      description={tx("Automated opt-out timing and per-member rate limits")}
      adminOnly={false} userRole={userRole}>

      {/* System settings — super_admin only */}
      {isAdmin && (
        <>
          <div className="flex items-center gap-3 mb-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <div onClick={() => setForm(f => ({...f, enabled: !f.enabled}))}
                className={`w-10 h-5 rounded-full transition-colors cursor-pointer relative ${form.enabled ? 'bg-shield-600' : 'bg-slate-700'}`}>
                <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${form.enabled ? 'translate-x-5 rtl:-translate-x-5' : 'translate-x-0.5 rtl:-translate-x-0.5'}`}/>
              </div>
              <span className="text-slate-300 text-sm">{form.enabled ? tx("Scheduler enabled") : tx("Scheduler disabled")}</span>
            </label>
            {status?.running && <span className="text-xs text-emerald-400 border border-emerald-800 bg-emerald-900/20 px-2 py-0.5 rounded-sm">{tx("running")}</span>}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label={tx("Daily run time (server local)")}>
              <input type="time" value={form.run_time ?? '02:00'} onChange={e => setForm(f=>({...f,run_time:e.target.value}))} className={inp}/>
            </Field>
            <Field label={tx("Timezone")}>
              <div className="relative">
                <select value={form.timezone ?? 'America/Chicago'} onChange={e => setForm(f=>({...f,timezone:e.target.value}))}
                  className={`${inp} appearance-none pe-7`}>
                  {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
                </select>
                <ChevronDown size={11} className="absolute end-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"/>
              </div>
            </Field>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label={tx("System max opt-outs / day")} hint={tx("Hard ceiling across all members combined")}>
              <input type="number" min="1" max="200" value={form.max_optouts_per_day ?? 20}
                onChange={e => setForm(f=>({...f,max_optouts_per_day:parseInt(e.target.value)}))} className={inp}/>
            </Field>
            <Field label={tx("Default recheck interval (days)")} hint={tx("How long before re-verifying a confirmed removal")}>
              <input type="number" min="30" max="365" value={form.recheck_interval_days ?? 90}
                onChange={e => setForm(f=>({...f,recheck_interval_days:parseInt(e.target.value)}))} className={inp}/>
            </Field>
          </div>

          {/* ── Which brokers go first ── */}
          <div className="border-t border-slate-700/50 pt-4">
            <label htmlFor="dispatch-order" className="text-slate-400 text-xs font-medium mb-2 block">{tx("Which brokers go first each day")}</label>
            <select id="dispatch-order" value={form.dispatch_order ?? 'aggregators_first'}
              onChange={e => setForm(f => ({...f, dispatch_order: e.target.value}))} className={inp}>
              <option value="aggregators_first">{tx("Aggregators first: brokers that feed other brokers (recommended)")}</option>
              <option value="priority">{tx("By priority (Broker priority page)")}</option>
              <option value="fifo">{tx("Oldest requests first")}</option>
              <option value="easy_first">{tx("Easiest first (quick wins)")}</option>
            </select>
            <p className="text-slate-500 text-xs mt-1">{tx("See which brokers count as aggregators under Admin → Data sharing.")}</p>
          </div>

          {/* ── Job spread mode ── */}
          <div className="border-t border-slate-700/50 pt-4">
            <p className="text-slate-400 text-xs font-medium mb-2">{tx("How to spread opt-out jobs")}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
              {[
                { v: 'burst',       label: tx("Burst"),       desc: tx("All at once at the run time") },
                { v: 'window',      label: tx("Time window"), desc: tx("Spread across a set window (e.g. overnight)") },
                { v: 'rate',        label: tx("Rate limited"), desc: tx("Fixed number per hour, all day") },
                { v: 'distributed', label: tx("Distributed"), desc: tx("Small batches across 24 hours") },
              ].map(m => (
                <button key={m.v} onClick={() => setForm(f => ({...f, spread_mode: m.v}))}
                  className={`flex flex-col items-start px-3 py-2.5 rounded-lg border text-start transition-colors ${
                    (form.spread_mode ?? 'burst') === m.v ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700 hover:border-slate-600'
                  }`}>
                  <span className={`text-sm font-medium ${(form.spread_mode ?? 'burst') === m.v ? 'text-shield-300' : 'text-slate-300'}`}>{m.label}</span>
                  <span className="text-slate-500 text-xs">{m.desc}</span>
                </button>
              ))}
            </div>

            {/* Mode-specific config */}
            {(form.spread_mode ?? 'burst') === 'burst' && (
              <p className="text-slate-500 text-xs bg-slate-900 rounded-lg px-3 py-2">
                {tx("All pending opt-outs (up to the daily cap) are sent at {v}. Simple, but creates a traffic burst that some brokers may flag.", { v: form.run_time ?? '02:00' })}
              </p>
            )}

            {(form.spread_mode ?? 'burst') === 'window' && (
              <div className="bg-slate-900 rounded-lg px-3 py-3 space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <Field label={tx("Start hour (0–23)")}>
                    <input type="number" min="0" max="23" value={form.window_start_hour ?? 22}
                      onChange={e => setForm(f=>({...f,window_start_hour:parseInt(e.target.value)}))} className={inp}/>
                  </Field>
                  <Field label={tx("End hour (0–23)")}>
                    <input type="number" min="0" max="23" value={form.window_end_hour ?? 6}
                      onChange={e => setForm(f=>({...f,window_end_hour:parseInt(e.target.value)}))} className={inp}/>
                  </Field>
                  <Field label={tx("Every N minutes")}>
                    <input type="number" min="5" max="120" value={form.window_interval_minutes ?? 30}
                      onChange={e => setForm(f=>({...f,window_interval_minutes:parseInt(e.target.value)}))} className={inp}/>
                  </Field>
                </div>
                <p className="text-slate-500 text-xs">
                  {tx("The daily cap of {v} is spread evenly across", { v: form.max_optouts_per_day ?? 20 })}
                  {' '}{form.window_start_hour ?? 22}{tx(":00–{v}:00, firing every {v2} min.", { v: form.window_end_hour ?? 6, v2: form.window_interval_minutes ?? 30 })}
                </p>
              </div>
            )}

            {(form.spread_mode ?? 'burst') === 'rate' && (
              <div className="bg-slate-900 rounded-lg px-3 py-3 space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Field label={tx("Max per hour")}>
                    <input type="number" min="1" max="60" value={form.rate_per_hour ?? 5}
                      onChange={e => setForm(f=>({...f,rate_per_hour:parseInt(e.target.value)}))} className={inp}/>
                  </Field>
                  <Field label={tx("Check every N minutes")}>
                    <input type="number" min="5" max="60" value={form.rate_interval_minutes ?? 20}
                      onChange={e => setForm(f=>({...f,rate_interval_minutes:parseInt(e.target.value)}))} className={inp}/>
                  </Field>
                </div>
                <p className="text-slate-500 text-xs">
                  {tx("Sends up to {v}/hour continuously, checking every {v2} min. Still capped at {v3}/day total.", { v: form.rate_per_hour ?? 5, v2: form.rate_interval_minutes ?? 20, v3: form.max_optouts_per_day ?? 20 })}
                </p>
              </div>
            )}

            {(form.spread_mode ?? 'burst') === 'distributed' && (
              <div className="bg-slate-900 rounded-lg px-3 py-3 space-y-3">
                <Field label={tx("Batch interval (minutes)")}>
                  <input type="number" min="15" max="240" value={form.distributed_interval_minutes ?? 60}
                    onChange={e => setForm(f=>({...f,distributed_interval_minutes:parseInt(e.target.value)}))} className={inp}/>
                </Field>
                <p className="text-slate-500 text-xs">
                  {tx("The daily cap of {v} is divided into small batches sent every", { v: form.max_optouts_per_day ?? 20 })}
                  {' '}{form.distributed_interval_minutes ?? 60}{" "}{tx("min around the clock — about {n} per batch.", { n: Math.max(1, Math.floor((form.max_optouts_per_day ?? 20) / Math.max(1, Math.floor(1440 / (form.distributed_interval_minutes ?? 60))))) })}
                </p>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.pause_before_send ?? true} onChange={e => setForm(f=>({...f,pause_before_send:e.target.checked}))} className="w-3.5 h-3.5 rounded-sm accent-shield-500"/>
              <span className="text-slate-300 text-sm">{tx("Pause before sending")}</span>
              <span className="text-slate-600 text-xs">{tx("— get opt-outs ready, but wait for you to press Send")}</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.auto_recheck ?? true} onChange={e => setForm(f=>({...f,auto_recheck:e.target.checked}))} className="w-3.5 h-3.5 rounded-sm accent-shield-500"/>
              <span className="text-slate-300 text-sm">{tx("Ask again automatically")}</span>
              <span className="text-slate-600 text-xs">{tx("— send the request again when its check-again date arrives")}</span>
            </label>
          </div>

          {/* Next run times */}
          {status?.next_runs && Object.keys(status.next_runs).length > 0 && (
            <div className="bg-slate-900 rounded-lg px-3 py-2.5 space-y-1">
              <p className="text-slate-500 text-xs mb-1.5 uppercase tracking-wide">{tx("Next scheduled runs")}</p>
              {Object.entries(status.next_runs).map(([id, time]) => (
                <div key={id} className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">{id.replace('_', ' ')}</span>
                  <span className="text-slate-300 font-mono">{fmtDateTime(time)}</span>
                </div>
              ))}
            </div>
          )}

          {/* Manual triggers */}
          <div>
            <p className="text-slate-500 text-xs mb-2 uppercase tracking-wide">{tx("Manual triggers")}</p>
            <div className="flex gap-2 flex-wrap">
              {[
                { job: 'optout', label: tx("Send opt-outs"), icon: Zap },
                { job: 'email_monitor', label: tx("Poll inbox"), icon: Mail },
                { job: 'recheck', label: tx("Run re-checks"), icon: RotateCcw },
              ].map(({ job, label, icon: Icon }) => (
                <button key={job} onClick={() => trigger(job)} disabled={triggering[job]}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors disabled:opacity-50">
                  {triggering[job] ? <RefreshCw size={11} className="animate-spin"/> : <Icon size={11}/>}
                  {triggering[job] ? tx("Running…") : label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex justify-end"><SaveButton saving={saving} saved={saved} onClick={save}/></div>
          <div className="border-t border-slate-700/50 pt-4"/>
        </>
      )}

      {/* Per-member limits — parents + super_admin */}
      {isParent && memberConfigs.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Users size={13} className="text-slate-500"/>
            <p className="text-slate-400 text-xs font-medium uppercase tracking-wide">{tx("Per-member opt-out limits")}</p>
          </div>
          <div className="space-y-2">
            {memberConfigs.map(mc => (
              <div key={mc.member_id} className="flex items-center gap-3 bg-slate-900 rounded-lg px-3 py-2.5">
                <div className="w-7 h-7 rounded-full bg-shield-600/30 border border-shield-600/40 flex items-center justify-center text-xs font-medium text-shield-300 shrink-0">
                  {mc.member_name.split(' ').map(w=>w[0]).slice(0,2).join('').toUpperCase()}
                </div>
                <span className="text-slate-300 text-sm flex-1 truncate">{mc.member_name}</span>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input type="checkbox" checked={mc.enabled}
                      onChange={e => updateMemberLimit(mc.member_id, 'enabled', e.target.checked)}
                      className="w-3 h-3 rounded-sm accent-shield-500"/>
                    <span className="text-slate-500 text-xs">{tx("active")}</span>
                  </label>
                  <div className="flex items-center gap-1 bg-slate-800 border border-slate-700 rounded-lg px-2 py-1">
                    <input type="number" min="0" max="50"
                      value={mc.max_optouts_per_day ?? ''}
                      onChange={e => updateMemberLimit(mc.member_id, 'max_optouts_per_day', e.target.value ? parseInt(e.target.value) : 0)}
                      placeholder={tx("{effective_limit} (default)", { effective_limit: mc.effective_limit })}
                      className="w-20 bg-transparent text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden text-end"/>
                    <span className="text-slate-600 text-xs">{tx("/day")}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <p className="text-slate-600 text-xs mt-2">{tx("Blank = use system default ({v}/day). Set 0 to pause a member.", { v: initial.max_optouts_per_day ?? 20 })}</p>
        </div>
      )}

      {!isAdmin && !isParent && (
        <p className="text-slate-500 text-sm">{tx("Scheduler settings are managed by your administrator.")}</p>
      )}
    </Section>
  )
}

// ── Data section ──────────────────────────────────────────────────────────────
// ── Data Lifecycle, Retention Schedules & Crypto-Shredding (ISO/IEC 27701 & COPPA) ─────────────
function RetentionPicker({ label, hint, value, onChange, presets, min = 7 }) {
  const isCustom = !presets.includes(Number(value))
  const [customMode, setCustomMode] = useState(isCustom)
  const [customVal, setCustomVal] = useState(String(value || min))

  useEffect(() => {
    if (!presets.includes(Number(value))) {
      setCustomMode(true)
      setCustomVal(String(value))
    } else {
      setCustomMode(false)
    }
  }, [value, presets])

  const selectPreset = (p) => {
    setCustomMode(false)
    onChange(p)
  }

  const selectCustom = () => {
    setCustomMode(true)
    onChange(Math.max(min, parseInt(customVal, 10) || min))
  }

  const onCustomInputChange = (e) => {
    const v = e.target.value
    setCustomVal(v)
    const num = parseInt(v, 10)
    if (!isNaN(num) && num >= min) {
      onChange(num)
    }
  }

  return (
    <div className="py-3 border-b border-slate-700/50">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-2">
        <div>
          <p className="text-slate-200 text-sm font-medium">{label}</p>
          {hint && <p className="text-slate-500 text-xs mt-0.5">{hint}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 shrink-0">
          {presets.map(p => (
            <button
              key={p}
              type="button"
              onClick={() => selectPreset(p)}
              className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
                !customMode && Number(value) === p
                  ? 'bg-shield-600/30 border-shield-500 text-shield-200 font-semibold'
                  : 'bg-slate-900 border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-600'
              }`}
            >
              {p >= 365 ? (p === 365 ? tx("1 year") : tx("{n} years", { n: p / 365 })) : tx("{n} days", { n: p })}
            </button>
          ))}
          <button
            type="button"
            onClick={selectCustom}
            className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
              customMode
                ? 'bg-shield-600/30 border-shield-500 text-shield-200 font-semibold'
                : 'bg-slate-900 border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-600'
            }`}
          >
            {tx("Custom")}
          </button>
        </div>
      </div>
      {customMode && (
        <div className="flex items-center gap-2 mt-2 bg-slate-900/60 p-2 rounded-lg border border-slate-700/50 w-fit">
          <span className="text-xs text-slate-400">{tx("Custom duration:")}</span>
          <input
            type="number"
            min={min}
            value={customVal}
            onChange={onCustomInputChange}
            className="w-20 bg-slate-900 border border-slate-700 rounded-md px-2 py-1 text-xs text-slate-200 text-end"
          />
          <span className="text-xs text-slate-400">{tx("days")}</span>
          <span className="text-xs text-slate-500">{tx("(minimum {min} days)", { min })}</span>
        </div>
      )}
    </div>
  )
}

function DataLifecycleSection({ userRole, initial = {}, onSaved }) {
  const [resetting, setResetting] = useState(false)
  const [msg, setMsg]             = useState('')
  const [log, setLog]             = useState(null)
  const [confirmText, setConfirmText] = useState('')
  const [deleting, setDeleting]   = useState(false)
  const [purging, setPurging]     = useState(false)
  const [purgeStats, setPurgeStats] = useState(null)
  const [savingPolicy, setSavingPolicy] = useState(false)
  const isAdmin = userRole === 'super_admin'

  // Retention schedule state
  const [logsDays, setLogsDays]           = useState(initial.logs_retention_days ?? initial.auto_purge_logs_days ?? 365)
  const [artifactsDays, setArtifactsDays] = useState(initial.artifacts_retention_days ?? 90)
  const [coppaDays, setCoppaDays]         = useState(initial.coppa_children_retention_days ?? 30)
  const [auditDays, setAuditDays]         = useState(initial.audit_access_retention_days ?? 365)

  // Crypto-shredding state
  const [cryptoShredEnabled, setCryptoShredEnabled] = useState(initial.crypto_shredding_enabled ?? true)
  const [cryptoShredPasses, setCryptoShredPasses]   = useState(initial.crypto_shredding_passes ?? 3)
  const [cryptoShredVacuum, setCryptoShredVacuum]   = useState(initial.crypto_shredding_vacuum ?? true)
  const [coppaStrictShredding, setCoppaStrictShredding] = useState(initial.coppa_strict_shredding ?? true)

  useEffect(() => {
    api.get('/privacy/my-access-log').then(r => setLog(r.data)).catch(() => setLog([]))
    if (isAdmin) {
      api.get('/settings').then(r => {
        const p = r.data?.privacy || {}
        if (p.logs_retention_days) setLogsDays(p.logs_retention_days)
        else if (p.auto_purge_logs_days) setLogsDays(p.auto_purge_logs_days)
        if (p.artifacts_retention_days) setArtifactsDays(p.artifacts_retention_days)
        if (p.coppa_children_retention_days) setCoppaDays(p.coppa_children_retention_days)
        if (p.audit_access_retention_days) setAuditDays(p.audit_access_retention_days)
        if (typeof p.crypto_shredding_enabled === 'boolean') setCryptoShredEnabled(p.crypto_shredding_enabled)
        if (typeof p.crypto_shredding_passes === 'number') setCryptoShredPasses(p.crypto_shredding_passes)
        if (typeof p.crypto_shredding_vacuum === 'boolean') setCryptoShredVacuum(p.crypto_shredding_vacuum)
        if (typeof p.coppa_strict_shredding === 'boolean') setCoppaStrictShredding(p.coppa_strict_shredding)
      }).catch(() => {})
    }
  }, [isAdmin])

  const exportMine = async () => {
    try {
      const r = await api.get('/privacy/export', { responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a'); a.href = url; a.download = 'openoptout-my-data.json'; a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch { setMsg(tx("Couldn't download your data. Please try again.")) }
  }

  const saveLifecyclePolicy = async () => {
    setSavingPolicy(true)
    setMsg('')
    try {
      const payload = {
        logs_retention_days: Number(logsDays),
        auto_purge_logs_days: Number(logsDays),
        artifacts_retention_days: Number(artifactsDays),
        coppa_children_retention_days: Number(coppaDays),
        audit_access_retention_days: Number(auditDays),
        crypto_shredding_enabled: Boolean(cryptoShredEnabled),
        crypto_shredding_passes: Number(cryptoShredPasses),
        crypto_shredding_vacuum: Boolean(cryptoShredVacuum),
        coppa_strict_shredding: Boolean(coppaStrictShredding),
      }
      const res = await api.patch('/settings/privacy', payload)
      if (onSaved) onSaved(res.data)
      setMsg(tx("Data lifecycle & retention policy saved successfully."))
    } catch (e) {
      setMsg(detailText(e) || tx("Couldn't save retention settings."))
    } finally {
      setSavingPolicy(false)
    }
  }

  const runPurgeNow = async () => {
    setPurging(true)
    setMsg('')
    setPurgeStats(null)
    try {
      const res = await api.post('/privacy/purge')
      setPurgeStats(res.data?.removed || {})
      setMsg(tx("Retention purge completed successfully."))
    } catch (e) {
      setMsg(detailText(e) || tx("Failed to run retention purge."))
    } finally {
      setPurging(false)
    }
  }

  const deleteMe = async () => {
    setDeleting(true); setMsg('')
    try {
      await api.delete('/privacy/me', { data: { confirm: confirmText } })
      localStorage.removeItem('token')
      window.location.href = '/login'
    } catch (e) {
      setMsg(detailText(e) || tx("Couldn't delete your account."))
      setDeleting(false)
    }
  }

  const resetRequests = async () => {
    if (!confirm('Delete ALL removal request history? Family data stays. Cannot be undone.')) return
    setResetting(true)
    try { await api.delete('/settings/danger/reset-requests'); alert('History cleared.') }
    finally { setResetting(false) }
  }

  const row = 'flex flex-wrap items-center justify-between gap-2 py-3 border-b border-slate-700/50'

  return (
    <Section
      icon={Database}
      title={tx("Data Lifecycle & Privacy Compliance (ISO/IEC 27701 & COPPA)")}
      description={tx("Automated crypto-shredding upon member deletion, data retention schedules, and privacy record rights")}
    >
      {msg && <p role="status" className="text-shield-300 text-sm mb-3 bg-shield-950/40 border border-shield-800 px-3 py-2 rounded-lg">{msg}</p>}

      {/* ── ISO/IEC 27701 & COPPA Compliance Banner ── */}
      <div className="mb-4 bg-slate-900/60 border border-slate-700/70 rounded-xl p-3.5 flex items-start gap-3">
        <ShieldCheck size={20} className="text-emerald-400 shrink-0 mt-0.5" />
        <div className="text-xs space-y-1">
          <p className="text-slate-200 font-semibold">
            {tx("ISO/IEC 27701 (Privacy Information Management) & COPPA Compliant Controls")}
          </p>
          <p className="text-slate-400 leading-relaxed">
            {tx("Ensures strict purpose limitation and data minimization: personal details are kept only as long as necessary, minor data is handled with elevated protections, and member deletion executes multi-pass cryptographic shredding so records cannot be recovered.")}
          </p>
        </div>
      </div>

      {isAdmin && (
        <div className="mb-6 space-y-4">
          {/* ── 1. Automated Crypto-Shredding upon Member Deletion ── */}
          <div className="py-3 border-b border-slate-700/50">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-slate-200 text-sm font-semibold">{tx("Automated Crypto-Shredding upon Member Deletion")}</p>
                  <span className="text-[10px] px-1.5 py-0.5 rounded-sm bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-medium">
                    {tx("ISO/IEC 27701")}
                  </span>
                </div>
                <p className="text-slate-400 text-xs mt-1">
                  {tx("When a member or account is deleted, OpenOptOut automatically overwrites PII ciphertext in storage with high-entropy cryptographic bytes before issuing deletions, rendering deleted records unrecoverable even through physical disk inspection.")}
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={cryptoShredEnabled}
                onClick={() => setCryptoShredEnabled(!cryptoShredEnabled)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                  cryptoShredEnabled ? 'bg-shield-600' : 'bg-slate-700'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                    cryptoShredEnabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            {cryptoShredEnabled && (
              <div className="mt-3 bg-slate-900/60 p-3 rounded-lg border border-slate-700/50 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-slate-300 text-xs font-medium">{tx("Cryptographic Overwrite Passes")}</p>
                    <p className="text-slate-500 text-[11px]">{tx("Multi-pass random entropy overwrites before row deletion")}</p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {[
                      { val: 1, label: tx("1 Pass (Fast)") },
                      { val: 3, label: tx("3 Passes (DoD 5220.22-M)") },
                      { val: 7, label: tx("7 Passes (Enhanced)") },
                    ].map(opt => (
                      <button
                        key={opt.val}
                        type="button"
                        onClick={() => setCryptoShredPasses(opt.val)}
                        className={`px-2 py-1 text-xs rounded-md border transition-colors ${
                          cryptoShredPasses === opt.val
                            ? 'bg-shield-600/30 border-shield-500 text-shield-200 font-semibold'
                            : 'bg-slate-900 border-slate-700 text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-800">
                  <div>
                    <p className="text-slate-300 text-xs font-medium">{tx("Database Space Sanitization (Vacuum)")}</p>
                    <p className="text-slate-500 text-[11px]">{tx("Automatically zero and reclaim unallocated SQLite storage pages after deletion")}</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={cryptoShredVacuum}
                    onChange={e => setCryptoShredVacuum(e.target.checked)}
                    className="w-4 h-4 rounded-sm border-slate-700 bg-slate-900 text-shield-600 focus:ring-shield-500"
                  />
                </div>

                <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-800">
                  <div>
                    <div className="flex items-center gap-1.5">
                      <p className="text-slate-300 text-xs font-medium">{tx("Strict Minor / Child Record Shredding")}</p>
                      <span className="text-[9px] px-1 rounded-sm bg-blue-500/20 text-blue-300 border border-blue-500/30">
                        {tx("COPPA Mandate")}
                      </span>
                    </div>
                    <p className="text-slate-500 text-[11px]">{tx("Immediately shred all child profile traces, confirmation links and request payloads upon verified removal")}</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={coppaStrictShredding}
                    onChange={e => setCoppaStrictShredding(e.target.checked)}
                    className="w-4 h-4 rounded-sm border-slate-700 bg-slate-900 text-shield-600 focus:ring-shield-500"
                  />
                </div>
              </div>
            )}
          </div>

          {/* ── 2. Data Retention Schedules (Common Presets + Custom Option) ── */}
          <div className="pt-2">
            <div className="mb-2">
              <h3 className="text-slate-200 text-sm font-semibold">{tx("Data Retention Schedules")}</h3>
              <p className="text-slate-400 text-xs mt-0.5">
                {tx("Choose common industry retention periods or set custom durations for each data classification.")}
              </p>
            </div>

            {/* Logs Retention */}
            <RetentionPicker
              label={tx("Automation & Broker Logs")}
              hint={tx("Execution logs, HTTP traces, email excerpts and unmatched search hits")}
              value={logsDays}
              onChange={setLogsDays}
              presets={[30, 90, 180, 365]}
              min={7}
            />

            {/* Artifacts Retention */}
            <RetentionPicker
              label={tx("Submission Artifacts & CAPTCHA Images")}
              hint={tx("Temporary challenge screenshots and raw broker submission payloads")}
              value={artifactsDays}
              onChange={setArtifactsDays}
              presets={[14, 30, 90, 180]}
              min={7}
            />

            {/* COPPA Children Retention */}
            <RetentionPicker
              label={tx("Minor / Child Request Artifacts (COPPA)")}
              hint={tx("Purge auxiliary verification records and email snippets once child opt-out is verified")}
              value={coppaDays}
              onChange={setCoppaDays}
              presets={[7, 14, 30, 60]}
              min={1}
            />

            {/* Staff Audit Trail Retention */}
            <RetentionPicker
              label={tx("Staff Audit & Access Logs")}
              hint={tx("Record of staff or administrators inspecting member records (ISO 27701 minimum 1 year recommended)")}
              value={auditDays}
              onChange={setAuditDays}
              presets={[180, 365, 730]}
              min={90}
            />

            <div className="flex flex-wrap items-center justify-between gap-3 pt-4">
              <button
                type="button"
                onClick={saveLifecyclePolicy}
                disabled={savingPolicy}
                className="flex items-center gap-1.5 px-4 py-2 text-sm bg-shield-600 hover:bg-shield-500 text-white font-medium rounded-lg transition-colors shadow-sm disabled:opacity-50"
              >
                <Check size={14} />
                {savingPolicy ? tx("Saving…") : tx("Save Retention & Shredding Policy")}
              </button>

              <button
                type="button"
                onClick={runPurgeNow}
                disabled={purging}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors disabled:opacity-50"
              >
                <RotateCcw size={12} className={purging ? "animate-spin" : ""} />
                {purging ? tx("Purging…") : tx("Run Retention Purge Now")}
              </button>
            </div>

            {purgeStats && (
              <div className="mt-3 p-3 bg-slate-900 border border-slate-700/60 rounded-lg text-xs text-slate-300">
                <p className="font-medium text-emerald-400 mb-1">{tx("Retention Purge Results:")}</p>
                <p>{tx("Removed {a} logs, {c} captchas, {s} screenshots, {p} COPPA traces.", {
                  a: purgeStats.automation_logs || 0,
                  c: purgeStats.captchas || 0,
                  s: purgeStats.screenshot_files || 0,
                  p: purgeStats.coppa_records || 0,
                })}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 3. Data Portability & Access Rights ── */}
      <div className={row}>
        <div>
          <p className="text-slate-200 text-sm font-medium">{tx("Download my data (GDPR / CCPA Portability)")}</p>
          <p className="text-slate-500 text-xs">{tx("Everything OpenOptOut keeps about you and the people you manage, as an encrypted JSON file")}</p>
        </div>
        <button onClick={exportMine}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
          <Download size={13}/>{tx("Download JSON")}
        </button>
      </div>

      {/* ── 4. Audit Trail (Who looked at our details) ── */}
      <div className="py-3 border-b border-slate-700/50">
        <p className="text-slate-200 text-sm font-medium">{tx("Access Audit Trail")}</p>
        <p className="text-slate-500 text-xs mb-2">{tx("Staff or admins who viewed, changed, exported, crypto-shredded or removed your family's details")}</p>
        {log === null ? <p className="text-slate-500 text-xs">{tx("Loading…")}</p> :
          log.length === 0 ? <p className="text-slate-400 text-sm">{tx("Nobody outside your family.")}</p> : (
          <ul className="text-sm space-y-1 max-h-48 overflow-y-auto font-mono text-xs">
            {log.map((e, i) => (
              <li key={i} className="text-slate-300 bg-slate-900/40 px-2 py-1 rounded-sm border border-slate-800">
                <span className="text-slate-500">{fmtDateTime(e.at)}</span> · <span className="text-shield-300 font-semibold">{e.who}</span> {({ view: tx("looked at"), edit: tx("changed"), export: tx("downloaded"), delete: tx("removed"), crypto_shred: tx("crypto-shredded") })[e.action] || e.action}{" "}{tx("{person}'s {v}", { person: e.person, v: e.detail || 'details' })}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ── 5. Account Self-Deletion ── */}
      <div className="py-3 border-b border-slate-700/50">
        <p className="text-slate-200 text-sm font-medium">{tx("Delete my account & family profiles")}</p>
        <p className="text-slate-500 text-xs mb-2">
          {tx("Deletes your account and everything about you. When automated crypto-shredding is active, your records are overwritten with random entropy before deletion. This can't be undone.")}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="del-confirm" className="sr-only">{tx("Type DELETE to confirm")}</label>
          <input id="del-confirm" value={confirmText} onChange={e => setConfirmText(e.target.value)} placeholder={tx("Type DELETE")}
            className="w-36 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-200" />
          <button onClick={deleteMe} disabled={deleting || confirmText.trim().toUpperCase() !== 'DELETE'}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-300 border border-red-800 rounded-lg hover:bg-red-900/30 disabled:opacity-40">
            <Trash2 size={12}/>{deleting ? tx("Deleting…") : tx("Delete my account")}
          </button>
        </div>
      </div>

      {/* ── 6. Danger Zone (Super Admin only) ── */}
      {isAdmin && (
        <div className="pt-3">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={13} className="text-red-400 shrink-0"/>
            <p className="text-red-400 text-xs font-medium uppercase tracking-wide">{tx("Danger zone")}</p>
          </div>
          <div className="border border-red-900/50 rounded-lg p-3 bg-red-950/20 flex items-center justify-between">
            <div>
              <p className="text-slate-200 text-sm font-medium">{tx("Reset removal history")}</p>
              <p className="text-slate-500 text-xs">{tx("Deletes all opt-out requests and email logs. Family data kept.")}</p>
            </div>
            <button onClick={resetRequests} disabled={resetting}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-400 border border-red-800 rounded-lg hover:bg-red-900/30 transition-colors disabled:opacity-40 ms-3 shrink-0">
              <Trash2 size={12}/>{resetting ? tx("Resetting…") : tx("Reset")}
            </button>
          </div>
        </div>
      )}
    </Section>
  )
}


// ── Vault limits ──────────────────────────────────────────────────────────────

function VaultLimitsSection({ initial, userRole, onSaved }) {
  const [form, setForm]     = useState(initial)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)
  const isAdmin = userRole === 'super_admin'

  // Derived: matrix size preview
  const discoveryPerBroker = form.max_names * form.max_addresses + form.max_names
  const optoutPerBroker    = form.max_names * form.max_addresses *
    Math.max(form.max_phones + 1, 1) * Math.max(form.max_emails + 1, 1)

  const save = async () => {
    setSaving(true)
    try {
      await api.patch('/settings/vault-limits', form)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      onSaved(form)
    } catch (err) {
      alert(detailText(err) ?? tx("Save failed"))
    } finally { setSaving(false) }
  }

  const FIELDS = [
    { key: 'max_names',     label: tx("Names"),   color: 'text-purple-400', max: 20,
      hint: tx("e.g. Robert Nunez, Rob Nunez, R. Nunez, Roberto Nunez") },
    { key: 'max_addresses', label: tx("Past addresses"),  color: 'text-amber-400',  max: 30,
      hint: tx("Every address increases discovery and opt-out coverage significantly") },
    { key: 'max_phones',    label: tx("Phone numbers"),   color: 'text-emerald-400', max: 20,
      hint: tx("Include all numbers tied to any of the listed addresses") },
    { key: 'max_emails',    label: tx("Email addresses"), color: 'text-blue-400',   max: 20,
      hint: tx("Include old, inactive, and alias addresses") },
  ]

  // Children limit is shown separately — it\'s 0-based (0 = unlimited)
  const childrenLimit = form.max_children_per_parent ?? 0

  return (
    <Section icon={Shield} title={tx("How many details each person can add")}
      description={tx("More details find more listings, but each one adds searches")}
      adminOnly userRole={userRole}>
      {!isAdmin ? (
        <div className="space-y-2">
          {FIELDS.map(f => (
            <div key={f.key} className="flex items-center justify-between py-1.5">
              <span className={`text-sm ${f.color}`}>{f.label}</span>
              <span className="text-slate-200 font-semibold text-sm">{initial[f.key]}</span>
            </div>
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {FIELDS.map(f => (
              <Field key={f.key} label={f.label} hint={f.hint}>
                <div className="flex items-center gap-2">
                  <input
                    type="number" min="1" max={f.max}
                    value={form[f.key]}
                    onChange={e => setForm(prev => ({...prev, [f.key]: Math.min(f.max, Math.max(1, parseInt(e.target.value) || 1))}))}
                    className={`${inp} text-center w-20`}
                  />
                  <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all`}
                      style={{
                        width: `${Math.round((form[f.key] / f.max) * 100)}%`,
                        background: f.color.replace('text-', '').includes('purple') ? '#a855f7'
                          : f.color.includes('amber') ? '#f59e0b'
                          : f.color.includes('emerald') ? '#10b981' : '#3b82f6'
                      }} />
                  </div>
                  <span className="text-slate-600 text-xs w-10 text-end">{tx("max")}{" "}{f.max}</span>
                </div>
              </Field>
            ))}
          </div>

          {/* Children per parent */}
          <div className="border-t border-slate-700/50 pt-4">
            <p className="text-slate-400 text-xs font-medium mb-2">{tx("Children per parent")}</p>
            <div className="flex items-center gap-3">
              <input
                type="number" min="0" max="100"
                value={childrenLimit}
                onChange={e => setForm(prev => ({...prev, max_children_per_parent: Math.max(0, parseInt(e.target.value) || 0)}))}
                className="w-24 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 text-center focus:outline-hidden focus:border-shield-500"
              />
              <div>
                <p className="text-slate-300 text-sm">
                  {childrenLimit === 0 ? tx("Unlimited") : txn(childrenLimit, "Max {n} child profile per parent", "Max {n} child profiles per parent")}
                </p>
                <p className="text-slate-600 text-xs mt-0.5">
                  {tx("0 = unlimited. Per-parent overrides can be set in Admin panel → Grant access.")}
                </p>
              </div>
            </div>
          </div>

          {/* Matrix size preview */}
          <div className="bg-slate-900 rounded-lg px-4 py-3 border border-slate-700/50">
            <p className="text-slate-500 text-xs uppercase tracking-wide mb-2">{tx("Searches this adds up to, per site")}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-slate-400 text-xs">{txr("To find someone <0>(each name with each address)</0>", [<span className="text-slate-600" />])}</p>
                <p className="text-slate-200 font-semibold">{fmtNumber(discoveryPerBroker)}{" "}{tx("searches")}</p>
              </div>
              <div>
                <p className="text-slate-400 text-xs">{txr("To remove someone <0>(every mix)</0>", [<span className="text-slate-600" />])}</p>
                <p className="text-slate-200 font-semibold">{fmtNumber(optoutPerBroker)}{" "}{tx("submissions")}</p>
              </div>
            </div>
            {optoutPerBroker > 500 && (
              <p className="text-amber-400 text-xs mt-2 flex items-center gap-1">
                <AlertTriangle size={11} />
                {tx("That's a lot of requests. We space them out so sites don't block us, so {optoutPerBroker} requests on every site will take a long time.", { optoutPerBroker })}
              </p>
            )}
          </div>

          <div className="flex justify-end pt-1">
            <SaveButton saving={saving} saved={saved} onClick={save} />
          </div>
        </>
      )}
    </Section>
  )
}


// ── Plugin system section ─────────────────────────────────────────────────────

function PluginSystemSection({ userRole }) {
  const [config, setConfig] = useState({ enabled: false, storage_mode: 'db', plugins_dir: '/data/plugins', denied: false, lockdown_mode: false })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)
  const [denying, setDenying] = useState(false)
  const isAdmin = userRole === 'super_admin'

  const load = () => api.get('/settings/plugins').then(r => setConfig(r.data)).catch(() => {})
  useEffect(() => { if (isAdmin) load() }, [isAdmin])

  if (!isAdmin) return null

  const save = async () => {
    setSaving(true)
    try {
      const { data } = await api.patch('/settings/plugins', config)
      setConfig(data); setSaved(true); setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }

  const deny = async () => {
    if (!confirm(tx("Deny the plugin system? This immediately stops ALL running plugins and blocks any from running until you explicitly re-allow it."))) return
    setDenying(true)
    try { await api.post('/settings/plugins/deny'); await load() }
    finally { setDenying(false) }
  }

  const allow = async () => {
    const typed = prompt('Re-allowing lets plugins run again. Type ALLOW to confirm.')
    if (typed !== 'ALLOW') return
    await api.post('/settings/plugins/allow', { confirm: true })
    await load()
  }

  // Denied state overrides everything — show a prominent locked banner.
  if (config.denied) {
    return (
      <Section icon={Puzzle} title={tx("Plugin system")}
        description={tx("Sandboxed, process-isolated plugins")} adminOnly userRole={userRole}>
        <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl border border-red-800 bg-red-900/15">
          <Ban size={16} className="text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-red-300 text-sm font-medium">{tx("Plugin system is DENIED")}</p>
            <p className="text-red-400/80 text-xs mt-0.5">
              {tx("All plugins are stopped and nothing can run. The plugin controls are locked until you re-allow the system.")}
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <button onClick={allow}
            className="flex items-center gap-1.5 px-4 py-1.5 text-sm text-amber-300 border border-amber-800 rounded-lg hover:bg-amber-900/20">
            <ShieldCheck size={13} />{" "}{tx("Re-allow (type-to-confirm)")}
          </button>
        </div>
      </Section>
    )
  }

  return (
    <Section icon={Puzzle} title={tx("Plugin system")}
      description={tx("Enable sandboxed, process-isolated plugins")}
      adminOnly userRole={userRole}>

      <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg border border-blue-800 bg-blue-900/10">
        <Info size={13} className="text-blue-400 shrink-0 mt-0.5" />
        <p className="text-blue-300/90 text-xs">
          {tx("Plugins run as isolated subprocesses with OS-level sandboxing and per-plugin permissions. After enabling here, restart the server, then install and enable individual plugins on the Plugins page. Untrusted plugins are only fully contained on Linux with bubblewrap installed.")}
        </p>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <div onClick={() => setConfig(c => ({ ...c, enabled: !c.enabled }))}
          className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${config.enabled ? 'bg-shield-600' : 'bg-slate-700'}`}>
          <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.enabled ? 'translate-x-4 rtl:-translate-x-4' : 'translate-x-0.5 rtl:-translate-x-0.5'}`} />
        </div>
        <span className="text-slate-300 text-sm">{tx("Enable the plugin system")}</span>
      </label>

      {config.enabled && (
        <>
          <div>
            <label className="text-slate-400 text-xs mb-1.5 block">{tx("Plugin storage backend")}</label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {[
                { v: 'db',   label: tx("Database"), desc: tx("Store plugin data in the app database") },
                { v: 'file', label: tx("File"),     desc: tx("Store plugin data as JSON files on disk") },
              ].map(o => (
                <button key={o.v} onClick={() => setConfig(c => ({ ...c, storage_mode: o.v }))}
                  className={`flex flex-col items-start px-3 py-2.5 rounded-lg border text-start transition-colors ${config.storage_mode === o.v ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700 hover:border-slate-600'}`}>
                  <span className={`text-sm font-medium ${config.storage_mode === o.v ? 'text-shield-300' : 'text-slate-300'}`}>{o.label}</span>
                  <span className="text-slate-500 text-xs">{o.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-slate-400 text-xs mb-1 block">{tx("Plugins directory")}</label>
            <input value={config.plugins_dir || ''} onChange={e => setConfig(c => ({ ...c, plugins_dir: e.target.value }))}
              placeholder="/data/plugins" className={inp} />
            <p className="text-slate-600 text-xs mt-1">{tx("Root folder for plugins inside the container. Each plugin is stored in a subfolder for its type: email/, captcha/, forms/, discovery/, brokers/, themes/, languages/, general/.")}</p>
          </div>

          {/* Lockdown mode */}
          <div className="flex items-start gap-2.5 px-3 py-2.5 rounded-lg border border-slate-700 bg-slate-800/40">
            <div onClick={() => setConfig(c => ({ ...c, lockdown_mode: !c.lockdown_mode }))}
              className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative shrink-0 mt-0.5 ${config.lockdown_mode ? 'bg-amber-600' : 'bg-slate-700'}`}>
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.lockdown_mode ? 'translate-x-4 rtl:-translate-x-4' : 'translate-x-0.5 rtl:-translate-x-0.5'}`} />
            </div>
            <div>
              <p className="text-slate-200 text-sm">{tx("Lockdown mode")}</p>
              <p className="text-slate-500 text-xs mt-0.5">
                {tx("Auto-disable any plugin on its first detected violation (spawning a process, writing outside its sandbox, opening a network socket, etc.). Recommended when running untrusted plugins.")}
              </p>
            </div>
          </div>
        </>
      )}

      <div className="flex items-center justify-between">
        <button onClick={deny} disabled={denying}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-400 border border-red-800/60 rounded-lg hover:bg-red-900/20 disabled:opacity-40">
          <Ban size={13} /> {denying ? tx("Denying…") : tx("Deny & stop all plugins")}
        </button>
        <SaveButton saving={saving} saved={saved} onClick={save} />
      </div>
      {config.enabled && <p className="text-slate-600 text-xs text-end">{tx("Restart the server for changes to take effect.")}</p>}
    </Section>
  )
}


// ── Encryption status section ─────────────────────────────────────────────────

function EncryptionSection({ userRole }) {
  const [status, setStatus] = useState(null)
  const isAdmin = userRole === 'super_admin'

  useEffect(() => {
    if (!isAdmin) return
    api.get('/settings/encryption-status').then(r => setStatus(r.data)).catch(() => {})
  }, [isAdmin])

  const StatusPill = ({ ok, label, sub }) => (
    <div className={`flex items-center justify-between px-3 py-2.5 rounded-lg border ${ok ? 'border-emerald-800 bg-emerald-900/10' : 'border-slate-700 bg-slate-900'}`}>
      <div>
        <p className={`text-sm font-medium ${ok ? 'text-emerald-300' : 'text-slate-400'}`}>{label}</p>
        {sub && <p className="text-slate-600 text-xs mt-0.5">{sub}</p>}
      </div>
      <span className={`text-xs px-2 py-0.5 rounded-sm border ${ok ? 'text-emerald-400 border-emerald-800 bg-emerald-900/20' : 'text-slate-500 border-slate-700'}`}>
        {ok ? 'enabled' : 'disabled'}
      </span>
    </div>
  )

  return (
    <Section icon={Shield} title={tx("Encryption at rest")}
      description={tx("Database and field-level encryption configuration")}
      adminOnly userRole={userRole}>
      {!isAdmin ? (
        <p className="text-slate-500 text-sm">{tx("Encryption settings are managed by your administrator.")}</p>
      ) : !status ? (
        <p className="text-slate-500 text-sm">{tx("Loading…")}</p>
      ) : (
        <>
          <div className="space-y-2">
            <StatusPill
              ok={status.db_encryption_enabled}
              label={tx("SQLCipher database encryption")}
              sub={status.db_encryption_enabled
                ? tx("Entire SQLite file is AES-256 encrypted")
                : status.sqlcipher_available
                  ? tx("Set DB_ENCRYPTION_KEY in .env to enable")
                  : tx("sqlcipher3-binary not installed (see README)")}
            />
            <StatusPill
              ok={status.field_encryption_enabled}
              label={tx("Personal details encrypted")}
              sub={status.field_encryption_enabled
                ? tx("Names, addresses, phones, emails encrypted before DB write")
                : tx("Set FIELD_ENCRYPTION_KEY in .env to enable (falls back to SECRET_KEY)")}
            />
            <StatusPill
              ok={status.secret_key_set}
              label={tx("SECRET_KEY configured")}
              sub={status.secret_key_set ? tx("Custom key set") : tx("Using default — change this immediately")}
            />
          </div>

          {status.db_type === 'postgres' && (
            <div className="px-3 py-2.5 bg-blue-900/10 border border-blue-800 rounded-lg text-blue-300 text-xs">
              {tx("PostgreSQL detected — SQLCipher does not apply. Use your provider's built-in encryption: RDS Storage Encryption, Azure Transparent Data Encryption, or Cloud SQL CMEK. Field-level encryption is still active and recommended.")}
            </div>
          )}

          {!status.db_encryption_enabled && status.sqlcipher_available && status.db_type === 'sqlite' && (
            <div className="bg-slate-900 rounded-lg p-3 text-xs space-y-2">
              <p className="text-slate-400 font-medium">{tx("To enable SQLCipher encryption:")}</p>
              <ol className="text-slate-500 space-y-1 ms-3">
                <li>{txr("1. Generate a key: <0>openssl rand -hex 32</0>", [<code className="bg-slate-800 px-1.5 rounded-sm text-slate-300" />])}</li>
                <li>{txr("2. Add to .env: <0>DB_ENCRYPTION_KEY=your-key-here</0>", [<code className="bg-slate-800 px-1.5 rounded-sm text-slate-300" />])}</li>
                <li>{txr("3. Migrate existing data: <0>docker exec openoptout-api python -m backend.core.encryption migrate</0>", [<code className="bg-slate-800 px-1.5 rounded-sm text-slate-300" />])}</li>
                <li>{tx("4. Back up the original .db file, replace with the _encrypted.db file")}</li>
                <li>{tx("5. Restart the container")}</li>
              </ol>
              <p className="text-amber-400">{tx("⚠ Migration must be done before enabling the key — not after. Back up first.")}</p>
            </div>
          )}

          {!status.field_encryption_enabled && (
            <div className="bg-slate-900 rounded-lg p-3 text-xs space-y-1">
              <p className="text-slate-400 font-medium">{tx("To enable field-level encryption:")}</p>
              <p className="text-slate-500">{txr("Add to .env: <0>FIELD_ENCRYPTION_KEY=your-key-here</0>", [<code className="bg-slate-800 px-1.5 rounded-sm text-slate-300" />])}</p>
              <p className="text-slate-600">{tx("Existing plaintext values are read correctly on first access. New writes are encrypted immediately.")}</p>
            </div>
          )}
        </>
      )}
    </Section>
  )
}


// ── Automation / bot-evasion section ──────────────────────────────────────────

function AutomationSection({ userRole }) {
  const [config, setConfig]   = useState({ rotate_user_agents: true, custom_user_agents: [], inter_submission_delay_seconds: 1.5, best_guess_forms: false })
  const [builtins, setBuiltins] = useState([])
  const [newUA, setNewUA]     = useState('')
  const [saving, setSaving]   = useState(false)
  const [saved, setSaved]     = useState(false)
  const [showBuiltins, setShowBuiltins] = useState(false)
  const isAdmin = userRole === 'super_admin'

  useEffect(() => {
    api.get('/settings/automation').then(r => setConfig(r.data)).catch(() => {})
    if (isAdmin) api.get('/settings/automation/builtin-agents').then(r => setBuiltins(r.data)).catch(() => {})
  }, [isAdmin])

  const save = async () => {
    setSaving(true)
    try {
      const { data } = await api.patch('/settings/automation', config)
      setConfig(data); setSaved(true); setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }

  const addUA = () => {
    if (!newUA.trim()) return
    setConfig(c => ({ ...c, custom_user_agents: [...c.custom_user_agents, newUA.trim()] }))
    setNewUA('')
  }

  const removeUA = (i) => {
    setConfig(c => ({ ...c, custom_user_agents: c.custom_user_agents.filter((_, idx) => idx !== i) }))
  }

  if (!isAdmin) return null

  return (
    <Section icon={Bot} title={tx("How we fill in forms")}
      description={tx("User-agent rotation and submission timing to reduce blocking")}
      adminOnly userRole={userRole}>

      <div className="flex items-start gap-2 px-3 py-2.5 bg-slate-900 border border-slate-700/50 rounded-lg">
        <Info size={13} className="text-slate-500 shrink-0 mt-0.5" />
        <p className="text-slate-500 text-xs">
          {tx("User-agent rotation is one layer of evasion. Sophisticated brokers also fingerprint TLS, canvas, and timing — rotation helps against simple blocking but is not a guarantee. Pair it with a reasonable submission delay for best results.")}
        </p>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <div onClick={() => setConfig(c => ({...c, rotate_user_agents: !c.rotate_user_agents}))}
          className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${config.rotate_user_agents ? 'bg-shield-600' : 'bg-slate-700'}`}>
          <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.rotate_user_agents ? 'translate-x-4 rtl:-translate-x-4' : 'translate-x-0.5 rtl:-translate-x-0.5'}`} />
        </div>
        <span className="text-slate-300 text-sm">{tx("Rotate user agents")}</span>
        <span className="text-slate-600 text-xs">{tx("— each broker gets a randomized browser fingerprint")}</span>
      </label>

      {config.rotate_user_agents && (
        <>
          <div>
            <button onClick={() => setShowBuiltins(s => !s)}
              className="flex items-center gap-1.5 text-slate-400 hover:text-slate-300 text-xs transition-colors">
              <ChevronDown size={11} className={showBuiltins ? 'rotate-180 transition-transform' : 'transition-transform'} />
              {tx("{length} built-in user agents", { length: builtins.length })}
            </button>
            {showBuiltins && (
              <div className="mt-2 bg-slate-900 rounded-lg p-3 max-h-40 overflow-y-auto space-y-1">
                {builtins.map((a, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="text-slate-600 w-14 shrink-0">{a.platform}</span>
                    <span className="text-slate-500 font-mono truncate">{a.ua}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <Field label={tx("Custom user agents")} hint={tx("Add your own UA strings — mixed into the rotation pool")}>
            <div className="flex gap-2">
              <input value={newUA} onChange={e => setNewUA(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addUA() } }}
                placeholder={tx("Mozilla/5.0 (...) ...")} className={inp + ' font-mono text-xs'} />
              <button onClick={addUA}
                className="px-3 py-1.5 bg-shield-600 text-white text-sm rounded-lg hover:bg-shield-700 transition-colors shrink-0">
                {tx("Add")}
              </button>
            </div>
          </Field>

          {config.custom_user_agents.length > 0 && (
            <div className="space-y-1.5">
              {config.custom_user_agents.map((ua, i) => (
                <div key={i} className="flex items-center gap-2 px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg">
                  <span className="text-slate-400 font-mono text-xs truncate flex-1">{ua}</span>
                  <button onClick={() => removeUA(i)} className="text-slate-600 hover:text-red-400 transition-colors shrink-0">
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <Field label={tx("Delay between submissions (seconds)")}
        hint={tx("Pause between each form submission per broker. Longer is slower, but sites are less likely to block us.")}>
        <input type="number" min="0.5" max="30" step="0.5"
          value={config.inter_submission_delay_seconds}
          onChange={e => setConfig(c => ({...c, inter_submission_delay_seconds: parseFloat(e.target.value)}))}
          className={inp + ' w-32'} />
      </Field>

      <label className="flex items-start gap-2 text-sm text-slate-300">
        <input type="checkbox" checked={!!config.best_guess_forms} className="mt-0.5 accent-shield-500"
          onChange={e => setConfig(c => ({...c, best_guess_forms: e.target.checked}))} />
        <span>
          {txr("Try a best guess on broker sites OpenOptOut has no steps for<0>Off by default. A guess can type someone's details into the wrong box, like a newsletter signup. When it's off, those sites go on the checklist instead. A guess only counts when the site says it received the request.</0>", [<span className="block text-slate-500 text-xs" />])}
        </span>
      </label>

      <div className="flex justify-end">
        <SaveButton saving={saving} saved={saved} onClick={save} />
      </div>
    </Section>
  )
}


// ── Proxy / IP masking section ────────────────────────────────────────────────

function ProxySection({ userRole }) {
  const [config, setConfig]   = useState({ enabled: false, mode: 'single', provider: 'generic', scheme: 'http', host: '', port: '' })
  const [status, setStatus]   = useState(null)
  const [presets, setPresets] = useState({})
  const [saving, setSaving]   = useState(false)
  const [saved, setSaved]     = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const isAdmin = userRole === 'super_admin'

  const load = () => {
    api.get('/settings/proxy').then(r => {
      setConfig(r.data.config); setStatus(r.data.status); setPresets(r.data.presets)
    }).catch(() => {})
  }
  useEffect(() => { if (isAdmin) load() }, [isAdmin])

  if (!isAdmin) return null

  const save = async () => {
    setSaving(true)
    try { await api.patch('/settings/proxy', config); setSaved(true); setTimeout(() => setSaved(false), 2000); load() }
    finally { setSaving(false) }
  }

  const test = async () => {
    setTesting(true); setTestResult(null)
    try { const { data } = await api.post('/settings/proxy/test'); setTestResult(data) }
    finally { setTesting(false) }
  }

  const preset = presets[config.provider] || {}
  const isPool = config.mode === 'pool'

  return (
    <Section icon={Globe} title={tx("Proxy / IP masking")}
      description={tx("Route automation through proxies to mask the server IP")}
      adminOnly userRole={userRole}>

      <div className="flex items-start gap-2 px-3 py-2.5 bg-blue-900/10 border border-blue-800 rounded-lg">
        <Shield size={13} className="text-blue-400 shrink-0 mt-0.5" />
        <p className="text-blue-300 text-xs">
          {tx("IP masking is the most effective anti-blocking measure — brokers track primarily by IP. Residential proxies work best. Credentials are read only from environment variables or mounted files, never stored here. Use reputable providers with consented IP networks.")}
        </p>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <div onClick={() => setConfig(c => ({...c, enabled: !c.enabled}))}
          className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${config.enabled ? 'bg-shield-600' : 'bg-slate-700'}`}>
          <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.enabled ? 'translate-x-4 rtl:-translate-x-4' : 'translate-x-0.5 rtl:-translate-x-0.5'}`} />
        </div>
        <span className="text-slate-300 text-sm">{tx("Enable proxy for automation traffic")}</span>
      </label>

      {config.enabled && (
        <>
          {/* Mode: single vs pool */}
          <Field label={tx("Mode")}>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button onClick={() => setConfig(c => ({...c, mode: 'single'}))}
                className={`flex flex-col items-start px-3 py-2.5 rounded-lg border text-start transition-colors ${config.mode === 'single' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700 hover:border-slate-600'}`}>
                <span className={`text-sm font-medium ${config.mode === 'single' ? 'text-shield-300' : 'text-slate-300'}`}>{tx("Single proxy")}</span>
                <span className="text-slate-500 text-xs">{tx("One IP for all traffic")}</span>
              </button>
              <button onClick={() => setConfig(c => ({...c, mode: 'pool'}))}
                className={`flex flex-col items-start px-3 py-2.5 rounded-lg border text-start transition-colors ${config.mode === 'pool' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700 hover:border-slate-600'}`}>
                <span className={`text-sm font-medium ${config.mode === 'pool' ? 'text-shield-300' : 'text-slate-300'}`}>{tx("Rotating pool")}</span>
                <span className="text-slate-500 text-xs">{tx("Different IP per broker")}</span>
              </button>
            </div>
          </Field>

          {/* Provider preset */}
          <Field label={tx("Provider")}>
            <div className="relative">
              <select value={config.provider} onChange={e => {
                  const p = presets[e.target.value] || {}
                  setConfig(c => ({...c, provider: e.target.value,
                    host: p.host_hint || c.host, port: p.default_port || c.port,
                    scheme: p.scheme || c.scheme }))
                }}
                className={inp + ' appearance-none pe-8'}>
                {Object.entries(presets).map(([key, p]) => (
                  <option key={key} value={key}>{p.label}</option>
                ))}
              </select>
              <ChevronDown size={12} className="absolute end-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
            </div>
            {preset.note && <p className="text-slate-500 text-xs mt-1.5 bg-slate-900 rounded-lg px-3 py-2">{preset.note}</p>}
          </Field>

          {/* Host/port/scheme — hidden in pool mode (pool comes from env) */}
          {!isPool && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="col-span-2">
                <Field label={tx("Host")}>
                  <input value={config.host || ''} onChange={e => setConfig(c => ({...c, host: e.target.value}))}
                    placeholder={preset.host_hint || 'gate.provider.com'} className={inp} />
                </Field>
              </div>
              <Field label={tx("Port")}>
                <input type="number" value={config.port || ''} onChange={e => setConfig(c => ({...c, port: parseInt(e.target.value)}))}
                  placeholder={String(preset.default_port || 8080)} className={inp} />
              </Field>
              <Field label={tx("Scheme")}>
                <div className="relative">
                  <select value={config.scheme || 'http'} onChange={e => setConfig(c => ({...c, scheme: e.target.value}))}
                    className={inp + ' appearance-none pe-7'}>
                    <option value="http">{"http"}</option>
                    <option value="https">{"https"}</option>
                    <option value="socks5">{"socks5"}</option>
                  </select>
                  <ChevronDown size={11} className="absolute end-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
                </div>
              </Field>
            </div>
          )}

          {isPool && (
            <div className="bg-slate-900 rounded-lg px-3 py-2.5 text-xs text-slate-500">
              {txr("Pool mode reads the proxy list from the <0>PROXY_POOL</0> environment variable or <1>PROXY_POOL_FILE</1>. Each entry is a proxy URL. A random proxy is chosen per broker.", [<code className="bg-slate-800 px-1 rounded-sm text-slate-300" />, <code className="bg-slate-800 px-1 rounded-sm text-slate-300" />])}
              {status && <span className="block mt-1 text-slate-400">{tx("Detected pool size:")}{" "}{status.pool_size}</span>}
            </div>
          )}

          {/* Credential status */}
          {status && (
            <div className="bg-slate-900 rounded-lg p-3">
              <div className="flex items-center gap-1.5 mb-2">
                <Lock size={12} className="text-slate-400" />
                <p className="text-slate-400 text-xs font-medium">{tx("Credentials")}</p>
                <span className="text-slate-600 text-xs">{tx("— from env / mounted files")}</span>
              </div>
              <div className="flex gap-4">
                <div className="flex items-center gap-1.5 text-xs">
                  {status.creds_user_set ? <Check size={12} className="text-emerald-400" /> : <X size={12} className="text-slate-600" />}
                  <span className={status.creds_user_set ? 'text-slate-300' : 'text-slate-600'}>{tx("Username")}</span>
                </div>
                <div className="flex items-center gap-1.5 text-xs">
                  {status.creds_pass_set ? <Check size={12} className="text-emerald-400" /> : <X size={12} className="text-slate-600" />}
                  <span className={status.creds_pass_set ? 'text-slate-300' : 'text-slate-600'}>{tx("Password")}</span>
                </div>
              </div>
              {!status.creds_user_set && (
                <p className="text-amber-400 text-xs mt-2">
                  {tx("No credentials detected. Set them via environment variables (see .env.example) before testing.")}
                </p>
              )}
            </div>
          )}

          {/* Test result */}
          {testResult && (
            <div className={`px-3 py-2.5 rounded-lg border text-sm ${testResult.ok ? 'border-emerald-800 bg-emerald-900/10 text-emerald-300' : 'border-red-800 bg-red-900/10 text-red-300'}`}>
              {testResult.ok
                ? <p className="font-medium">✓ {testResult.exit_ip ? tx("Traffic exiting via {exit_ip}", { exit_ip: testResult.exit_ip }) : tx("Connected through proxy")}</p>
                : <p>✗ {testResult.error}</p>}
            </div>
          )}

          <div className="flex gap-2 justify-end">
            <button onClick={test} disabled={testing}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 disabled:opacity-40 transition-colors">
              {testing ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
              {testing ? tx("Testing…") : tx("Test proxy")}
            </button>
            <SaveButton saving={saving} saved={saved} onClick={save} />
          </div>
        </>
      )}
    </Section>
  )
}

// ── Multi-Factor Authentication (MFA) Section ──────────────────────────────

function MfaAccountSection({ user }) {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // TOTP setup
  const [showTotpSetup, setShowTotpSetup] = useState(false)
  const [totpData, setTotpData] = useState(null)
  const [totpCode, setTotpCode] = useState('')
  const [totpSubmitting, setTotpSubmitting] = useState(false)
  const [copiedSecret, setCopiedSecret] = useState(false)

  // TOTP disable
  const [showTotpDisable, setShowTotpDisable] = useState(false)
  const [disablePassword, setDisablePassword] = useState('')
  const [disableSubmitting, setDisableSubmitting] = useState(false)

  // WebAuthn register
  const [showAddKey, setShowAddKey] = useState(false)
  const [keyName, setKeyName] = useState('My security key')
  const [keySubmitting, setKeySubmitting] = useState(false)

  // Backup codes modal
  const [showBackupCodes, setShowBackupCodes] = useState(false)
  const [backupCodesList, setBackupCodesList] = useState([])
  const [copiedCodes, setCopiedCodes] = useState(false)

  const loadStatus = async () => {
    try {
      const { data } = await api.get('/auth/mfa/status')
      setStatus(data)
    } catch {
      // User might be unauthenticated or non-local
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadStatus() }, [])

  const startTotpSetup = async () => {
    setError(''); setSuccess(''); setTotpSubmitting(true)
    try {
      const { data } = await api.post('/auth/mfa/totp/setup')
      setTotpData(data)
      setShowTotpSetup(true)
    } catch (err) {
      setError(detailText(err) || tx("Failed to start authenticator setup"))
    } finally {
      setTotpSubmitting(false)
    }
  }

  const activateTotp = async e => {
    e?.preventDefault()
    if (!totpCode.trim()) return
    const currentPassword = window.prompt(tx("Your current password, to confirm it's really you"))
    if (!currentPassword) return
    setError(''); setSuccess(''); setTotpSubmitting(true)
    try {
      const { data } = await api.post('/auth/mfa/totp/activate', {
        secret: totpData?.secret,
        code: totpCode.trim(),
        backup_codes: totpData?.backup_codes || [],
        current_password: currentPassword,
      })
      setShowTotpSetup(false)
      setTotpCode('')
      setSuccess(tx("Authenticator app enabled successfully!"))
      if (data.backup_codes?.length) {
        setBackupCodesList(data.backup_codes)
        setShowBackupCodes(true)
      }
      loadStatus()
    } catch (err) {
      setError(detailText(err) || tx("That code didn't work. Codes change every 30 seconds, so use the newest one."))
    } finally {
      setTotpSubmitting(false)
    }
  }

  const disableTotp = async e => {
    e?.preventDefault()
    if (!disablePassword) return
    setError(''); setSuccess(''); setDisableSubmitting(true)
    try {
      await api.post('/auth/mfa/totp/disable', { password: disablePassword })
      setShowTotpDisable(false)
      setDisablePassword('')
      setSuccess(tx("Authenticator app removed."))
      loadStatus()
    } catch (err) {
      setError(detailText(err) || tx("Failed to disable authenticator. Check your password."))
    } finally {
      setDisableSubmitting(false)
    }
  }

  const registerSecurityKey = async () => {
    const currentPassword = window.prompt(tx("Your current password, to confirm it's really you"))
    if (!currentPassword) return
    setError(''); setSuccess(''); setKeySubmitting(true)
    try {
      const { data: optData } = await api.post('/auth/mfa/webauthn/register-options')
      const credential = await performWebAuthnRegister(optData.options)
      const { data: regData } = await api.post('/auth/mfa/webauthn/register', {
        credential,
        key_name: keyName.trim() || 'My security key',
        current_password: currentPassword,
      })
      setShowAddKey(false)
      setKeyName('My security key')
      setSuccess('Security key registered successfully!')
      if (regData.backup_codes?.length) {
        setBackupCodesList(regData.backup_codes)
        setShowBackupCodes(true)
      }
      loadStatus()
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        setError('Security key interaction was cancelled or timed out.')
      } else {
        setError(detailText(err) || err.message || 'Failed to register security key.')
      }
    } finally {
      setKeySubmitting(false)
    }
  }

  const deleteKey = async (keyId, keyLabel) => {
    if (!confirm(tx("Remove security key \"{keyLabel}\"?", { keyLabel }))) return
    const password = window.prompt(tx("Your password"))
    if (!password) return
    setError(''); setSuccess('')
    try {
      await api.delete(`/auth/mfa/webauthn/${keyId}`, { data: { password } })
      setSuccess(tx("Removed security key \"{keyLabel}\".", { keyLabel }))
      loadStatus()
    } catch (err) {
      setError(detailText(err) || tx("Failed to remove security key."))
    }
  }

  const copyCodes = () => {
    navigator.clipboard.writeText(backupCodesList.join('\n'))
    setCopiedCodes(true)
    setTimeout(() => setCopiedCodes(false), 2000)
  }

  const copySecret = (text) => {
    navigator.clipboard.writeText(text)
    setCopiedSecret(true)
    setTimeout(() => setCopiedSecret(false), 2000)
  }

  if (loading) return null

  const isMandatedRole = ['super_admin', 'manager'].includes(user?.role)
  const hasMfa = status?.totp_enabled || (status?.webauthn_keys?.length || 0) > 0

  return (
    <Section
      icon={ShieldCheck}
      title={tx("Two-Factor Authentication (MFA)")}
      description={tx("Protect your account with TOTP authenticator apps or FIDO2 security keys (YubiKey / Mac Touch ID / iPhone Face ID / Android)")}
      userRole={user?.role}
    >
      {/* Notifications */}
      {error && (
        <div className="px-3 py-2 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-xs">
          {error}
        </div>
      )}
      {success && (
        <div className="px-3 py-2 bg-emerald-900/30 border border-emerald-800 rounded-lg text-emerald-400 text-xs flex items-center gap-1.5">
          <Check size={13} /> {success}
        </div>
      )}

      {/* Mandate Policy Status Badge */}
      {isMandatedRole && (
        <div className={`p-3 rounded-lg border flex items-start gap-2.5 text-xs ${
          status?.mfa_mandated
            ? (hasMfa ? 'bg-emerald-950/20 border-emerald-800/60 text-emerald-300' : 'bg-amber-950/30 border-amber-800 text-amber-300')
            : 'bg-slate-900 border-slate-700/60 text-slate-400'
        }`}>
          {status?.mfa_mandated ? (
            hasMfa ? <ShieldCheck size={15} className="text-emerald-400 shrink-0 mt-0.5" /> : <ShieldAlert size={15} className="text-amber-400 shrink-0 mt-0.5" />
          ) : (
            <Clock size={15} className="text-slate-400 shrink-0 mt-0.5" />
          )}
          <div>
            <p className="font-medium">
              {status?.mfa_mandated
                ? (hasMfa ? tx("Administrative Mandate: Compliant") : tx("Administrative Mandate: Action Required"))
                : tx("Administrative Grace Period Active ({v} days remaining)", { v: status?.days_until_mandate ?? 3 })}
            </p>
            <p className="text-[11px] mt-0.5 opacity-80">
              {status?.mfa_mandated
                ? tx("Multi-Factor Authentication is mandated for local Super Admin and Admin accounts 3 days after system install.")
                : tx("MFA will become mandatory for local administrative accounts 3 days after install. Configure at least one factor to prevent login restrictions.")}
            </p>
          </div>
        </div>
      )}

      {/* ── 1. TOTP Authenticator Card ── */}
      <div className="p-3.5 bg-slate-900/70 border border-slate-700/60 rounded-xl space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-slate-800 text-shield-400 rounded-lg">
              <Smartphone size={16} />
            </div>
            <div>
              <p className="text-slate-200 text-sm font-medium">{tx("Authenticator App (TOTP)")}</p>
              <p className="text-slate-500 text-xs">{tx("Google Authenticator, Yubico Authenticator, 1Password, Bitwarden")}</p>
            </div>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded border ${
            status?.totp_enabled
              ? 'text-emerald-400 border-emerald-800 bg-emerald-900/20'
              : 'text-slate-500 border-slate-700 bg-slate-800/50'
          }`}>
            {status?.totp_enabled ? tx("Enabled") : tx("Not configured")}
          </span>
        </div>

        {/* Action Buttons */}
        {!showTotpSetup && !showTotpDisable && (
          <div className="flex gap-2 justify-end pt-1">
            {status?.totp_enabled ? (
              <>
                <button
                  type="button"
                  onClick={startTotpSetup}
                  disabled={totpSubmitting}
                  className="px-3 py-1.5 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
                  {tx("Reconfigure")}
                </button>
                <button
                  type="button"
                  onClick={() => setShowTotpDisable(true)}
                  className="px-3 py-1.5 text-xs text-red-400 border border-red-900/50 rounded-lg hover:bg-red-950/30 transition-colors">
                  {tx("Disable")}
                </button>
              </>
            ) : status?.allowed_methods?.totp === false ? (
              <span className="text-xs text-amber-400 bg-amber-950/40 border border-amber-800/60 px-2.5 py-1 rounded-md">
                {tx("Disabled by institutional policy")}
              </span>
            ) : (
              <button
                type="button"
                onClick={startTotpSetup}
                disabled={totpSubmitting}
                className="px-3 py-1.5 text-xs text-white bg-shield-600 hover:bg-shield-700 rounded-lg transition-colors flex items-center gap-1.5">
                {totpSubmitting ? <RefreshCw size={12} className="animate-spin" /> : <Plus size={12} />}
                {tx("Set up Authenticator")}
              </button>
            )}
          </div>
        )}

        {/* TOTP Setup Form */}
        {showTotpSetup && totpData && (
          <div className="p-3 bg-slate-800/90 border border-slate-700 rounded-lg space-y-3 mt-2">
            <div>
              <label className={labelCls}>{tx("Secret Key (Base32)")}</label>
              <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-lg p-2 font-mono text-xs text-shield-300">
                <span className="truncate flex-1 tracking-wider">{totpData.secret}</span>
                <button
                  type="button"
                  onClick={() => copySecret(totpData.secret)}
                  className="text-slate-400 hover:text-white shrink-0">
                  {copiedSecret ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                </button>
              </div>
              <p className="text-slate-500 text-[11px] mt-1">
                {tx("Enter this key manually in your authenticator app, or import the otpauth URI.")}
              </p>
            </div>

            <form onSubmit={activateTotp} className="space-y-3">
              <div>
                <label className={labelCls}>{tx("Enter 6-digit verification code")}</label>
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  placeholder="000000"
                  value={totpCode}
                  onChange={e => setTotpCode(e.target.value)}
                  className={`${inp} text-center font-mono tracking-widest text-base w-40`}
                  autoFocus
                />
              </div>
              <div className="flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={() => { setShowTotpSetup(false); setTotpCode('') }}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">
                  {tx("Cancel")}
                </button>
                <button
                  type="submit"
                  disabled={totpSubmitting || totpCode.trim().length < 6}
                  className="px-3.5 py-1.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg text-xs font-medium transition-colors">
                  {totpSubmitting ? tx("Verifying…") : tx("Verify & Enable")}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* TOTP Disable Form */}
        {showTotpDisable && (
          <form onSubmit={disableTotp} className="p-3 bg-slate-800/90 border border-slate-700 rounded-lg space-y-3 mt-2">
            <p className="text-slate-300 text-xs">{tx("Enter your account password to disable the authenticator app:")}</p>
            <input
              type="password"
              placeholder={tx("Your password")}
              value={disablePassword}
              onChange={e => setDisablePassword(e.target.value)}
              className={inp}
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => { setShowTotpDisable(false); setDisablePassword('') }}
                className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">
                {tx("Cancel")}
              </button>
              <button
                type="submit"
                disabled={disableSubmitting || !disablePassword}
                className="px-3.5 py-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white rounded-lg text-xs font-medium transition-colors">
                {disableSubmitting ? tx("Removing…") : tx("Confirm Disable")}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* ── 2. Hardware Security Keys & WebAuthn Card ── */}
      <div className="p-3.5 bg-slate-900/70 border border-slate-700/60 rounded-xl space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-slate-800 text-emerald-400 rounded-lg">
              <Fingerprint size={16} />
            </div>
            <div>
              <p className="text-slate-200 text-sm font-medium">{tx("Security Keys & Platform Biometrics")}</p>
              <p className="text-slate-500 text-xs">{tx("FIDO2 / WebAuthn: YubiKey, Google Titan, Mac Touch ID, and iPhone / Android (Face ID via QR code)")}</p>
            </div>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded border ${
            (status?.webauthn_keys?.length || 0) > 0
              ? 'text-emerald-400 border-emerald-800 bg-emerald-900/20'
              : 'text-slate-500 border-slate-700 bg-slate-800/50'
          }`}>
            {tx("{v} registered", { v: status?.webauthn_keys?.length || 0 })}
          </span>
        </div>

        {/* Enrolled Keys List */}
        {status?.webauthn_keys?.length > 0 && (
          <div className="space-y-2 pt-1">
            {status.webauthn_keys.map(k => (
              <div key={k.id} className="flex items-center justify-between p-2.5 bg-slate-800/80 border border-slate-700/70 rounded-lg text-xs">
                <div className="flex items-center gap-2 min-w-0">
                  <Key size={13} className="text-slate-400 shrink-0" />
                  <span className="text-slate-200 font-medium truncate">{k.name}</span>
                  {k.fips_certified && (
                    <span className="px-1.5 py-0.5 rounded-sm text-[10px] bg-purple-900/40 border border-purple-700 text-purple-300 shrink-0">
                      {tx("FIPS 140-2 / 140-3")}
                    </span>
                  )}
                  <span className="text-slate-500 text-[11px] shrink-0">
                    {tx("Added {v}", { v: k.created_at ? fmtDate(k.created_at) : tx("recently") })}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => deleteKey(k.id, k.name)}
                  className="text-slate-500 hover:text-red-400 transition-colors p-1"
                  title={tx("Remove security key")}>
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Add Key Form / Trigger */}
        {!showAddKey ? (
          <div className="flex justify-end pt-1">
            {status?.allowed_methods?.webauthn === false ? (
              <span className="text-xs text-amber-400 bg-amber-950/40 border border-amber-800/60 px-2.5 py-1 rounded-md">
                {tx("Disabled by institutional policy")}
              </span>
            ) : (
              <button
                type="button"
                onClick={() => setShowAddKey(true)}
                className="px-3 py-1.5 text-xs text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors flex items-center gap-1.5">
                <Plus size={12} />{" "}{tx("Add Key / Touch ID / Phone")}
              </button>
            )}
          </div>
        ) : (
          <div className="p-3 bg-slate-800/90 border border-slate-700 rounded-lg space-y-3 mt-2">
            <div>
              <label className={labelCls}>{tx("Key or Device Name")}</label>
              <input
                type="text"
                placeholder={tx("e.g. Work YubiKey 5C, MacBook Touch ID, or Personal iPhone")}
                value={keyName}
                onChange={e => setKeyName(e.target.value)}
                className={inp}
                autoFocus
              />
            </div>
            <p className="text-slate-400 text-xs">
              {tx("When you click Register, your browser will ask you to touch your YubiKey, use Mac Touch ID, or scan the on-screen QR code with your iPhone (Face ID) or Android device.")}
            </p>
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => { setShowAddKey(false); setKeyName(tx("My security key")) }}
                className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200">
                {tx("Cancel")}
              </button>
              <button
                type="button"
                onClick={registerSecurityKey}
                disabled={keySubmitting}
                className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5">
                {keySubmitting ? <RefreshCw size={12} className="animate-spin" /> : <Fingerprint size={12} />}
                {keySubmitting ? tx("Waiting for touch or phone scan…") : tx("Register Key / Touch ID / Phone")}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── 3. Backup Recovery Codes Info ── */}
      {hasMfa && (
        <div className="p-3 bg-slate-900/40 border border-slate-800 rounded-xl flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <Key size={14} className="text-slate-400" />
            <span className="text-slate-300">{tx("Backup Recovery Codes")}</span>
            <span className="text-slate-500">{tx("— {v} codes remaining", { v: status?.backup_codes_remaining ?? 0 })}</span>
          </div>
          <span className="text-slate-500 text-[11px]">
            {tx("Single-use offline emergency access")}
          </span>
        </div>
      )}

      {/* Backup Codes Display Modal */}
      {showBackupCodes && (
        <div className="p-4 bg-slate-950 border border-emerald-800/80 rounded-xl space-y-3 mt-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-emerald-400 text-xs font-semibold">
              <Check size={14} />{" "}{tx("New Backup Recovery Codes Generated")}
            </div>
            <button
              type="button"
              onClick={() => setShowBackupCodes(false)}
              className="text-slate-500 hover:text-slate-300">
              <X size={14} />
            </button>
          </div>
          <p className="text-slate-400 text-xs">
            {tx("Save these codes in a secure location (such as a password manager). If you lose access to your primary authenticator, each code can be used once to access your account.")}
          </p>
          <div className="grid grid-cols-2 gap-1.5 bg-slate-900 p-3 rounded-lg font-mono text-xs text-slate-200 text-center border border-slate-800">
            {backupCodesList.map((code, idx) => (
              <span key={idx} className="py-0.5">{code}</span>
            ))}
          </div>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={copyCodes}
              className="px-3 py-1.5 border border-slate-700 hover:bg-slate-800 text-slate-300 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors">
              {copiedCodes ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
              {copiedCodes ? tx("Copied to Clipboard") : tx("Copy All Codes")}
            </button>
            <button
              type="button"
              onClick={() => setShowBackupCodes(false)}
              className="px-3.5 py-1.5 bg-shield-600 hover:bg-shield-700 text-white rounded-lg text-xs font-medium transition-colors">
              {tx("Done")}
            </button>
          </div>
        </div>
      )}
    </Section>
  )
}


// ── Institutional WebAuthn & MFA Policy Section (Super Admin) ─────────────

function ActiveSessionsSection({ user }) {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [revokingId, setRevokingId] = useState(null)
  const [signingOutEverywhere, setSigningOutEverywhere] = useState(false)

  const load = async () => {
    try {
      const { data } = await api.get('/auth/sessions')
      setSessions(data)
    } catch {
      // Unauthenticated or non-local; nothing to show
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const revoke = async (id) => {
    setError(''); setSuccess(''); setRevokingId(id)
    try {
      await api.delete(`/auth/sessions/${id}`)
      setSuccess(tx("Signed out of that device."))
      load()
    } catch (err) {
      setError(detailText(err) || tx("Failed to sign out that session."))
    } finally {
      setRevokingId(null)
    }
  }

  const signOutEverywhere = async () => {
    if (!confirm(tx("Sign out of every device, including this one?"))) return
    setError(''); setSuccess(''); setSigningOutEverywhere(true)
    try {
      await api.post('/auth/signout-everywhere')
      setSuccess(tx("Signed out everywhere."))
      localStorage.removeItem('token')
      window.location.reload()
    } catch (err) {
      setError(detailText(err) || tx("Failed to sign out everywhere."))
      setSigningOutEverywhere(false)
    }
  }

  if (loading) return null

  return (
    <Section
      icon={Smartphone}
      title={tx("Active Sessions")}
      description={tx("Devices and browsers currently signed in to your account")}
      userRole={user?.role}
    >
      {error && (
        <div className="px-3 py-2 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-xs">
          {error}
        </div>
      )}
      {success && (
        <div className="px-3 py-2 bg-emerald-900/30 border border-emerald-800 rounded-lg text-emerald-400 text-xs flex items-center gap-1.5">
          <Check size={13} /> {success}
        </div>
      )}

      {sessions.length === 0 && (
        <p className="text-slate-500 text-xs">{tx("No active sessions found.")}</p>
      )}

      {sessions.map(s => (
        <div key={s.id} className="p-3.5 bg-slate-900/70 border border-slate-700/60 rounded-xl flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-slate-200 text-sm font-medium flex items-center gap-1.5 flex-wrap">
              {s.user_agent || tx("Unknown device")}
              {s.is_current && (
                <span className="px-1.5 py-0.5 text-[10px] rounded bg-shield-900/60 text-shield-300 border border-shield-800">
                  {tx("This device")}
                </span>
              )}
              {s.remember_me && (
                <span className="px-1.5 py-0.5 text-[10px] rounded bg-slate-800 text-slate-400 border border-slate-700">
                  {tx("Stays signed in")}
                </span>
              )}
            </p>
            <p className="text-slate-500 text-xs mt-0.5">
              {tx("Signed in {time}", { time: fmtDateTime(s.created_at) })}
              {s.ip ? ` · ${s.ip}` : ''}
            </p>
          </div>
          {!s.is_current && (
            <button
              onClick={() => revoke(s.id)}
              disabled={revokingId === s.id}
              className="shrink-0 px-2.5 py-1.5 text-xs text-red-300 border border-red-800/60 rounded-lg hover:bg-red-950/40 transition-colors disabled:opacity-40"
            >
              {revokingId === s.id ? tx("Signing out…") : tx("Sign out")}
            </button>
          )}
        </div>
      ))}

      {sessions.length > 1 && (
        <button
          onClick={signOutEverywhere}
          disabled={signingOutEverywhere}
          className="flex items-center gap-1 px-3 py-1.5 text-sm text-red-300 border border-red-800/60 rounded-lg hover:bg-red-950/40 transition-colors disabled:opacity-40"
        >
          {signingOutEverywhere ? <RefreshCw size={12} className="animate-spin" /> : null}
          {tx("Sign out of every device")}
        </button>
      )}
    </Section>
  )
}

function WebAuthnPolicySection({ userRole }) {
  const isAdmin = userRole === 'super_admin'
  const [config, setConfig] = useState({
    authenticator_attachment: 'any',
    user_verification: 'preferred',
    fips_only: false,
    rp_name: 'OpenOptOut',
    rp_id: null,
  })
  const [mfaRoles, setMfaRoles] = useState({
    super_admin: { totp: true, webauthn: true, backup_codes: true },
    manager:     { totp: true, webauthn: true, backup_codes: true },
    parent:      { totp: true, webauthn: true, backup_codes: true },
    member:      { totp: true, webauthn: true, backup_codes: true },
  })
  const [mfaCompliance, setMfaCompliance] = useState({
    super_admin: { enabled: true, value: 3, unit: 'days' },
    manager:     { enabled: true, value: 3, unit: 'days' },
    parent:      { enabled: false, value: 7, unit: 'days' },
    member:      { enabled: false, value: 7, unit: 'days' },
  })
  const [descriptions, setDescriptions] = useState({})
  const [policyError, setPolicyError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const load = () => {
    api.get('/settings/security/webauthn').then(r => {
      if (r.data.config) setConfig(r.data.config)
      if (r.data.descriptions) setDescriptions(r.data.descriptions)
    }).catch(() => {})

    api.get('/settings/security/mfa-policy').then(r => {
      if (r.data.roles) setMfaRoles(r.data.roles)
      if (r.data.compliance) setMfaCompliance(r.data.compliance)
    }).catch(() => {})
  }

  useEffect(() => { if (isAdmin) load() }, [isAdmin])

  if (!isAdmin) return null

  const save = async () => {
    // Invariant: administrative accounts must keep at least one method enabled
    if (!mfaRoles.super_admin?.totp && !mfaRoles.super_admin?.webauthn) {
      setPolicyError(tx("Super Admin role must retain at least one active MFA method (TOTP or Security Key) to prevent lockout."))
      return
    }
    if (!mfaRoles.manager?.totp && !mfaRoles.manager?.webauthn) {
      setPolicyError(tx("Manager role must retain at least one active MFA method (TOTP or Security Key) to prevent lockout."))
      return
    }

    setSaving(true); setPolicyError('')
    try {
      await Promise.all([
        api.patch('/settings/security/webauthn', config),
        api.patch('/settings/security/mfa-policy', { roles: mfaRoles, compliance: mfaCompliance }),
      ])
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      setPolicyError(detailText(err) || tx("Failed to save security policy."))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Section
      icon={Key}
      title={tx("Institutional MFA & Hardware Security Key Policy")}
      description={tx("Configure allowed MFA methods, post-creation compliance timers per permissions group, and FIPS compliance")}
      adminOnly
      userRole={userRole}
    >
      {/* ── 1. Role-Based MFA Methods & Compliance Policy ── */}
      <div className="space-y-2 pb-2">
        <label className={labelCls}>{tx("Permissions Group MFA Methods & Compliance Timers")}</label>
        <p className="text-slate-400 text-xs">
          {tx("Enable or restrict specific MFA options and set compliance timers for local accounts based on time elapsed since account creation. If a user does not complete setup in time, they will be required to enroll upon login.")}
        </p>

        {policyError && (
          <div className="p-3 bg-red-950/30 border border-red-800/80 rounded-lg text-xs text-red-300">
            {policyError}
          </div>
        )}

        <div className="overflow-x-auto rounded-lg border border-slate-700/80 bg-slate-900/60 mt-2">
          <table className="w-full text-start text-xs">
            <thead>
              <tr className="border-b border-slate-700/80 text-slate-400 bg-slate-800/50">
                <th className="py-2.5 px-3 font-medium">{tx("Permissions Group")}</th>
                <th className="py-2.5 px-2 font-medium text-center">{tx("TOTP")}</th>
                <th className="py-2.5 px-2 font-medium text-center">{tx("FIDO2 / Keys")}</th>
                <th className="py-2.5 px-2 font-medium text-center">{tx("Backup Codes")}</th>
                <th className="py-2.5 px-3 font-medium">{tx("Compliance Timer (Post-Creation)")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 text-slate-300">
              {[
                { key: 'super_admin', label: tx("Super Admin"), desc: tx("Full institutional administrator") },
                { key: 'manager',     label: tx("Manager / Admin"), desc: tx("Staff managers & unit administrators") },
                { key: 'parent',      label: tx("Parent"), desc: tx("Account holder managing family members") },
                { key: 'member',      label: tx("Member"), desc: tx("Standard managed member account") },
              ].map(r => {
                const roleCfg = mfaRoles[r.key] || { totp: true, webauthn: true, backup_codes: true }
                const comp = mfaCompliance[r.key] || { enabled: false, value: 3, unit: 'days' }
                return (
                  <tr key={r.key} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-2.5 px-3">
                      <p className="font-medium text-white">{r.label}</p>
                      <p className="text-slate-500 text-[11px]">{r.desc}</p>
                    </td>
                    <td className="py-2.5 px-2 text-center">
                      <input
                        type="checkbox"
                        checked={!!roleCfg.totp}
                        onChange={e => {
                          setPolicyError('')
                          setMfaRoles(prev => ({
                            ...prev,
                            [r.key]: { ...(prev[r.key] || {}), totp: e.target.checked }
                          }))
                        }}
                        className="rounded-sm border-slate-600 bg-slate-800 text-shield-500 focus:ring-shield-500 w-4 h-4 cursor-pointer"
                        title={tx("Allow TOTP")}
                      />
                    </td>
                    <td className="py-2.5 px-2 text-center">
                      <input
                        type="checkbox"
                        checked={!!roleCfg.webauthn}
                        onChange={e => {
                          setPolicyError('')
                          setMfaRoles(prev => ({
                            ...prev,
                            [r.key]: { ...(prev[r.key] || {}), webauthn: e.target.checked }
                          }))
                        }}
                        className="rounded-sm border-slate-600 bg-slate-800 text-shield-500 focus:ring-shield-500 w-4 h-4 cursor-pointer"
                        title={tx("Allow FIDO2 / WebAuthn")}
                      />
                    </td>
                    <td className="py-2.5 px-2 text-center">
                      <input
                        type="checkbox"
                        checked={!!roleCfg.backup_codes}
                        onChange={e => {
                          setPolicyError('')
                          setMfaRoles(prev => ({
                            ...prev,
                            [r.key]: { ...(prev[r.key] || {}), backup_codes: e.target.checked }
                          }))
                        }}
                        className="rounded-sm border-slate-600 bg-slate-800 text-shield-500 focus:ring-shield-500 w-4 h-4 cursor-pointer"
                        title={tx("Allow Backup Codes")}
                      />
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
                          <input
                            type="checkbox"
                            checked={!!comp.enabled}
                            onChange={e => {
                              setPolicyError('')
                              setMfaCompliance(prev => ({
                                ...prev,
                                [r.key]: { ...(prev[r.key] || {}), enabled: e.target.checked }
                              }))
                            }}
                            className="rounded-sm border-slate-600 bg-slate-800 text-shield-500 focus:ring-shield-500 w-3.5 h-3.5 cursor-pointer"
                          />
                          <span className="text-[11px] text-slate-400">{tx("Mandate")}</span>
                        </label>
                        {comp.enabled && (
                          <div className="flex items-center gap-1">
                            <input
                              type="number"
                              min="1"
                              max="99"
                              value={comp.value ?? 3}
                              onChange={e => {
                                setPolicyError('')
                                const raw = parseInt(e.target.value, 10)
                                const clamped = isNaN(raw) ? 1 : Math.max(1, Math.min(99, raw))
                                setMfaCompliance(prev => ({
                                  ...prev,
                                  [r.key]: { ...(prev[r.key] || {}), value: clamped }
                                }))
                              }}
                              className="w-12 px-1.5 py-0.5 bg-slate-800 border border-slate-700 rounded-sm text-slate-100 font-mono text-xs text-center focus:outline-hidden focus:border-shield-500"
                            />
                            <select
                              value={comp.unit || 'days'}
                              onChange={e => {
                                setPolicyError('')
                                setMfaCompliance(prev => ({
                                  ...prev,
                                  [r.key]: { ...(prev[r.key] || {}), unit: e.target.value }
                                }))
                              }}
                              className="px-1.5 py-0.5 bg-slate-800 border border-slate-700 rounded-sm text-slate-200 text-xs focus:outline-hidden focus:border-shield-500">
                              <option value="hours">{tx("Hours")}</option>
                              <option value="days">{tx("Days")}</option>
                              <option value="weeks">{tx("Weeks")}</option>
                            </select>
                          </div>
                        )}
                        {!comp.enabled && (
                          <span className="text-[11px] text-slate-500">{tx("Optional")}</span>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="text-slate-500 text-[11px] pt-1">
          {tx("💡 Timer applies to local accounts from their creation timestamp. Once the timer elapses, users must enroll before accessing their dashboard.")}
        </p>
      </div>

      {/* 2. Authenticator Attachment */}
      <Field
        label={tx("Allowed Authenticator Types")}
        hint={tx("Choose whether administrators can enroll external security keys, platform biometrics, or both.")}
      >
        <div className="relative">
          <select
            value={config.authenticator_attachment || 'any'}
            onChange={e => setConfig(c => ({ ...c, authenticator_attachment: e.target.value }))}
            className={inp + ' appearance-none pe-7'}
          >
            <option value="any">{tx("Any Authenticator (External Keys + Mac Touch ID + iPhone/Android QR scan) — Recommended")}</option>
            <option value="cross-platform">{tx("External Hardware Keys Only (YubiKey / Titan)")}</option>
            <option value="platform">{tx("Built-in Platform Biometrics Only (Mac Touch ID / Windows Hello)")}</option>
          </select>
          <ChevronDown size={11} className="absolute end-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
        </div>
      </Field>

      {/* Contextual support warning/explanation for Authenticator Attachment */}
      <div className={`p-3 rounded-lg border text-xs ${
        config.authenticator_attachment === 'any'
          ? 'bg-blue-900/10 border-blue-800/60 text-blue-300'
          : 'bg-amber-900/15 border-amber-800/80 text-amber-300'
      }`}>
        <p className="font-semibold mb-0.5">
          {config.authenticator_attachment === 'any' ? tx("Broad Compatibility (Recommended)") : tx("Service Support & Restriction Notice")}
        </p>
        <p className="opacity-90">
          {config.authenticator_attachment === 'any' && (
            descriptions?.authenticator_attachment?.any ||
            tx("Allows both roaming USB/NFC hardware security keys (YubiKey, Titan) and built-in platform authenticators (Apple Touch ID, Windows Hello). Staff on any device can enroll their preferred hardware factor.")
          )}
          {config.authenticator_attachment === 'cross-platform' && (
            descriptions?.authenticator_attachment?.['cross-platform'] ||
            tx("Requires external roaming hardware keys. Restricts built-in platform authenticators like Mac Touch ID. If selected, staff on laptops without a physical USB/NFC key cannot enroll biometrics.")
          )}
          {config.authenticator_attachment === 'platform' && (
            descriptions?.authenticator_attachment?.platform ||
            tx("Requires built-in device biometrics (Apple Touch ID, Windows Hello). Restricts external USB/NFC security keys. If selected, staff using desktop workstations or external keyboards without built-in sensors cannot enroll.")
          )}
        </p>
      </div>

      {/* 2. User Verification */}
      <Field
        label={tx("User Verification Requirement")}
        hint={tx("Specifies whether PIN or biometric verification is required when authenticating with a security key.")}
      >
        <div className="relative">
          <select
            value={config.user_verification || 'preferred'}
            onChange={e => setConfig(c => ({ ...c, user_verification: e.target.value }))}
            className={inp + ' appearance-none pe-7'}
          >
            <option value="preferred">{tx("Preferred (PIN / Biometric asked if supported) — Recommended")}</option>
            <option value="required">{tx("Strictly Required (Mandatory PIN or Fingerprint / Touch ID)")}</option>
            <option value="discouraged">{tx("Discouraged (Capacitive presence touch only, no PIN)")}</option>
          </select>
          <ChevronDown size={11} className="absolute end-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
        </div>
      </Field>

      {/* Contextual support warning/explanation for User Verification */}
      <div className={`p-3 rounded-lg border text-xs ${
        config.user_verification === 'preferred'
          ? 'bg-blue-900/10 border-blue-800/60 text-blue-300'
          : 'bg-amber-900/15 border-amber-800/80 text-amber-300'
      }`}>
        <p className="font-semibold mb-0.5">
          {config.user_verification === 'preferred' ? tx("Usability & Security Balance") : tx("Verification Impact")}
        </p>
        <p className="opacity-90">
          {config.user_verification === 'preferred' && (
            descriptions?.user_verification?.preferred ||
            tx("Prompts for PIN or biometric verification (e.g. YubiKey Bio fingerprint, Touch ID, or security key PIN) if the key supports it, but does not block keys without PINs.")
          )}
          {config.user_verification === 'required' && (
            descriptions?.user_verification?.required ||
            tx("Strictly mandates PIN or biometric verification. Basic U2F keys or hardware keys without a configured PIN will fail authentication and cannot sign in.")
          )}
          {config.user_verification === 'discouraged' && (
            descriptions?.user_verification?.discouraged ||
            tx("Only checks physical presence (a basic capacitive touch). Does not require biometric or PIN verification.")
          )}
        </p>
      </div>

      {/* 3. NIST FIPS 140-2 / FIPS 140-3 Validation */}
      <div className="space-y-2 pt-1">
        <label className="flex items-center gap-2 cursor-pointer">
          <div
            onClick={() => setConfig(c => ({ ...c, fips_only: !c.fips_only }))}
            className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${config.fips_only ? 'bg-purple-600' : 'bg-slate-700'}`}>
            <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.fips_only ? 'translate-x-4 rtl:-translate-x-4' : 'translate-x-0.5 rtl:-translate-x-0.5'}`} />
          </div>
          <span className="text-slate-300 text-sm font-medium">{tx("Enforce NIST FIPS 140-2 / FIPS 140-3 Validated Keys")}</span>
        </label>

        {config.fips_only && (
          <div className="p-3 bg-purple-950/30 border border-purple-800/80 rounded-lg text-xs text-purple-300 space-y-1">
            <p className="font-semibold flex items-center gap-1.5">
              <ShieldAlert size={14} className="text-purple-400" />{" "}{tx("High-Security Institutional Compliance Active")}
            </p>
            <p className="opacity-90">
              {tx("When enabled, OpenOptOut verifies cryptographic Authenticator Attestation GUIDs (AAGUIDs) against certified YubiKey FIPS hardware (YubiKey 5 NFC FIPS, 5C FIPS, 5Ci FIPS, 5 Series FIPS 140-3).")}
            </p>
            <p className="text-amber-300 font-medium pt-1">
              {tx("⚠ Service Support Restriction: Consumer YubiKeys, Google Titan keys, and Apple Mac Touch ID will be REJECTED during registration. Only enroll this if your organization issues certified FIPS 140 tokens.")}
            </p>
          </div>
        )}
      </div>

      <div className="flex justify-end pt-2">
        <SaveButton saving={saving} saved={saved} onClick={save} />
      </div>
    </Section>
  )
}

// ── Institutional Passwordless Authentication Policy (Super Admin) ───────────
function PasswordlessPolicySection({ userRole }) {
  if (userRole !== 'super_admin') return null

  const [config, setConfig] = useState({
    enabled: false,
    allow_passkey: true,
    allow_magic_link: true,
    enforce_passwordless_local: false,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/settings/security/passwordless')
      .then(r => {
        if (r.data?.config) setConfig(r.data.config)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setError('')
    setSaving(true)
    try {
      const res = await api.patch('/settings/security/passwordless', config)
      if (res.data?.config) setConfig(res.data.config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (err) {
      setError(detailText(err) || tx("Failed to save passwordless authentication settings."))
    } finally {
      setSaving(false)
    }
  }

  if (loading) return null

  return (
    <Section
      icon={Fingerprint}
      title={tx("Passwordless Authentication Policy")}
      description={tx("Configure passwordless sign-in methods (FIDO2 Passkeys and one-time email codes) for local user and staff accounts.")}
      adminOnly
      userRole={userRole}
    >
      {error && (
        <div className="p-3 bg-red-950/40 border border-red-800/80 rounded-lg text-xs text-red-300 flex items-center gap-2">
          <AlertTriangle size={14} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Scope banner */}
      <div className="p-3 bg-slate-900/60 border border-slate-700/60 rounded-lg text-xs text-slate-300 space-y-1">
        <p className="font-semibold text-slate-200 flex items-center gap-1.5">
          <Info size={14} className="text-shield-400" />{" "}{tx("Local Accounts Scope Notice")}
        </p>
        <p className="text-slate-400">
          {tx("Passwordless policies strictly govern local accounts. Accounts authenticated via 3rd-party identity providers (LDAP, SIP2, SAML, Google/Microsoft OIDC) continue to rely on their external identity providers as their source of truth.")}
        </p>
      </div>

      {/* Master Enable */}
      <div className="flex items-center justify-between py-2 border-b border-slate-700/40">
        <div>
          <p className="text-sm font-medium text-slate-200">{tx("Enable Passwordless Authentication")}</p>
          <p className="text-xs text-slate-400">{tx("Permit local staff and users to sign in without entering an account password.")}</p>
        </div>
        <input
          type="checkbox"
          checked={!!config.enabled}
          onChange={e => setConfig(c => ({ ...c, enabled: e.target.checked }))}
          className="rounded border-slate-600 bg-slate-800 text-shield-500 focus:ring-shield-500 w-4 h-4 cursor-pointer"
        />
      </div>

      {config.enabled && (
        <div className="space-y-3 pt-2 ps-2">
          {/* FIDO2 / WebAuthn Passkeys */}
          <div className="flex items-center justify-between py-1.5">
            <div>
              <p className="text-xs font-medium text-slate-200">{tx("FIDO2 / WebAuthn Passkeys")}</p>
              <p className="text-[11px] text-slate-400">{tx("Allow Touch ID, Face ID, Windows Hello, and hardware security keys (YubiKey).")}</p>
            </div>
            <input
              type="checkbox"
              checked={!!config.allow_passkey}
              onChange={e => setConfig(c => ({ ...c, allow_passkey: e.target.checked }))}
              className="rounded border-slate-600 bg-slate-800 text-shield-500 focus:ring-shield-500 w-4 h-4 cursor-pointer"
            />
          </div>

          {/* Email One-Time Codes */}
          <div className="flex items-center justify-between py-1.5">
            <div>
              <p className="text-xs font-medium text-slate-200">{tx("Email Verification Codes / Magic Links")}</p>
              <p className="text-[11px] text-slate-400">{tx("Allow single-use 6-digit codes sent directly to the user's registered inbox.")}</p>
            </div>
            <input
              type="checkbox"
              checked={!!config.allow_magic_link}
              onChange={e => setConfig(c => ({ ...c, allow_magic_link: e.target.checked }))}
              className="rounded border-slate-600 bg-slate-800 text-shield-500 focus:ring-shield-500 w-4 h-4 cursor-pointer"
            />
          </div>

          {/* Enforce Passwordless (Disables password login for local accounts) */}
          <div className="flex items-center justify-between py-1.5 pt-2 border-t border-slate-700/40">
            <div>
              <p className="text-xs font-medium text-amber-300">{tx("Enforce Passwordless for Local Accounts")}</p>
              <p className="text-[11px] text-slate-400">{tx("Disables standard password inputs on the login form for local users.")}</p>
            </div>
            <input
              type="checkbox"
              checked={!!config.enforce_passwordless_local}
              onChange={e => setConfig(c => ({ ...c, enforce_passwordless_local: e.target.checked }))}
              className="rounded border-slate-600 bg-slate-800 text-amber-500 focus:ring-amber-500 w-4 h-4 cursor-pointer"
            />
          </div>
        </div>
      )}

      <div className="flex justify-end pt-2">
        <SaveButton saving={saving} saved={saved} onClick={save} />
      </div>
    </Section>
  )
}

// ── Role-Based Session Duration & Remember Me Policy (Super Admin) ────────────
function SessionPolicySection({ userRole }) {
  if (userRole !== 'super_admin') return null

  const [policy, setPolicy] = useState({
    remember_me_enabled: true,
    roles: {
      super_admin: { session_duration_hours: 8, remember_me_allowed: true, remember_me_mode: 'username_only', remember_me_duration_days: 1 },
      manager:     { session_duration_hours: 8, remember_me_allowed: true, remember_me_mode: 'username_only', remember_me_duration_days: 3 },
      parent:      { session_duration_hours: 24, remember_me_allowed: true, remember_me_mode: 'extend_session', remember_me_duration_days: 30 },
      member:      { session_duration_hours: 24, remember_me_allowed: true, remember_me_mode: 'extend_session', remember_me_duration_days: 30 },
    },
  })
  const [activeTab, setActiveTab] = useState('super_admin')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  const roleLabels = {
    super_admin: tx("Super Admin"),
    manager: tx("Manager / Staff"),
    parent: tx("User / Parent"),
    member: tx("Patron / Member"),
  }

  useEffect(() => {
    api.get('/settings/security/session-policy')
      .then(r => {
        if (r.data?.policy) setPolicy(r.data.policy)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setError('')
    setSaving(true)
    try {
      const res = await api.patch('/settings/security/session-policy', policy)
      if (res.data?.policy) setPolicy(res.data.policy)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (err) {
      setError(detailText(err) || tx("Failed to save session duration and remember-me policies."))
    } finally {
      setSaving(false)
    }
  }

  if (loading) return null

  const curRoleCfg = policy.roles?.[activeTab] || {
    session_duration_hours: 8,
    remember_me_allowed: true,
    remember_me_mode: 'username_only',
    remember_me_duration_days: 1,
  }

  const updateCurrentRole = updates => {
    setPolicy(prev => ({
      ...prev,
      roles: {
        ...prev.roles,
        [activeTab]: {
          ...(prev.roles?.[activeTab] || {}),
          ...updates,
        },
      },
    }))
  }

  return (
    <Section
      icon={Clock}
      title={tx("Session Duration & Remember Me Policy")}
      description={tx("Configure standard session duration and role-specific Remember Me behavior (prefilling username vs extending session).")}
      adminOnly
      userRole={userRole}
    >
      {error && (
        <div className="p-3 bg-red-950/40 border border-red-800/80 rounded-lg text-xs text-red-300 flex items-center gap-2">
          <AlertTriangle size={14} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Global Remember Me Kill Switch */}
      <div className="flex items-center justify-between py-2 border-b border-slate-700/40">
        <div>
          <p className="text-sm font-medium text-slate-200">{tx("Global \"Remember Me\" Feature")}</p>
          <p className="text-xs text-slate-400">{tx("Master switch: when disabled, Remember Me checkboxes are hidden across the entire system.")}</p>
        </div>
        <input
          type="checkbox"
          checked={!!policy.remember_me_enabled}
          onChange={e => setPolicy(p => ({ ...p, remember_me_enabled: e.target.checked }))}
          className="rounded border-slate-600 bg-slate-800 text-shield-500 focus:ring-shield-500 w-4 h-4 cursor-pointer"
        />
      </div>

      {/* Role Tabs */}
      <div className="pt-3">
        <div className="flex border-b border-slate-700/60 gap-1 overflow-x-auto">
          {Object.entries(roleLabels).map(([rk, label]) => (
            <button
              key={rk}
              type="button"
              onClick={() => setActiveTab(rk)}
              className={`px-3 py-1.5 text-xs font-medium rounded-t-lg transition-colors whitespace-nowrap ${
                activeTab === rk
                  ? 'bg-slate-700 text-white border-t border-x border-slate-600'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Selected Role Configuration Card */}
        <div className="p-4 bg-slate-900/50 rounded-b-lg border-x border-b border-slate-700/60 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Standard Session Duration */}
            <div>
              <label className={labelCls}>{tx("Standard Session Lifetime (Hours)")}</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="1"
                  max="720"
                  value={curRoleCfg.session_duration_hours ?? 8}
                  onChange={e => {
                    const v = Math.max(1, parseInt(e.target.value, 10) || 1)
                    updateCurrentRole({ session_duration_hours: v })
                  }}
                  className={inp}
                />
                <span className="text-xs text-slate-400 shrink-0">{tx("hours")}</span>
              </div>
              <p className="text-[11px] text-slate-500 mt-1">{tx("How long people stay signed in if they don't tick \"Remember me\".")}</p>
            </div>

            {/* Idle Timeout */}
            <div>
              <label className={labelCls}>{tx("Idle Timeout (Minutes)")}</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="0"
                  max="1440"
                  value={curRoleCfg.idle_timeout_minutes ?? 0}
                  onChange={e => {
                    const v = Math.max(0, parseInt(e.target.value, 10) || 0)
                    updateCurrentRole({ idle_timeout_minutes: v })
                  }}
                  className={inp}
                />
                <span className="text-xs text-slate-400 shrink-0">{tx("minutes")}</span>
              </div>
              <p className="text-[11px] text-slate-500 mt-1">{tx("Sign out automatically after this long with no activity, even within the session lifetime above. 0 disables it.")}</p>
            </div>

            {/* Remember Me Allowed */}
            <div>
              <label className={labelCls}>{tx("Remember Me Allowed for Role")}</label>
              <div className="flex items-center h-10">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!curRoleCfg.remember_me_allowed}
                    onChange={e => updateCurrentRole({ remember_me_allowed: e.target.checked })}
                    className="rounded border-slate-600 bg-slate-800 text-shield-500 focus:ring-shield-500 w-4 h-4 cursor-pointer"
                  />
                  <span className="text-xs text-slate-300">{tx("Allow this role to use Remember Me")}</span>
                </label>
              </div>
            </div>
          </div>

          {curRoleCfg.remember_me_allowed && policy.remember_me_enabled && (
            <div className="pt-3 border-t border-slate-800/80 grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Remember Me Mode */}
              <div>
                <label className={labelCls}>{tx("Remember Me Mode")}</label>
                <select
                  value={curRoleCfg.remember_me_mode || 'username_only'}
                  onChange={e => updateCurrentRole({ remember_me_mode: e.target.value })}
                  className={inp}
                >
                  <option value="username_only">{tx("Save Username Only (Recommended for Staff/Admin)")}</option>
                  <option value="extend_session">{tx("Extend Active Session (Recommended for Patrons/Users)")}</option>
                </select>
                <p className="text-[11px] text-slate-500 mt-1">
                  {curRoleCfg.remember_me_mode === 'username_only'
                    ? tx("Device only saves email/username for quick prefill; session lifetime remains short.")
                    : tx("Device retains an active signed JWT login session for the configured days.")}
                </p>
              </div>

              {/* Extended Session Duration (Days) */}
              <div>
                <label className={labelCls}>
                  {curRoleCfg.remember_me_mode === 'extend_session'
                    ? tx("Extended Session Lifetime (Days)")
                    : tx("Device Prefill Retention (Days)")}
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min="1"
                    max="30"
                    value={curRoleCfg.remember_me_duration_days ?? 30}
                    onChange={e => {
                      const v = Math.min(30, Math.max(1, parseInt(e.target.value, 10) || 1))
                      updateCurrentRole({ remember_me_duration_days: v })
                    }}
                    className={inp}
                  />
                  <span className="text-xs text-slate-400 shrink-0">{tx("days")}</span>
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  {curRoleCfg.remember_me_mode === 'extend_session'
                    ? tx("How long you stay signed in on this device. 30 days is the maximum.")
                    : tx("Institutional recommendation for device credential cache. 30 days is the maximum.")}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="flex justify-end pt-2">
        <SaveButton saving={saving} saved={saved} onClick={save} />
      </div>
    </Section>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
// ── Unclear matches ──────────────────────────────────────────────────────────
// Some sites list several people with your name and hide the city and age, so
// there's no way to tell which one is you. Admins pick what happens; people can
// pick for themselves if the admin allows it.
const MATCH_HELP = {
  ask: tx("They go on your Checklist with whatever the site does show, and you tick the ones that are you."),
  skip: tx("OpenOptOut leaves them alone and marks the site skipped. Nothing is sent about people who might not be you."),
  remove_all: tx("OpenOptOut asks the site to remove every one (up to 10 per site). This may include other people with the same name."),
}

function ChoiceList({ name, value, onChange, choices, extra }) {
  return (
    <fieldset className="space-y-2">
      <legend className="sr-only">{name}</legend>
      {extra}
      {choices.map(c => (
        <label key={c.value} className="flex items-start gap-2 cursor-pointer">
          <input type="radio" name={name} value={c.value} checked={value === c.value}
            onChange={() => onChange(c.value)} className="mt-1" />
          <span>
            <span className="text-slate-200 text-sm">{c.label}</span>
            <span className="block text-slate-500 text-xs">{MATCH_HELP[c.value]}</span>
          </span>
        </label>
      ))}
    </fieldset>
  )
}

function MatchingSection() {
  const [m, setM] = useState(null)
  const [def, setDef] = useState('ask')
  const [usersChoose, setUsersChoose] = useState(true)
  const [mine, setMine] = useState('')
  const [msg, setMsg] = useState('')

  const load = () => api.get('/settings/matching').then(r => {
    setM(r.data); setDef(r.data.unclear_listings); setUsersChoose(r.data.users_choose); setMine(r.data.mine || '')
  }).catch(() => setM(false))
  useEffect(() => { load() }, [])
  if (!m) return null

  const saveDefault = async () => {
    setMsg('')
    try { await api.patch('/settings/matching', { unclear_listings: def, users_choose: usersChoose }); setMsg(tx("Saved.")); load() }
    catch (e) { setMsg(detailText(e) || tx("Couldn't save that.")) }
  }
  const saveMine = async v => {
    setMine(v); setMsg('')
    try { await api.patch('/settings/matching/mine', { unclear_listings: v || null }); setMsg(tx("Saved.")); load() }
    catch (e) { setMsg(detailText(e) || tx("Couldn't save that.")) }
  }
  const defaultLabel = (m.choices.find(c => c.value === m.unclear_listings) || {}).label

  return (
    <Section icon={Users} title={tx("When a site shows only a name")}
      description={tx("Some sites list people with your name but hide the city and age, so we can't tell which one is you")}>
      {msg && <p role="status" className="text-slate-300 text-sm">{msg}</p>}
      {m.can_set_default && (
        <div className="space-y-3">
          <p className="text-slate-300 text-sm font-medium">{tx("For everyone (default)")}</p>
          <ChoiceList name="match-default" value={def} onChange={setDef} choices={m.choices} />
          <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
            <input type="checkbox" checked={usersChoose} onChange={e => setUsersChoose(e.target.checked)} />
            {tx("Let people choose this for themselves")}
          </label>
          <SaveButton onClick={saveDefault} />
        </div>
      )}
      {m.users_choose ? (
        <div className="space-y-3 pt-2">
          <p className="text-slate-300 text-sm font-medium">{tx("For me and the people I manage")}</p>
          <ChoiceList name="match-mine" value={mine} onChange={saveMine} choices={m.choices}
            extra={
              <label className="flex items-start gap-2 cursor-pointer">
                <input type="radio" name="match-mine" value="" checked={mine === ''} onChange={() => saveMine('')} className="mt-1" />
                <span className="text-slate-200 text-sm">{tx("Use the default ({defaultLabel})", { defaultLabel })}</span>
              </label>
            } />
        </div>
      ) : (
        !m.can_set_default && <p className="text-slate-400 text-sm">{tx("Your administrator has set this for everyone: {defaultLabel}.", { defaultLabel })}</p>
      )}
    </Section>
  )
}

function HstsSection({ userRole }) {
  const [enabled, setEnabled] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const isAdmin = userRole === 'super_admin'

  useEffect(() => {
    if (!isAdmin) return
    api.get('/settings/security/hsts').then(r => {
      setEnabled(!!r.data.enabled)
    }).catch(() => {})
  }, [isAdmin])

  if (!isAdmin) return null

  const save = async () => {
    setSaving(true)
    try {
      const r = await api.patch('/settings/security/hsts', { enabled })
      setEnabled(!!r.data.enabled)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Section icon={Lock} title={tx("HTTP Strict Transport Security (HSTS)")}
      description={tx("Require browsers to connect only over HTTPS")}
      adminOnly userRole={userRole}>
      <label className="flex items-start gap-2.5 cursor-pointer">
        <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} className="mt-1 accent-shield-500" />
        <div>
          <span className="text-slate-200 text-sm font-medium block">{tx("Enable HSTS (HTTP Strict Transport Security)")}</span>
          <span className="text-slate-400 text-xs block mt-0.5">
            {tx("Tells browsers to always connect to this site over HTTPS and refuse plain HTTP connections. Enable this when your SSL certificate is active or handled by an external service.")}
          </span>
        </div>
      </label>
      <div className="flex justify-end pt-2">
        <SaveButton saving={saving} saved={saved} onClick={save} />
      </div>
    </Section>
  )
}

function ClientMtlsSection({ userRole }) {
  const isAdmin = userRole === 'super_admin'
  const [data, setData] = useState(null)
  const [enabled, setEnabled] = useState(false)
  const [mode, setMode] = useState('require')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')
  const [showIssueModal, setShowIssueModal] = useState(false)
  const [showCaModal, setShowCaModal] = useState(false)
  const [caPemInput, setCaPemInput] = useState('')

  const [devName, setDevName] = useState('')
  const [devPass, setDevPass] = useState('')
  const [devDays, setDevDays] = useState(365)
  const [issuing, setIssuing] = useState(false)
  const [issueResult, setIssueResult] = useState(null)

  const reload = () => {
    if (!isAdmin) return
    api.get('/settings/security/mtls').then(r => {
      setData(r.data)
      setEnabled(!!r.data.enabled)
      setMode(r.data.mode || 'require')
    }).catch(() => {})
  }

  useEffect(() => {
    reload()
  }, [isAdmin])

  if (!isAdmin) return null

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const r = await api.patch('/settings/security/mtls', { enabled, mode })
      setData(r.data)
      setEnabled(!!r.data.enabled)
      setMode(r.data.mode || 'require')
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(detailText(e) || tx("Failed to save mTLS settings"))
    } finally {
      setSaving(false)
    }
  }

  const initCa = async (caPem = null) => {
    setError('')
    try {
      const r = await api.post('/settings/security/mtls/ca', { ca_pem: caPem || null })
      setData(r.data)
      setShowCaModal(false)
      setCaPemInput('')
    } catch (e) {
      setError(detailText(e) || tx("Failed to initialize CA"))
    }
  }

  const issueCert = async (e) => {
    e.preventDefault()
    if (!devName.trim()) return
    setIssuing(true)
    setError('')
    try {
      const r = await api.post('/settings/security/mtls/mint', {
        device_name: devName.trim(),
        password: devPass,
        days: Number(devDays) || 365,
      })
      const b64 = r.data.p12_base64
      const filename = r.data.filename || `${devName.trim()}.p12`
      const a = document.createElement('a')
      a.href = `data:application/x-pkcs12;base64,${b64}`
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)

      setIssueResult(r.data)
      setDevName('')
      setDevPass('')
      reload()
    } catch (err) {
      setError(detailText(err) || tx("Failed to issue client certificate"))
    } finally {
      setIssuing(false)
    }
  }

  const revokeCert = async (target) => {
    if (!window.confirm(tx("Revoke this client certificate? The device will no longer be able to connect."))) return
    setError('')
    try {
      await api.post('/settings/security/mtls/revoke', { serial_or_name: target })
      reload()
    } catch (err) {
      setError(detailText(err) || tx("Failed to revoke certificate"))
    }
  }

  const copyCmd = (text, id) => {
    navigator.clipboard.writeText(text)
    setCopied(id)
    setTimeout(() => setCopied(''), 2000)
  }

  const caStatus = data?.ca_status

  return (
    <Section icon={ShieldCheck} title={tx("Client-Certificate Authentication (mTLS)")}
      description={tx("Require devices to present a client certificate signed by your local CA before reaching OpenOptOut")}
      adminOnly userRole={userRole}>
      <div className="space-y-4">
        {error && (
          <div role="alert" className="p-3 rounded-lg border border-red-800 bg-red-950/40 text-red-300 text-xs flex items-start gap-2">
            <AlertTriangle size={14} className="shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <label className="flex items-start gap-2.5 cursor-pointer">
          <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} className="mt-1 accent-shield-500" />
          <div>
            <span className="text-slate-200 text-sm font-medium block">{tx("Enable Client-Certificate Authentication (mTLS)")}</span>
            <span className="text-slate-400 text-xs block mt-0.5">
              {tx("When enabled on your reverse proxy, only devices with a client certificate installed in their OS or browser keystore can reach the site. Unauthenticated requests are dropped at the TLS handshake.")}
            </span>
          </div>
        </label>

        {enabled && (
          <div className="ps-6 space-y-3">
            <div>
              <label className={labelCls}>{tx("Verification Mode")}</label>
              <select className={inp} value={mode} onChange={e => setMode(e.target.value)}>
                <option value="require">{tx("Require certificate (strict — drop unauthenticated connections)")}</option>
                <option value="optional">{tx("Optional certificate (accept if presented — useful for healthchecks)")}</option>
              </select>
            </div>

            <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-700/60 space-y-2">
              <span className="text-slate-300 text-xs font-medium block">
                {tx("Host proxy setup command")}
              </span>
              <p className="text-slate-400 text-xs">
                {tx("Run this command on your host server to configure Caddy or Traefik:")}
              </p>
              <div className="flex items-center justify-between gap-2 bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 font-mono text-xs text-slate-300">
                <span className="truncate">{data?.commands?.linux || "./scripts/enable-https.sh --client-mtls"}</span>
                <button type="button" onClick={() => copyCmd(data?.commands?.linux || "./scripts/enable-https.sh --client-mtls", 'linux')}
                  className="shrink-0 text-slate-400 hover:text-white" title={tx("Copy command")}>
                  {copied === 'linux' ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="p-3.5 rounded-lg border border-slate-700 bg-slate-800/40 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-slate-200 text-sm font-medium flex items-center gap-1.5">
              <Key size={14} className="text-shield-400" />
              {tx("Local Certificate Authority (CA)")}
            </span>
            {caStatus && caStatus.level !== 'error' ? (
              <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${caStatus.level === 'ok' ? 'bg-emerald-950 border border-emerald-700 text-emerald-300' : 'bg-amber-950 border border-amber-700 text-amber-300'}`}>
                {caStatus.level === 'ok' ? tx("Active") : tx("Expires soon")}
              </span>
            ) : (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
                {tx("Not configured")}
              </span>
            )}
          </div>

          {caStatus && caStatus.level !== 'error' ? (
            <div className="text-xs space-y-1 text-slate-300">
              <div className="flex justify-between">
                <span className="text-slate-400">{tx("Subject:")}</span>
                <span className="font-mono">{caStatus.subject || "OpenOptOut Client CA"}</span>
              </div>
              {caStatus.fingerprint && (
                <div className="flex justify-between">
                  <span className="text-slate-400">{tx("SHA-256:")}</span>
                  <span className="font-mono text-[11px] truncate max-w-[280px]" title={caStatus.fingerprint}>{caStatus.fingerprint}</span>
                </div>
              )}
              {caStatus.not_after && (
                <div className="flex justify-between">
                  <span className="text-slate-400">{tx("Valid until:")}</span>
                  <span>{fmtDate(caStatus.not_after)} ({caStatus.days_left} {tx("days")})</span>
                </div>
              )}
            </div>
          ) : (
            <p className="text-slate-400 text-xs">
              {tx("No Client CA has been created yet. You can create one here or manage it offline with scripts/openoptout-mtls.sh.")}
            </p>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            {(!caStatus || caStatus.level === 'error') ? (
              <>
                <button type="button" onClick={() => initCa()}
                  className="px-2.5 py-1 text-xs bg-shield-600 hover:bg-shield-500 text-white rounded-md font-medium">
                  {tx("Create Local CA")}
                </button>
                <button type="button" onClick={() => setShowCaModal(true)}
                  className="px-2.5 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md font-medium">
                  {tx("Upload CA Certificate")}
                </button>
              </>
            ) : data?.can_mint_in_app && (
              <button type="button" onClick={() => { setShowIssueModal(true); setIssueResult(null) }}
                className="px-2.5 py-1 text-xs bg-shield-600 hover:bg-shield-500 text-white rounded-md font-medium flex items-center gap-1">
                <Plus size={13} />
                {tx("Issue Device Certificate")}
              </button>
            )}
          </div>
        </div>

        {data?.clients?.length > 0 && (
          <div className="space-y-2">
            <span className="text-slate-300 text-xs font-medium block">
              {tx("Issued Client Certificates ({count})", { count: data.clients.length })}
            </span>
            <div className="overflow-x-auto rounded-lg border border-slate-700">
              <table className="w-full text-start text-xs text-slate-300">
                <thead className="bg-slate-800 text-slate-400">
                  <tr>
                    <th className="py-2 px-3 text-start font-medium">{tx("Device / Name")}</th>
                    <th className="py-2 px-3 text-start font-medium">{tx("Serial")}</th>
                    <th className="py-2 px-3 text-start font-medium">{tx("Issued")}</th>
                    <th className="py-2 px-3 text-start font-medium">{tx("Status")}</th>
                    <th className="py-2 px-3 text-end font-medium">{tx("Action")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {data.clients.map((c, i) => (
                    <tr key={c.id || i} className="hover:bg-slate-800/40">
                      <td className="py-2 px-3 font-medium text-white">{c.name}</td>
                      <td className="py-2 px-3 font-mono text-[11px] text-slate-400">{c.serial}</td>
                      <td className="py-2 px-3 text-slate-400">{c.issued_at ? fmtDate(c.issued_at) : '—'}</td>
                      <td className="py-2 px-3">
                        <span className={`px-1.5 py-0.5 rounded-sm text-[10px] uppercase font-semibold ${c.revoked ? 'bg-red-950 text-red-300 border border-red-800' : 'bg-emerald-950 text-emerald-300 border border-emerald-800'}`}>
                          {c.revoked ? tx("Revoked") : tx("Valid")}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-end">
                        {!c.revoked && (
                          <button type="button" onClick={() => revokeCert(c.id || c.serial)}
                            className="text-red-400 hover:text-red-300 text-xs font-medium">
                            {tx("Revoke")}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {showIssueModal && (
          <div className="p-4 rounded-lg border border-slate-700 bg-slate-800 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-white text-sm font-semibold">{tx("Issue Client Certificate")}</span>
              <button type="button" onClick={() => setShowIssueModal(false)} className="text-slate-400 hover:text-white">
                <X size={14} />
              </button>
            </div>
            {issueResult ? (
              <div className="space-y-3">
                <div className="p-3 rounded-lg border border-emerald-700 bg-emerald-950/40 text-emerald-200 text-xs">
                  {tx("Client certificate issued and downloaded for {name}!", { name: issueResult.device_name })}
                </div>
                <div className="text-xs text-slate-300 space-y-1">
                  <span className="font-semibold text-white block">{tx("How to install on your device:")}</span>
                  <p>• {tx("macOS / iOS: Double-click the .p12 file to add it to Keychain Access or Profiles.")}</p>
                  <p>• {tx("Windows: Double-click the .p12 file, choose Current User -> Personal store.")}</p>
                  <p>• {tx("Linux / Firefox: Settings -> Privacy & Security -> View Certificates -> Import.")}</p>
                  <p>• {tx("Android: Settings -> Security -> Install from device storage -> VPN & app user certificate.")}</p>
                </div>
                <button type="button" onClick={() => { setShowIssueModal(false); setIssueResult(null) }}
                  className="px-3 py-1.5 text-xs bg-slate-700 text-white rounded-md">
                  {tx("Done")}
                </button>
              </div>
            ) : (
              <form onSubmit={issueCert} className="space-y-3">
                <div>
                  <label className={labelCls}>{tx("Device or User Name")}</label>
                  <input className={inp} value={devName} onChange={e => setDevName(e.target.value)}
                    placeholder={tx("e.g. Jordan's MacBook Pro")} required />
                </div>
                <div>
                  <label className={labelCls}>{tx("Bundle Password (optional)")}</label>
                  <input className={inp} type="password" value={devPass} onChange={e => setDevPass(e.target.value)}
                    placeholder={tx("Password protecting the .p12 file")} />
                </div>
                <div>
                  <label className={labelCls}>{tx("Validity (days)")}</label>
                  <input className={inp} type="number" value={devDays} onChange={e => setDevDays(e.target.value)}
                    min="1" max="1825" />
                </div>
                <div className="flex justify-end gap-2 pt-1">
                  <button type="button" onClick={() => setShowIssueModal(false)}
                    className="px-3 py-1.5 text-xs bg-slate-700 text-slate-300 rounded-md">
                    {tx("Cancel")}
                  </button>
                  <button type="submit" disabled={issuing || !devName.trim()}
                    className="px-3 py-1.5 text-xs bg-shield-600 hover:bg-shield-500 disabled:opacity-50 text-white rounded-md font-medium">
                    {issuing ? tx("Generating…") : tx("Mint & Download .p12")}
                  </button>
                </div>
              </form>
            )}
          </div>
        )}

        {showCaModal && (
          <div className="p-4 rounded-lg border border-slate-700 bg-slate-800 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-white text-sm font-semibold">{tx("Upload Existing CA Certificate")}</span>
              <button type="button" onClick={() => setShowCaModal(false)} className="text-slate-400 hover:text-white">
                <X size={14} />
              </button>
            </div>
            <p className="text-slate-400 text-xs">
              {tx("Paste your PEM-formatted CA certificate below. The private key will remain offline on your CA host.")}
            </p>
            <textarea className={`${inp} font-mono text-xs h-28`}
              placeholder="-----BEGIN CERTIFICATE-----..."
              value={caPemInput} onChange={e => setCaPemInput(e.target.value)} />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowCaModal(false)}
                className="px-3 py-1.5 text-xs bg-slate-700 text-slate-300 rounded-md">
                {tx("Cancel")}
              </button>
              <button type="button" onClick={() => initCa(caPemInput)} disabled={!caPemInput.trim()}
                className="px-3 py-1.5 text-xs bg-shield-600 hover:bg-shield-500 disabled:opacity-50 text-white rounded-md font-medium">
                {tx("Save CA Certificate")}
              </button>
            </div>
          </div>
        )}

        <div className="flex justify-end pt-2">
          <SaveButton saving={saving} saved={saved} onClick={save} />
        </div>
      </div>
    </Section>
  )
}

function MasterSecretKeySection({ userRole }) {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    if (userRole !== 'super_admin') return
    api.get('/settings/security/secret-key')
      .then(r => setStatus(r.data))
      .catch(() => {})
  }, [userRole])

  if (userRole !== 'super_admin') return null

  return (
    <Section icon={Key} title={tx("Master Secret Key & Entropy Generator")}
      description={tx("Generate or enter a 128+ character master key saved to secret.key and lock down its file permissions")}
      adminOnly userRole={userRole}>
      <SecretKeyGeneratorPanel status={status} onStatusChange={setStatus} />
    </Section>
  )
}

export default function Settings() {
  const { user } = useAuth()
  const [settings, setSettings]           = useState(null)
  const [memberConfigs, setMemberConfigs] = useState([])
  const [loading, setLoading]             = useState(true)

  // Sub-menu / tab navigation across the top
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window !== 'undefined') {
      const qTab = new URLSearchParams(window.location.search).get('tab')
      if (['general', 'security', 'lifecycle', 'automation', 'plugins'].includes(qTab)) {
        return qTab
      }
    }
    return 'general'
  })

  const [vaultLimits, setVaultLimits] = useState({ max_names: 4, max_addresses: 10, max_phones: 5, max_emails: 5 })

  useEffect(() => {
    const isParent = ['parent', 'manager', 'super_admin'].includes(user?.role)
    Promise.all([
      api.get('/settings'),
      isParent ? api.get('/scheduler/members') : Promise.resolve({ data: [] }),
      api.get('/settings/vault-limits'),
    ]).then(([s, m, v]) => {
      setSettings(s.data)
      setMemberConfigs(m.data)
      setVaultLimits(v.data)
    }).finally(() => setLoading(false))
  }, [user])

  const handleTabChange = (tabId) => {
    setActiveTab(tabId)
    if (typeof window !== 'undefined' && window.history?.replaceState) {
      const url = new URL(window.location.href)
      url.searchParams.set('tab', tabId)
      window.history.replaceState({}, '', url.toString())
    }
  }

  if (loading) return <div className="p-4 md:p-6"><p className="text-slate-500 text-sm">{tx("Loading…")}</p></div>

  // A manager holding the section's permission gets its admin controls.
  const sectionRole = perm => (can(user, perm) ? 'super_admin' : user?.role)

  const TABS = [
    { id: 'general', label: tx("General"), icon: Palette },
    { id: 'security', label: tx("Access & Security"), icon: Shield },
    { id: 'lifecycle', label: tx("Data Lifecycle"), icon: Database },
    { id: 'automation', label: tx("Automation"), icon: Bot },
    { id: 'plugins', label: tx("Plugins"), icon: Puzzle },
  ]

  return (
    <div className="p-4 md:p-6 max-w-3xl">
      <div className="mb-6">
        <h1 className="text-white text-xl font-semibold">{tx("Settings")}</h1>
        <p className="text-slate-400 text-sm mt-0.5">{tx("Configure how OpenOptOut looks and behaves")}</p>
      </div>

      {/* ── Sub-menu tabs across the top ── */}
      <nav role="tablist" aria-label={tx("Settings categories")} className="flex items-center gap-1.5 border-b border-slate-700/60 pb-2 mb-6 overflow-x-auto scrollbar-none">
        {TABS.map(tab => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              aria-controls={`panel-${tab.id}`}
              id={`tab-${tab.id}`}
              onClick={() => handleTabChange(tab.id)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap focus:outline-hidden ${
                isActive
                  ? 'bg-shield-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Icon size={16} className={isActive ? 'text-white' : 'text-slate-400'} />
              <span>{tab.label}</span>
            </button>
          )
        })}
      </nav>

      {/* ── Tab Panels ── */}
      {activeTab === 'general' && (
        <div role="tabpanel" id="panel-general" aria-labelledby="tab-general" className="space-y-4">
          <AppearanceSection initial={settings?.appearance ?? {}} onSaved={a => setSettings(s=>({...s,appearance:a}))} userRole={sectionRole('branding.manage')}/>
          <RegionalSection userRole={sectionRole('settings.system')}/>
          <VaultLimitsSection
            initial={vaultLimits}
            userRole={sectionRole('settings.system')}
            onSaved={v => setVaultLimits(v)}
          />
        </div>
      )}

      {activeTab === 'security' && (
        <div role="tabpanel" id="panel-security" aria-labelledby="tab-security" className="space-y-4">
          <MfaAccountSection user={user} />
          <ActiveSessionsSection user={user} />
          <WebAuthnPolicySection userRole={user?.role} />
          <PasswordlessPolicySection userRole={user?.role} />
          <SessionPolicySection userRole={user?.role} />
          <MasterSecretKeySection userRole={sectionRole('settings.system')} />
          <HstsSection userRole={sectionRole('settings.system')} />
          <ClientMtlsSection userRole={sectionRole('settings.system')} />
        </div>
      )}

      {activeTab === 'lifecycle' && (
        <div role="tabpanel" id="panel-lifecycle" aria-labelledby="tab-lifecycle" className="space-y-4">
          <DataLifecycleSection
            userRole={user?.role}
            initial={settings?.privacy ?? {}}
            onSaved={p => setSettings(s => ({ ...s, privacy: p }))}
          />
          <EncryptionSection userRole={sectionRole('database.view')}/>
        </div>
      )}

      {activeTab === 'automation' && (
        <div role="tabpanel" id="panel-automation" aria-labelledby="tab-automation" className="space-y-4">
          <EmailSection initial={settings?.email ?? {}} userRole={sectionRole('email.manage')}/>
          <SchedulerSection
            initial={settings?.scheduler ?? {}}
            memberConfigs={memberConfigs}
            onMemberConfigUpdate={updated => setMemberConfigs(mc => mc.map(x => x.member_id === updated.member_id ? updated : x))}
            userRole={sectionRole('scheduler.manage')}
            onSaved={s => setSettings(prev=>({...prev,scheduler:s}))}
          />
          <AutomationSection userRole={sectionRole('settings.system')}/>
          <ProxySection userRole={sectionRole('settings.system')}/>
          <MatchingSection />
        </div>
      )}

      {activeTab === 'plugins' && (
        <div role="tabpanel" id="panel-plugins" aria-labelledby="tab-plugins" className="space-y-4">
          <PluginSystemSection userRole={user?.role}/>
        </div>
      )}
    </div>
  )
}
