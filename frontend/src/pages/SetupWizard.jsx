import { useState, useRef, useEffect } from 'react'
import {
  Database, Mail, Palette, CheckCircle2, AlertTriangle, ChevronRight,
  ChevronLeft, SkipForward, Server, Shield, Globe, Home, Copy, Check,
  UploadCloud, X
} from 'lucide-react'
import api from '../api'

const STEPS = ['database', 'email', 'deployment', 'branding', 'summary']

export default function SetupWizard({ onDone }) {
  const [step, setStep] = useState(0)
  const [summary, setSummary] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const next = () => setStep(s => Math.min(s + 1, STEPS.length - 1))
  const back = () => setStep(s => Math.max(s - 1, 0))

  const skip = async (name) => {
    setBusy(true); setError('')
    try { await api.post('/wizard/skip', { step: name }); next() }
    catch (e) { setError(e.response?.data?.detail || 'Failed to skip') }
    finally { setBusy(false) }
  }

  const finish = async () => {
    setBusy(true)
    try {
      const r = await api.post('/wizard/complete')
      setSummary(r.data)
      setStep(4)
    } catch (e) { setError(e.response?.data?.detail || 'Failed to finish') }
    finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {/* Progress */}
        <div className="flex items-center justify-center gap-2 mb-6">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium
                ${i < step ? 'bg-shield-600 text-white' : i === step ? 'bg-shield-500 text-white' : 'bg-slate-800 text-slate-500'}`}>
                {i < step ? <CheckCircle2 size={16} /> : i + 1}
              </div>
              {i < STEPS.length - 1 && <div className={`w-8 h-0.5 ${i < step ? 'bg-shield-600' : 'bg-slate-800'}`} />}
            </div>
          ))}
        </div>

        <div className="bg-slate-900 rounded-2xl border border-slate-800 p-6">
          {error && (
            <div className="mb-4 px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs">{error}</div>
          )}

          {step === 0 && <DatabaseStep onNext={next} onSkip={() => skip('database')} busy={busy} setError={setError} />}
          {step === 1 && <EmailStep onNext={next} onSkip={() => skip('email')} onBack={back} busy={busy} setError={setError} />}
          {step === 2 && <DeploymentStep onNext={next} onSkip={() => skip('deployment')} onBack={back} busy={busy} setError={setError} />}
          {step === 3 && <BrandingStep onNext={finish} onSkip={async () => { await skip('branding'); finish() }} onBack={back} busy={busy} setError={setError} />}
          {step === 4 && <SummaryStep summary={summary} onDone={onDone} />}
        </div>
      </div>
    </div>
  )
}

function StepHeader({ icon: Icon, title, subtitle }) {
  return (
    <div className="mb-5">
      <h2 className="text-white text-lg font-semibold flex items-center gap-2">
        <Icon size={18} className="text-shield-500" /> {title}
      </h2>
      {subtitle && <p className="text-slate-400 text-sm mt-1">{subtitle}</p>}
    </div>
  )
}

const inp = "w-full bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-3 py-2 placeholder-slate-500"

function Buttons({ onBack, onSkip, onNext, nextLabel = 'Continue', busy }) {
  return (
    <div className="flex items-center justify-between mt-6">
      <div>
        {onBack && <button onClick={onBack} className="flex items-center gap-1 text-slate-400 hover:text-slate-200 text-sm px-2 py-1.5"><ChevronLeft size={15} /> Back</button>}
      </div>
      <div className="flex items-center gap-2">
        {onSkip && <button onClick={onSkip} disabled={busy} className="flex items-center gap-1 text-slate-400 hover:text-slate-200 text-sm px-3 py-1.5"><SkipForward size={14} /> Skip</button>}
        <button onClick={onNext} disabled={busy} className="flex items-center gap-1 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-sm rounded-lg px-4 py-2">
          {busy ? 'Saving…' : nextLabel} <ChevronRight size={15} />
        </button>
      </div>
    </div>
  )
}

// ── Step 1: Database ──────────────────────────────────────────────────────────
function DatabaseStep({ onNext, onSkip, busy, setError }) {
  const [kind, setKind] = useState('sqlite')
  const [pg, setPg] = useState({ host: '', port: 5432, database: '', username: '', password: '', sslmode: 'prefer' })
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true); setError('')
    try {
      await api.post('/wizard/database', kind === 'postgres' ? { kind, ...pg } : { kind })
      onNext()
    } catch (e) { setError(e.response?.data?.detail || 'Failed to save database settings') }
    finally { setSaving(false) }
  }

  return (
    <div>
      <StepHeader icon={Database} title="Database" subtitle="Where OpenOptOut stores its data." />
      <div className="space-y-3">
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${kind === 'sqlite' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <input type="radio" checked={kind === 'sqlite'} onChange={() => setKind('sqlite')} className="mt-1 accent-shield-500" />
          <div>
            <div className="text-slate-200 text-sm font-medium">SQLite (this machine)</div>
            <div className="text-slate-400 text-xs">Simplest. Stored in a local file on this server. Good for small/single-machine deployments.</div>
          </div>
        </label>
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${kind === 'postgres' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <input type="radio" checked={kind === 'postgres'} onChange={() => setKind('postgres')} className="mt-1 accent-shield-500" />
          <div className="flex-1">
            <div className="text-slate-200 text-sm font-medium flex items-center gap-1"><Server size={13} /> PostgreSQL (dedicated / remote server)</div>
            <div className="text-slate-400 text-xs">For larger deployments. Point at your own Postgres server — it does not have to be on this machine.</div>
          </div>
        </label>
        {kind === 'postgres' && (
          <div className="grid grid-cols-2 gap-2 pl-2 pt-1">
            <input className={inp} placeholder="Host (e.g. db.internal)" value={pg.host} onChange={e => setPg({ ...pg, host: e.target.value })} />
            <input className={inp} placeholder="Port" value={pg.port} onChange={e => setPg({ ...pg, port: +e.target.value || 5432 })} />
            <input className={inp} placeholder="Database name" value={pg.database} onChange={e => setPg({ ...pg, database: e.target.value })} />
            <input className={inp} placeholder="Username" value={pg.username} onChange={e => setPg({ ...pg, username: e.target.value })} />
            <input className={inp} type="password" placeholder="Password" value={pg.password} onChange={e => setPg({ ...pg, password: e.target.value })} />
            <select className={inp} value={pg.sslmode} onChange={e => setPg({ ...pg, sslmode: e.target.value })}>
              <option value="prefer">SSL: prefer</option>
              <option value="require">SSL: require</option>
              <option value="disable">SSL: disable</option>
            </select>
            <p className="col-span-2 text-amber-400/80 text-xs flex items-center gap-1"><AlertTriangle size={11} /> Changing the database takes effect after a restart.</p>
          </div>
        )}
      </div>
      <Buttons onSkip={onSkip} onNext={save} busy={saving || busy} />
    </div>
  )
}

// ── Step 2: Email ─────────────────────────────────────────────────────────────
function EmailStep({ onNext, onSkip, onBack, busy, setError }) {
  const [mode, setMode] = useState('shared')
  const [provider, setProvider] = useState('')
  const [smtp, setSmtp] = useState({ smtp_host: '', smtp_port: 587, imap_host: '', imap_port: 993, username: '', password: '', tls: 'starttls', from_address: '' })
  const [advanced, setAdvanced] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploaded, setUploaded] = useState([])       // extra providers uploaded here
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState('')

  const uploadProvider = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true); setUploadMsg(''); setError('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      // expected_type=email: the server refuses any other kind of plugin before
      // installing it, and puts this one in the email plugins folder.
      const r = await api.post('/plugins/upload?expected_type=email', fd,
        { headers: { 'Content-Type': 'multipart/form-data' } })
      // Enable it (email providers are a trusted class; the upload already ran
      // the hidden-recipient inspection and blocked on high-severity findings).
      try {
        await api.post(`/plugins/${r.data.plugin_id}/enable`, {
          granted_permissions: r.data.requested_permissions || [],
          acknowledge_methods: true,
        })
      } catch (_) { /* enable may need review; still selectable */ }
      setUploaded(u => [...u, { plugin_id: r.data.plugin_id, name: r.data.plugin_id }])
      setProvider(r.data.plugin_id)
      setUploadMsg(`Installed "${r.data.plugin_id}" into plugins/${r.data.destination} and selected it.`)
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed (the inspector may have rejected it).')
    } finally { setUploading(false); e.target.value = '' }
  }

  const save = async () => {
    setSaving(true); setError('')
    try {
      // Proton (via Bridge) is the generic-SMTP transport pointed at the local
      // Bridge endpoint — save it as 'smtp' with the Bridge fields.
      const effectiveProvider = provider === 'proton' ? 'smtp' : provider
      const body = { mode, provider: effectiveProvider, separate_admin_smtp: advanced }
      if (effectiveProvider === 'smtp') Object.assign(body, smtp)
      await api.post('/wizard/email', body)
      onNext()
    } catch (e) { setError(e.response?.data?.detail || 'Failed to save email settings') }
    finally { setSaving(false) }
  }

  // Proton: pre-fill the SMTP fields with Proton Bridge's default LOCAL endpoints.
  // Bridge must already be installed and running on this host — the wizard cannot
  // install it (OS-level software with an interactive Proton login + 2FA).
  const chooseProton = () => {
    setProvider('proton')
    setSmtp(s => ({ ...s, smtp_host: '127.0.0.1', smtp_port: 1025,
                    imap_host: '127.0.0.1', imap_port: 1143, tls: 'starttls' }))
  }

  return (
    <div>
      <StepHeader icon={Mail} title="Email" subtitle="How opt-out requests are sent and confirmations received. This is the most important step." />

      {/* Loud warning */}
      <div className="mb-4 px-3 py-2.5 rounded-lg border border-amber-700 bg-amber-950/30 flex items-start gap-2">
        <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
        <p className="text-amber-200 text-xs">Without email configured, opt-outs are prepared but <strong>never actually sent</strong>. You can skip this and set it up later in Settings, but the tool won't do anything until you do.</p>
      </div>

      {/* Mode */}
      <p className="text-slate-300 text-sm font-medium mb-2">Deployment mode</p>
      <div className="space-y-2 mb-4">
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${mode === 'shared' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <input type="radio" checked={mode === 'shared'} onChange={() => setMode('shared')} className="mt-1 accent-shield-500" />
          <div>
            <div className="text-slate-200 text-sm font-medium">Shared inbox</div>
            <div className="text-slate-400 text-xs">One account sends all opt-outs and receives all confirmations. Simplest to run.</div>
          </div>
        </label>
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${mode === 'per_user' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <input type="radio" checked={mode === 'per_user'} onChange={() => setMode('per_user')} className="mt-1 accent-shield-500" />
          <div>
            <div className="text-slate-200 text-sm font-medium">Per-user email</div>
            <div className="text-slate-400 text-xs">Each user grants access to their own email; their opt-outs come from their own address. More private; uses OAuth.</div>
          </div>
        </label>
      </div>

      {/* Transport */}
      <p className="text-slate-300 text-sm font-medium mb-2">Email provider / transport</p>
      <div className="px-3 py-2 rounded-lg border border-slate-700 bg-slate-800/40 mb-2">
        <p className="text-slate-400 text-xs flex items-start gap-1.5"><Shield size={12} className="text-shield-400 shrink-0 mt-0.5" /> <span><strong className="text-slate-300">OAuth is recommended</strong> where available (Gmail, Outlook, Yahoo) — it's more secure and won't break as providers tighten SMTP. Use SMTP/app-password only if your provider or self-hosted setup requires it.</span></p>
      </div>
      <select className={inp} value={provider} onChange={e => {
        if (e.target.value === 'proton') { chooseProton() } else { setProvider(e.target.value) }
      }}>
        <option value="">Choose a provider…</option>
        <option value="gmail">Gmail / Google Workspace (OAuth)</option>
        <option value="outlook">Outlook / Microsoft 365 (OAuth)</option>
        <option value="yahoo">Yahoo (OAuth or app-password)</option>
        <option value="smtp">Generic SMTP / IMAP (self-hosted / on-prem)</option>
        <option value="proton">Proton Mail (via Proton Bridge)</option>
        {uploaded.map(u => (
          <option key={u.plugin_id} value={u.plugin_id}>{u.name} (uploaded)</option>
        ))}
      </select>

      {/* Bring your own provider */}
      <div className="mt-2 px-3 py-2.5 rounded-lg border border-slate-700 bg-slate-800/40">
        <p className="text-slate-300 text-xs font-medium mb-1">Use a different email service?</p>
        <p className="text-slate-400 text-xs mb-2">
          Upload an email-provider plugin (e.g. Proton, Apple, or any custom service). It's
          inspected for hidden recipients before it's trusted, then installed and selectable here.
        </p>
        <label className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-800 cursor-pointer">
          {uploading ? 'Uploading…' : 'Upload provider plugin (.zip)'}
          <input type="file" accept=".zip" className="hidden" onChange={uploadProvider} disabled={uploading} />
        </label>
        {uploadMsg && <p className="text-emerald-300/90 text-xs mt-1.5">{uploadMsg}</p>}
      </div>
      {provider && provider !== 'smtp' && provider !== 'proton' && (
        <ConnectOAuth provider={provider} setError={setError} />
      )}
      {provider === 'proton' && (
        <div className="mt-2 px-3 py-2.5 rounded-lg border border-amber-700/70 bg-amber-950/25">
          <p className="text-amber-200 text-xs font-medium mb-1">Proton requires Proton Bridge (installed separately)</p>
          <p className="text-amber-300/90 text-xs">
            Proton Mail has no standard API. You must install and run <strong>Proton Bridge</strong> on
            this server (or a reachable host) and log into it with your Proton account — the wizard
            can't do this for you, since it's OS-level software with an interactive login. Once Bridge
            is running, it exposes a local SMTP/IMAP endpoint that OpenOptOut connects to. The fields
            below are pre-filled with Bridge's defaults — adjust if your Bridge uses different ports.
            {' '}<a href="https://proton.me/mail/bridge" target="_blank" rel="noopener noreferrer" className="underline">Proton Bridge docs →</a>
          </p>
          <p className="text-amber-300/70 text-xs mt-1">
            Note: if OpenOptOut runs in Docker, <code>127.0.0.1</code> refers to the container — you may
            need to point at the host (e.g. <code>host.docker.internal</code>) and allow Bridge to accept it.
          </p>
        </div>
      )}
      {(provider === 'smtp' || provider === 'proton') && (
        <div className="grid grid-cols-2 gap-2 mt-2">
          <input className={inp} placeholder="SMTP host" value={smtp.smtp_host} onChange={e => setSmtp({ ...smtp, smtp_host: e.target.value })} />
          <input className={inp} placeholder="SMTP port" value={smtp.smtp_port} onChange={e => setSmtp({ ...smtp, smtp_port: +e.target.value || 587 })} />
          <input className={inp} placeholder="IMAP host (to read confirmations)" value={smtp.imap_host} onChange={e => setSmtp({ ...smtp, imap_host: e.target.value })} />
          <input className={inp} placeholder="IMAP port" value={smtp.imap_port} onChange={e => setSmtp({ ...smtp, imap_port: +e.target.value || 993 })} />
          <input className={inp} placeholder="Username" value={smtp.username} onChange={e => setSmtp({ ...smtp, username: e.target.value })} />
          <input className={inp} type="password" placeholder={provider === 'proton' ? 'Bridge password' : 'Password / app-password'} value={smtp.password} onChange={e => setSmtp({ ...smtp, password: e.target.value })} />
          <input className={inp} placeholder="From address" value={smtp.from_address} onChange={e => setSmtp({ ...smtp, from_address: e.target.value })} />
          <select className={inp} value={smtp.tls} onChange={e => setSmtp({ ...smtp, tls: e.target.value })}>
            <option value="starttls">STARTTLS</option>
            <option value="ssl">SSL</option>
            <option value="none">No TLS</option>
          </select>
        </div>
      )}

      {/* Advanced */}
      <label className="flex items-center gap-2 mt-4 text-xs text-slate-400 cursor-pointer">
        <input type="checkbox" checked={advanced} onChange={e => setAdvanced(e.target.checked)} className="accent-shield-500" />
        Advanced: use a separate account for the tool's own admin/notification email
      </label>

      <Buttons onBack={onBack} onSkip={onSkip} onNext={save} busy={saving || busy} />
    </div>
  )
}

// OAuth "Connect account" flow: register client creds (host-held), then run the
// host-side authorization and confirm the account connected.
function ConnectOAuth({ provider, setError }) {
  const [client, setClient] = useState({ client_id: '', client_secret: '', redirect_uri: '' })
  const [status, setStatus] = useState(null)   // null | 'connecting' | connected obj
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  // default the redirect URI to this app's callback
  const defaultRedirect = typeof window !== 'undefined'
    ? `${window.location.origin}/api/email-oauth/callback` : ''

  const checkStatus = async () => {
    try {
      const r = await api.get('/email-oauth/status?account_ref=default')
      if (r.data.connected) setStatus(r.data)
    } catch { /* not connected yet */ }
  }

  const connect = async () => {
    setBusy(true); setError('')
    try {
      // 1) store the operator's client credentials (secret stays host-side)
      await api.post('/email-oauth/client', {
        provider_key: provider,
        client_id: client.client_id,
        client_secret: client.client_secret,
        redirect_uri: client.redirect_uri || defaultRedirect,
      })
      // 2) begin authorization; open the consent screen
      const r = await api.post('/email-oauth/begin', { provider_key: provider, account_ref: 'default' })
      setStatus('connecting')
      const popup = window.open(r.data.authorize_url, 'oauth', 'width=520,height=680')
      // 3) poll for completion (the callback stores tokens host-side)
      const iv = setInterval(async () => {
        try {
          const st = await api.get('/email-oauth/status?account_ref=default')
          if (st.data.connected) {
            clearInterval(iv)
            setStatus(st.data)
            if (popup && !popup.closed) popup.close()
          }
        } catch { /* keep polling */ }
      }, 2500)
      setTimeout(() => clearInterval(iv), 300000)  // stop after 5 min
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not start the connect flow')
    } finally { setBusy(false) }
  }

  if (status && status !== 'connecting') {
    return (
      <div className="mt-2 px-3 py-2 rounded-lg border border-emerald-800/60 bg-emerald-950/20 text-emerald-200 text-xs flex items-center gap-2">
        <CheckCircle2 size={13} /> Account connected{status.expired ? ' (token will refresh on use)' : ''}.
      </div>
    )
  }

  return (
    <div className="mt-2 px-3 py-3 rounded-lg border border-slate-700 bg-slate-800/40">
      <p className="text-slate-300 text-xs font-medium mb-1">Connect this account (OAuth)</p>
      <p className="text-slate-400 text-xs mb-2">
        Register your OAuth app's credentials, then grant access. The client secret is stored
        encrypted on this server and never shared with plugins. You create these in the provider's
        developer console ({provider === 'gmail' ? 'Google Cloud' : provider === 'outlook' ? 'Azure' : 'the provider console'}).
      </p>
      <div className="mb-2 px-2.5 py-2 rounded-lg border border-amber-800/50 bg-amber-950/20">
        <p className="text-amber-200/90 text-xs font-medium mb-1">Before connecting: register this redirect URI</p>
        <p className="text-slate-400 text-xs mb-1.5">
          In that developer console, find "Authorized redirect URIs" (Google) or "Redirect URIs" (Azure)
          on this OAuth client and add this exact value — it won't work otherwise, and you'll see an
          error like "doesn't comply with OAuth 2.0 policy" or "redirect_uri_mismatch":
        </p>
        <div className="flex items-center gap-1.5">
          <code className="flex-1 text-[11px] text-slate-200 bg-slate-900/70 rounded-sm px-2 py-1 break-all">{defaultRedirect}</code>
          <button type="button" onClick={() => {
              navigator.clipboard?.writeText(defaultRedirect); setCopied(true); setTimeout(() => setCopied(false), 1500)
            }}
            className="shrink-0 p-1.5 rounded-sm text-slate-400 hover:text-slate-200 hover:bg-slate-700/60"
            title="Copy redirect URI">
            {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
          </button>
        </div>
        <p className="text-slate-500 text-[11px] mt-1.5">
          This is computed from the address you're using to reach OpenOptOut right now — if you
          later move to a different domain or turn on HTTPS, add that URI here too and register it
          the same way; each address needs its own entry.
        </p>
      </div>
      <div className="space-y-2">
        <input className={inp} placeholder="Client ID" value={client.client_id} onChange={e => setClient({ ...client, client_id: e.target.value })} />
        <input className={inp} type="password" placeholder="Client secret" value={client.client_secret} onChange={e => setClient({ ...client, client_secret: e.target.value })} />
        <input className={inp} placeholder={`Redirect URI (default: ${defaultRedirect})`} value={client.redirect_uri} onChange={e => setClient({ ...client, redirect_uri: e.target.value })} />
      </div>
      <button onClick={connect} disabled={busy || !client.client_id || !client.client_secret}
        className="mt-2 px-3 py-1.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-xs rounded-lg">
        {status === 'connecting' ? 'Waiting for consent…' : busy ? 'Starting…' : 'Connect account'}
      </button>
      {status === 'connecting' && (
        <p className="text-slate-400 text-xs mt-1.5">A consent window opened — approve access there, then this will update automatically.</p>
      )}
    </div>
  )
}

// ── Step 3: Deployment / reverse proxy ─────────────────────────────────────────
function DeploymentStep({ onNext, onSkip, onBack, busy, setError }) {
  const [mode, setMode] = useState('managed')
  const [domain, setDomain] = useState('')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true); setError('')
    try {
      await api.post('/wizard/deployment', { reverse_proxy: mode, domain: (mode === 'managed' || mode === 'native') ? domain : '' })
      onNext()
    } catch (e) { setError(e.response?.data?.detail || 'Failed to save deployment settings') }
    finally { setSaving(false) }
  }

  return (
    <div>
      <StepHeader icon={Globe} title="How is HTTPS handled here?" subtitle="Decides whether OpenOptOut should manage HTTPS itself, or stay out of the way of something that already does." />
      <div className="space-y-3">
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${mode === 'managed' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <input type="radio" checked={mode === 'managed'} onChange={() => setMode('managed')} className="mt-1 accent-shield-500" />
          <div className="flex-1">
            <div className="text-slate-200 text-sm font-medium flex items-center gap-1"><Home size={13} /> Running via Docker — set up HTTPS for me</div>
            <div className="text-slate-400 text-xs">Docker (bare metal or a VM — it doesn't matter which), nothing else already on ports 80 or 443. OpenOptOut's built-in Caddy container gets and renews certificates automatically.</div>
            {mode === 'managed' && (
              <input className={`${inp} mt-2`} placeholder="Domain, if you know it yet (e.g. privacy.yourlibrary.org) — optional"
                value={domain} onChange={e => setDomain(e.target.value)} />
            )}
          </div>
        </label>
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${mode === 'native' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <input type="radio" checked={mode === 'native'} onChange={() => setMode('native')} className="mt-1 accent-shield-500" />
          <div className="flex-1">
            <div className="text-slate-200 text-sm font-medium flex items-center gap-1"><Server size={13} /> Native install, no containers — set up HTTPS for me</div>
            <div className="text-slate-400 text-xs">OpenOptOut runs directly on this VM or bare-metal host (systemd on Linux, a Windows Service on Windows) — no Docker. HTTPS is handled the same way: certbot + nginx on Linux, or win-acme + IIS on Windows. See docs/NATIVE_INSTALL.md.</div>
            {mode === 'native' && (
              <input className={`${inp} mt-2`} placeholder="Domain, if you know it yet (e.g. privacy.yourlibrary.org) — optional"
                value={domain} onChange={e => setDomain(e.target.value)} />
            )}
          </div>
        </label>
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${mode === 'external' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <input type="radio" checked={mode === 'external'} onChange={() => setMode('external')} className="mt-1 accent-shield-500" />
          <div className="flex-1">
            <div className="text-slate-200 text-sm font-medium flex items-center gap-1"><Server size={13} /> Something else already terminates HTTPS</div>
            <div className="text-slate-400 text-xs">A load balancer, IIS, nginx, or another team's reverse proxy already handles TLS in front of OpenOptOut — whether OpenOptOut itself runs in Docker or natively. We won't suggest anything that would fight it for ports 80/443, or nag about plain HTTP once you're reaching it over https.</div>
          </div>
        </label>
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${mode === 'none' ? 'border-amber-700 bg-amber-950/10' : 'border-slate-700'}`}>
          <input type="radio" checked={mode === 'none'} onChange={() => setMode('none')} className="mt-1 accent-shield-500" />
          <div>
            <div className="text-slate-200 text-sm font-medium">Neither — decide later</div>
            <div className="text-slate-400 text-xs">Fine for local testing. You'll keep seeing a plain-HTTP warning until this is behind HTTPS one way or the other.</div>
          </div>
        </label>
      </div>
      <Buttons onBack={onBack} onSkip={onSkip} onNext={save} busy={saving || busy} />
    </div>
  )
}

// ── Step 4: Branding ──────────────────────────────────────────────────────────
// A hex text field that's still freely typable, with a small color-swatch
// "prefix" button that opens the native color picker on click (a hidden real
// <input type="color"> triggered via .click() — same trick already used for
// the hidden file input below, since a color input can't be styled directly
// but can be driven from any element).
function HexColorField({ label, value, onChange, placeholder = '#4f46e5' }) {
  const colorRef = useRef()
  const isValidHex = /^#[0-9A-Fa-f]{6}$/.test(value || '')
  const swatchColor = isValidHex ? value : '#334155'

  return (
    <div>
      {label && <p className="text-slate-400 text-xs mb-1">{label}</p>}
      <div className="relative">
        <button type="button" onClick={() => colorRef.current?.click()}
          className="absolute left-2 top-1/2 -translate-y-1/2 w-5 h-5 rounded-sm border border-slate-600"
          style={{ background: swatchColor }} title="Pick a color" />
        <input className={`${inp} pl-9 font-mono`} placeholder={placeholder}
          value={value} onChange={e => onChange(e.target.value)} />
        {/* Visually hidden but real — native color pickers can't be built from
            scratch, so this is what actually renders the OS/browser picker. */}
        <input ref={colorRef} type="color" value={isValidHex ? value : placeholder}
          onChange={e => onChange(e.target.value)}
          className="absolute w-0 h-0 opacity-0 pointer-events-none" tabIndex={-1} />
      </div>
    </div>
  )
}

// Drag-and-drop (native HTML5 dragover/drop events) logo uploader, click-to-
// browse fallback. Uploads straight to POST /api/branding/logo — the same
// endpoint Settings → Branding uses — so the logo shows up everywhere in the
// app immediately, not just after "Finish".
function LogoDropzone({ logoUrl, onUploaded, onRemoved, setError }) {
  const fileRef = useRef()
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)

  const upload = async (file) => {
    if (!file) return
    if (!['image/png', 'image/svg+xml', 'image/jpeg', 'image/webp'].includes(file.type)) {
      setError('Logo must be PNG, SVG, JPEG, or WebP'); return
    }
    setError(''); setUploading(true)
    const fd = new FormData(); fd.append('file', file)
    try {
      const r = await api.post('/branding/logo', fd)
      onUploaded(r.data.logo_url)
    } catch (e) {
      setError(e.response?.data?.detail || 'Logo upload failed')
    } finally { setUploading(false) }
  }

  const remove = async () => {
    try { await api.delete('/branding/logo'); onRemoved() } catch { /* ignore */ }
  }

  return (
    <div>
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); upload(e.dataTransfer.files?.[0]) }}
        onClick={() => fileRef.current?.click()}
        role="button" tabIndex={0}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') fileRef.current?.click() }}
        className={`flex flex-col items-center justify-center gap-1.5 border-2 border-dashed rounded-lg py-5 px-3 cursor-pointer transition-colors
          ${dragOver ? 'border-shield-500 bg-shield-900/20' : 'border-slate-700 hover:border-slate-600'}`}>
        {logoUrl ? (
          <img src={`${logoUrl}`} alt="Logo" className="h-12 object-contain" />
        ) : (
          <UploadCloud size={20} className={dragOver ? 'text-shield-400' : 'text-slate-500'} />
        )}
        <p className="text-slate-400 text-xs text-center">
          {uploading ? 'Uploading…' : logoUrl ? 'Drop a new image to replace, or click to browse' : 'Drag & drop a logo here, or click to browse'}
        </p>
        <p className="text-slate-600 text-[11px]">PNG, SVG, JPEG, or WebP</p>
        <input ref={fileRef} type="file" accept="image/png,image/svg+xml,image/jpeg,image/webp"
          className="hidden" onChange={e => { upload(e.target.files?.[0]); e.target.value = '' }} />
      </div>
      {logoUrl && (
        <button type="button" onClick={remove}
          className="mt-1 flex items-center gap-1 text-slate-500 hover:text-red-400 text-xs">
          <X size={11} /> Remove logo
        </button>
      )}
    </div>
  )
}

function BrandingStep({ onNext, onSkip, onBack, busy, setError }) {
  const [b, setB] = useState({ system_name: '', primary_color: '' })
  const [logoUrl, setLogoUrl] = useState(null)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true); setError('')
    try { await api.post('/wizard/branding', b); onNext() }
    catch (e) { setError(e.response?.data?.detail || 'Failed to save branding') }
    finally { setSaving(false) }
  }

  return (
    <div>
      <StepHeader icon={Palette} title="Branding (optional)" subtitle="Cosmetic only — you can set or change this anytime in Settings." />
      <div className="space-y-3">
        <input className={inp} placeholder="System name (e.g. Springfield Library Privacy)" value={b.system_name} onChange={e => setB({ ...b, system_name: e.target.value })} />
        <div>
          <p className="text-slate-400 text-xs mb-1">Logo</p>
          <LogoDropzone logoUrl={logoUrl} onUploaded={setLogoUrl} onRemoved={() => setLogoUrl(null)} setError={setError} />
        </div>
        <HexColorField label="Primary color" value={b.primary_color} onChange={v => setB({ ...b, primary_color: v })} />
      </div>
      <Buttons onBack={onBack} onSkip={onSkip} onNext={save} nextLabel="Finish" busy={saving || busy} />
    </div>
  )
}

// ── Step 5: Summary ───────────────────────────────────────────────────────────
function SummaryStep({ summary, onDone }) {
  const steps = summary?.steps || {}
  const reverseProxy = summary?.reverse_proxy
  const [mfaStatus, setMfaStatus] = useState(null)

  useEffect(() => {
    api.get('/auth/mfa/status')
      .then(r => setMfaStatus(r.data))
      .catch(() => {})
  }, [])

  return (
    <div>
      <StepHeader icon={CheckCircle2} title="You're ready" subtitle="Here's what's set up." />
      <div className="space-y-2 mb-4">
        {['database', 'email', 'deployment', 'branding'].map(s => (
          <div key={s} className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/50">
            <span className="text-slate-300 text-sm capitalize">{s}</span>
            <span className={`text-xs ${steps[s] === 'done' ? 'text-emerald-400' : 'text-slate-500'}`}>
              {steps[s] === 'done' ? '✓ configured' : 'skipped'}
            </span>
          </div>
        ))}
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/50">
          <span className="text-slate-300 text-sm">Super Admin MFA</span>
          <span className={`text-xs ${mfaStatus?.mfa_enabled ? 'text-emerald-400' : 'text-amber-400'}`}>
            {mfaStatus?.mfa_enabled ? '✓ configured' : '3-day grace period active'}
          </span>
        </div>
      </div>
      {summary?.warnings?.length > 0 && (
        <div className="space-y-2 mb-4">
          {summary.warnings.map((w, i) => (
            <div key={i} className="px-3 py-2 rounded-lg border border-amber-700 bg-amber-950/30 text-amber-200 text-xs flex items-start gap-2">
              <AlertTriangle size={13} className="shrink-0 mt-0.5" /> {w}
            </div>
          ))}
        </div>
      )}
      {/* Someone chose "already has a reverse proxy" — trust that call and stay quiet;
          otherwise, the generic plain-HTTP check (also on the Dashboard) still applies. */}
      {reverseProxy !== 'external' &&
        typeof window !== 'undefined' && window.location.protocol === 'http:' &&
        !['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname) && (
        <div className="mb-4 px-3 py-2 rounded-lg border border-amber-700 bg-amber-950/30 text-amber-200 text-xs flex items-start gap-2">
          <AlertTriangle size={13} className="shrink-0 mt-0.5" />
          <span>
            This site is using plain HTTP, so passwords cross the network unencrypted, and Google/Microsoft
            sign-in won't work.{' '}
            {reverseProxy === 'native'
              ? <>Turn on HTTPS on the server with <code>scripts/enable-https-native.sh</code> (Linux) or follow the Windows steps in <code>docs/NATIVE_INSTALL.md</code>.</>
              : <>Turn on HTTPS on the server with <code>./scripts/enable-https.sh</code> (Linux/macOS) or <code>scripts\enable-https.ps1</code> (Windows) — see docs/HTTPS.md.</>}
          </span>
        </div>
      )}
      {(reverseProxy === 'managed' || reverseProxy === 'native') && (
        <div className="mb-4 px-3 py-2 rounded-lg border border-slate-700 bg-slate-800/40 text-slate-400 text-xs">
          After you run the script and restart{reverseProxy === 'native' ? ' the service' : ' the containers'}, the dashboard will show a live
          check confirming whether the certificate actually came up — no need to just take it on faith.
        </div>
      )}
      <div className="text-slate-400 text-sm mb-4">
        Next: add the people you're removing data for, and import your broker list — both from the dashboard.
      </div>
      <button onClick={onDone} className="w-full bg-shield-600 hover:bg-shield-700 text-white text-sm rounded-lg py-2.5">
        Go to dashboard
      </button>
    </div>
  )
}
