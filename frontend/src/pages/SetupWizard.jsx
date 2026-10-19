import { useState, useRef, useEffect } from 'react'
import {
  Database, Mail, Palette, CheckCircle2, AlertTriangle, ChevronRight,
  ChevronLeft, SkipForward, Server, Shield, Globe, Home, Copy, Check,
  UploadCloud, X, Eye, EyeOff, Key, Sparkles, Sliders, Zap
} from 'lucide-react'
import api from '../api'
import { tx, txr } from '../i18n/tx'
import { SecretKeyGeneratorPanel } from '../components/SecretKeyBanner'

const EXPRESS_STEPS = ['security', 'database', 'deployment', 'email', 'summary']
const ADVANCED_STEPS = ['security', 'database', 'email', 'deployment', 'branding', 'summary']

export default function SetupWizard({ onDone }) {
  const [mode, setMode] = useState('express') // 'express' | 'advanced'
  const [step, setStep] = useState(0)
  const [summary, setSummary] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [expressDeploy, setExpressDeploy] = useState({ mode: 'local', domain: '' })

  const currentSteps = mode === 'express' ? EXPRESS_STEPS : ADVANCED_STEPS

  useEffect(() => {
    api.get('/wizard/state')
      .then(r => {
        if (r.data?.mode && (r.data.mode === 'express' || r.data.mode === 'advanced')) {
          setMode(r.data.mode)
        }
      })
      .catch(() => {})
  }, [])

  const switchMode = async (newMode) => {
    if (newMode === mode) return
    setMode(newMode)
    setStep(0)
    setError('')
    try {
      await api.post('/wizard/mode', { mode: newMode })
    } catch (_) {}
  }

  const next = () => setStep(s => Math.min(s + 1, currentSteps.length - 1))
  const back = () => setStep(s => Math.max(s - 1, 0))

  const skip = async (name) => {
    setBusy(true); setError('')
    try {
      await api.post('/wizard/skip', { step: name })
      next()
    } catch (e) {
      setError(e.response?.data?.detail || tx("Failed to skip"))
    } finally {
      setBusy(false)
    }
  }

  const finish = async () => {
    setBusy(true); setError('')
    try {
      const r = await api.post('/wizard/complete')
      setSummary(r.data)
      setStep(currentSteps.length - 1)
    } catch (e) {
      setError(e.response?.data?.detail || tx("Failed to finish"))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {/* Top-level Express vs Advanced Setup Mode Selector */}
        <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-4 mb-4 shadow-xl">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-shield-500/20 border border-shield-500/30 flex items-center justify-center text-shield-400 shrink-0">
                <Shield size={18} />
              </div>
              <div>
                <h1 className="text-white text-sm font-semibold">{tx("System Setup Wizard")}</h1>
                <p className="text-slate-400 text-xs">
                  {mode === 'express'
                    ? tx("Express Mode: zero-touch defaults tailored for home users.")
                    : tx("Advanced Mode: granular control for administrators.")}
                </p>
              </div>
            </div>

            <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 self-start sm:self-auto">
              <button
                type="button"
                onClick={() => switchMode('express')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  mode === 'express'
                    ? 'bg-shield-600 text-white shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Zap size={13} />
                <span>{tx("Express Setup")}</span>
              </button>
              <button
                type="button"
                onClick={() => switchMode('advanced')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  mode === 'advanced'
                    ? 'bg-shield-600 text-white shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Sliders size={13} />
                <span>{tx("Advanced Setup")}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Progress indicator */}
        <div className="flex items-center justify-center gap-2 mb-6">
          {currentSteps.map((s, i) => (
            <div key={s} className="flex items-center">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium transition-colors
                ${i < step ? 'bg-shield-600 text-white' : i === step ? 'bg-shield-500 text-white' : 'bg-slate-800 text-slate-500'}`}>
                {i < step ? <CheckCircle2 size={16} /> : i + 1}
              </div>
              {i < currentSteps.length - 1 && (
                <div className={`w-8 h-0.5 ${i < step ? 'bg-shield-600' : 'bg-slate-800'}`} />
              )}
            </div>
          ))}
        </div>

        {/* Active Step Container */}
        <div className="bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl">
          {error && (
            <div className="mb-4 px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs">
              {error}
            </div>
          )}

          {mode === 'express' ? (
            <>
              {step === 0 && (
                <SecurityStep
                  onNext={next}
                  onSkip={() => skip('security')}
                  busy={busy}
                  setError={setError}
                />
              )}
              {step === 1 && (
                <ExpressDatabaseStep
                  onNext={next}
                  onSkip={() => skip('database')}
                  onBack={back}
                  busy={busy}
                  setError={setError}
                />
              )}
              {step === 2 && (
                <ExpressDeploymentStep
                  onNext={next}
                  onSkip={() => skip('deployment')}
                  onBack={back}
                  busy={busy}
                  setError={setError}
                  deployment={expressDeploy}
                  setDeployment={setExpressDeploy}
                />
              )}
              {step === 3 && (
                <ExpressEmailStep
                  onNext={finish}
                  onSkip={async () => { await skip('email'); finish() }}
                  onBack={back}
                  busy={busy}
                  setError={setError}
                />
              )}
              {step === 4 && <SummaryStep summary={summary} onDone={onDone} />}
            </>
          ) : (
            <>
              {step === 0 && (
                <SecurityStep
                  onNext={next}
                  onSkip={() => skip('security')}
                  busy={busy}
                  setError={setError}
                />
              )}
              {step === 1 && (
                <DatabaseStep
                  onNext={next}
                  onSkip={() => skip('database')}
                  onBack={back}
                  busy={busy}
                  setError={setError}
                />
              )}
              {step === 2 && (
                <EmailStep
                  onNext={next}
                  onSkip={() => skip('email')}
                  onBack={back}
                  busy={busy}
                  setError={setError}
                />
              )}
              {step === 3 && (
                <DeploymentStep
                  onNext={next}
                  onSkip={() => skip('deployment')}
                  onBack={back}
                  busy={busy}
                  setError={setError}
                />
              )}
              {step === 4 && (
                <BrandingStep
                  onNext={finish}
                  onSkip={async () => { await skip('branding'); finish() }}
                  onBack={back}
                  busy={busy}
                  setError={setError}
                />
              )}
              {step === 5 && <SummaryStep summary={summary} onDone={onDone} />}
            </>
          )}
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

function Buttons({ onBack, onSkip, onNext, nextLabel, busy }) {
  const lbl = nextLabel || tx("Continue")
  return (
    <div className="flex items-center justify-between mt-6">
      <div>
        {onBack && <button type="button" onClick={onBack} className="flex items-center gap-1 text-slate-400 hover:text-slate-200 text-sm px-2 py-1.5"><ChevronLeft size={15} />{" "}{tx("Back")}</button>}
      </div>
      <div className="flex items-center gap-2">
        {onSkip && <button type="button" onClick={onSkip} disabled={busy} className="flex items-center gap-1 text-slate-400 hover:text-slate-200 text-sm px-3 py-1.5"><SkipForward size={14} />{" "}{tx("Skip")}</button>}
        <button type="button" onClick={onNext} disabled={busy} className="flex items-center gap-1 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-sm rounded-lg px-4 py-2">
          {busy ? tx("Saving…") : lbl} <ChevronRight size={15} />
        </button>
      </div>
    </div>
  )
}

// ── Step 0: Security & Master Encryption Key ─────────────────────────────────
function SecurityStep({ onNext, onSkip, onBack, busy, setError }) {
  const [keyData, setKeyData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [revealed, setRevealed] = useState(false)
  const [copied, setCopied] = useState(false)
  const [showChaos, setShowChaos] = useState(false)

  const loadKey = async () => {
    try {
      const res = await api.get('/wizard/master-key')
      setKeyData(res.data)
    } catch (e) {
      setError(e.response?.data?.detail || tx("Failed to load master encryption key"))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadKey()
  }, [])

  const copyKey = async () => {
    if (!keyData?.key) return
    try {
      await navigator.clipboard.writeText(keyData.key)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch {
      /* clipboard fallback */
    }
  }

  const keyLen = keyData?.key?.length || keyData?.status?.active_key_length || 0
  const fileExists = keyData?.status?.file_exists ?? false
  const isSecurePerms = keyData?.status?.permissions_secure ?? true
  const filePath = keyData?.status?.file_path || 'secret.key'

  return (
    <div>
      <StepHeader
        icon={Key}
        title={tx("Master Encryption Key & System Security")}
        subtitle={tx("All personal family details stored by OpenOptOut are encrypted using this master key.")}
      />

      <div className="space-y-4">
        {/* Info Box */}
        <div className="px-3.5 py-3 rounded-xl border border-slate-700 bg-slate-800/40 text-xs text-slate-300 flex items-start gap-2.5">
          <Shield size={16} className="text-shield-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-medium text-slate-200">
              {tx("Automatic Cryptographic Protection")}
            </p>
            <p className="text-slate-400 leading-relaxed">
              {tx("OpenOptOut generated this high-entropy encryption key at first install and saved it with strict file permissions (0600) on your server. It secures family records, identity tokens, and broker credentials.")}
            </p>
          </div>
        </div>

        {/* Masked Key Display Box */}
        <div className="p-4 rounded-xl border border-slate-700/80 bg-slate-950/70 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Key size={13} className="text-shield-400" />
              {tx("Active Master Encryption Key")}
            </span>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setRevealed(r => !r)}
                className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border border-slate-700 bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
                title={revealed ? tx("Hide key") : tx("Reveal key")}
              >
                {revealed ? <EyeOff size={13} /> : <Eye size={13} />}
                <span>{revealed ? tx("Hide") : tx("Reveal")}</span>
              </button>
              <button
                type="button"
                onClick={copyKey}
                disabled={!keyData?.key}
                className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-md bg-shield-600 hover:bg-shield-500 text-white font-medium transition-colors disabled:opacity-50"
                title={tx("Copy key to clipboard")}
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
                <span>{copied ? tx("Copied!") : tx("Copy Key")}</span>
              </button>
            </div>
          </div>

          <div className="p-3 bg-slate-900 border border-slate-800 rounded-lg">
            {loading ? (
              <span className="text-slate-500 text-xs">{tx("Loading master key…")}</span>
            ) : revealed ? (
              <code className="text-xs text-emerald-400 font-mono break-all select-all block leading-relaxed">
                {keyData?.key || tx("Key loaded in memory")}
              </code>
            ) : (
              <div className="text-xs text-slate-400 font-mono tracking-widest break-all select-none">
                {'•'.repeat(Math.min(keyLen || 128, 64))}
              </div>
            )}
          </div>

          {/* Key status badges */}
          <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border font-mono ${
              fileExists && isSecurePerms
                ? 'bg-emerald-950/40 text-emerald-300 border-emerald-800/60'
                : 'bg-amber-950/40 text-amber-300 border-amber-800/60'
            }`}>
              <Check size={11} />
              <span>{filePath} ({fileExists && isSecurePerms ? '0600 secure' : fileExists ? 'check permissions' : 'saved'})</span>
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border bg-slate-800/60 text-slate-300 border-slate-700 font-mono">
              <span>{keyLen} {tx("chars entropy")}</span>
            </span>
          </div>

          <p className="text-slate-400 text-xs">
            {tx("Tip: Copy and back up this master key to your password manager (e.g. 1Password, Bitwarden, Apple Keychain). You will need it if you ever migrate or restore from backup.")}
          </p>
        </div>

        {/* Collapsible Interactive Chaos / Entropy Generator */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 overflow-hidden">
          <button
            type="button"
            onClick={() => setShowChaos(c => !c)}
            className="w-full p-3.5 flex items-center justify-between text-start text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800/40 transition-colors"
          >
            <span className="flex items-center gap-2">
              <Sparkles size={14} className="text-amber-400" />
              <span>{tx("Interactive Entropy Generator (Optional Chaos & Randomness)")}</span>
            </span>
            <span className="text-slate-500 text-xs">
              {showChaos ? tx("Hide") : tx("Expand")}
            </span>
          </button>
          {showChaos && (
            <div className="p-4 border-t border-slate-800 bg-slate-950/40">
              <p className="text-slate-400 text-xs mb-3">
                {tx("Mix custom entropy from mouse physics, keyboard timings, and image chunk shuffling. Any new key saved here will automatically update secret.key.")}
              </p>
              <SecretKeyGeneratorPanel
                status={keyData?.status || {}}
                onStatusChange={() => loadKey()}
                compact={true}
              />
            </div>
          )}
        </div>
      </div>

      <Buttons onBack={onBack} onSkip={onSkip} onNext={onNext} nextLabel={tx("Continue")} busy={busy} />
    </div>
  )
}

// ── Express Step 1: Database ──────────────────────────────────────────────────
function ExpressDatabaseStep({ onNext, onBack, onSkip, busy, setError }) {
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true); setError('')
    try {
      await api.post('/wizard/database', { kind: 'sqlite' })
      onNext()
    } catch (e) {
      setError(e.response?.data?.detail || tx("Failed to save database settings"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <StepHeader
        icon={Database}
        title={tx("Database & Local Storage")}
        subtitle={tx("OpenOptOut stores family records in a high-speed encrypted local SQLite database.")}
      />
      <div className="space-y-3">
        <div className="p-4 rounded-xl border border-shield-600/80 bg-shield-900/20 space-y-2">
          <div className="flex items-center gap-2 text-white font-medium text-sm">
            <CheckCircle2 size={16} className="text-shield-400" />
            <span>{tx("SQLite Local Database (Pre-configured & Ready)")}</span>
          </div>
          <p className="text-slate-300 text-xs leading-relaxed">
            {tx("Zero configuration required. All family opt-out logs, broker manifests, and identity vault entries are encrypted locally on this server's filesystem.")}
          </p>
          <div className="pt-1 flex items-center gap-2 text-xs text-slate-400">
            <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">sqlite3</span>
            <span>{tx("Zero network latency · Automatic file backups supported")}</span>
          </div>
        </div>
      </div>
      <Buttons onBack={onBack} onSkip={onSkip} onNext={save} nextLabel={tx("Continue")} busy={saving || busy} />
    </div>
  )
}

// ── Express Step 2: Deployment ────────────────────────────────────────────────
function ExpressDeploymentStep({ onNext, onBack, onSkip, busy, setError, deployment, setDeployment }) {
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true); setError('')
    try {
      const isLocal = deployment.mode === 'local'
      const body = isLocal
        ? { reverse_proxy: 'none', domain: '', rate_limit: true, hsts: false }
        : {
            reverse_proxy: 'managed',
            front_door: 'caddy',
            certificate: 'letsencrypt',
            domain: (deployment.domain || '').trim(),
            rate_limit: true,
            cloudflare_proxy: false,
            client_mtls: false,
            hsts: true,
          }
      await api.post('/wizard/deployment', body)
      onNext()
    } catch (e) {
      setError(e.response?.data?.detail || tx("Failed to save deployment settings"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <StepHeader
        icon={Globe}
        title={tx("Access & Network Connection")}
        subtitle={tx("Choose how you and your family will access the OpenOptOut interface.")}
      />

      <div className="space-y-3">
        {/* Local only */}
        <label className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-colors ${
          deployment.mode === 'local' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
        }`}>
          <input
            type="radio"
            name="express_deploy"
            checked={deployment.mode === 'local'}
            onChange={() => setDeployment({ ...deployment, mode: 'local' })}
            className="mt-1 accent-shield-500"
          />
          <div className="space-y-1">
            <div className="text-slate-200 text-sm font-medium flex items-center gap-1.5">
              <Home size={15} className="text-shield-400" />
              <span>{tx("Local Network Access (Recommended for Home Users)")}</span>
            </div>
            <p className="text-slate-400 text-xs leading-relaxed">
              {tx("Access OpenOptOut via your local home network (e.g. http://localhost:8000 or http://192.168.1.x:8000). Completely private and not accessible from the public internet.")}
            </p>
          </div>
        </label>

        {/* Domain with Caddy HTTPS */}
        <label className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-colors ${
          deployment.mode === 'domain' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
        }`}>
          <input
            type="radio"
            name="express_deploy"
            checked={deployment.mode === 'domain'}
            onChange={() => setDeployment({ ...deployment, mode: 'domain' })}
            className="mt-1 accent-shield-500"
          />
          <div className="flex-1 space-y-1">
            <div className="text-slate-200 text-sm font-medium flex items-center gap-1.5">
              <Globe size={15} className="text-shield-400" />
              <span>{tx("Custom Domain with Automatic HTTPS")}</span>
            </div>
            <p className="text-slate-400 text-xs leading-relaxed">
              {tx("Securely publish OpenOptOut on your own domain. Caddy automatically provisions free Let's Encrypt TLS certificates and blocks malicious traffic.")}
            </p>
            {deployment.mode === 'domain' && (
              <div className="pt-2">
                <input
                  className={inp}
                  placeholder={tx("e.g. privacy.myfamily.org")}
                  value={deployment.domain}
                  onChange={e => setDeployment({ ...deployment, domain: e.target.value })}
                  autoFocus
                />
              </div>
            )}
          </div>
        </label>
      </div>

      <Buttons onBack={onBack} onSkip={onSkip} onNext={save} nextLabel={tx("Continue")} busy={saving || busy} />
    </div>
  )
}

// ── Express Step 3: Email ─────────────────────────────────────────────────────
function ExpressEmailStep({ onNext, onBack, onSkip, busy, setError }) {
  const [saving, setSaving] = useState(false)
  const [option, setOption] = useState('later') // 'later' | 'connect'
  const [provider, setProvider] = useState('')

  const save = async () => {
    setSaving(true); setError('')
    try {
      if (option === 'later' || !provider) {
        await api.post('/wizard/skip', { step: 'email' })
      } else {
        await api.post('/wizard/email', { mode: 'per_user', provider, separate_admin_smtp: false })
      }
      onNext()
    } catch (e) {
      setError(e.response?.data?.detail || tx("Failed to save email settings"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <StepHeader
        icon={Mail}
        title={tx("System Email (Optional)")}
        subtitle={tx("Used for password recovery and administrator alerts. Opt-outs are always sent from each family member's own connected inbox.")}
      />

      <div className="space-y-3">
        <label className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-colors ${
          option === 'later' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
        }`}>
          <input
            type="radio"
            name="express_email"
            checked={option === 'later'}
            onChange={() => setOption('later')}
            className="mt-1 accent-shield-500"
          />
          <div className="space-y-1">
            <div className="text-slate-200 text-sm font-medium">
              {tx("Configure Later in Settings (Fastest)")}
            </div>
            <p className="text-slate-400 text-xs leading-relaxed">
              {tx("Skip for now and launch the dashboard immediately. You or your family can link email accounts anytime in the Settings page.")}
            </p>
          </div>
        </label>

        <label className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-colors ${
          option === 'connect' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
        }`}>
          <input
            type="radio"
            name="express_email"
            checked={option === 'connect'}
            onChange={() => setOption('connect')}
            className="mt-1 accent-shield-500"
          />
          <div className="flex-1 space-y-2">
            <div className="text-slate-200 text-sm font-medium">
              {tx("Connect an Email Provider Now")}
            </div>
            <p className="text-slate-400 text-xs">
              {tx("Link Gmail, Outlook, Yahoo, or your personal mail server for instant system alerts.")}
            </p>
            {option === 'connect' && (
              <div className="pt-1">
                <select className={inp} value={provider} onChange={e => setProvider(e.target.value)}>
                  <option value="">{tx("Choose a provider…")}</option>
                  <option value="gmail">{tx("Gmail / Google Workspace (sign in with Google)")}</option>
                  <option value="outlook">{tx("Outlook / Microsoft 365 (sign in with Microsoft)")}</option>
                  <option value="yahoo">{tx("Yahoo Mail (sign in with Yahoo)")}</option>
                  <option value="smtp">{tx("Other mail server (SMTP / IMAP)")}</option>
                </select>
                {provider && provider !== 'smtp' && (
                  <div className="mt-2">
                    <ConnectOAuth provider={provider} setError={setError} />
                  </div>
                )}
              </div>
            )}
          </div>
        </label>
      </div>

      <Buttons onBack={onBack} onSkip={onSkip} onNext={save} nextLabel={tx("Complete Setup")} busy={saving || busy} />
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
    } catch (e) { setError(e.response?.data?.detail || tx("Failed to save database settings")) }
    finally { setSaving(false) }
  }

  return (
    <div>
      <StepHeader icon={Database} title={tx("Database")} subtitle={tx("Where OpenOptOut stores its data.")} />
      <div className="space-y-3">
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${kind === 'sqlite' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <input type="radio" checked={kind === 'sqlite'} onChange={() => setKind('sqlite')} className="mt-1 accent-shield-500" />
          <div>
            <div className="text-slate-200 text-sm font-medium">{tx("SQLite (this machine)")}</div>
            <div className="text-slate-400 text-xs">{tx("Simplest. Stored in a local file on this server. Good for small/single-machine deployments.")}</div>
          </div>
        </label>
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${kind === 'postgres' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <input type="radio" checked={kind === 'postgres'} onChange={() => setKind('postgres')} className="mt-1 accent-shield-500" />
          <div className="flex-1">
            <div className="text-slate-200 text-sm font-medium flex items-center gap-1"><Server size={13} />{" "}{tx("PostgreSQL (dedicated / remote server)")}</div>
            <div className="text-slate-400 text-xs">{tx("For larger deployments. Point at your own Postgres server — it does not have to be on this machine.")}</div>
          </div>
        </label>
        {kind === 'postgres' && (
          <div className="grid grid-cols-2 gap-2 ps-2 pt-1">
            <input className={inp} placeholder={tx("Host (e.g. db.internal)")} value={pg.host} onChange={e => setPg({ ...pg, host: e.target.value })} />
            <input className={inp} placeholder={tx("Port")} value={pg.port} onChange={e => setPg({ ...pg, port: +e.target.value || 5432 })} />
            <input className={inp} placeholder={tx("Database name")} value={pg.database} onChange={e => setPg({ ...pg, database: e.target.value })} />
            <input className={inp} placeholder={tx("Username")} value={pg.username} onChange={e => setPg({ ...pg, username: e.target.value })} />
            <input className={inp} type="password" placeholder={tx("Password")} value={pg.password} onChange={e => setPg({ ...pg, password: e.target.value })} />
            <select className={inp} value={pg.sslmode} onChange={e => setPg({ ...pg, sslmode: e.target.value })}>
              <option value="prefer">{tx("SSL: prefer")}</option>
              <option value="require">{tx("SSL: require")}</option>
              <option value="disable">{tx("SSL: disable")}</option>
            </select>
            <p className="col-span-2 text-amber-400/80 text-xs flex items-center gap-1"><AlertTriangle size={11} />{" "}{tx("Changing the database takes effect after a restart.")}</p>
          </div>
        )}
      </div>
      <Buttons onSkip={onSkip} onNext={save} busy={saving || busy} />
    </div>
  )
}

// ── Step 2: Email ─────────────────────────────────────────────────────────────
function EmailStep({ onNext, onSkip, onBack, busy, setError }) {
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
      setUploadMsg(tx("Installed \"{plugin_id}\" into plugins/{destination} and selected it.", { plugin_id: r.data.plugin_id, destination: r.data.destination }))
    } catch (err) {
      setError(err.response?.data?.detail || tx("Upload failed (the inspector may have rejected it)."))
    } finally { setUploading(false); e.target.value = '' }
  }

  const save = async () => {
    setSaving(true); setError('')
    try {
      // Proton (via Bridge) is the generic-SMTP transport pointed at the local
      // Bridge endpoint — save it as 'smtp' with the Bridge fields.
      const effectiveProvider = provider === 'proton' ? 'smtp' : provider
      const body = { mode: 'per_user', provider: effectiveProvider, separate_admin_smtp: advanced }
      if (effectiveProvider === 'smtp') Object.assign(body, smtp)
      await api.post('/wizard/email', body)
      onNext()
    } catch (e) { setError(e.response?.data?.detail || tx("Failed to save email settings")) }
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
      <StepHeader icon={Mail} title={tx("Email")} subtitle={tx("The system inbox sends sign-in links, status updates and admin alerts. It never sends opt-outs.")} />

      <div className="mb-4 px-3 py-2.5 rounded-lg border border-slate-700 bg-slate-800/40 flex items-start gap-2">
        <Shield size={14} className="text-shield-400 shrink-0 mt-0.5" />
        <p className="text-slate-300 text-xs">{tx("Opt-outs are sent from each family's own inbox, which they connect after signing in. Some brokers allow only one opt-out per email address, so using one shared address for everyone doesn't work. If you set up Gmail, Outlook or Yahoo sign-in here, families can connect those inboxes with one click.")}</p>
      </div>

      {/* Transport */}
      <p className="text-slate-300 text-sm font-medium mb-2">{tx("Email service")}</p>
      <div className="px-3 py-2 rounded-lg border border-slate-700 bg-slate-800/40 mb-2">
        <p className="text-slate-400 text-xs flex items-start gap-1.5"><Shield size={12} className="text-shield-400 shrink-0 mt-0.5" /> <span>{txr("<0>Use \"sign in with Google / Microsoft / Yahoo\" when you can.</0> It's safer than storing a password and keeps working when providers change their rules. Use a mail server with an app password only if your service doesn't offer sign-in.", [<strong className="text-slate-300" />])}</span></p>
      </div>
      <select className={inp} value={provider} onChange={e => {
        if (e.target.value === 'proton') { chooseProton() } else { setProvider(e.target.value) }
      }}>
        <option value="">{tx("Choose a provider…")}</option>
        <option value="gmail">{tx("Gmail / Google Workspace (sign in with Google)")}</option>
        <option value="outlook">{tx("Outlook / Microsoft 365 (sign in with Microsoft)")}</option>
        <option value="yahoo">{tx("Yahoo Mail (sign in with Yahoo)")}</option>
        <option value="smtp">{tx("Other mail server (SMTP / IMAP)")}</option>
        <option value="proton">{tx("Proton Mail (via Proton Bridge)")}</option>
        {uploaded.map(u => (
          <option key={u.plugin_id} value={u.plugin_id}>{u.name}{" "}{tx("(uploaded)")}</option>
        ))}
      </select>

      {/* Bring your own provider */}
      <div className="mt-2 px-3 py-2.5 rounded-lg border border-slate-700 bg-slate-800/40">
        <p className="text-slate-300 text-xs font-medium mb-1">{tx("Use a different email service?")}</p>
        <p className="text-slate-400 text-xs mb-2">
          {tx("Upload an email-provider plugin (e.g. Proton, Apple, or any custom service). It's inspected for hidden recipients before it's trusted, then installed and selectable here.")}
        </p>
        <label className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-800 cursor-pointer">
          {uploading ? tx("Uploading…") : tx("Add an email service plugin (.zip)")}
          <input type="file" accept=".zip" className="hidden" onChange={uploadProvider} disabled={uploading} />
        </label>
        {uploadMsg && <p className="text-emerald-300/90 text-xs mt-1.5">{uploadMsg}</p>}
      </div>
      {provider && provider !== 'smtp' && provider !== 'proton' && (
        <ConnectOAuth provider={provider} setError={setError} />
      )}
      {provider === 'proton' && (
        <div className="mt-2 px-3 py-2.5 rounded-lg border border-amber-700/70 bg-amber-950/25">
          <p className="text-amber-200 text-xs font-medium mb-1">{tx("Proton requires Proton Bridge (installed separately)")}</p>
          <p className="text-amber-300/90 text-xs">
            {txr("Proton Mail has no standard API. You must install and run <0>Proton Bridge</0> on this server (or a reachable host) and log into it with your Proton account — the wizard can't do this for you, since it's OS-level software with an interactive login. Once Bridge is running, it exposes a local SMTP/IMAP endpoint that OpenOptOut connects to. The fields below are pre-filled with Bridge's defaults — adjust if your Bridge uses different ports. <1>Proton Bridge docs →</1>", [<strong />, <a href="https://proton.me/mail/bridge" target="_blank" rel="noopener noreferrer" className="underline" />])}
          </p>
          <p className="text-amber-300/70 text-xs mt-1">
            {txr("Note: if OpenOptOut runs in Docker, <0>127.0.0.1</0> refers to the container — you may need to point at the host (e.g. <1>host.docker.internal</1>) and allow Bridge to accept it.", [<code />, <code />])}
          </p>
        </div>
      )}
      {(provider === 'smtp' || provider === 'proton') && (
        <div className="grid grid-cols-2 gap-2 mt-2">
          <input className={inp} placeholder={tx("SMTP host")} value={smtp.smtp_host} onChange={e => setSmtp({ ...smtp, smtp_host: e.target.value })} />
          <input className={inp} placeholder={tx("SMTP port")} value={smtp.smtp_port} onChange={e => setSmtp({ ...smtp, smtp_port: +e.target.value || 587 })} />
          <input className={inp} placeholder={tx("IMAP host (to read confirmations)")} value={smtp.imap_host} onChange={e => setSmtp({ ...smtp, imap_host: e.target.value })} />
          <input className={inp} placeholder={tx("IMAP port")} value={smtp.imap_port} onChange={e => setSmtp({ ...smtp, imap_port: +e.target.value || 993 })} />
          <input className={inp} placeholder={tx("Username")} value={smtp.username} onChange={e => setSmtp({ ...smtp, username: e.target.value })} />
          <input className={inp} type="password" placeholder={provider === 'proton' ? tx("Bridge password") : tx("Password / app-password")} value={smtp.password} onChange={e => setSmtp({ ...smtp, password: e.target.value })} />
          <input className={inp} placeholder={tx("From address")} value={smtp.from_address} onChange={e => setSmtp({ ...smtp, from_address: e.target.value })} />
          <select className={inp} value={smtp.tls} onChange={e => setSmtp({ ...smtp, tls: e.target.value })}>
            <option value="starttls">{tx("STARTTLS")}</option>
            <option value="ssl">{tx("SSL")}</option>
            <option value="none">{tx("No TLS")}</option>
          </select>
        </div>
      )}

      {/* Advanced */}
      <label className="flex items-center gap-2 mt-4 text-xs text-slate-400 cursor-pointer">
        <input type="checkbox" checked={advanced} onChange={e => setAdvanced(e.target.checked)} className="accent-shield-500" />
        {tx("Advanced: use a separate account for the tool's own admin/notification email")}
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
      setError(e.response?.data?.detail || tx("Could not start the connect flow"))
    } finally { setBusy(false) }
  }

  if (status && status !== 'connecting') {
    return (
      <div className="mt-2 px-3 py-2 rounded-lg border border-emerald-800/60 bg-emerald-950/20 text-emerald-200 text-xs flex items-center gap-2">
        <CheckCircle2 size={13} />{" "}{tx("Account connected")}{status.expired ? tx("(token will refresh on use)") : ''}.
      </div>
    )
  }

  return (
    <div className="mt-2 px-3 py-3 rounded-lg border border-slate-700 bg-slate-800/40">
      <p className="text-slate-300 text-xs font-medium mb-1">{tx("Set up sign-in for this service")}</p>
      <p className="text-slate-400 text-xs mb-2">
        {tx("Register your OAuth app's credentials, then grant access. The client secret is stored encrypted on this server and never shared with plugins. You create these in the provider's developer console (")}{provider === 'gmail' ? tx("Google Cloud") : provider === 'outlook' ? tx("Azure") : tx("the provider console")}).
      </p>
      <div className="mb-2 px-2.5 py-2 rounded-lg border border-amber-800/50 bg-amber-950/20">
        <p className="text-amber-200/90 text-xs font-medium mb-1">{tx("Before connecting: register this redirect URI")}</p>
        <p className="text-slate-400 text-xs mb-1.5">
          {tx("In that developer console, find \"Authorized redirect URIs\" (Google) or \"Redirect URIs\" (Azure) on this OAuth client and add this exact value — it won't work otherwise, and you'll see an error like \"doesn't comply with OAuth 2.0 policy\" or \"redirect_uri_mismatch\":")}
        </p>
        <div className="flex items-center gap-1.5">
          <code className="flex-1 text-[11px] text-slate-200 bg-slate-900/70 rounded-sm px-2 py-1 break-all">{defaultRedirect}</code>
          <button type="button" onClick={() => {
              navigator.clipboard?.writeText(defaultRedirect); setCopied(true); setTimeout(() => setCopied(false), 1500)
            }}
            className="shrink-0 p-1.5 rounded-sm text-slate-400 hover:text-slate-200 hover:bg-slate-700/60"
            title={tx("Copy redirect URI")}>
            {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
          </button>
        </div>
        <p className="text-slate-500 text-[11px] mt-1.5">
          {tx("This is computed from the address you're using to reach OpenOptOut right now — if you later move to a different domain or turn on HTTPS, add that URI here too and register it the same way; each address needs its own entry.")}
        </p>
      </div>
      <div className="space-y-2">
        <input className={inp} placeholder={tx("Client ID")} value={client.client_id} onChange={e => setClient({ ...client, client_id: e.target.value })} />
        <input className={inp} type="password" placeholder={tx("Client secret")} value={client.client_secret} onChange={e => setClient({ ...client, client_secret: e.target.value })} />
        <input className={inp} placeholder={tx("Redirect URI (default: {defaultRedirect})", { defaultRedirect })} value={client.redirect_uri} onChange={e => setClient({ ...client, redirect_uri: e.target.value })} />
      </div>
      <button onClick={connect} disabled={busy || !client.client_id || !client.client_secret}
        className="mt-2 px-3 py-1.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-xs rounded-lg">
        {status === 'connecting' ? tx("Waiting for consent…") : busy ? tx("Starting…") : tx("Connect account")}
      </button>
      {status === 'connecting' && (
        <p className="text-slate-400 text-xs mt-1.5">{tx("A consent window opened — approve access there, then this will update automatically.")}</p>
      )}
    </div>
  )
}

// ── Step 3: Deployment / reverse proxy ─────────────────────────────────────────
// Smaller radio choice used for the follow-up questions under "set up HTTPS for me".
function SubChoice({ name, value, current, onChange, title, children, warn }) {
  const on = current === value
  return (
    <label className={`flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer ${on ? (warn ? 'border-amber-600 bg-amber-950/20' : 'border-shield-600 bg-shield-900/20') : 'border-slate-700'}`}>
      <input type="radio" name={name} value={value} checked={on} onChange={() => onChange(value)} className="mt-1 accent-shield-500" />
      <div>
        <div className="text-slate-200 text-sm font-medium">{title}</div>
        <div className="text-slate-400 text-xs">{children}</div>
      </div>
    </label>
  )
}

function DeploymentStep({ onNext, onSkip, onBack, busy, setError }) {
  const [mode, setMode] = useState('managed')
  const [domain, setDomain] = useState('')
  const [frontDoor, setFrontDoor] = useState('caddy')
  const [certificate, setCertificate] = useState('letsencrypt')
  const [rateLimit, setRateLimit] = useState(true)
  const [cloudflareProxy, setCloudflareProxy] = useState(false)
  const [clientMtls, setClientMtls] = useState(false)
  const [hsts, setHsts] = useState(true)
  const [saving, setSaving] = useState(false)

  const sslInstalled = (mode === 'managed' && (frontDoor === 'cloudflare-tunnel' || certificate !== 'none')) || mode === 'native' || mode === 'external'

  const save = async () => {
    setSaving(true); setError('')
    try {
      const body = {
        reverse_proxy: mode,
        domain: (mode === 'managed' || mode === 'native') ? domain : '',
        hsts: sslInstalled ? hsts : false,
      }
      if (mode === 'managed') {
        body.front_door = frontDoor
        if (frontDoor !== 'cloudflare-tunnel') {
          body.certificate = certificate
          body.rate_limit = rateLimit
          body.cloudflare_proxy = certificate === 'cloudflare-dns' && cloudflareProxy
          body.client_mtls = certificate !== 'none' && clientMtls
        }
      }
      await api.post('/wizard/deployment', body)
      onNext()
    } catch (e) { setError(e.response?.data?.detail || tx("Failed to save deployment settings")) }
    finally { setSaving(false) }
  }

  return (
    <div>
      <StepHeader icon={Globe} title={tx("How is HTTPS handled here?")} subtitle={tx("Decides whether OpenOptOut should manage HTTPS itself, or stay out of the way of something that already does.")} />
      <div className="space-y-3">
        <div className={`p-3 rounded-lg border ${mode === 'managed' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <label className="flex items-start gap-3 cursor-pointer">
            <input type="radio" checked={mode === 'managed'} onChange={() => setMode('managed')} className="mt-1 accent-shield-500" />
            <div className="flex-1">
              <div className="text-slate-200 text-sm font-medium flex items-center gap-1"><Home size={13} />{" "}{tx("Running via Docker — set up HTTPS for me")}</div>
              <div className="text-slate-400 text-xs">{tx("Docker (bare metal or a VM — it doesn't matter which), nothing else already on ports 80 or 443. OpenOptOut runs its own front door and keeps the certificate renewed.")}</div>
            </div>
          </label>
          {/* Follow-up questions sit OUTSIDE the label above: nested labels are invalid HTML and make screen readers announce this whole panel as one option. */}
          {mode === 'managed' && (
            <div className="mt-3 space-y-3 sm:ps-7">
              <input className={inp} placeholder={tx("Domain, if you know it yet (e.g. privacy.yourlibrary.org) — optional")}
                aria-label={tx("Domain (optional)")} value={domain} onChange={e => setDomain(e.target.value)} />
              <fieldset className="space-y-2">
                <legend className="text-slate-300 text-xs font-medium mb-1.5">{tx("How should people reach it?")}</legend>
                <SubChoice name="front_door" value="caddy" current={frontDoor} onChange={setFrontDoor} title={tx("Caddy (recommended)")}>
                  {tx("Simplest choice if you have no preference.")}
                </SubChoice>
                <SubChoice name="front_door" value="traefik" current={frontDoor} onChange={setFrontDoor} title={"Traefik"}>
                  {tx("Same protection, for teams that already use Traefik.")}
                </SubChoice>
                <SubChoice name="front_door" value="cloudflare-tunnel" current={frontDoor} onChange={setFrontDoor} title={tx("Cloudflare Tunnel")} warn>
                  {tx("No open ports or router setup at all. Cloudflare can see all traffic — see the warning below.")}
                </SubChoice>
              </fieldset>
              {frontDoor === 'cloudflare-tunnel' ? (
                <div role="alert" className="px-3 py-2 rounded-lg border border-amber-700 bg-amber-950/30 text-amber-200 text-xs flex items-start gap-2">
                  <AlertTriangle size={13} className="shrink-0 mt-0.5" aria-hidden="true" />
                  <span>
                    {txr("<0>Cloudflare decrypts all traffic to this site.</0> Its servers can see everything people send and receive here: names, home addresses, phone numbers, emails, and sign-in tokens. For no open ports without that, pick Caddy or Traefik with <1>Let's Encrypt via Cloudflare DNS</1> instead.", [<strong />, <em />])}
                  </span>
                </div>
              ) : (<>
                <fieldset className="space-y-2">
                  <legend className="text-slate-300 text-xs font-medium mb-1.5">{tx("Where should the HTTPS certificate come from?")}</legend>
                  <SubChoice name="certificate" value="letsencrypt" current={certificate} onChange={setCertificate} title={tx("Let's Encrypt")}>
                    {tx("Free and automatic. Ports 80 and 443 must be reachable from the internet.")}
                  </SubChoice>
                  <SubChoice name="certificate" value="cloudflare-dns" current={certificate} onChange={setCertificate} title={tx("Let's Encrypt via Cloudflare DNS")}>
                    {tx("Free and automatic, with no open ports. Your domain's DNS must be on Cloudflare, which only sees a DNS record — never your traffic. Many home internet plans block ports or share one IP between homes; then this is often the only option that works.")}
                  </SubChoice>
                  <SubChoice name="certificate" value="none" current={certificate} onChange={setCertificate} title={tx("None for now")} warn>
                    {tx("Plain HTTP until you add a certificate later. Fine for testing; not for real people's data.")}
                  </SubChoice>
                  <details className="group" open={certificate === 'incommon'}>
                    <summary className="text-slate-400 text-xs cursor-pointer select-none py-1 hover:text-slate-200">{tx("Advanced")}</summary>
                    <div className="mt-2">
                      <SubChoice name="certificate" value="incommon" current={certificate} onChange={setCertificate}
                        title={<>{txr("InCommon (CERTInext) <0>Beta · untested</0>", [<span className="ms-1 inline-block whitespace-nowrap text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded-sm bg-amber-900/60 text-amber-200 align-middle" />])}</>}>
                        {tx("Mostly for universities and research institutions in InCommon, which get free certificates through CERTInext. Setup will ask for the ACME key ID, HMAC key and server address from your campus IT, and won't continue without them, so have them ready.")}
                      </SubChoice>
                    </div>
                  </details>
                </fieldset>
                <fieldset className="space-y-2">
                  <legend className="text-slate-300 text-xs font-medium mb-1.5">{tx("Protection against floods of traffic")}</legend>
                  <label className="flex items-start gap-2.5 p-2.5 rounded-lg border border-slate-700 cursor-pointer">
                    <input type="checkbox" checked={rateLimit} onChange={e => setRateLimit(e.target.checked)} className="mt-1 accent-shield-500" />
                    <div>
                      <div className="text-slate-200 text-sm font-medium">{tx("Limit how fast any one visitor can send requests (recommended)")}</div>
                      <div className="text-slate-400 text-xs">{tx("Normal use never notices. Floods and password-guessing get slowed down before they reach OpenOptOut.")}</div>
                    </div>
                  </label>
                  {certificate === 'cloudflare-dns' && (
                    <label className={`flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer ${cloudflareProxy ? 'border-amber-600 bg-amber-950/20' : 'border-slate-700'}`}>
                      <input type="checkbox" checked={cloudflareProxy} onChange={e => setCloudflareProxy(e.target.checked)} className="mt-1 accent-shield-500" />
                      <div>
                        <div className="text-slate-200 text-sm font-medium">{tx("Also put it behind Cloudflare's proxy (DDoS protection)")}</div>
                        <div className="text-slate-400 text-xs">{tx("For sites that are public and big enough to be a target. Cloudflare absorbs attacks and hides this server's address; the server then lets in only Cloudflare. Needs ports 80/443 open to the internet.")}</div>
                      </div>
                    </label>
                  )}
                  {certificate === 'cloudflare-dns' && cloudflareProxy && (
                    <div role="alert" className="px-3 py-2 rounded-lg border border-amber-700 bg-amber-950/30 text-amber-200 text-xs flex items-start gap-2">
                      <AlertTriangle size={13} className="shrink-0 mt-0.5" aria-hidden="true" />
                      <span>
                        {txr("<0>Cloudflare decrypts all traffic to this site.</0> Its servers can see everything people send and receive here: names, home addresses, phone numbers, emails, and sign-in tokens.", [<strong />])}
                      </span>
                    </div>
                  )}
                </fieldset>
                {certificate !== 'none' && (
                  <fieldset className="space-y-2">
                    <legend className="text-slate-300 text-xs font-medium mb-1.5">{tx("Client certificates (mTLS)")}</legend>
                    <label className="flex items-start gap-2.5 p-2.5 rounded-lg border border-slate-700 cursor-pointer">
                      <input type="checkbox" checked={clientMtls} onChange={e => setClientMtls(e.target.checked)} className="mt-1 accent-shield-500" />
                      <div>
                        <div className="text-slate-200 text-sm font-medium">{tx("Require a client certificate (mTLS)")}</div>
                        <div className="text-slate-400 text-xs">{tx("Only devices with an installed client certificate can reach OpenOptOut. The reverse proxy checks the certificate before any request reaches the app. Unauthenticated requests are dropped at the TLS handshake.")}</div>
                      </div>
                    </label>
                  </fieldset>
                )}
              </>)}
            </div>
          )}
        </div>
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${mode === 'native' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <input type="radio" checked={mode === 'native'} onChange={() => setMode('native')} className="mt-1 accent-shield-500" />
          <div className="flex-1">
            <div className="text-slate-200 text-sm font-medium flex items-center gap-1"><Server size={13} />{" "}{tx("Native install, no containers — set up HTTPS for me")}</div>
            <div className="text-slate-400 text-xs">{tx("OpenOptOut runs directly on this VM or bare-metal host (systemd on Linux, a Windows Service on Windows) — no Docker. HTTPS is handled the same way: certbot + nginx on Linux, or win-acme + IIS on Windows. See docs/admin/native-install.md.")}</div>
            {mode === 'native' && (
              <input className={`${inp} mt-2`} placeholder={tx("Domain, if you know it yet (e.g. privacy.yourlibrary.org) — optional")}
                value={domain} onChange={e => setDomain(e.target.value)} />
            )}
          </div>
        </label>
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${mode === 'external' ? 'border-shield-600 bg-shield-900/20' : 'border-slate-700'}`}>
          <input type="radio" checked={mode === 'external'} onChange={() => setMode('external')} className="mt-1 accent-shield-500" />
          <div className="flex-1">
            <div className="text-slate-200 text-sm font-medium flex items-center gap-1"><Server size={13} />{" "}{tx("Something else already terminates HTTPS")}</div>
            <div className="text-slate-400 text-xs">{tx("A load balancer, IIS, nginx, or another team's reverse proxy already handles TLS in front of OpenOptOut — whether OpenOptOut itself runs in Docker or natively. We won't suggest anything that would fight it for ports 80/443, or nag about plain HTTP once you're reaching it over https.")}</div>
          </div>
        </label>
        <label className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${mode === 'none' ? 'border-amber-700 bg-amber-950/10' : 'border-slate-700'}`}>
          <input type="radio" checked={mode === 'none'} onChange={() => setMode('none')} className="mt-1 accent-shield-500" />
          <div>
            <div className="text-slate-200 text-sm font-medium">{tx("Neither — decide later")}</div>
            <div className="text-slate-400 text-xs">{tx("Fine for local testing. You'll keep seeing a plain-HTTP warning until this is behind HTTPS one way or the other.")}</div>
          </div>
        </label>
        {sslInstalled && (
          <label className="flex items-start gap-2.5 p-3 rounded-lg border border-slate-700 bg-slate-800/30 cursor-pointer">
            <input type="checkbox" checked={hsts} onChange={e => setHsts(e.target.checked)} className="mt-1 accent-shield-500" />
            <div>
              <div className="text-slate-200 text-sm font-medium">{tx("Enable HSTS (HTTP Strict Transport Security)")}</div>
              <div className="text-slate-400 text-xs">{tx("Tells browsers to always connect to this site over HTTPS and refuse plain HTTP connections. Enable this when your SSL certificate is active or handled by an external service.")}</div>
            </div>
          </label>
        )}
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
          className="absolute start-2 top-1/2 -translate-y-1/2 w-5 h-5 rounded-sm border border-slate-600"
          style={{ background: swatchColor }} title={tx("Pick a color")} />
        <input className={`${inp} ps-9 font-mono`} placeholder={placeholder}
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
      setError(tx("Logo must be PNG, SVG, JPEG, or WebP")); return
    }
    setError(''); setUploading(true)
    const fd = new FormData(); fd.append('file', file)
    try {
      const r = await api.post('/branding/logo', fd)
      onUploaded(r.data.logo_url)
    } catch (e) {
      setError(e.response?.data?.detail || tx("Logo upload failed"))
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
          <img src={`${logoUrl}`} alt={tx("Logo")} className="h-12 object-contain" />
        ) : (
          <UploadCloud size={20} className={dragOver ? 'text-shield-400' : 'text-slate-500'} />
        )}
        <p className="text-slate-400 text-xs text-center">
          {uploading ? tx("Uploading…") : logoUrl ? tx("Drop a new image to replace, or click to browse") : tx("Drag & drop a logo here, or click to browse")}
        </p>
        <p className="text-slate-600 text-[11px]">{tx("PNG, SVG, JPEG, or WebP")}</p>
        <input ref={fileRef} type="file" accept="image/png,image/svg+xml,image/jpeg,image/webp"
          className="hidden" onChange={e => { upload(e.target.files?.[0]); e.target.value = '' }} />
      </div>
      {logoUrl && (
        <button type="button" onClick={remove}
          className="mt-1 flex items-center gap-1 text-slate-500 hover:text-red-400 text-xs">
          <X size={11} />{" "}{tx("Remove logo")}
        </button>
      )}
    </div>
  )
}

function BrandingStep({ onNext, onSkip, onBack, busy, setError }) {
  const [b, setB] = useState({ system_name: '', primary_color: '', operator: '' })
  const [logoUrl, setLogoUrl] = useState(null)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true); setError('')
    try { await api.post('/wizard/branding', b); onNext() }
    catch (e) { setError(e.response?.data?.detail || tx("Failed to save branding")) }
    finally { setSaving(false) }
  }

  return (
    <div>
      <StepHeader icon={Palette} title={tx("Name and branding (optional)")} subtitle={tx("You can set or change these anytime.")} />
      <div className="space-y-3">
        <label className="block text-slate-300 text-sm">{tx("Who runs this OpenOptOut?")}
          <input className={`${inp} mt-1`} placeholder={tx("e.g. The Rivera family, or Riverside Public Library")} maxLength={200}
            value={b.operator} onChange={e => setB({ ...b, operator: e.target.value })} />
          <span className="block text-slate-500 text-xs mt-1">{tx("People see this name when they first sign in: \"The Rivera family uses OpenOptOut to…\". You can change it on the Terms page.")}</span>
        </label>
        <input className={inp} placeholder={tx("System name (e.g. Springfield Library Privacy)")} value={b.system_name} onChange={e => setB({ ...b, system_name: e.target.value })} />
        <div>
          <p className="text-slate-400 text-xs mb-1">{tx("Logo")}</p>
          <LogoDropzone logoUrl={logoUrl} onUploaded={setLogoUrl} onRemoved={() => setLogoUrl(null)} setError={setError} />
        </div>
        <HexColorField label={tx("Primary color")} value={b.primary_color} onChange={v => setB({ ...b, primary_color: v })} />
      </div>
      <Buttons onBack={onBack} onSkip={onSkip} onNext={save} nextLabel="Finish" busy={saving || busy} />
    </div>
  )
}

// The exact enable-https command for the choices made in the deployment step, with a copy button — one less thing to get wrong on the server.
function CommandBox({ commands }) {
  const [os, setOs] = useState(
    typeof navigator !== 'undefined' && /Win/i.test(navigator.userAgent || '') ? 'windows' : 'linux')
  const [copied, setCopied] = useState(false)
  const cmd = commands[os]
  const copy = async () => {
    try { await navigator.clipboard.writeText(cmd); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { /* clipboard blocked: the text is selectable */ }
  }
  return (
    <div className="mb-4 rounded-lg border border-slate-700 bg-slate-800/40 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-slate-300 text-xs font-medium">{tx("Run this on the server")}</span>
        <div className="flex gap-1" role="group" aria-label={tx("Server type")}>
          {[['linux', tx("Linux / Mac")], ['windows', 'Windows']].map(([k, label]) => (
            <button key={k} type="button" onClick={() => setOs(k)} aria-pressed={os === k}
              className={`text-xs px-2 py-1 rounded-sm ${os === k ? 'bg-shield-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}>{label}</button>
          ))}
        </div>
      </div>
      <div className="flex items-start gap-2">
        <code className="flex-1 text-xs text-slate-200 bg-slate-900 rounded-sm px-2 py-1.5 select-all">
          {/* Wrap only between words, never inside a flag like --cert. */}
          {cmd.split(' ').map((t, i) => <span key={i}>{i ? ' ' : ''}<span className="whitespace-nowrap">{t}</span></span>)}
        </code>
        <button type="button" onClick={copy} aria-label={copied ? tx("Copied") : tx("Copy command")}
          className="shrink-0 p-1.5 rounded-sm text-slate-400 hover:text-slate-200 hover:bg-slate-700">
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>
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
      <StepHeader icon={CheckCircle2} title={tx("You're ready")} subtitle={tx("Here's what's set up.")} />
      <div className="space-y-2 mb-4">
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/50">
          <span className="text-slate-300 text-sm">{tx("Master Encryption Key")}</span>
          <span className="text-xs text-emerald-400">
            {tx("✓ 0600 file secured")}
          </span>
        </div>
        {['database', 'email', 'deployment', 'branding'].map(s => (
          <div key={s} className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/50">
            <span className="text-slate-300 text-sm capitalize">{s}</span>
            <span className={`text-xs ${steps[s] === 'done' ? 'text-emerald-400' : 'text-slate-500'}`}>
              {steps[s] === 'done' ? tx("✓ configured") : 'skipped'}
            </span>
          </div>
        ))}
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/50">
          <span className="text-slate-300 text-sm">{tx("Super Admin MFA")}</span>
          <span className={`text-xs ${mfaStatus?.mfa_enabled ? 'text-emerald-400' : 'text-amber-400'}`}>
            {mfaStatus?.mfa_enabled ? tx("✓ configured") : '3-day grace period active'}
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
            {tx("This site is using plain HTTP, so passwords cross the network unencrypted, and Google/Microsoft sign-in won't work.")}{' '}
            {reverseProxy === 'native'
              ? <>{txr("Turn on HTTPS on the server with <0>scripts/enable-https-native.sh</0> (Linux) or follow the Windows steps in <1>docs/admin/native-install.md</1>.", [<code />, <code />])}</>
              : <>{txr("Turn on HTTPS on the server with <0>./scripts/enable-https.sh</0> (Linux/macOS) or <1>scripts\\enable-https.ps1</1> (Windows) — see docs/admin/https.md.", [<code />, <code />])}</>}
          </span>
        </div>
      )}
      {summary?.enable_https_commands && <CommandBox commands={summary.enable_https_commands} />}
      {(reverseProxy === 'managed' || reverseProxy === 'native') && (
        <div className="mb-4 px-3 py-2 rounded-lg border border-slate-700 bg-slate-800/40 text-slate-400 text-xs">
          {tx("After you run the script and restart")}{reverseProxy === 'native' ? tx("the service") : tx("the containers")}{tx(", the dashboard will show a live check confirming whether the certificate actually came up — no need to just take it on faith.")}
        </div>
      )}
      <div className="text-slate-400 text-sm mb-4">
        {tx("Next: add the people you're removing data for, and import your broker list — both from the dashboard.")}
      </div>
      <button onClick={onDone} className="w-full bg-shield-600 hover:bg-shield-700 text-white text-sm rounded-lg py-2.5">
        {tx("Go to dashboard")}
      </button>
    </div>
  )
}
