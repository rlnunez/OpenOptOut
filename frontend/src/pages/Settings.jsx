import { useEffect, useState, useRef } from 'react'
import {
  Palette, Mail, CalendarClock, Database, AlertTriangle, Shield, Bot, Info, Globe, Lock,
  Check, X, RefreshCw, TestTube, Eye, EyeOff, ChevronDown,
  Download, Trash2, Upload, Sun, Moon, Monitor, Play, Pause,
  Clock, Zap, RotateCcw, Users, Puzzle, Ban, ShieldCheck, Star, Plus
} from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'

// ── Shared ────────────────────────────────────────────────────────────────────
const inp = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-shield-500"
const labelCls = "text-slate-400 text-xs mb-1 block"

function Field({ label, hint, children }) {
  return (
    <div>
      <label className={labelCls}>{label}</label>
      {children}
      {hint && <p className="text-slate-600 text-xs mt-1">{hint}</p>}
    </div>
  )
}

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
        {locked && <span className="text-xs text-slate-600 border border-slate-700 px-2 py-0.5 rounded">admin only</span>}
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
      {saving ? 'Saving…' : saved ? 'Saved' : 'Save'}
    </button>
  )
}

function PasswordField({ label, hint, value, onChange, isSet }) {
  const [show, setShow] = useState(false)
  return (
    <Field label={label} hint={hint}>
      <div className="relative">
        <input type={show ? 'text' : 'password'} value={value} onChange={e => onChange(e.target.value)}
          placeholder={isSet ? '••••••••  (blank = keep current)' : 'Enter password…'}
          className={`${inp} pr-9`} />
        <button type="button" onClick={() => setShow(s => !s)}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
          {show ? <EyeOff size={13} /> : <Eye size={13} />}
        </button>
      </div>
    </Field>
  )
}

// ── Appearance ────────────────────────────────────────────────────────────────
const THEMES = [
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'system', label: 'System', icon: Monitor },
]
const ACCENT_PRESETS = [
  { color: '#6366f1', label: 'Indigo' }, { color: '#0ea5e9', label: 'Sky' },
  { color: '#10b981', label: 'Emerald' }, { color: '#f59e0b', label: 'Amber' },
  { color: '#ef4444', label: 'Red' }, { color: '#8b5cf6', label: 'Violet' },
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
    <Section icon={Palette} title="Appearance" description="Customize how the app looks for everyone" adminOnly userRole={userRole}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="App name">
          <input value={form.app_name ?? ''} onChange={e => setForm(f => ({...f, app_name: e.target.value}))}
            placeholder="OpenOptOut" className={inp} />
        </Field>
        <Field label="App icon" hint="PNG or SVG shown in sidebar">
          <div className="flex items-center gap-2">
            {form.app_icon_url && <img src={form.app_icon_url} alt="icon" className="w-8 h-8 rounded object-cover border border-slate-600" />}
            <button onClick={() => iconRef.current?.click()}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors">
              <Upload size={11} /> Upload
            </button>
            {form.app_icon_url && <button onClick={() => setForm(f => ({...f, app_icon_url: null}))} className="text-slate-600 hover:text-red-400"><X size={13} /></button>}
            <input ref={iconRef} type="file" accept="image/*" className="hidden" onChange={handleIconUpload} />
          </div>
        </Field>
      </div>
      <Field label="Theme">
        <div className="flex gap-2">
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
      <Field label="Accent color">
        <div className="flex items-center gap-2 flex-wrap">
          {ACCENT_PRESETS.map(p => (
            <button key={p.color} onClick={() => setForm(f => ({...f, accent_color: p.color}))} title={p.label}
              className={`w-7 h-7 rounded-full border-2 transition-all ${form.accent_color === p.color ? 'border-white scale-110' : 'border-transparent hover:scale-105'}`}
              style={{ background: p.color }} />
          ))}
          <div className="flex items-center gap-1.5 ml-1">
            <input type="color" value={form.accent_color ?? '#6366f1'} onChange={e => setForm(f => ({...f, accent_color: e.target.value}))}
              className="w-7 h-7 rounded cursor-pointer bg-transparent border-0" />
            <span className="text-slate-500 text-xs font-mono">{form.accent_color}</span>
          </div>
        </div>
      </Field>
      <div className="flex justify-end pt-1"><SaveButton saving={saving} saved={saved} onClick={save} /></div>
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
    catch (e) { setError(e.response?.data?.detail || 'Could not switch accounts') }
    finally { setBusy(false) }
  }

  const disconnect = async (ref) => {
    setBusy(true); setError('')
    try { await api.delete(`/email-oauth/accounts/${ref}`); load(); onChanged?.() }
    catch (e) { setError(e.response?.data?.detail || 'Could not disconnect') }
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
      setError(e.response?.data?.detail || 'Could not start the connect flow')
    } finally { setBusy(false) }
  }

  return (
    <div>
      <p className="text-slate-400 text-xs font-medium mb-2 uppercase tracking-wide">Connected accounts (OAuth)</p>
      {error && <div className="mb-2 px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs">{error}</div>}
      {loading ? (
        <p className="text-slate-500 text-xs">Loading…</p>
      ) : accounts.length === 0 ? (
        <p className="text-slate-500 text-xs mb-2">No OAuth account connected yet — connect one below (recommended for highest security), or configure SMTP/App Password below.</p>
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
                {a.expired && <span className="text-amber-400 text-xs shrink-0">token expired — will refresh on use</span>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {!a.active && (
                  <button onClick={() => activate(a.account_ref)} disabled={busy}
                    className="text-xs text-slate-400 hover:text-shield-300 disabled:opacity-40">Make active</button>
                )}
                <button onClick={() => disconnect(a.account_ref)} disabled={busy}
                  className="text-slate-500 hover:text-red-400 disabled:opacity-40" title="Disconnect">
                  <X size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {!adding ? (
        <button onClick={() => { setAdding(true); setError('') }} className="flex items-center gap-1.5 text-shield-400 hover:text-shield-300 text-xs">
          <Plus size={12} /> Connect {accounts.length ? 'another' : 'an'} account
        </button>
      ) : (
        <div className="px-3 py-2.5 rounded-lg border border-slate-700 bg-slate-800/40">
          <div className="flex items-center gap-2 mb-2">
            <select className={inp} value={addProvider} onChange={e => setAddProvider(e.target.value)}>
              <option value="gmail">Gmail / Google Workspace</option>
              <option value="outlook">Outlook / Microsoft 365</option>
              <option value="yahoo">Yahoo</option>
            </select>
          </div>
          <p className="text-slate-500 text-xs mb-2">
            If this provider already has a client registered, leave these blank to reuse it —
            one client can authorize several accounts. Otherwise, enter it (from the provider's
            developer console) to register one now.
          </p>
          <div className="space-y-2 mb-2">
            <input className={inp} placeholder="Client ID (optional if already registered)" value={client.client_id}
              onChange={e => setClient({ ...client, client_id: e.target.value })} />
            <input className={inp} type="password" placeholder="Client secret (optional if already registered)" value={client.client_secret}
              onChange={e => setClient({ ...client, client_secret: e.target.value })} />
          </div>
          <div className="flex items-center gap-2">
            <button onClick={connect} disabled={busy}
              className="px-3 py-1.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-xs rounded-lg">
              {busy ? 'Connecting…' : 'Connect'}
            </button>
            <button onClick={() => { setAdding(false); setError('') }} className="text-slate-500 hover:text-slate-300 text-xs">Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

const EMAIL_PRESETS = [
  { key: 'gmail',      label: 'Gmail' },
  { key: 'outlook',    label: 'Outlook' },
  { key: 'yahoo',      label: 'Yahoo' },
  { key: 'fastmail',   label: 'Fastmail' },
  { key: 'protonmail', label: 'ProtonMail' },
  { key: 'custom',     label: 'Custom' },
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
      from_name: initial.from_name ?? 'OpenOptOut Removals', from_email: initial.from_email ?? '',
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
      setTestResult({ connected: false, errors: [err.response?.data?.detail ?? 'Connection failed'] })
    } finally { setTesting(false) }
  }

  return (
    <Section icon={Mail} title="Email configuration"
      description="One shared inbox for all opt-out requests and confirmation matching"
      adminOnly userRole={userRole}>
      {!isAdmin ? (
        <p className="text-slate-500 text-sm">Email settings are managed by your administrator.</p>
      ) : (
        <>
          <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border ${
            initial.connected ? 'bg-emerald-900/20 text-emerald-400 border-emerald-800' : 'bg-slate-900 text-slate-500 border-slate-700'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${initial.connected ? 'bg-emerald-400' : 'bg-slate-600'}`} />
            {initial.connected
              ? (initial.provider_connected ? `Connected via ${initial.provider}` : 'Email connected')
              : 'Not configured'}
          </div>

          {gracePeriod?.active && (
            <div className="p-3.5 bg-indigo-950/40 border border-indigo-700/60 rounded-xl text-xs space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 text-indigo-300 font-medium">
                  <Clock size={14} className="text-indigo-400" />
                  <span>Dual-Inbox Grace Period Active (Item 11)</span>
                </div>
                <span className="bg-indigo-900/60 text-indigo-200 px-2 py-0.5 rounded text-[11px] font-mono">
                  {gracePeriod.days_remaining} days remaining
                </span>
              </div>
              <p className="text-slate-300 leading-relaxed">
                Background monitoring preserves dual-inbox checks during mode and mailbox transitions. Currently polling the previous mailbox (<strong>{gracePeriod.previous_inbox || 'previous account'}</strong>) alongside the primary inbox to catch delayed broker confirmation replies.
              </p>
              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={extendGracePeriod}
                  className="px-2.5 py-1 bg-indigo-800/50 hover:bg-indigo-800 border border-indigo-600 rounded text-indigo-200 transition-colors"
                >
                  Extend +30 Days
                </button>
                <button
                  type="button"
                  onClick={dismissGracePeriod}
                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded text-slate-300 transition-colors"
                >
                  Dismiss Grace Period
                </button>
              </div>
            </div>
          )}

          <Field label="Email Mode">
            <div className="flex gap-2">
              {[
                { value: 'shared', label: 'Shared central inbox', hint: 'Dispatches all opt-outs from one central organizational inbox' },
                { value: 'per_user', label: 'Per-user mail authorization', hint: 'Family members authorize their individual mailboxes' }
              ].map(m => (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => setForm(f => ({ ...f, mode: m.value }))}
                  className={`flex-1 text-left p-3 rounded-lg border text-xs transition-colors ${
                    (form.mode || 'shared') === m.value
                      ? 'border-shield-600 bg-shield-900/20 text-slate-200'
                      : 'border-slate-700 bg-slate-900/60 text-slate-400 hover:border-slate-600'
                  }`}
                >
                  <div className="font-medium text-slate-200">{m.label}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">{m.hint}</div>
                </button>
              ))}
            </div>
          </Field>

          <ConnectedAccounts currentProvider={initial.provider} onChanged={() => { /* status badge refreshes on next page load; accounts list refreshes itself */ }} />

          <Field label="Provider">
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
            <p className="text-slate-400 text-xs font-medium mb-2 uppercase tracking-wide">IMAP — incoming confirmations</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="col-span-2"><Field label="Host"><input value={form.imap_host ?? ''} onChange={e => setForm(f=>({...f,imap_host:e.target.value}))} placeholder="imap.gmail.com" className={inp}/></Field></div>
              <Field label="Port"><input type="number" value={form.imap_port ?? 993} onChange={e => setForm(f=>({...f,imap_port:parseInt(e.target.value)}))} className={inp}/></Field>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <Field label="Username / email"><input value={form.imap_user ?? ''} onChange={e => setForm(f=>({...f,imap_user:e.target.value}))} placeholder="removals@example.com" className={inp}/></Field>
              <PasswordField label="Password / App Password" value={imapPw} onChange={setImapPw} isSet={initial.imap_password_set}
                hint={form.preset === 'gmail' ? 'Use a Gmail App Password' : form.preset === 'yahoo' ? 'Use a Yahoo App Password' : undefined} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <Field label="Folder"><input value={form.imap_folder ?? 'INBOX'} onChange={e => setForm(f=>({...f,imap_folder:e.target.value}))} placeholder="INBOX" className={inp}/></Field>
              <Field label="Poll every (minutes)"><input type="number" min="5" max="60" value={form.poll_interval_minutes ?? 15} onChange={e => setForm(f=>({...f,poll_interval_minutes:parseInt(e.target.value)}))} className={inp}/></Field>
            </div>
            <label className="flex items-center gap-2 mt-2 cursor-pointer">
              <input type="checkbox" checked={form.imap_ssl ?? true} onChange={e => setForm(f=>({...f,imap_ssl:e.target.checked}))} className="w-3.5 h-3.5 rounded accent-shield-500"/>
              <span className="text-slate-400 text-sm">Use SSL/TLS</span>
            </label>
          </div>

          {/* SMTP */}
          <div>
            <p className="text-slate-400 text-xs font-medium mb-2 uppercase tracking-wide">SMTP — outgoing opt-out emails</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="col-span-2"><Field label="Host"><input value={form.smtp_host ?? ''} onChange={e => setForm(f=>({...f,smtp_host:e.target.value}))} placeholder="smtp.gmail.com" className={inp}/></Field></div>
              <Field label="Port"><input type="number" value={form.smtp_port ?? 587} onChange={e => setForm(f=>({...f,smtp_port:parseInt(e.target.value)}))} className={inp}/></Field>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <Field label="Username"><input value={form.smtp_user ?? ''} onChange={e => setForm(f=>({...f,smtp_user:e.target.value}))} placeholder="removals@example.com" className={inp}/></Field>
              <PasswordField label="Password / App Password" value={smtpPw} onChange={setSmtpPw} isSet={initial.smtp_password_set}/>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <Field label='"From" name'><input value={form.from_name ?? ''} onChange={e => setForm(f=>({...f,from_name:e.target.value}))} placeholder="OpenOptOut Removals" className={inp}/></Field>
              <Field label='"From" email'><input type="email" value={form.from_email ?? ''} onChange={e => setForm(f=>({...f,from_email:e.target.value}))} placeholder="removals@example.com" className={inp}/></Field>
            </div>
            <label className="flex items-center gap-2 mt-2 cursor-pointer">
              <input type="checkbox" checked={form.smtp_tls ?? true} onChange={e => setForm(f=>({...f,smtp_tls:e.target.checked}))} className="w-3.5 h-3.5 rounded accent-shield-500"/>
              <span className="text-slate-400 text-sm">Use STARTTLS</span>
            </label>
          </div>

          {testResult && (
            <div className={`px-3 py-2.5 rounded-lg border text-sm ${testResult.connected ? 'bg-emerald-900/20 border-emerald-800 text-emerald-300' : 'bg-red-900/20 border-red-800 text-red-300'}`}>
              {testResult.connected ? <span className="flex items-center gap-1.5"><Check size={13}/>IMAP and SMTP connected successfully</span> : (
                <div><p className="flex items-center gap-1.5 mb-1"><X size={13}/>Connection failed</p>
                  {testResult.errors?.map((e,i) => <p key={i} className="text-xs opacity-80 ml-4">{e}</p>)}</div>
              )}
            </div>
          )}

          <div className="flex items-center justify-between pt-1">
            <button onClick={test} disabled={testing || !initial.imap_password_set}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors disabled:opacity-40">
              {testing ? <RefreshCw size={12} className="animate-spin"/> : <TestTube size={12}/>}
              {testing ? 'Testing…' : 'Test connection'}
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
    <Section icon={CalendarClock} title="Scheduler"
      description="Automated opt-out timing and per-member rate limits"
      adminOnly={false} userRole={userRole}>

      {/* System settings — super_admin only */}
      {isAdmin && (
        <>
          <div className="flex items-center gap-3 mb-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <div onClick={() => setForm(f => ({...f, enabled: !f.enabled}))}
                className={`w-10 h-5 rounded-full transition-colors cursor-pointer relative ${form.enabled ? 'bg-shield-600' : 'bg-slate-700'}`}>
                <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${form.enabled ? 'translate-x-5' : 'translate-x-0.5'}`}/>
              </div>
              <span className="text-slate-300 text-sm">{form.enabled ? 'Scheduler enabled' : 'Scheduler disabled'}</span>
            </label>
            {status?.running && <span className="text-xs text-emerald-400 border border-emerald-800 bg-emerald-900/20 px-2 py-0.5 rounded">running</span>}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Daily run time (server local)">
              <input type="time" value={form.run_time ?? '02:00'} onChange={e => setForm(f=>({...f,run_time:e.target.value}))} className={inp}/>
            </Field>
            <Field label="Timezone">
              <div className="relative">
                <select value={form.timezone ?? 'America/Chicago'} onChange={e => setForm(f=>({...f,timezone:e.target.value}))}
                  className={`${inp} appearance-none pr-7`}>
                  {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
                </select>
                <ChevronDown size={11} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"/>
              </div>
            </Field>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="System max opt-outs / day" hint="Hard ceiling across all members combined">
              <input type="number" min="1" max="200" value={form.max_optouts_per_day ?? 20}
                onChange={e => setForm(f=>({...f,max_optouts_per_day:parseInt(e.target.value)}))} className={inp}/>
            </Field>
            <Field label="Default recheck interval (days)" hint="How long before re-verifying a confirmed removal">
              <input type="number" min="30" max="365" value={form.recheck_interval_days ?? 90}
                onChange={e => setForm(f=>({...f,recheck_interval_days:parseInt(e.target.value)}))} className={inp}/>
            </Field>
          </div>

          {/* ── Job spread mode ── */}
          <div className="border-t border-slate-700/50 pt-4">
            <p className="text-slate-400 text-xs font-medium mb-2">How to spread opt-out jobs</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
              {[
                { v: 'burst',       label: 'Burst',       desc: 'All at once at the run time' },
                { v: 'window',      label: 'Time window', desc: 'Spread across a set window (e.g. overnight)' },
                { v: 'rate',        label: 'Rate limited', desc: 'Fixed number per hour, all day' },
                { v: 'distributed', label: 'Distributed', desc: 'Small batches across 24 hours' },
              ].map(m => (
                <button key={m.v} onClick={() => setForm(f => ({...f, spread_mode: m.v}))}
                  className={`flex flex-col items-start px-3 py-2.5 rounded-lg border text-left transition-colors ${
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
                All pending opt-outs (up to the daily cap) are sent at {form.run_time ?? '02:00'}.
                Simple, but creates a traffic burst that some brokers may flag.
              </p>
            )}

            {(form.spread_mode ?? 'burst') === 'window' && (
              <div className="bg-slate-900 rounded-lg px-3 py-3 space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <Field label="Start hour (0–23)">
                    <input type="number" min="0" max="23" value={form.window_start_hour ?? 22}
                      onChange={e => setForm(f=>({...f,window_start_hour:parseInt(e.target.value)}))} className={inp}/>
                  </Field>
                  <Field label="End hour (0–23)">
                    <input type="number" min="0" max="23" value={form.window_end_hour ?? 6}
                      onChange={e => setForm(f=>({...f,window_end_hour:parseInt(e.target.value)}))} className={inp}/>
                  </Field>
                  <Field label="Every N minutes">
                    <input type="number" min="5" max="120" value={form.window_interval_minutes ?? 30}
                      onChange={e => setForm(f=>({...f,window_interval_minutes:parseInt(e.target.value)}))} className={inp}/>
                  </Field>
                </div>
                <p className="text-slate-500 text-xs">
                  The daily cap of {form.max_optouts_per_day ?? 20} is spread evenly across
                  {' '}{form.window_start_hour ?? 22}:00–{form.window_end_hour ?? 6}:00, firing every {form.window_interval_minutes ?? 30} min.
                </p>
              </div>
            )}

            {(form.spread_mode ?? 'burst') === 'rate' && (
              <div className="bg-slate-900 rounded-lg px-3 py-3 space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Field label="Max per hour">
                    <input type="number" min="1" max="60" value={form.rate_per_hour ?? 5}
                      onChange={e => setForm(f=>({...f,rate_per_hour:parseInt(e.target.value)}))} className={inp}/>
                  </Field>
                  <Field label="Check every N minutes">
                    <input type="number" min="5" max="60" value={form.rate_interval_minutes ?? 20}
                      onChange={e => setForm(f=>({...f,rate_interval_minutes:parseInt(e.target.value)}))} className={inp}/>
                  </Field>
                </div>
                <p className="text-slate-500 text-xs">
                  Sends up to {form.rate_per_hour ?? 5}/hour continuously, checking every {form.rate_interval_minutes ?? 20} min.
                  Still capped at {form.max_optouts_per_day ?? 20}/day total.
                </p>
              </div>
            )}

            {(form.spread_mode ?? 'burst') === 'distributed' && (
              <div className="bg-slate-900 rounded-lg px-3 py-3 space-y-3">
                <Field label="Batch interval (minutes)">
                  <input type="number" min="15" max="240" value={form.distributed_interval_minutes ?? 60}
                    onChange={e => setForm(f=>({...f,distributed_interval_minutes:parseInt(e.target.value)}))} className={inp}/>
                </Field>
                <p className="text-slate-500 text-xs">
                  The daily cap of {form.max_optouts_per_day ?? 20} is divided into small batches sent every
                  {' '}{form.distributed_interval_minutes ?? 60} min around the clock —
                  about {Math.max(1, Math.floor((form.max_optouts_per_day ?? 20) / Math.max(1, Math.floor(1440 / (form.distributed_interval_minutes ?? 60)))))} per batch.
                </p>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.pause_before_send ?? true} onChange={e => setForm(f=>({...f,pause_before_send:e.target.checked}))} className="w-3.5 h-3.5 rounded accent-shield-500"/>
              <span className="text-slate-300 text-sm">Pause before sending</span>
              <span className="text-slate-600 text-xs">— queue opt-outs but require manual trigger to fire</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.auto_recheck ?? true} onChange={e => setForm(f=>({...f,auto_recheck:e.target.checked}))} className="w-3.5 h-3.5 rounded accent-shield-500"/>
              <span className="text-slate-300 text-sm">Auto re-queue expired removals</span>
              <span className="text-slate-600 text-xs">— re-submit opt-out when recheck date passes</span>
            </label>
          </div>

          {/* Next run times */}
          {status?.next_runs && Object.keys(status.next_runs).length > 0 && (
            <div className="bg-slate-900 rounded-lg px-3 py-2.5 space-y-1">
              <p className="text-slate-500 text-xs mb-1.5 uppercase tracking-wide">Next scheduled runs</p>
              {Object.entries(status.next_runs).map(([id, time]) => (
                <div key={id} className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">{id.replace('_', ' ')}</span>
                  <span className="text-slate-300 font-mono">{time ? new Date(time).toLocaleString() : '—'}</span>
                </div>
              ))}
            </div>
          )}

          {/* Manual triggers */}
          <div>
            <p className="text-slate-500 text-xs mb-2 uppercase tracking-wide">Manual triggers</p>
            <div className="flex gap-2 flex-wrap">
              {[
                { job: 'optout', label: 'Send opt-outs', icon: Zap },
                { job: 'email_monitor', label: 'Poll inbox', icon: Mail },
                { job: 'recheck', label: 'Run re-checks', icon: RotateCcw },
              ].map(({ job, label, icon: Icon }) => (
                <button key={job} onClick={() => trigger(job)} disabled={triggering[job]}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors disabled:opacity-50">
                  {triggering[job] ? <RefreshCw size={11} className="animate-spin"/> : <Icon size={11}/>}
                  {triggering[job] ? 'Running…' : label}
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
            <p className="text-slate-400 text-xs font-medium uppercase tracking-wide">Per-member opt-out limits</p>
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
                      className="w-3 h-3 rounded accent-shield-500"/>
                    <span className="text-slate-500 text-xs">active</span>
                  </label>
                  <div className="flex items-center gap-1 bg-slate-800 border border-slate-700 rounded-lg px-2 py-1">
                    <input type="number" min="0" max="50"
                      value={mc.max_optouts_per_day ?? ''}
                      onChange={e => updateMemberLimit(mc.member_id, 'max_optouts_per_day', e.target.value ? parseInt(e.target.value) : 0)}
                      placeholder={`${mc.effective_limit} (default)`}
                      className="w-20 bg-transparent text-sm text-slate-200 placeholder-slate-600 focus:outline-none text-right"/>
                    <span className="text-slate-600 text-xs">/day</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <p className="text-slate-600 text-xs mt-2">Blank = use system default ({initial.max_optouts_per_day ?? 20}/day). Set 0 to pause a member.</p>
        </div>
      )}

      {!isAdmin && !isParent && (
        <p className="text-slate-500 text-sm">Scheduler settings are managed by your administrator.</p>
      )}
    </Section>
  )
}

// ── Data section ──────────────────────────────────────────────────────────────
function DataSection({ userRole }) {
  const [resetting, setResetting] = useState(false)
  const isAdmin = userRole === 'super_admin'

  const resetRequests = async () => {
    if (!confirm('Delete ALL removal request history? Family data stays. Cannot be undone.')) return
    setResetting(true)
    try { await api.delete('/settings/danger/reset-requests'); alert('History cleared.') }
    finally { setResetting(false) }
  }

  return (
    <Section icon={Database} title="Privacy & data" description="Export your data or manage retention">
      <div className="flex items-center justify-between py-2 border-b border-slate-700/50">
        <div>
          <p className="text-slate-200 text-sm">Export all data</p>
          <p className="text-slate-500 text-xs">Download family data and removal history as JSON</p>
        </div>
        <button onClick={() => window.open('/api/settings/export','_blank')}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
          <Download size={12}/>Export
        </button>
      </div>
      {isAdmin && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={13} className="text-red-400 shrink-0"/>
            <p className="text-red-400 text-xs font-medium uppercase tracking-wide">Danger zone</p>
          </div>
          <div className="border border-red-900/50 rounded-lg p-3 bg-red-950/20 flex items-center justify-between">
            <div>
              <p className="text-slate-200 text-sm">Reset removal history</p>
              <p className="text-slate-500 text-xs">Deletes all opt-out requests and email logs. Family data kept.</p>
            </div>
            <button onClick={resetRequests} disabled={resetting}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-400 border border-red-800 rounded-lg hover:bg-red-900/30 transition-colors disabled:opacity-40 ml-3 shrink-0">
              <Trash2 size={12}/>{resetting ? 'Resetting…' : 'Reset'}
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
      alert(err.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }

  const FIELDS = [
    { key: 'max_names',     label: 'Name variants',   color: 'text-purple-400', max: 20,
      hint: 'e.g. Robert Nunez, Rob Nunez, R. Nunez, Roberto Nunez' },
    { key: 'max_addresses', label: 'Past addresses',  color: 'text-amber-400',  max: 30,
      hint: 'Every address increases discovery and opt-out coverage significantly' },
    { key: 'max_phones',    label: 'Phone numbers',   color: 'text-emerald-400', max: 20,
      hint: 'Include all numbers tied to any of the listed addresses' },
    { key: 'max_emails',    label: 'Email addresses', color: 'text-blue-400',   max: 20,
      hint: 'Include old, inactive, and alias addresses' },
  ]

  // Children limit is shown separately — it\'s 0-based (0 = unlimited)
  const childrenLimit = form.max_children_per_parent ?? 0

  return (
    <Section icon={Shield} title="Vault limits"
      description="Maximum identity entries per family member — affects combination matrix size"
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
                  <span className="text-slate-600 text-xs w-10 text-right">max {f.max}</span>
                </div>
              </Field>
            ))}
          </div>

          {/* Children per parent */}
          <div className="border-t border-slate-700/50 pt-4">
            <p className="text-slate-400 text-xs font-medium mb-2">Children per parent</p>
            <div className="flex items-center gap-3">
              <input
                type="number" min="0" max="100"
                value={childrenLimit}
                onChange={e => setForm(prev => ({...prev, max_children_per_parent: Math.max(0, parseInt(e.target.value) || 0)}))}
                className="w-24 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 text-center focus:outline-none focus:border-shield-500"
              />
              <div>
                <p className="text-slate-300 text-sm">
                  {childrenLimit === 0 ? 'Unlimited' : `Max ${childrenLimit} child profile${childrenLimit !== 1 ? 's' : ''} per parent`}
                </p>
                <p className="text-slate-600 text-xs mt-0.5">
                  0 = unlimited. Per-parent overrides can be set in Admin panel → Grant access.
                </p>
              </div>
            </div>
          </div>

          {/* Matrix size preview */}
          <div className="bg-slate-900 rounded-lg px-4 py-3 border border-slate-700/50">
            <p className="text-slate-500 text-xs uppercase tracking-wide mb-2">Resulting matrix size per broker</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-slate-400 text-xs">Discovery pass <span className="text-slate-600">(name × address)</span></p>
                <p className="text-slate-200 font-semibold">{discoveryPerBroker.toLocaleString()} searches</p>
              </div>
              <div>
                <p className="text-slate-400 text-xs">Opt-out pass <span className="text-slate-600">(all combinations)</span></p>
                <p className="text-slate-200 font-semibold">{optoutPerBroker.toLocaleString()} submissions</p>
              </div>
            </div>
            {optoutPerBroker > 500 && (
              <p className="text-amber-400 text-xs mt-2 flex items-center gap-1">
                <AlertTriangle size={11} />
                Large matrix — the bot uses a 1.5s inter-submission delay to avoid rate limiting.
                At {optoutPerBroker} combinations × 420 brokers this will take significant time.
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
    if (!confirm('Deny the plugin system? This immediately stops ALL running plugins and blocks any from running until you explicitly re-allow it.')) return
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
      <Section icon={Puzzle} title="Plugin system"
        description="Sandboxed, process-isolated plugins" adminOnly userRole={userRole}>
        <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl border border-red-800 bg-red-900/15">
          <Ban size={16} className="text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-red-300 text-sm font-medium">Plugin system is DENIED</p>
            <p className="text-red-400/80 text-xs mt-0.5">
              All plugins are stopped and nothing can run. The plugin controls are locked until you re-allow the system.
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <button onClick={allow}
            className="flex items-center gap-1.5 px-4 py-1.5 text-sm text-amber-300 border border-amber-800 rounded-lg hover:bg-amber-900/20">
            <ShieldCheck size={13} /> Re-allow (type-to-confirm)
          </button>
        </div>
      </Section>
    )
  }

  return (
    <Section icon={Puzzle} title="Plugin system"
      description="Enable sandboxed, process-isolated plugins"
      adminOnly userRole={userRole}>

      <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg border border-blue-800 bg-blue-900/10">
        <Info size={13} className="text-blue-400 shrink-0 mt-0.5" />
        <p className="text-blue-300/90 text-xs">
          Plugins run as isolated subprocesses with OS-level sandboxing and per-plugin permissions.
          After enabling here, restart the server, then install and enable individual plugins
          on the Plugins page. Untrusted plugins are only fully contained on Linux with bubblewrap installed.
        </p>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <div onClick={() => setConfig(c => ({ ...c, enabled: !c.enabled }))}
          className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${config.enabled ? 'bg-shield-600' : 'bg-slate-700'}`}>
          <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </div>
        <span className="text-slate-300 text-sm">Enable the plugin system</span>
      </label>

      {config.enabled && (
        <>
          <div>
            <label className="text-slate-400 text-xs mb-1.5 block">Plugin storage backend</label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {[
                { v: 'db',   label: 'Database', desc: 'Store plugin data in the app database' },
                { v: 'file', label: 'File',     desc: 'Store plugin data as JSON files on disk' },
              ].map(o => (
                <button key={o.v} onClick={() => setConfig(c => ({ ...c, storage_mode: o.v }))}
                  className={`flex flex-col items-start px-3 py-2.5 rounded-lg border text-left transition-colors ${config.storage_mode === o.v ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700 hover:border-slate-600'}`}>
                  <span className={`text-sm font-medium ${config.storage_mode === o.v ? 'text-shield-300' : 'text-slate-300'}`}>{o.label}</span>
                  <span className="text-slate-500 text-xs">{o.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-slate-400 text-xs mb-1 block">Plugins directory</label>
            <input value={config.plugins_dir || ''} onChange={e => setConfig(c => ({ ...c, plugins_dir: e.target.value }))}
              placeholder="/data/plugins" className={inp} />
            <p className="text-slate-600 text-xs mt-1">Root folder for plugins inside the container. Each plugin is stored in a subfolder for its type: email/, captcha/, forms/, discovery/, brokers/, themes/, languages/, general/.</p>
          </div>

          {/* Lockdown mode */}
          <div className="flex items-start gap-2.5 px-3 py-2.5 rounded-lg border border-slate-700 bg-slate-800/40">
            <div onClick={() => setConfig(c => ({ ...c, lockdown_mode: !c.lockdown_mode }))}
              className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative shrink-0 mt-0.5 ${config.lockdown_mode ? 'bg-amber-600' : 'bg-slate-700'}`}>
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.lockdown_mode ? 'translate-x-4' : 'translate-x-0.5'}`} />
            </div>
            <div>
              <p className="text-slate-200 text-sm">Lockdown mode</p>
              <p className="text-slate-500 text-xs mt-0.5">
                Auto-disable any plugin on its first detected violation (spawning a process, writing outside
                its sandbox, opening a network socket, etc.). Recommended when running untrusted plugins.
              </p>
            </div>
          </div>
        </>
      )}

      <div className="flex items-center justify-between">
        <button onClick={deny} disabled={denying}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-400 border border-red-800/60 rounded-lg hover:bg-red-900/20 disabled:opacity-40">
          <Ban size={13} /> {denying ? 'Denying…' : 'Deny & stop all plugins'}
        </button>
        <SaveButton saving={saving} saved={saved} onClick={save} />
      </div>
      {config.enabled && <p className="text-slate-600 text-xs text-right">Restart the server for changes to take effect.</p>}
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
      <span className={`text-xs px-2 py-0.5 rounded border ${ok ? 'text-emerald-400 border-emerald-800 bg-emerald-900/20' : 'text-slate-500 border-slate-700'}`}>
        {ok ? 'enabled' : 'disabled'}
      </span>
    </div>
  )

  return (
    <Section icon={Shield} title="Encryption at rest"
      description="Database and field-level encryption configuration"
      adminOnly userRole={userRole}>
      {!isAdmin ? (
        <p className="text-slate-500 text-sm">Encryption settings are managed by your administrator.</p>
      ) : !status ? (
        <p className="text-slate-500 text-sm">Loading…</p>
      ) : (
        <>
          <div className="space-y-2">
            <StatusPill
              ok={status.db_encryption_enabled}
              label="SQLCipher database encryption"
              sub={status.db_encryption_enabled
                ? "Entire SQLite file is AES-256 encrypted"
                : status.sqlcipher_available
                  ? "Set DB_ENCRYPTION_KEY in .env to enable"
                  : "sqlcipher3-binary not installed (see README)"}
            />
            <StatusPill
              ok={status.field_encryption_enabled}
              label="Field-level PII encryption"
              sub={status.field_encryption_enabled
                ? "Names, addresses, phones, emails encrypted before DB write"
                : "Set FIELD_ENCRYPTION_KEY in .env to enable (falls back to SECRET_KEY)"}
            />
            <StatusPill
              ok={status.secret_key_set}
              label="SECRET_KEY configured"
              sub={status.secret_key_set ? "Custom key set" : "Using default — change this immediately"}
            />
          </div>

          {status.db_type === 'postgres' && (
            <div className="px-3 py-2.5 bg-blue-900/10 border border-blue-800 rounded-lg text-blue-300 text-xs">
              PostgreSQL detected — SQLCipher does not apply. Use your provider's built-in encryption:
              RDS Storage Encryption, Azure Transparent Data Encryption, or Cloud SQL CMEK.
              Field-level encryption is still active and recommended.
            </div>
          )}

          {!status.db_encryption_enabled && status.sqlcipher_available && status.db_type === 'sqlite' && (
            <div className="bg-slate-900 rounded-lg p-3 text-xs space-y-2">
              <p className="text-slate-400 font-medium">To enable SQLCipher encryption:</p>
              <ol className="text-slate-500 space-y-1 ml-3">
                <li>1. Generate a key: <code className="bg-slate-800 px-1.5 rounded text-slate-300">openssl rand -hex 32</code></li>
                <li>2. Add to .env: <code className="bg-slate-800 px-1.5 rounded text-slate-300">DB_ENCRYPTION_KEY=your-key-here</code></li>
                <li>3. Migrate existing data: <code className="bg-slate-800 px-1.5 rounded text-slate-300">docker exec openoptout-api python -m backend.core.encryption migrate</code></li>
                <li>4. Back up the original .db file, replace with the _encrypted.db file</li>
                <li>5. Restart the container</li>
              </ol>
              <p className="text-amber-400">⚠ Migration must be done before enabling the key — not after. Back up first.</p>
            </div>
          )}

          {!status.field_encryption_enabled && (
            <div className="bg-slate-900 rounded-lg p-3 text-xs space-y-1">
              <p className="text-slate-400 font-medium">To enable field-level encryption:</p>
              <p className="text-slate-500">Add to .env: <code className="bg-slate-800 px-1.5 rounded text-slate-300">FIELD_ENCRYPTION_KEY=your-key-here</code></p>
              <p className="text-slate-600">Existing plaintext values are read correctly on first access. New writes are encrypted immediately.</p>
            </div>
          )}
        </>
      )}
    </Section>
  )
}


// ── Automation / bot-evasion section ──────────────────────────────────────────

function AutomationSection({ userRole }) {
  const [config, setConfig]   = useState({ rotate_user_agents: true, custom_user_agents: [], inter_submission_delay_seconds: 1.5 })
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
    <Section icon={Bot} title="Automation & bot evasion"
      description="User-agent rotation and submission timing to reduce blocking"
      adminOnly userRole={userRole}>

      <div className="flex items-start gap-2 px-3 py-2.5 bg-slate-900 border border-slate-700/50 rounded-lg">
        <Info size={13} className="text-slate-500 shrink-0 mt-0.5" />
        <p className="text-slate-500 text-xs">
          User-agent rotation is one layer of evasion. Sophisticated brokers also fingerprint TLS,
          canvas, and timing — rotation helps against simple blocking but is not a guarantee.
          Pair it with a reasonable submission delay for best results.
        </p>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <div onClick={() => setConfig(c => ({...c, rotate_user_agents: !c.rotate_user_agents}))}
          className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${config.rotate_user_agents ? 'bg-shield-600' : 'bg-slate-700'}`}>
          <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.rotate_user_agents ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </div>
        <span className="text-slate-300 text-sm">Rotate user agents</span>
        <span className="text-slate-600 text-xs">— each broker gets a randomized browser fingerprint</span>
      </label>

      {config.rotate_user_agents && (
        <>
          <div>
            <button onClick={() => setShowBuiltins(s => !s)}
              className="flex items-center gap-1.5 text-slate-400 hover:text-slate-300 text-xs transition-colors">
              <ChevronDown size={11} className={showBuiltins ? 'rotate-180 transition-transform' : 'transition-transform'} />
              {builtins.length} built-in user agents
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

          <Field label="Custom user agents" hint="Add your own UA strings — mixed into the rotation pool">
            <div className="flex gap-2">
              <input value={newUA} onChange={e => setNewUA(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addUA() } }}
                placeholder="Mozilla/5.0 (...) ..." className={inp + ' font-mono text-xs'} />
              <button onClick={addUA}
                className="px-3 py-1.5 bg-shield-600 text-white text-sm rounded-lg hover:bg-shield-700 transition-colors shrink-0">
                Add
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

      <Field label="Delay between submissions (seconds)"
        hint="Pause between each form submission per broker. Higher = slower but less bot-like.">
        <input type="number" min="0.5" max="30" step="0.5"
          value={config.inter_submission_delay_seconds}
          onChange={e => setConfig(c => ({...c, inter_submission_delay_seconds: parseFloat(e.target.value)}))}
          className={inp + ' w-32'} />
      </Field>

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
    <Section icon={Globe} title="Proxy / IP masking"
      description="Route automation through proxies to mask the server IP"
      adminOnly userRole={userRole}>

      <div className="flex items-start gap-2 px-3 py-2.5 bg-blue-900/10 border border-blue-800 rounded-lg">
        <Shield size={13} className="text-blue-400 shrink-0 mt-0.5" />
        <p className="text-blue-300 text-xs">
          IP masking is the most effective anti-blocking measure — brokers track primarily by IP.
          Residential proxies work best. Credentials are read only from environment variables or
          mounted files, never stored here. Use reputable providers with consented IP networks.
        </p>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <div onClick={() => setConfig(c => ({...c, enabled: !c.enabled}))}
          className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${config.enabled ? 'bg-shield-600' : 'bg-slate-700'}`}>
          <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </div>
        <span className="text-slate-300 text-sm">Enable proxy for automation traffic</span>
      </label>

      {config.enabled && (
        <>
          {/* Mode: single vs pool */}
          <Field label="Mode">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button onClick={() => setConfig(c => ({...c, mode: 'single'}))}
                className={`flex flex-col items-start px-3 py-2.5 rounded-lg border text-left transition-colors ${config.mode === 'single' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700 hover:border-slate-600'}`}>
                <span className={`text-sm font-medium ${config.mode === 'single' ? 'text-shield-300' : 'text-slate-300'}`}>Single proxy</span>
                <span className="text-slate-500 text-xs">One IP for all traffic</span>
              </button>
              <button onClick={() => setConfig(c => ({...c, mode: 'pool'}))}
                className={`flex flex-col items-start px-3 py-2.5 rounded-lg border text-left transition-colors ${config.mode === 'pool' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700 hover:border-slate-600'}`}>
                <span className={`text-sm font-medium ${config.mode === 'pool' ? 'text-shield-300' : 'text-slate-300'}`}>Rotating pool</span>
                <span className="text-slate-500 text-xs">Different IP per broker</span>
              </button>
            </div>
          </Field>

          {/* Provider preset */}
          <Field label="Provider">
            <div className="relative">
              <select value={config.provider} onChange={e => {
                  const p = presets[e.target.value] || {}
                  setConfig(c => ({...c, provider: e.target.value,
                    host: p.host_hint || c.host, port: p.default_port || c.port,
                    scheme: p.scheme || c.scheme }))
                }}
                className={inp + ' appearance-none pr-8'}>
                {Object.entries(presets).map(([key, p]) => (
                  <option key={key} value={key}>{p.label}</option>
                ))}
              </select>
              <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
            </div>
            {preset.note && <p className="text-slate-500 text-xs mt-1.5 bg-slate-900 rounded-lg px-3 py-2">{preset.note}</p>}
          </Field>

          {/* Host/port/scheme — hidden in pool mode (pool comes from env) */}
          {!isPool && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="col-span-2">
                <Field label="Host">
                  <input value={config.host || ''} onChange={e => setConfig(c => ({...c, host: e.target.value}))}
                    placeholder={preset.host_hint || 'gate.provider.com'} className={inp} />
                </Field>
              </div>
              <Field label="Port">
                <input type="number" value={config.port || ''} onChange={e => setConfig(c => ({...c, port: parseInt(e.target.value)}))}
                  placeholder={String(preset.default_port || 8080)} className={inp} />
              </Field>
              <Field label="Scheme">
                <div className="relative">
                  <select value={config.scheme || 'http'} onChange={e => setConfig(c => ({...c, scheme: e.target.value}))}
                    className={inp + ' appearance-none pr-7'}>
                    <option value="http">http</option>
                    <option value="https">https</option>
                    <option value="socks5">socks5</option>
                  </select>
                  <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
                </div>
              </Field>
            </div>
          )}

          {isPool && (
            <div className="bg-slate-900 rounded-lg px-3 py-2.5 text-xs text-slate-500">
              Pool mode reads the proxy list from the <code className="bg-slate-800 px-1 rounded text-slate-300">PROXY_POOL</code> environment
              variable or <code className="bg-slate-800 px-1 rounded text-slate-300">PROXY_POOL_FILE</code>.
              Each entry is a proxy URL. A random proxy is chosen per broker.
              {status && <span className="block mt-1 text-slate-400">Detected pool size: {status.pool_size}</span>}
            </div>
          )}

          {/* Credential status */}
          {status && (
            <div className="bg-slate-900 rounded-lg p-3">
              <div className="flex items-center gap-1.5 mb-2">
                <Lock size={12} className="text-slate-400" />
                <p className="text-slate-400 text-xs font-medium">Credentials</p>
                <span className="text-slate-600 text-xs">— from env / mounted files</span>
              </div>
              <div className="flex gap-4">
                <div className="flex items-center gap-1.5 text-xs">
                  {status.creds_user_set ? <Check size={12} className="text-emerald-400" /> : <X size={12} className="text-slate-600" />}
                  <span className={status.creds_user_set ? 'text-slate-300' : 'text-slate-600'}>Username</span>
                </div>
                <div className="flex items-center gap-1.5 text-xs">
                  {status.creds_pass_set ? <Check size={12} className="text-emerald-400" /> : <X size={12} className="text-slate-600" />}
                  <span className={status.creds_pass_set ? 'text-slate-300' : 'text-slate-600'}>Password</span>
                </div>
              </div>
              {!status.creds_user_set && (
                <p className="text-amber-400 text-xs mt-2">
                  No credentials detected. Set them via environment variables (see .env.example) before testing.
                </p>
              )}
            </div>
          )}

          {/* Test result */}
          {testResult && (
            <div className={`px-3 py-2.5 rounded-lg border text-sm ${testResult.ok ? 'border-emerald-800 bg-emerald-900/10 text-emerald-300' : 'border-red-800 bg-red-900/10 text-red-300'}`}>
              {testResult.ok
                ? <p className="font-medium">✓ {testResult.exit_ip ? `Traffic exiting via ${testResult.exit_ip}` : 'Connected through proxy'}</p>
                : <p>✗ {testResult.error}</p>}
            </div>
          )}

          <div className="flex gap-2 justify-end">
            <button onClick={test} disabled={testing}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 disabled:opacity-40 transition-colors">
              {testing ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
              {testing ? 'Testing…' : 'Test proxy'}
            </button>
            <SaveButton saving={saving} saved={saved} onClick={save} />
          </div>
        </>
      )}
    </Section>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Settings() {
  const { user } = useAuth()
  const [settings, setSettings]           = useState(null)
  const [memberConfigs, setMemberConfigs] = useState([])
  const [loading, setLoading]             = useState(true)

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

  if (loading) return <div className="p-4 md:p-6"><p className="text-slate-500 text-sm">Loading…</p></div>

  // A manager holding the section's permission gets its admin controls.
  const sectionRole = perm => (can(user, perm) ? 'super_admin' : user?.role)

  return (
    <div className="p-4 md:p-6 max-w-3xl">
      <div className="mb-6">
        <h1 className="text-white text-xl font-semibold">Settings</h1>
        <p className="text-slate-400 text-sm mt-0.5">Configure how OpenOptOut looks and behaves</p>
      </div>
      <AppearanceSection initial={settings?.appearance ?? {}} onSaved={a => setSettings(s=>({...s,appearance:a}))} userRole={sectionRole('branding.manage')}/>
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
      <VaultLimitsSection
        initial={vaultLimits}
        userRole={sectionRole('settings.system')}
        onSaved={v => setVaultLimits(v)}
      />
      <EncryptionSection userRole={sectionRole('database.view')}/>
      {/* Never delegated: the plugin-system switch and the danger zone. */}
      <PluginSystemSection userRole={user?.role}/>
      <DataSection userRole={user?.role}/>
    </div>
  )
}
