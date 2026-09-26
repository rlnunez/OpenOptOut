import { useEffect, useState, useRef } from 'react'
import {
  Palette, Upload, X, Check, RefreshCw, Shield, Users,
  Building, Bell, Key, TestTube, Plus, Trash2, Eye, EyeOff,
  ChevronDown, Globe, Server, CreditCard, AlertTriangle
} from 'lucide-react'
import api from '../api'
import { useAuth } from '../hooks/useAuth'
import { useBranding } from '../hooks/useBranding'

const inp = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-shield-500"

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="text-slate-400 text-xs mb-1 block">{label}</label>
      {children}
      {hint && <p className="text-slate-600 text-xs mt-1">{hint}</p>}
    </div>
  )
}

function Section({ icon: Icon, title, description, children }) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden mb-4">
      <div className="px-5 py-4 border-b border-slate-700/50 flex items-center gap-2.5">
        <Icon size={15} className="text-shield-400 shrink-0" />
        <div>
          <p className="text-slate-200 text-sm font-medium">{title}</p>
          {description && <p className="text-slate-500 text-xs mt-0.5">{description}</p>}
        </div>
      </div>
      <div className="px-5 py-4 space-y-4">{children}</div>
    </div>
  )
}

function SaveBtn({ saving, saved, onClick }) {
  return (
    <button onClick={onClick} disabled={saving}
      className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
        saved ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800'
              : 'bg-shield-600 hover:bg-shield-700 text-white disabled:opacity-40'
      }`}>
      {saving ? <RefreshCw size={12} className="animate-spin" /> : saved ? <Check size={12} /> : null}
      {saving ? 'Saving…' : saved ? 'Saved' : 'Save'}
    </button>
  )
}

function PwField({ label, hint, value, onChange, isSet }) {
  const [show, setShow] = useState(false)
  return (
    <Field label={label} hint={hint}>
      <div className="relative">
        <input type={show ? 'text' : 'password'} value={value} onChange={e => onChange(e.target.value)}
          placeholder={isSet ? '••••••••  (blank = keep current)' : 'Enter value…'}
          className={`${inp} pr-9`} />
        <button type="button" onClick={() => setShow(s => !s)}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
          {show ? <EyeOff size={13} /> : <Eye size={13} />}
        </button>
      </div>
    </Field>
  )
}

// ── Color swatch picker ───────────────────────────────────────────────────────
const SWATCHES = ['#6366f1','#0ea5e9','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6']

function ColorPicker({ label, value, onChange }) {
  return (
    <Field label={label}>
      <div className="flex items-center gap-2 flex-wrap">
        {SWATCHES.map(c => (
          <button key={c} onClick={() => onChange(c)} title={c}
            className={`w-7 h-7 rounded-full border-2 transition-all ${value === c ? 'border-white scale-110' : 'border-transparent hover:scale-105'}`}
            style={{ background: c }} />
        ))}
        <div className="flex items-center gap-1.5 ml-1">
          <input type="color" value={value} onChange={e => onChange(e.target.value)}
            className="w-7 h-7 rounded cursor-pointer bg-transparent border-0" />
          <span className="text-slate-500 text-xs font-mono">{value}</span>
        </div>
      </div>
    </Field>
  )
}

// ── Branding section ──────────────────────────────────────────────────────────
function BrandingSection() {
  const { branding, refresh } = useBranding()
  const [form, setForm]   = useState({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)
  const [uploading, setUploading] = useState(false)
  const logoRef = useRef()

  useEffect(() => { setForm({ ...branding }) }, [branding])

  const save = async () => {
    setSaving(true)
    try {
      await api.patch('/branding/config', form)
      setSaved(true); setTimeout(() => setSaved(false), 2000)
      refresh()
    } finally { setSaving(false) }
  }

  const uploadLogo = async e => {
    const file = e.target.files?.[0]; if (!file) return
    setUploading(true)
    const fd = new FormData(); fd.append('file', file)
    try {
      await api.post('/branding/logo', fd)
      refresh()
    } finally { setUploading(false); e.target.value = '' }
  }

  const deleteLogo = async () => {
    await api.delete('/branding/logo')
    refresh()
  }

  return (
    <Section icon={Palette} title="Branding" description="White-label appearance for your organization">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="System / service name">
          <input value={form.system_name || ''} onChange={e => setForm(f => ({...f, system_name: e.target.value}))}
            placeholder="PrivacyShield" className={inp} />
        </Field>
        <Field label="Tagline">
          <input value={form.tagline || ''} onChange={e => setForm(f => ({...f, tagline: e.target.value}))}
            placeholder="Your personal data removal service" className={inp} />
        </Field>
      </div>

      <Field label="Logo" hint="PNG, SVG, or JPEG · shown in sidebar and login page">
        <div className="flex items-center gap-3">
          {branding.logo_url ? (
            <img src={`${branding.logo_url}?v=${Date.now()}`} alt="Logo"
              className="h-10 object-contain border border-slate-700 rounded bg-slate-900 px-2" />
          ) : (
            <div className="h-10 w-20 border border-dashed border-slate-700 rounded flex items-center justify-center text-slate-700 text-xs">
              No logo
            </div>
          )}
          <button onClick={() => logoRef.current?.click()} disabled={uploading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors disabled:opacity-40">
            <Upload size={11} />{uploading ? 'Uploading…' : 'Upload logo'}
          </button>
          {branding.logo_url && (
            <button onClick={deleteLogo} className="text-slate-600 hover:text-red-400 transition-colors">
              <X size={14} />
            </button>
          )}
          <input ref={logoRef} type="file" accept="image/*" className="hidden" onChange={uploadLogo} />
        </div>
      </Field>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <ColorPicker label="Primary color" value={form.primary_color || '#6366f1'} onChange={v => setForm(f => ({...f, primary_color: v}))} />
        <ColorPicker label="Accent color"  value={form.accent_color  || '#4f46e5'} onChange={v => setForm(f => ({...f, accent_color: v}))} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Contact email" hint="Shown to users when they need help">
          <input type="email" value={form.contact_email || ''} onChange={e => setForm(f => ({...f, contact_email: e.target.value}))}
            placeholder="privacy@yourlibrary.org" className={inp} />
        </Field>
        <Field label="Contact phone">
          <input value={form.contact_phone || ''} onChange={e => setForm(f => ({...f, contact_phone: e.target.value}))}
            placeholder="(555) 000-0000" className={inp} />
        </Field>
      </div>

      <Field label="Support / help URL" hint="Link to your IT helpdesk or knowledge base">
        <input value={form.support_url || ''} onChange={e => setForm(f => ({...f, support_url: e.target.value}))}
          placeholder="https://it.yourlibrary.org/privacy-help" className={inp} />
      </Field>

      <Field label="Login page welcome message" hint="Shown below the system name on the login screen">
        <textarea value={form.welcome_message || ''} onChange={e => setForm(f => ({...f, welcome_message: e.target.value}))}
          rows={2} placeholder="Welcome to the Raleigh Public Library Privacy Protection Service…"
          className={`${inp} resize-none`} />
      </Field>

      <Field label="Opt-out email footer" hint="Appended to all removal request emails sent on behalf of users">
        <textarea value={form.email_footer || ''} onChange={e => setForm(f => ({...f, email_footer: e.target.value}))}
          rows={2} placeholder="This request was submitted on your behalf by Raleigh Public Library's privacy protection service."
          className={`${inp} resize-none`} />
      </Field>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Terms of service URL" hint="Link shown at registration">
          <input value={form.terms_url || ''} onChange={e => setForm(f => ({...f, terms_url: e.target.value}))}
            placeholder="https://yourlibrary.org/terms" className={inp} />
        </Field>
        <Field label="">
          <label className="flex items-center gap-2 cursor-pointer mt-5">
            <input type="checkbox" checked={form.show_powered_by ?? true}
              onChange={e => setForm(f => ({...f, show_powered_by: e.target.checked}))}
              className="w-3.5 h-3.5 rounded accent-shield-500" />
            <span className="text-slate-300 text-sm">Show "Powered by PrivacyShield" footer</span>
          </label>
        </Field>
      </div>

      <div className="flex justify-end"><SaveBtn saving={saving} saved={saved} onClick={save} /></div>
    </Section>
  )
}

// ── Registration section ──────────────────────────────────────────────────────
function RegistrationSection() {
  const [config, setConfig] = useState({ mode: 'open', allowed_domains: '', require_invite: false, self_registration: true })
  const [saving, setSaving]   = useState(false)
  const [saved, setSaved]     = useState(false)
  const [codes, setCodes]     = useState([])
  const [newCode, setNewCode] = useState({ max_uses: 1, expires_days: '', role: 'parent', note: '' })

  useEffect(() => {
    api.get('/branding/registration').then(r => setConfig(r.data)).catch(() => {})
    api.get('/auth/invite-codes').then(r => setCodes(r.data)).catch(() => {})
  }, [])

  const save = async () => {
    setSaving(true)
    try { await api.patch('/branding/registration', config); setSaved(true); setTimeout(() => setSaved(false), 2000) }
    finally { setSaving(false) }
  }

  const createCode = async () => {
    const { data } = await api.post('/auth/invite-codes', {
      ...newCode, expires_days: newCode.expires_days ? parseInt(newCode.expires_days) : null,
    })
    setCodes(c => [data, ...c])
    setNewCode({ max_uses: 1, expires_days: '', role: 'parent', note: '' })
  }

  const revokeCode = async id => {
    await api.delete(`/auth/invite-codes/${id}`)
    setCodes(c => c.filter(x => x.id !== id))
  }

  const MODES = [
    { value: 'open',       label: 'Open',        desc: 'Anyone can register' },
    { value: 'domain',     label: 'Domain',       desc: 'Only allowed email domains' },
    { value: 'invite',     label: 'Invite code',  desc: 'Code required to register' },
    { value: 'admin_only', label: 'Admin only',   desc: 'No self-registration' },
  ]

  return (
    <Section icon={Users} title="Registration controls" description="Who can create accounts on this instance">
      <Field label="Registration mode">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {MODES.map(m => (
            <button key={m.value} onClick={() => setConfig(c => ({...c, mode: m.value}))}
              className={`flex flex-col items-start px-3 py-2.5 rounded-lg border text-left transition-colors ${
                config.mode === m.value ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700 hover:border-slate-600'
              }`}>
              <span className={`text-sm font-medium ${config.mode === m.value ? 'text-shield-300' : 'text-slate-300'}`}>{m.label}</span>
              <span className="text-slate-500 text-xs">{m.desc}</span>
            </button>
          ))}
        </div>
      </Field>

      {config.mode === 'domain' && (
        <Field label="Allowed email domains" hint="Comma-separated, e.g. library.org, city.gov">
          <input value={config.allowed_domains || ''} onChange={e => setConfig(c => ({...c, allowed_domains: e.target.value}))}
            placeholder="library.org, cityofexample.gov" className={inp} />
        </Field>
      )}

      <div className="flex justify-end"><SaveBtn saving={saving} saved={saved} onClick={save} /></div>

      {/* Invite codes */}
      <div className="border-t border-slate-700/50 pt-4">
        <p className="text-slate-400 text-xs font-medium uppercase tracking-wide mb-3">Invite codes</p>
        <div className="flex gap-2 mb-3 flex-wrap">
          <input value={newCode.note} onChange={e => setNewCode(n => ({...n, note: e.target.value}))}
            placeholder="Note (e.g. Staff batch Jan 2025)" className={`${inp} flex-1 min-w-32`} />
          <input type="number" min="1" value={newCode.max_uses}
            onChange={e => setNewCode(n => ({...n, max_uses: parseInt(e.target.value)}))}
            className={`${inp} w-20 text-center`} title="Max uses" />
          <input type="number" min="1" value={newCode.expires_days}
            onChange={e => setNewCode(n => ({...n, expires_days: e.target.value}))}
            placeholder="Days" className={`${inp} w-20 text-center`} title="Expires in days (blank=never)" />
          <div className="relative">
            <select value={newCode.role} onChange={e => setNewCode(n => ({...n, role: e.target.value}))}
              className={`${inp} appearance-none pr-7 w-28`}>
              <option value="parent">parent</option>
              <option value="member">member</option>
            </select>
            <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
          </div>
          <button onClick={createCode}
            className="flex items-center gap-1 px-3 py-1.5 bg-shield-600 text-white text-sm rounded-lg hover:bg-shield-700 transition-colors">
            <Plus size={13} /> Generate
          </button>
        </div>

        {codes.length > 0 && (
          <div className="space-y-1.5">
            {codes.map(c => (
              <div key={c.id} className={`flex items-center gap-3 px-3 py-2 rounded-lg border text-sm ${c.is_active ? 'border-slate-700 bg-slate-900' : 'border-slate-800 opacity-50'}`}>
                <code className="text-shield-400 font-mono flex-1">{c.code}</code>
                <span className="text-slate-500 text-xs">{c.uses}/{c.max_uses === 0 ? '∞' : c.max_uses} uses</span>
                <span className="text-slate-600 text-xs">{c.role}</span>
                {c.note && <span className="text-slate-600 text-xs truncate max-w-32">{c.note}</span>}
                {c.expires_at && <span className="text-slate-600 text-xs">{new Date(c.expires_at).toLocaleDateString()}</span>}
                <button onClick={() => revokeCode(c.id)} className="text-slate-600 hover:text-red-400 transition-colors">
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </Section>
  )
}

// ── Banner section ────────────────────────────────────────────────────────────
function BannerSection() {
  const { banner, setBanner } = useBranding()
  const [form, setForm]   = useState({ message: '', severity: 'info', active: true, expires_at: '' })
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (banner) setForm({ ...banner, expires_at: '' }) }, [banner])

  const save = async () => {
    setSaving(true)
    try {
      const { data } = await api.put('/branding/banner', {
        ...form,
        expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null,
      })
      setBanner(data)
    } finally { setSaving(false) }
  }

  const clear = async () => {
    await api.delete('/branding/banner')
    setBanner(null)
    setForm({ message: '', severity: 'info', active: true, expires_at: '' })
  }

  const SEVERITIES = [
    { v: 'info',        label: 'Info',        color: 'text-blue-400' },
    { v: 'warning',     label: 'Warning',     color: 'text-amber-400' },
    { v: 'maintenance', label: 'Maintenance', color: 'text-orange-400' },
    { v: 'success',     label: 'Success',     color: 'text-emerald-400' },
  ]

  return (
    <Section icon={Bell} title="Announcement banner" description="Shown at the top of the dashboard for all users">
      {banner?.active && (
        <div className="px-3 py-2 bg-blue-900/20 border border-blue-800 rounded-lg text-blue-300 text-sm mb-2">
          Active: "{banner.message}"
        </div>
      )}
      <Field label="Message">
        <input value={form.message} onChange={e => setForm(f => ({...f, message: e.target.value}))}
          placeholder="System maintenance Saturday 2–4am. Opt-out sending will be paused."
          className={inp} />
      </Field>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Severity">
          <div className="flex gap-2">
            {SEVERITIES.map(s => (
              <button key={s.v} onClick={() => setForm(f => ({...f, severity: s.v}))}
                className={`px-2.5 py-1.5 rounded-lg text-xs border transition-colors ${
                  form.severity === s.v ? 'border-current bg-current/10' : 'border-slate-700 text-slate-500 hover:text-slate-300'
                } ${s.color}`}>{s.label}</button>
            ))}
          </div>
        </Field>
        <Field label="Expires (optional)">
          <input type="datetime-local" value={form.expires_at}
            onChange={e => setForm(f => ({...f, expires_at: e.target.value}))}
            className={inp} />
        </Field>
      </div>
      <div className="flex gap-2 justify-end">
        {banner?.active && (
          <button onClick={clear} className="px-3 py-1.5 text-sm text-red-400 border border-red-800 rounded-lg hover:bg-red-900/20 transition-colors">
            Clear banner
          </button>
        )}
        <button onClick={save} disabled={saving || !form.message.trim()}
          className="flex items-center gap-1.5 px-4 py-1.5 bg-shield-600 text-white text-sm rounded-lg hover:bg-shield-700 disabled:opacity-40 transition-colors">
          {saving ? <RefreshCw size={12} className="animate-spin" /> : null}
          {saving ? 'Saving…' : banner?.active ? 'Update banner' : 'Set banner'}
        </button>
      </div>
    </Section>
  )
}

// ── Auth providers section ────────────────────────────────────────────────────
function ILSPresetPicker({ config, setConfig }) {
  const [presets, setPresets] = useState({})
  const [open, setOpen]       = useState(false)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    api.get('/branding/auth-providers/sip2/presets').then(r => setPresets(r.data)).catch(() => {})
  }, [])

  const applyPreset = (key) => {
    const p = presets[key]
    if (!p) return
    setSelected(key)
    setOpen(false)
    setConfig(c => ({
      ...c,
      // Auto-set port based on TLS setting + preset defaults
      sip2_port: c.sip2_use_tls ? (p.port_tls || 6443) : (p.port_plain || 6001),
    }))
  }

  const selectedPreset = selected ? presets[selected] : null

  return (
    <div className="mb-3">
      <p className="text-slate-400 text-xs mb-1.5">ILS system</p>
      <div className="relative">
        <button onClick={() => setOpen(o => !o)}
          className="w-full flex items-center justify-between px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-300 hover:border-slate-600 transition-colors">
          <span>{selectedPreset?.label || 'Select your ILS (optional)'}</span>
          <ChevronDown size={13} className={`text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        {open && (
          <div className="absolute top-full mt-1 left-0 right-0 bg-slate-800 border border-slate-700 rounded-xl shadow-xl z-10 overflow-hidden">
            {Object.entries(presets).map(([key, p]) => (
              <button key={key} onClick={() => applyPreset(key)}
                className="w-full text-left px-4 py-2.5 hover:bg-slate-700 transition-colors border-b border-slate-700/50 last:border-0">
                <p className="text-slate-200 text-sm">{p.label}</p>
              </button>
            ))}
          </div>
        )}
      </div>
      {selectedPreset?.note && (
        <div className="mt-2 px-3 py-2.5 bg-amber-900/10 border border-amber-800 rounded-lg text-amber-300 text-xs">
          {selectedPreset.note}
        </div>
      )}
    </div>
  )
}


function AuthProvidersSection() {
  const [config, setConfig]   = useState(null)
  const [presets, setPresets] = useState({})
  const [saving, setSaving]   = useState({})
  const [testing, setTesting] = useState({})
  const [testResults, setTestResults] = useState({})
  const [ldapMsg, setLdapMsg] = useState(null)        // {ok, warnings} | {ok:false, error}
  const [sip2Msg, setSip2Msg] = useState(null)
  const [ldapCert, setLdapCert] = useState(null)      // stored/latest certificate status
  useEffect(() => { api.get('/branding/auth-providers/ldap/cert-status').then(r => setLdapCert(r.data)).catch(() => {}) }, [])

  useEffect(() => {
    api.get('/branding/auth-providers').then(r => setConfig(r.data)).catch(() => {})
    api.get('/auth/oidc/presets').then(r => setPresets(r.data)).catch(() => {})
  }, [])

  if (!config) return <p className="text-slate-500 text-sm">Loading…</p>

  const saveLdap = async () => {
    setSaving(s => ({...s, ldap: true})); setLdapMsg(null)
    try {
      const r = await api.patch('/branding/auth-providers/ldap', {
        enabled: config.ldap_enabled, host: config.ldap_host,
        base_dn: config.ldap_base_dn, bind_dn: config.ldap_bind_dn,
        user_attr: config.ldap_user_attr, name_attr: config.ldap_name_attr,
        email_attr: config.ldap_email_attr,
        tls_mode: config.ldap_tls_mode || 'ldaps', port: config.ldap_port || '',
        ca_cert_pem: config.ldap_ca_cert_pem || '',
        email_domain: config.ldap_email_domain, default_role: config.ldap_default_role,
        ...(config._ldap_pw ? { bind_password: config._ldap_pw } : {}),
      })
      setLdapMsg({ ok: true, warnings: r.data.warnings || [] })
    } catch (e) {
      setLdapMsg({ ok: false, error: e.response?.data?.detail || 'Save failed' })
    } finally { setSaving(s => ({...s, ldap: false})) }
  }

  const saveSip2 = async () => {
    setSaving(s => ({...s, sip2: true})); setSip2Msg(null)
    try {
      const r = await api.patch('/branding/auth-providers/sip2', {
        enabled: config.sip2_enabled, host: config.sip2_host, port: config.sip2_port,
        use_tls: config.sip2_use_tls,
        ca_cert_pem: config.sip2_ca_cert_pem || '',
        ca_cert_path: config.sip2_ca_cert_path || null,
        timeout_seconds: config.sip2_timeout || 10,
        institution_id: config.sip2_institution_id, ils_login: config.sip2_ils_login,
        email_domain: config.sip2_email_domain, default_role: config.sip2_default_role,
        ...(config._sip2_pw ? { ils_password: config._sip2_pw } : {}),
      })
      setSip2Msg({ ok: true, warnings: r.data.warnings || [] })
    } catch (e) {
      setSip2Msg({ ok: false, error: e.response?.data?.detail || 'Save failed' })
    } finally { setSaving(s => ({...s, sip2: false})) }
  }

  const testProvider = async (provider) => {
    setTesting(t => ({...t, [provider]: true}))
    try {
      const { data } = await api.post(`/branding/auth-providers/${provider}/test`)
      setTestResults(r => ({...r, [provider]: data}))
    } finally { setTesting(t => ({...t, [provider]: false})) }
  }

  return (
    <Section icon={Key} title="Authentication providers" description="Enable SSO and external authentication">
      {/* LDAP */}
      <div className="border border-slate-700/50 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 bg-slate-900/50 border-b border-slate-700/50">
          <div className="flex items-center gap-2">
            <Server size={13} className="text-slate-400" />
            <span className="text-slate-300 text-sm font-medium">LDAP / Active Directory</span>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <span className="text-slate-500 text-xs">{config.ldap_enabled ? 'Enabled' : 'Disabled'}</span>
            <div onClick={() => setConfig(c => ({...c, ldap_enabled: !c.ldap_enabled}))}
              className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${config.ldap_enabled ? 'bg-shield-600' : 'bg-slate-700'}`}>
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.ldap_enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
            </div>
          </label>
        </div>
        {config.ldap_enabled && (
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Host URL">
                <input value={config.ldap_host || ''} onChange={e => setConfig(c => ({...c, ldap_host: e.target.value}))}
                  placeholder="ldap://dc.example.com" className={inp} />
              </Field>
              <Field label="Base DN">
                <input value={config.ldap_base_dn || ''} onChange={e => setConfig(c => ({...c, ldap_base_dn: e.target.value}))}
                  placeholder="DC=example,DC=com" className={inp} />
              </Field>
              <Field label="Bind DN (service account)">
                <input value={config.ldap_bind_dn || ''} onChange={e => setConfig(c => ({...c, ldap_bind_dn: e.target.value}))}
                  placeholder="CN=svc,DC=example,DC=com" className={inp} />
              </Field>
              <PwField label="Bind password" value={config._ldap_pw || ''}
                onChange={v => setConfig(c => ({...c, _ldap_pw: v}))}
                isSet={config.ldap_password_set} />
              <Field label="Username attribute">
                <input value={config.ldap_user_attr || 'sAMAccountName'} onChange={e => setConfig(c => ({...c, ldap_user_attr: e.target.value}))}
                  placeholder="sAMAccountName" className={inp} />
              </Field>
              <Field label="Email domain fallback" hint="Used if no email attribute found">
                <input value={config.ldap_email_domain || ''} onChange={e => setConfig(c => ({...c, ldap_email_domain: e.target.value}))}
                  placeholder="example.com" className={inp} />
              </Field>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Connection security">
                <select value={config.ldap_tls_mode || 'ldaps'}
                  onChange={e => setConfig(c => ({...c, ldap_tls_mode: e.target.value}))} className={inp}>
                  <option value="ldaps">LDAPS — TLS on port 636 (recommended)</option>
                  <option value="starttls">StartTLS — upgrade on port 389</option>
                  <option value="none">None — unencrypted (not recommended)</option>
                </select>
              </Field>
              <Field label="Port" hint={`Blank = default (${(config.ldap_tls_mode || 'ldaps') === 'ldaps' ? 636 : 389})`}>
                <input value={config.ldap_port || ''} onChange={e => setConfig(c => ({...c, ldap_port: e.target.value}))}
                  placeholder={(config.ldap_tls_mode || 'ldaps') === 'ldaps' ? '636' : '389'} className={inp} />
              </Field>
            </div>
            {(config.ldap_tls_mode || 'ldaps') === 'none' && (
              <p className="text-amber-400 text-xs">
                Without encryption, every staff member's password crosses the network in clear text when they sign in.
              </p>
            )}
            {(config.ldap_tls_mode || 'ldaps') !== 'none' && (
              <Field label="CA certificate (optional)"
                hint="Needed if your directory's certificate comes from an internal CA (typical for Active Directory) or is self-signed. Paste the CA certificate in PEM format. Certificates are always verified.">
                <textarea value={config.ldap_ca_cert_pem || ''} rows={4}
                  onChange={e => setConfig(c => ({...c, ldap_ca_cert_pem: e.target.value}))}
                  placeholder="-----BEGIN CERTIFICATE-----" className={`${inp} font-mono text-xs`} />
              </Field>
            )}
            {testResults.ldap && (
              <div className={`text-xs ${testResults.ldap.connected ? 'text-emerald-400' : 'text-red-400'}`}>
                <p>{testResults.ldap.connected ? `✓ Connected (${testResults.ldap.tls_mode} — ${testResults.ldap.uri})` : `✗ ${testResults.ldap.error}`}</p>
                {testResults.ldap.warning && <p className="text-amber-400">{testResults.ldap.warning}</p>}
              </div>
            )}
            {ldapMsg && (ldapMsg.ok
              ? <div className="text-xs space-y-1">
                  <p className="text-emerald-400">✓ LDAP settings saved</p>
                  {ldapMsg.warnings.map((w, i) => <p key={i} className="text-amber-400">{w}</p>)}
                </div>
              : <p className="text-red-400 text-xs">✗ {ldapMsg.error}</p>)}
            {(() => {
              const c = testResults.ldap?.certificate || ldapCert
              if (!c || ['disabled', 'unchecked', 'none'].includes(c.level)) return null
              const color = c.level === 'ok' ? 'text-emerald-400' : c.level === 'warning' ? 'text-amber-400' : 'text-red-400'
              return (
                <div className="text-xs flex items-start justify-between gap-2">
                  <p className={color}>Server certificate: {c.message}
                    {c.checked_at && <span className="text-slate-600"> · checked {new Date(c.checked_at).toLocaleString()}</span>}
                  </p>
                  <button onClick={() => api.post('/branding/auth-providers/ldap/cert-check').then(r => setLdapCert(r.data))}
                    className="text-slate-400 hover:text-slate-200 shrink-0">Check now</button>
                </div>
              )
            })()}
            <div className="flex gap-2">
              <button onClick={() => testProvider('ldap')} disabled={testing.ldap}
                className="flex items-center gap-1 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors disabled:opacity-40">
                <TestTube size={12} />{testing.ldap ? 'Testing…' : 'Test connection'}
              </button>
              <button onClick={saveLdap} disabled={saving.ldap}
                className="flex items-center gap-1 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 disabled:opacity-40 transition-colors">
                {saving.ldap ? <RefreshCw size={12} className="animate-spin" /> : null}
                {saving.ldap ? 'Saving…' : 'Save LDAP'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* SIP2 */}
      <div className="border border-slate-700/50 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 bg-slate-900/50 border-b border-slate-700/50">
          <div className="flex items-center gap-2">
            <CreditCard size={13} className="text-slate-400" />
            <span className="text-slate-300 text-sm font-medium">SIP2 — Library patron authentication</span>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <span className="text-slate-500 text-xs">{config.sip2_enabled ? 'Enabled' : 'Disabled'}</span>
            <div onClick={() => setConfig(c => ({...c, sip2_enabled: !c.sip2_enabled}))}
              className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${config.sip2_enabled ? 'bg-shield-600' : 'bg-slate-700'}`}>
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.sip2_enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
            </div>
          </label>
        </div>
        {config.sip2_enabled && (
          <div className="p-4 space-y-3">
            <p className="text-slate-500 text-xs mb-2">
              SIP2 authenticates library patrons via barcode + PIN against your ILS.
              Enable TLS (SIP2S) for any internet-facing deployment.
            </p>

            {/* ILS preset picker */}
            <ILSPresetPicker config={config} setConfig={setConfig} />

            {/* TLS toggle — prominent, at the top */}
            <div className={`rounded-lg border p-3 ${config.sip2_use_tls ? 'border-emerald-800 bg-emerald-900/10' : 'border-amber-800 bg-amber-900/10'}`}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-medium ${config.sip2_use_tls ? 'text-emerald-300' : 'text-amber-300'}`}>
                    {config.sip2_use_tls ? 'TLS enabled (SIP2S)' : 'Plain text — TLS disabled'}
                  </span>
                  <div onClick={() => setConfig(c => ({
                    ...c,
                    sip2_use_tls: !c.sip2_use_tls,
                    // Auto-switch default port
                    sip2_port: !c.sip2_use_tls ? (c.sip2_port === 6001 ? 6443 : c.sip2_port)
                                               : (c.sip2_port === 6443 ? 6001 : c.sip2_port),
                  }))}
                    className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${config.sip2_use_tls ? 'bg-emerald-600' : 'bg-amber-700'}`}>
                    <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.sip2_use_tls ? 'translate-x-4' : 'translate-x-0.5'}`} />
                  </div>
                </div>
                <span className={`text-xs ${config.sip2_use_tls ? 'text-emerald-500' : 'text-amber-500'}`}>
                  {config.sip2_use_tls ? 'Recommended ✓' : 'Not recommended for production'}
                </span>
              </div>
              {!config.sip2_use_tls && (
                <p className="text-amber-500 text-xs">
                  Plain SIP2 sends library card numbers and PINs as unencrypted ASCII text.
                  Enable TLS unless this is an isolated internal network with no internet exposure.
                </p>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="col-span-2">
                <Field label="ILS host">
                  <input value={config.sip2_host || ''} onChange={e => setConfig(c => ({...c, sip2_host: e.target.value}))}
                    placeholder="ils.yourlibrary.org" className={inp} />
                </Field>
              </div>
              <Field label={`Port (default: ${config.sip2_use_tls ? '6443' : '6001'})`}>
                <input type="number" value={config.sip2_port || (config.sip2_use_tls ? 6443 : 6001)}
                  onChange={e => setConfig(c => ({...c, sip2_port: parseInt(e.target.value)}))}
                  className={inp} />
              </Field>
              <Field label="Institution ID">
                <input value={config.sip2_institution_id || ''} onChange={e => setConfig(c => ({...c, sip2_institution_id: e.target.value}))}
                  placeholder="MYLIBRARY" className={inp} />
              </Field>
              <Field label="ILS login (optional)">
                <input value={config.sip2_ils_login || ''} onChange={e => setConfig(c => ({...c, sip2_ils_login: e.target.value}))}
                  placeholder="sip2user" className={inp} />
              </Field>
              <PwField label="ILS password" value={config._sip2_pw || ''}
                onChange={v => setConfig(c => ({...c, _sip2_pw: v}))}
                isSet={config.sip2_password_set} />
              <Field label="Patron email domain" hint="Used as email surrogate for patron accounts">
                <input value={config.sip2_email_domain || 'library.local'} onChange={e => setConfig(c => ({...c, sip2_email_domain: e.target.value}))}
                  placeholder="library.local" className={inp} />
              </Field>
              <Field label="Connection timeout (seconds)">
                <input type="number" min="3" max="30" value={config.sip2_timeout || 10}
                  onChange={e => setConfig(c => ({...c, sip2_timeout: parseInt(e.target.value)}))}
                  className={inp} />
              </Field>
            </div>

            {/* TLS certificate options — verification is always on */}
            {config.sip2_use_tls && (
              <div className="bg-slate-900 rounded-lg p-3 space-y-2">
                <p className="text-slate-400 text-xs font-medium uppercase tracking-wide">TLS certificate</p>
                <p className="text-slate-500 text-xs">
                  The ILS certificate is always verified. If it comes from an internal CA or is
                  self-signed, paste that CA certificate here — don't paste the ILS server's own
                  certificate, or sign-in will break the next time it renews.
                </p>
                <textarea value={config.sip2_ca_cert_pem || ''} rows={4}
                  onChange={e => setConfig(c => ({...c, sip2_ca_cert_pem: e.target.value}))}
                  placeholder="-----BEGIN CERTIFICATE-----" className={`${inp} font-mono text-xs`} />
                {config.sip2_ca_cert_path && (
                  <p className="text-slate-500 text-xs">
                    Also using the CA file at <code className="text-slate-300">{config.sip2_ca_cert_path}</code> (legacy setting).
                  </p>
                )}
              </div>
            )}
            {testResults.sip2 && (
              <div className="text-xs space-y-0.5">
                <p className={testResults.sip2.connected ? 'text-emerald-400' : 'text-red-400'}>
                  {testResults.sip2.connected
                    ? `✓ Connected to ILS${testResults.sip2.tls ? ' over TLS' : ''}`
                    : `✗ ${testResults.sip2.error}`}
                </p>
                {testResults.sip2.certificate && (
                  <p className={testResults.sip2.certificate.level === 'ok' ? 'text-emerald-400' : 'text-amber-400'}>
                    Certificate: {testResults.sip2.certificate.message}
                  </p>
                )}
                {testResults.sip2.warning && <p className="text-amber-400">{testResults.sip2.warning}</p>}
                {testResults.sip2.note && <p className="text-amber-400">{testResults.sip2.note}</p>}
              </div>
            )}
            {sip2Msg && (sip2Msg.ok
              ? <div className="text-xs space-y-1">
                  <p className="text-emerald-400">✓ SIP2 settings saved</p>
                  {sip2Msg.warnings.map((w, i) => <p key={i} className="text-amber-400">{w}</p>)}
                </div>
              : <p className="text-red-400 text-xs">✗ {sip2Msg.error}</p>)}
            <div className="flex gap-2">
              <button onClick={() => testProvider('sip2')} disabled={testing.sip2}
                className="flex items-center gap-1 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors disabled:opacity-40">
                <TestTube size={12} />{testing.sip2 ? 'Testing…' : 'Test connection'}
              </button>
              <button onClick={saveSip2} disabled={saving.sip2}
                className="flex items-center gap-1 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 disabled:opacity-40 transition-colors">
                {saving.sip2 ? <RefreshCw size={12} className="animate-spin" /> : null}
                {saving.sip2 ? 'Saving…' : 'Save SIP2'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* SAML 2.0 (any standards-compliant IdP) */}
      <SamlPanel />

      {/* OIDC providers */}
      {config.oidc_providers.map(p => (
        <OIDCProviderPanel key={p.key} provider={p} onSaved={updated => {
          setConfig(c => ({...c, oidc_providers: c.oidc_providers.map(x => x.key === updated.key ? updated : x)}))
        }} />
      ))}
    </Section>
  )
}

function OIDCProviderPanel({ provider, onSaved }) {
  const [form, setForm] = useState({ ...provider })
  const [open, setOpen] = useState(provider.enabled)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      await api.put(`/branding/auth-providers/oidc/${form.key}`, form)
      onSaved(form)
    } finally { setSaving(false) }
  }

  return (
    <div className="border border-slate-700/50 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-slate-900/50 border-b border-slate-700/50 cursor-pointer"
        onClick={() => setOpen(o => !o)}>
        <div className="flex items-center gap-2">
          <Globe size={13} className="text-slate-400" />
          <span className="text-slate-300 text-sm font-medium">{provider.label}</span>
          {provider.enabled && <span className="text-xs text-emerald-400 border border-emerald-800 bg-emerald-900/20 px-1.5 py-0.5 rounded">enabled</span>}
        </div>
        <ChevronDown size={13} className={`text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </div>
      {open && (
        <div className="p-4 space-y-3">
          {provider.note && (
            <p className="text-slate-500 text-xs bg-slate-900 rounded-lg px-3 py-2">{provider.note}</p>
          )}
          <label className="flex items-center gap-2 cursor-pointer">
            <div onClick={() => setForm(f => ({...f, enabled: !f.enabled}))}
              className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${form.enabled ? 'bg-shield-600' : 'bg-slate-700'}`}>
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${form.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
            </div>
            <span className="text-slate-300 text-sm">Enable {provider.label}</span>
          </label>
          {form.enabled && (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {provider.key === 'microsoft' && (
                  <Field label="Tenant ID" hint="Your Azure AD directory/tenant ID">
                    <input value={form.tenant_id || ''} onChange={e => setForm(f => ({...f, tenant_id: e.target.value}))}
                      placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" className={inp} />
                  </Field>
                )}
                <Field label="Discovery URL" hint="Leave blank to use preset">
                  <input value={form.discovery_url || ''} onChange={e => setForm(f => ({...f, discovery_url: e.target.value}))}
                    placeholder={provider.discovery_url || 'https://...'} className={inp} />
                </Field>
                <Field label="Client ID">
                  <input value={form.client_id || ''} onChange={e => setForm(f => ({...f, client_id: e.target.value}))}
                    placeholder="Client / Application ID" className={inp} />
                </Field>
                <PwField label="Client secret" value={form.client_secret || ''}
                  onChange={v => setForm(f => ({...f, client_secret: v}))}
                  isSet={provider.client_secret_set} />
                <Field label="Default role for new users">
                  <div className="relative">
                    <select value={form.default_role || 'parent'} onChange={e => setForm(f => ({...f, default_role: e.target.value}))}
                      className={`${inp} appearance-none pr-7`}>
                      <option value="parent">parent</option>
                      <option value="member">member</option>
                    </select>
                    <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
                  </div>
                </Field>
                <Field label="Allowed email domains">
                  <input value={form.allowed_domains || ''} onChange={e => setForm(f => ({...f, allowed_domains: e.target.value}))}
                    placeholder="yourlibrary.org" className={inp} />
                </Field>
                <Field label="Required groups (optional)">
                  <input value={form.required_groups || ''} onChange={e => setForm(f => ({...f, required_groups: e.target.value}))}
                    placeholder="library-staff" className={inp} />
                </Field>
              </div>
              {provider.key === 'google' && !(form.allowed_domains || '').trim() && (
                <p className="text-amber-400 text-xs">
                  Without an allowed domain, anyone with any Google account can sign in. Enter your
                  Workspace domain — personal Google accounts are then rejected, even ones using your domain's address.
                </p>
              )}
              {provider.key === 'microsoft' && ['common','organizations','consumers'].includes((form.tenant_id || '').trim().toLowerCase()) && !(form.allowed_domains || '').trim() && (
                <p className="text-amber-400 text-xs">
                  This tenant setting accepts accounts from any organization. Use your own tenant ID, or set allowed domains.
                </p>
              )}
              <label className="flex items-center gap-2 text-xs text-slate-400">
                <input type="checkbox" checked={!!form.auto_provision}
                  onChange={e => setForm(f => ({...f, auto_provision: e.target.checked}))} />
                Create accounts for new users from this provider even when registration is invite-only or admin-only
              </label>
              <p className="text-slate-600 text-xs">
                Super admin is never granted automatically through sign-in; promote accounts manually.
              </p>
              <p className="text-slate-600 text-xs">
                Redirect URI to register with your provider:{' '}
                <code className="bg-slate-700 px-1.5 rounded text-slate-300">
                  {window.location.origin}/api/auth/oidc/{provider.key}/callback
                </code>
              </p>
            </>
          )}
          <div className="flex justify-end">
            <button onClick={save} disabled={saving}
              className="flex items-center gap-1 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 disabled:opacity-40 transition-colors">
              {saving ? <RefreshCw size={12} className="animate-spin" /> : null}
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Branding() {
  const { user } = useAuth()

  if (user?.role !== 'super_admin') {
    return (
      <div className="p-4 md:p-6">
        <p className="text-slate-500 text-sm">Super admin access required.</p>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 max-w-3xl">
      <div className="mb-6">
        <h1 className="text-white text-xl font-semibold">Branding & institutional settings</h1>
        <p className="text-slate-400 text-sm mt-0.5">White-label, authentication, and deployment configuration</p>
      </div>
      <BrandingSection />
      <RegistrationSection />
      <BannerSection />
      <AuthProvidersSection />
    </div>
  )
}


// ── SAML 2.0 sign-in (home lab → university) ─────────────────────────────────
function SamlPanel() {
  const [cfg, setCfg] = useState(null)
  const [form, setForm] = useState({})
  const [metaMode, setMetaMode] = useState('url')   // 'url' | 'paste'
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(false)

  const load = () => api.get('/auth/saml/config').then(r => {
    setCfg(r.data)
    setForm({
      enabled: !!r.data.enabled, label: r.data.label || '', sp_base_url: r.data.sp_base_url || '',
      idp_metadata_url: r.data.idp_metadata_url || '', idp_metadata_xml: '',
      idp_entity_id: r.data.idp_entity_id || '', attr_email: r.data.attr_email || '',
      attr_name: r.data.attr_name || '', attr_groups: r.data.attr_groups || '',
      allowed_domains: r.data.allowed_domains || '', required_groups: r.data.required_groups || '',
      default_role: r.data.default_role || 'parent', auto_provision: r.data.auto_provision !== false,
    })
  }).catch(() => setCfg(false))
  useEffect(() => { load() }, [])

  const save = async () => {
    setSaving(true); setMsg(''); setErr('')
    try {
      const body = { ...form }
      if (metaMode === 'url') delete body.idp_metadata_xml; else delete body.idp_metadata_url
      if (!body.idp_metadata_xml) delete body.idp_metadata_xml
      const r = await api.put('/auth/saml/config', body)
      setCfg(r.data); setForm(f => ({ ...f, idp_metadata_xml: '' })); setMsg('Saved.')
    } catch (e) { setErr(e.response?.data?.detail || 'Save failed') }
    finally { setSaving(false) }
  }

  if (cfg === null) return null
  if (cfg === false) return null
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  const Copy = ({ label, value }) => (
    <div>
      <p className="text-slate-500 text-xs">{label}</p>
      <code className="block bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-300 text-xs break-all">{value}</code>
    </div>
  )

  return (
    <div className="border border-slate-700/60 rounded-xl p-4 space-y-3">
      <button onClick={() => setOpen(o => !o)} className="w-full flex items-center justify-between">
        <span className="text-slate-200 text-sm font-medium flex items-center gap-2">
          <Key size={14} className="text-shield-400" /> SAML 2.0 single sign-on
          {cfg.enabled && <span className="text-emerald-400 text-xs">enabled</span>}
        </span>
        <ChevronDown size={14} className={`text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <>
          <p className="text-slate-500 text-xs">
            For any SAML identity provider: a home-lab Keycloak or Authentik, a university Shibboleth,
            Microsoft ADFS or Entra, Okta, and others. Google Workspace and Microsoft 365 can also use
            the simpler OIDC options below.
          </p>

          <div className="space-y-2">
            <p className="text-slate-300 text-xs font-medium">1. Register PrivacyShield at your identity provider</p>
            <Copy label="SP metadata URL (easiest — many IdPs import this directly)" value={cfg.sp.metadata_url} />
            <Copy label="Entity ID" value={cfg.sp.entity_id} />
            <Copy label="Assertion Consumer Service (ACS) URL — HTTP-POST" value={cfg.sp.acs_url} />
            <Field label="Public base URL" hint="Must match how users reach this site, e.g. https://privacy.example.edu. Change this before registering at the IdP.">
              <input value={form.sp_base_url} onChange={set('sp_base_url')} placeholder={cfg.sp.entity_id.replace('/api/auth/saml/metadata','')} className={inp} />
            </Field>
          </div>

          <div className="space-y-2">
            <p className="text-slate-300 text-xs font-medium">2. Add your identity provider's metadata</p>
            <div className="flex gap-3 text-xs">
              <label className="flex items-center gap-1 text-slate-400"><input type="radio" checked={metaMode==='url'} onChange={() => setMetaMode('url')} /> From URL</label>
              <label className="flex items-center gap-1 text-slate-400"><input type="radio" checked={metaMode==='paste'} onChange={() => setMetaMode('paste')} /> Paste XML</label>
            </div>
            {metaMode === 'url' ? (
              <input value={form.idp_metadata_url} onChange={set('idp_metadata_url')} placeholder="https://idp.example.edu/idp/shibboleth" className={inp} />
            ) : (
              <textarea value={form.idp_metadata_xml} onChange={set('idp_metadata_xml')} rows={5}
                placeholder="<md:EntityDescriptor …>" className={`${inp} font-mono text-xs`} />
            )}
            {cfg.has_idp_metadata && (
              <p className="text-emerald-400/80 text-xs">Metadata loaded: {(cfg.idp_entity_ids || []).join(', ') || 'no IdP found'}</p>
            )}
            {cfg.metadata_error && <p className="text-red-400 text-xs">Stored metadata problem: {cfg.metadata_error}</p>}
            {cfg.signing_cert && cfg.signing_cert.level !== 'none' && (
              <p className={`text-xs ${cfg.signing_cert.level === 'ok' ? 'text-emerald-400/80'
                : cfg.signing_cert.level === 'warning' ? 'text-amber-400' : 'text-red-400'}`}>
                IdP signing certificate: {cfg.signing_cert.message}
              </p>
            )}
            {(cfg.idp_entity_ids || []).length > 1 && (
              <Field label="Which identity provider to use">
                <select value={form.idp_entity_id} onChange={set('idp_entity_id')} className={inp}>
                  <option value="">Choose…</option>
                  {cfg.idp_entity_ids.map(id => <option key={id} value={id}>{id}</option>)}
                </select>
              </Field>
            )}
          </div>

          <div className="space-y-2">
            <p className="text-slate-300 text-xs font-medium">3. Who may sign in</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <Field label="Allowed email domains" hint="Optional, comma-separated">
                <input value={form.allowed_domains} onChange={set('allowed_domains')} placeholder="example.edu" className={inp} />
              </Field>
              <Field label="Required groups / affiliations" hint="Optional, any-of — e.g. staff,faculty">
                <input value={form.required_groups} onChange={set('required_groups')} placeholder="staff,faculty" className={inp} />
              </Field>
              <Field label="Role for new users">
                <select value={form.default_role} onChange={set('default_role')} className={inp}>
                  <option value="parent">parent</option>
                  <option value="member">member</option>
                </select>
              </Field>
              <Field label="Login button label">
                <input value={form.label} onChange={set('label')} placeholder="University SSO" className={inp} />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-400">
              <input type="checkbox" checked={!!form.auto_provision} onChange={set('auto_provision')} />
              Create accounts for new users from this IdP even when registration is invite-only or admin-only
            </label>
            <details className="text-xs text-slate-500">
              <summary className="cursor-pointer">Attribute names (only if your IdP uses unusual ones)</summary>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2">
                <input value={form.attr_email} onChange={set('attr_email')} placeholder="email attr (default: mail)" className={inp} />
                <input value={form.attr_name} onChange={set('attr_name')} placeholder="name attr (default: displayName)" className={inp} />
                <input value={form.attr_groups} onChange={set('attr_groups')} placeholder="groups attr (default: groups/memberOf)" className={inp} />
              </div>
            </details>
            <p className="text-slate-600 text-xs">Super admin is never granted automatically through sign-in.</p>
          </div>

          <div className="flex items-center justify-between gap-2 flex-wrap">
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input type="checkbox" checked={!!form.enabled} onChange={set('enabled')} /> Enable SAML sign-in
            </label>
            <button onClick={save} disabled={saving}
              className="flex items-center gap-1 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 disabled:opacity-40">
              {saving ? 'Saving…' : 'Save SAML'}
            </button>
          </div>
          {msg && <p className="text-emerald-400 text-xs">{msg}</p>}
          {err && <p className="text-red-400 text-xs">{err}</p>}
        </>
      )}
    </div>
  )
}
