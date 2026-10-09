import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ShieldCheck, CreditCard, Users, Key, Smartphone, Fingerprint, Lock,
  ShieldAlert, Copy, Check, ArrowLeft, RefreshCw, ChevronRight, Clock
} from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { useBranding } from '../hooks/useBranding'
import api from '../api'
import { performWebAuthnAuthenticate, performWebAuthnRegister } from '../utils/webauthn'

const inp = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"

export default function Login() {
  const { login, completeMfaLogin } = useAuth()
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

  // MFA Challenge State
  const [mfaChallenge, setMfaChallenge] = useState(null)
  const [mfaMethod, setMfaMethod]       = useState('totp') // 'totp' | 'webauthn' | 'backup'
  const [totpCode, setTotpCode]         = useState('')
  const [backupCode, setBackupCode]     = useState('')
  const [webauthnLoading, setWebauthnLoading] = useState(false)

  // MFA Mandated Setup State
  const [mfaMandate, setMfaMandate]           = useState(null)
  const [mandateStep, setMandateStep]         = useState('intro') // 'intro' | 'setup_totp' | 'setup_webauthn' | 'show_codes'
  const [mandateTotpData, setMandateTotpData] = useState(null)
  const [mandateTotpCode, setMandateTotpCode] = useState('')
  const [mandateKeyName, setMandateKeyName]   = useState('Primary Security Key')
  const [backupCodes, setBackupCodes]         = useState([])
  const [pendingToken, setPendingToken]       = useState(null)
  const [copiedCodes, setCopiedCodes]         = useState(false)
  const [copiedSecret, setCopiedSecret]       = useState(false)

  // First-run Setup Step 2: Super Admin MFA (skippable)
  const [setupStep, setSetupStep]               = useState('account') // 'account' | 'mfa'
  const [setupMfaMode, setSetupMfaMode]         = useState('choose')  // 'choose' | 'totp' | 'webauthn' | 'codes'
  const [setupTotpData, setSetupTotpData]       = useState(null)
  const [setupTotpCode, setSetupTotpCode]       = useState('')
  const [setupKeyName, setSetupKeyName]         = useState('Primary Security Key')
  const [setupBackupCodes, setSetupBackupCodes] = useState([])
  const [setupCopiedCodes, setSetupCopiedCodes] = useState(false)
  const [setupCopiedSecret, setSetupCopiedSecret] = useState(false)

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
    try {
      const res = await login(email, password)
      if (res?.mfa_required) {
        const allowed = res.allowed_methods || { totp: true, webauthn: true, backup_codes: true }
        const methods = res.methods || {}
        const canWebauthn = !!methods.webauthn && allowed.webauthn !== false
        const canTotp = !!methods.totp && allowed.totp !== false
        const canBackup = !!methods.has_backup_codes && allowed.backup_codes !== false

        setMfaChallenge({
          ticket: res.mfa_ticket,
          totpEnabled: canTotp,
          webauthnEnabled: canWebauthn,
          hasBackupCodes: canBackup,
          allowedMethods: allowed,
        })
        if (canWebauthn) {
          setMfaMethod('webauthn')
        } else if (canTotp) {
          setMfaMethod('totp')
        } else if (canBackup) {
          setMfaMethod('backup')
        }
        return
      }
      if (res?.mfa_mandated) {
        setMfaMandate({
          ticket: res.mfa_ticket,
          message: res.detail || res.message,
          allowedMethods: res.allowed_methods || { totp: true, webauthn: true, backup_codes: true },
        })
        setMandateStep('intro')
        return
      }
      navigate('/')
    } catch {
      setError('Invalid email or password')
    } finally {
      setLoading(false)
    }
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
      // Transition to Step 2: MFA setup for Super Admin (skippable)
      setSetupStep('mfa')
      setSetupMfaMode('choose')
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not create the administrator account')
    } finally { setLoading(false) }
  }

  // ── First-run Setup MFA Handlers ───────────────────────────────────────────
  const startSetupTotp = async () => {
    setError(''); setLoading(true)
    try {
      const { data } = await api.post('/auth/mfa/totp/setup')
      setSetupTotpData(data)
      setSetupMfaMode('totp')
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to initialize authenticator app setup.')
    } finally {
      setLoading(false)
    }
  }

  const handleActivateSetupTotp = async e => {
    e?.preventDefault()
    if (!setupTotpCode.trim()) return
    setError(''); setLoading(true)
    try {
      const { data } = await api.post('/auth/mfa/totp/activate', {
        secret: setupTotpData?.secret,
        code: setupTotpCode.trim(),
        backup_codes: setupTotpData?.backup_codes || [],
      })
      setSetupBackupCodes(data.backup_codes || setupTotpData?.backup_codes || [])
      setSetupMfaMode('codes')
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid verification code. Please check your app.')
    } finally {
      setLoading(false)
    }
  }

  const handleRegisterSetupWebAuthn = async () => {
    setError(''); setWebauthnLoading(true)
    try {
      const { data: optData } = await api.post('/auth/mfa/webauthn/register-options')
      const credential = await performWebAuthnRegister(optData.options)
      const { data: regData } = await api.post('/auth/mfa/webauthn/register', {
        credential,
        name: setupKeyName.trim() || 'Primary Security Key',
      })
      setSetupBackupCodes(regData.backup_codes || [])
      setSetupMfaMode('codes')
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        setError('Security key interaction was cancelled or timed out.')
      } else {
        setError(err.response?.data?.detail || err.message || 'Failed to register security key.')
      }
    } finally {
      setWebauthnLoading(false)
    }
  }

  const copySetupCodes = () => {
    navigator.clipboard.writeText(setupBackupCodes.join('\n'))
    setSetupCopiedCodes(true)
    setTimeout(() => setSetupCopiedCodes(false), 2000)
  }

  const copySetupSecret = (text) => {
    navigator.clipboard.writeText(text)
    setSetupCopiedSecret(true)
    setTimeout(() => setSetupCopiedSecret(false), 2000)
  }

  const skipSetupMfa = () => {
    navigate('/')
  }

  const finishSetupMfa = () => {
    navigate('/')
  }

  // ── MFA Verification Handlers ───────────────────────────────────────────────
  const handleVerifyTotp = async e => {
    e?.preventDefault()
    if (!totpCode.trim()) return
    setError(''); setLoading(true)
    try {
      const { data } = await api.post('/auth/mfa/verify-totp', {
        mfa_ticket: mfaChallenge.ticket,
        code: totpCode.trim(),
      })
      await completeMfaLogin(data.access_token)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid authenticator code')
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyBackup = async e => {
    e?.preventDefault()
    if (!backupCode.trim()) return
    setError(''); setLoading(true)
    try {
      const { data } = await api.post('/auth/mfa/verify-backup', {
        mfa_ticket: mfaChallenge.ticket,
        code: backupCode.trim(),
      })
      await completeMfaLogin(data.access_token)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid or already-used backup recovery code')
    } finally {
      setLoading(false)
    }
  }

  const handleTriggerWebAuthn = async () => {
    setError(''); setWebauthnLoading(true)
    try {
      const { data: optData } = await api.post('/auth/mfa/webauthn-options', {
        mfa_ticket: mfaChallenge.ticket,
      })
      const assertion = await performWebAuthnAuthenticate(optData.options)
      const { data: verifyData } = await api.post('/auth/mfa/verify-webauthn', {
        mfa_ticket: mfaChallenge.ticket,
        credential: assertion,
      })
      await completeMfaLogin(verifyData.access_token)
      navigate('/')
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        setError('Security key interaction was cancelled or timed out.')
      } else {
        setError(err.response?.data?.detail || err.message || 'Security key authentication failed.')
      }
    } finally {
      setWebauthnLoading(false)
    }
  }

  // ── Mandated Setup Handlers ────────────────────────────────────────────────
  const startMandateTotp = async () => {
    setError(''); setLoading(true)
    try {
      const { data } = await api.post('/auth/mfa/totp/setup', {}, {
        headers: { 'X-MFA-Ticket': mfaMandate.ticket }
      })
      setMandateTotpData(data)
      setMandateStep('setup_totp')
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to initialize authenticator setup.')
    } finally {
      setLoading(false)
    }
  }

  const handleActivateMandateTotp = async e => {
    e?.preventDefault()
    if (!mandateTotpCode.trim()) return
    setError(''); setLoading(true)
    try {
      const { data } = await api.post('/auth/mfa/totp/activate', {
        code: mandateTotpCode.trim()
      }, {
        headers: { 'X-MFA-Ticket': mfaMandate.ticket }
      })
      setBackupCodes(data.backup_codes || [])
      setPendingToken(data.access_token)
      setMandateStep('show_codes')
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid verification code. Please check your app.')
    } finally {
      setLoading(false)
    }
  }

  const handleRegisterMandateWebAuthn = async () => {
    setError(''); setWebauthnLoading(true)
    try {
      const { data: optData } = await api.post('/auth/mfa/webauthn/register-options', {}, {
        headers: { 'X-MFA-Ticket': mfaMandate.ticket }
      })
      const credential = await performWebAuthnRegister(optData.options)
      const { data: regData } = await api.post('/auth/mfa/webauthn/register', {
        credential,
        key_name: mandateKeyName || 'Primary Security Key'
      }, {
        headers: { 'X-MFA-Ticket': mfaMandate.ticket }
      })
      setBackupCodes(regData.backup_codes || [])
      setPendingToken(regData.access_token)
      setMandateStep('show_codes')
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        setError('Security key registration was cancelled or timed out.')
      } else {
        setError(err.response?.data?.detail || err.message || 'Failed to register security key.')
      }
    } finally {
      setWebauthnLoading(false)
    }
  }

  const finishMandatedLogin = async () => {
    if (pendingToken) {
      await completeMfaLogin(pendingToken)
      navigate('/')
    }
  }

  const copyCodes = () => {
    navigator.clipboard.writeText(backupCodes.join('\n'))
    setCopiedCodes(true)
    setTimeout(() => setCopiedCodes(false), 2000)
  }

  const copySecret = (text) => {
    navigator.clipboard.writeText(text)
    setCopiedSecret(true)
    setTimeout(() => setCopiedSecret(false), 2000)
  }

  const name         = branding?.system_name   || 'OpenOptOut'
  const tagline      = branding?.tagline        || 'Your personal data removal service'
  const staffLabel   = branding?.staff_tab_label  || 'Staff'
  const patronLabel  = branding?.patron_tab_label || 'Library Card'
  const staffWelcome = branding?.staff_welcome  || branding?.welcome_message
  const patronWelcome= branding?.patron_welcome || branding?.welcome_message

  const showTabs = showStaff && showPatron

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className={`w-full transition-all duration-200 ${needsSetup && setupStep === 'mfa' ? 'max-w-md' : 'max-w-sm'}`}>

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

          {/* 1. First-run setup: create administrator account + optional MFA step */}
          {needsSetup === null ? (
            <div className="text-center text-slate-500 text-sm py-6">Loading…</div>
          ) : needsSetup ? (
            setupStep === 'account' ? (
              <div>
                <div className="flex items-center justify-between mb-3 text-xs text-slate-400">
                  <span className="font-semibold text-shield-400">Step 1 of 2</span>
                  <span>Create Account</span>
                </div>
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
                    className="w-full bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-sm rounded-lg py-2 flex items-center justify-center gap-1.5 font-medium transition-colors">
                    {loading ? 'Creating account…' : <><span>Create administrator account</span><ChevronRight size={15} /></>}
                  </button>
                </form>
              </div>
            ) : (
              /* Step 2: Super Admin MFA Setup (Optional / Skippable) */
              <div className="space-y-4">
                <div className="flex items-center justify-between text-xs pb-1 border-b border-slate-800">
                  <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
                    <Check size={13} />
                    <span>Step 1: Account Created</span>
                  </div>
                  <span className="text-shield-400 font-semibold">Step 2: MFA Setup (Optional)</span>
                </div>

                <div>
                  <h2 className="text-white font-semibold text-sm flex items-center gap-2">
                    <Lock size={15} className="text-shield-400" /> Protect Your Super Admin Account
                  </h2>
                  <p className="text-slate-400 text-xs mt-1">
                    Super Admin accounts control all system data and policies. You can set up at least one MFA method now, or skip and set it up within your 3-day compliance window.
                  </p>
                </div>

                {error && (
                  <div className="p-2.5 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-xs">
                    {error}
                  </div>
                )}

                {setupMfaMode === 'choose' && (
                  <div className="space-y-3 pt-1">
                    {/* Option 1: TOTP */}
                    <div className="p-3 bg-slate-800/80 border border-slate-700/80 rounded-xl space-y-2.5">
                      <div className="flex items-start gap-2.5">
                        <div className="p-2 bg-slate-900 text-shield-400 rounded-lg shrink-0 mt-0.5">
                          <Smartphone size={16} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-slate-200 text-xs font-semibold">Authenticator App (TOTP)</p>
                          <p className="text-slate-400 text-[11px] mt-0.5">
                            Google Authenticator, Yubico Authenticator, 1Password, or Bitwarden on your mobile phone.
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={startSetupTotp}
                        disabled={loading}
                        className="w-full bg-slate-700 hover:bg-slate-600 text-white text-xs py-2 px-3 rounded-lg flex items-center justify-center gap-1.5 font-medium transition-colors">
                        {loading ? <RefreshCw size={12} className="animate-spin" /> : <Smartphone size={12} />}
                        Set up Authenticator App
                      </button>
                    </div>

                    {/* Option 2: WebAuthn / Security Key */}
                    <div className="p-3 bg-slate-800/80 border border-slate-700/80 rounded-xl space-y-2.5">
                      <div className="flex items-start gap-2.5">
                        <div className="p-2 bg-slate-900 text-emerald-400 rounded-lg shrink-0 mt-0.5">
                          <Fingerprint size={16} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-slate-200 text-xs font-semibold">Security Key & Biometrics</p>
                          <p className="text-slate-400 text-[11px] mt-0.5">
                            YubiKey, Titan Key, Mac Touch ID, Windows Hello, or mobile Face ID / Android via QR code.
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => { setError(''); setSetupMfaMode('webauthn') }}
                        className="w-full bg-slate-700 hover:bg-slate-600 text-white text-xs py-2 px-3 rounded-lg flex items-center justify-center gap-1.5 font-medium transition-colors">
                        <Fingerprint size={12} />
                        Register Security Key or Biometrics
                      </button>
                    </div>

                    {/* Compliance Grace Notice & Skip Button */}
                    <div className="pt-2 border-t border-slate-800 space-y-2">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
                        <Clock size={12} className="text-slate-400 shrink-0" />
                        <span>You have a 3-day grace period to configure this later in Settings.</span>
                      </div>
                      <button
                        type="button"
                        onClick={skipSetupMfa}
                        className="w-full border border-slate-700 hover:border-slate-600 bg-slate-800/60 hover:bg-slate-800 text-slate-300 hover:text-white text-xs py-2 px-3 rounded-lg flex items-center justify-center gap-1 font-medium transition-colors">
                        <span>Skip for now</span>
                        <ChevronRight size={13} />
                      </button>
                    </div>
                  </div>
                )}

                {setupMfaMode === 'totp' && (
                  <div className="space-y-3 pt-1">
                    <div className="flex items-center justify-between">
                      <button
                        type="button"
                        onClick={() => { setError(''); setSetupMfaMode('choose') }}
                        className="text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1">
                        <ArrowLeft size={12} /> Back to options
                      </button>
                      <button
                        type="button"
                        onClick={skipSetupMfa}
                        className="text-slate-500 hover:text-slate-300 text-xs">
                        Skip for now
                      </button>
                    </div>

                    {setupTotpData && (
                      <div className="space-y-3">
                        <div className="p-3 bg-slate-800/90 border border-slate-700 rounded-lg space-y-1.5">
                          <label className="text-[11px] font-medium text-slate-400">Secret Key (Base32)</label>
                          <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-lg p-2 font-mono text-xs text-shield-300">
                            <span className="truncate flex-1 tracking-wider">{setupTotpData.secret}</span>
                            <button
                              type="button"
                              onClick={() => copySetupSecret(setupTotpData.secret)}
                              className="text-slate-400 hover:text-white shrink-0">
                              {setupCopiedSecret ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                            </button>
                          </div>
                          <p className="text-slate-500 text-[11px]">
                            Enter this key in your authenticator app (Google Authenticator, Yubico Authenticator).
                          </p>
                        </div>

                        <form onSubmit={handleActivateSetupTotp} className="space-y-3">
                          <div>
                            <label className="text-[11px] font-medium text-slate-400 block mb-1">Enter 6-digit verification code</label>
                            <input
                              type="text"
                              inputMode="numeric"
                              pattern="[0-9]*"
                              maxLength={6}
                              placeholder="000000"
                              value={setupTotpCode}
                              onChange={e => setSetupTotpCode(e.target.value)}
                              className={`${inp} text-center font-mono tracking-widest text-base`}
                              autoFocus
                              required
                            />
                          </div>
                          <button
                            type="submit"
                            disabled={loading || setupTotpCode.trim().length !== 6}
                            className="w-full bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-xs py-2 rounded-lg font-medium flex items-center justify-center gap-1.5">
                            {loading ? <RefreshCw size={12} className="animate-spin" /> : <Check size={13} />}
                            Verify & Enable Authenticator
                          </button>
                        </form>
                      </div>
                    )}
                  </div>
                )}

                {setupMfaMode === 'webauthn' && (
                  <div className="space-y-3 pt-1">
                    <div className="flex items-center justify-between">
                      <button
                        type="button"
                        onClick={() => { setError(''); setSetupMfaMode('choose') }}
                        className="text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1">
                        <ArrowLeft size={12} /> Back to options
                      </button>
                      <button
                        type="button"
                        onClick={skipSetupMfa}
                        className="text-slate-500 hover:text-slate-300 text-xs">
                        Skip for now
                      </button>
                    </div>

                    <div className="space-y-3">
                      <div>
                        <label className="text-[11px] font-medium text-slate-400 block mb-1">Key or Device Label</label>
                        <input
                          className={inp}
                          placeholder="e.g. Primary YubiKey, Mac Touch ID"
                          value={setupKeyName}
                          onChange={e => setSetupKeyName(e.target.value)}
                        />
                      </div>
                      <button
                        type="button"
                        onClick={handleRegisterSetupWebAuthn}
                        disabled={webauthnLoading}
                        className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white text-xs py-2 rounded-lg font-medium flex items-center justify-center gap-1.5 transition-colors">
                        {webauthnLoading ? <RefreshCw size={12} className="animate-spin" /> : <Fingerprint size={14} />}
                        Tap Security Key or Touch Sensor
                      </button>
                      <p className="text-slate-500 text-[11px] text-center">
                        When prompted, touch your YubiKey or authenticate with Mac Touch ID / Face ID.
                      </p>
                    </div>
                  </div>
                )}

                {setupMfaMode === 'codes' && (
                  <div className="space-y-3 pt-1">
                    <div className="p-3 bg-emerald-950/30 border border-emerald-800 rounded-lg text-emerald-300 text-xs flex items-center gap-2">
                      <ShieldCheck size={16} className="text-emerald-400 shrink-0" />
                      <span className="font-semibold">MFA Successfully Configured!</span>
                    </div>

                    <div className="p-3 bg-slate-800/90 border border-slate-700 rounded-lg space-y-2">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-semibold text-slate-300">Backup Recovery Codes</label>
                        <button
                          type="button"
                          onClick={copySetupCodes}
                          className="text-xs text-shield-400 hover:text-shield-300 flex items-center gap-1 font-medium">
                          {setupCopiedCodes ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                          {setupCopiedCodes ? 'Copied!' : 'Copy all'}
                        </button>
                      </div>
                      <p className="text-slate-400 text-[11px]">
                        Save these one-time codes in a safe place. They will let you access your account if your authenticator is lost.
                      </p>
                      <div className="grid grid-cols-2 gap-1.5 p-2 bg-slate-900 border border-slate-800 rounded-lg font-mono text-[11px] text-slate-300">
                        {setupBackupCodes.map((c, i) => (
                          <div key={i} className="text-center py-0.5 tracking-wider">{c}</div>
                        ))}
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={finishSetupMfa}
                      className="w-full bg-shield-600 hover:bg-shield-700 text-white text-xs py-2 rounded-lg font-medium flex items-center justify-center gap-1.5 transition-colors">
                      <span>Complete Setup & Continue</span>
                      <ChevronRight size={14} />
                    </button>
                  </div>
                )}
              </div>
            )
          ) : mfaChallenge ? (
            /* 2. MFA Challenge Flow (TOTP, Security Key/Touch ID, Backup Code) */
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Lock size={16} className="text-shield-400" />
                <h2 className="text-white font-semibold text-sm">Two-Factor Authentication</h2>
              </div>
              <p className="text-slate-400 text-xs mb-4">
                Verify your identity to complete sign-in.
              </p>

              {error && (
                <div className="mb-4 px-3 py-2 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-xs">
                  {error}
                </div>
              )}

              {/* Method Switcher Tabs */}
              <div className="flex gap-1 bg-slate-800 p-1 rounded-lg mb-4 text-xs">
                {mfaChallenge.webauthnEnabled && (
                  <button
                    type="button"
                    onClick={() => { setMfaMethod('webauthn'); setError('') }}
                    className={`flex-1 py-1.5 rounded-sm flex items-center justify-center gap-1.5 transition-colors ${mfaMethod === 'webauthn' ? 'bg-slate-700 text-white font-medium' : 'text-slate-400 hover:text-slate-200'}`}>
                    <Fingerprint size={13} /> Key / Touch ID
                  </button>
                )}
                {mfaChallenge.totpEnabled && (
                  <button
                    type="button"
                    onClick={() => { setMfaMethod('totp'); setError('') }}
                    className={`flex-1 py-1.5 rounded-sm flex items-center justify-center gap-1.5 transition-colors ${mfaMethod === 'totp' ? 'bg-slate-700 text-white font-medium' : 'text-slate-400 hover:text-slate-200'}`}>
                    <Smartphone size={13} /> Authenticator
                  </button>
                )}
                {mfaChallenge.hasBackupCodes && (
                  <button
                    type="button"
                    onClick={() => { setMfaMethod('backup'); setError('') }}
                    className={`flex-1 py-1.5 rounded-sm flex items-center justify-center gap-1.5 transition-colors ${mfaMethod === 'backup' ? 'bg-slate-700 text-white font-medium' : 'text-slate-400 hover:text-slate-200'}`}>
                    <Key size={13} /> Backup
                  </button>
                )}
              </div>

              {/* WebAuthn Mode */}
              {mfaMethod === 'webauthn' && (
                <div className="space-y-3">
                  <div className="p-3 bg-slate-800/80 rounded-lg border border-slate-700/60 text-center">
                    <Fingerprint size={28} className="mx-auto text-shield-400 mb-2" />
                    <p className="text-slate-300 text-xs font-medium">Security Key, Biometrics, or Phone</p>
                    <p className="text-slate-500 text-[11px] mt-1">Touch YubiKey, use Mac Touch ID, or scan QR code with iPhone (Face ID) / Android</p>
                  </div>
                  <button
                    type="button"
                    onClick={handleTriggerWebAuthn}
                    disabled={webauthnLoading}
                    className="w-full py-2.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2">
                    {webauthnLoading ? <RefreshCw size={14} className="animate-spin" /> : <Fingerprint size={14} />}
                    {webauthnLoading ? 'Waiting for touch or phone scan…' : 'Use Security Key / Touch ID / Phone'}
                  </button>
                </div>
              )}

              {/* TOTP Mode */}
              {mfaMethod === 'totp' && (
                <form onSubmit={handleVerifyTotp} className="space-y-3">
                  <div>
                    <label className="text-slate-400 text-xs mb-1 block">6-digit Authenticator Code</label>
                    <input
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      maxLength={6}
                      autoFocus
                      placeholder="000000"
                      value={totpCode}
                      onChange={e => setTotpCode(e.target.value)}
                      className={`${inp} text-center font-mono tracking-widest text-lg`}
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={loading || totpCode.trim().length < 6}
                    className="w-full py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                    {loading ? 'Verifying…' : 'Verify Code'}
                  </button>
                </form>
              )}

              {/* Backup Code Mode */}
              {mfaMethod === 'backup' && (
                <form onSubmit={handleVerifyBackup} className="space-y-3">
                  <div>
                    <label className="text-slate-400 text-xs mb-1 block">8-character Backup Recovery Code</label>
                    <input
                      type="text"
                      autoFocus
                      placeholder="e.g. 9b4f2a1c"
                      value={backupCode}
                      onChange={e => setBackupCode(e.target.value.toLowerCase())}
                      className={`${inp} text-center font-mono tracking-wider`}
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={loading || !backupCode.trim()}
                    className="w-full py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                    {loading ? 'Verifying…' : 'Verify Recovery Code'}
                  </button>
                </form>
              )}

              <button
                type="button"
                onClick={() => { setMfaChallenge(null); setError('') }}
                className="w-full mt-3 py-1.5 text-xs text-slate-500 hover:text-slate-400 flex items-center justify-center gap-1 transition-colors">
                <ArrowLeft size={12} /> Cancel and return to sign in
              </button>
            </div>
          ) : mfaMandate ? (
            /* 3. Mandated Setup Wizard (Mandated after 3 days of install) */
            <div>
              <div className="flex items-center gap-2 mb-2">
                <ShieldAlert size={16} className="text-amber-400" />
                <h2 className="text-white font-semibold text-sm">MFA Setup Mandated</h2>
              </div>
              <p className="text-slate-400 text-xs mb-4">
                Multi-Factor Authentication is required for administrator accounts after 3 days of installation. Please configure an authentication method to continue.
              </p>

              {error && (
                <div className="mb-4 px-3 py-2 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-xs">
                  {error}
                </div>
              )}

              {/* Step: Intro / Choice */}
              {mandateStep === 'intro' && (
                <div className="space-y-2.5">
                  {mfaMandate?.allowedMethods?.totp !== false && (
                    <button
                      type="button"
                      onClick={startMandateTotp}
                      disabled={loading}
                      className="w-full p-3 bg-slate-800 hover:bg-slate-750 border border-slate-700 rounded-xl text-left transition-colors flex items-center gap-3">
                      <div className="p-2 bg-shield-500/10 text-shield-400 rounded-lg shrink-0">
                        <Smartphone size={18} />
                      </div>
                      <div>
                        <p className="text-slate-200 text-xs font-medium">Authenticator App (TOTP)</p>
                        <p className="text-slate-500 text-[11px] mt-0.5">Google Authenticator, 1Password, Yubico</p>
                      </div>
                    </button>
                  )}

                  {mfaMandate?.allowedMethods?.webauthn !== false && (
                    <button
                      type="button"
                      onClick={() => setMandateStep('setup_webauthn')}
                      className="w-full p-3 bg-slate-800 hover:bg-slate-750 border border-slate-700 rounded-xl text-left transition-colors flex items-center gap-3">
                      <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg shrink-0">
                        <Fingerprint size={18} />
                      </div>
                      <div>
                        <p className="text-slate-200 text-xs font-medium">Security Key / Touch ID / Phone (WebAuthn)</p>
                        <p className="text-slate-500 text-[11px] mt-0.5">YubiKey, Mac Touch ID, iPhone Face ID, Android</p>
                      </div>
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => { setMfaMandate(null); setError('') }}
                    className="w-full mt-2 py-1.5 text-xs text-slate-500 hover:text-slate-400 flex items-center justify-center gap-1 transition-colors">
                    <ArrowLeft size={12} /> Back to sign in
                  </button>
                </div>
              )}

              {/* Step: Setup TOTP */}
              {mandateStep === 'setup_totp' && mandateTotpData && (
                <div className="space-y-3">
                  <div>
                    <label className="text-slate-400 text-xs mb-1 block">Secret Key</label>
                    <div className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-lg p-2 font-mono text-xs text-shield-300">
                      <span className="truncate flex-1 tracking-wider">{mandateTotpData.secret}</span>
                      <button
                        type="button"
                        onClick={() => copySecret(mandateTotpData.secret)}
                        className="text-slate-400 hover:text-white shrink-0">
                        {copiedSecret ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                      </button>
                    </div>
                    <p className="text-slate-500 text-[11px] mt-1">
                      Enter this key in your authenticator app or password manager.
                    </p>
                  </div>

                  <form onSubmit={handleActivateMandateTotp} className="space-y-3">
                    <div>
                      <label className="text-slate-400 text-xs mb-1 block">Enter 6-digit code to verify</label>
                      <input
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        maxLength={6}
                        placeholder="000000"
                        value={mandateTotpCode}
                        onChange={e => setMandateTotpCode(e.target.value)}
                        className={`${inp} text-center font-mono tracking-widest text-lg`}
                        autoFocus
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={loading || mandateTotpCode.trim().length < 6}
                      className="w-full py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                      {loading ? 'Activating…' : 'Confirm & Activate'}
                    </button>
                  </form>

                  <button
                    type="button"
                    onClick={() => { setMandateStep('intro'); setError('') }}
                    className="w-full py-1 text-xs text-slate-500 hover:text-slate-400 flex items-center justify-center gap-1 transition-colors">
                    <ArrowLeft size={12} /> Choose a different method
                  </button>
                </div>
              )}

              {/* Step: Setup WebAuthn */}
              {mandateStep === 'setup_webauthn' && (
                <div className="space-y-3">
                  <div>
                    <label className="text-slate-400 text-xs mb-1 block">Key or Device Name</label>
                    <input
                      type="text"
                      value={mandateKeyName}
                      onChange={e => setMandateKeyName(e.target.value)}
                      placeholder="e.g. Primary YubiKey / Mac Touch ID"
                      className={inp}
                    />
                  </div>

                  <div className="p-3 bg-slate-800/80 rounded-lg border border-slate-700/60 text-center">
                    <Fingerprint size={28} className="mx-auto text-emerald-400 mb-2" />
                    <p className="text-slate-300 text-xs font-medium">Ready to register hardware</p>
                    <p className="text-slate-500 text-[11px] mt-1">
                      Click below, then touch your YubiKey, use Mac Touch ID, or scan the on-screen QR code with your iPhone (Face ID) or Android phone.
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={handleRegisterMandateWebAuthn}
                    disabled={webauthnLoading}
                    className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2">
                    {webauthnLoading ? <RefreshCw size={14} className="animate-spin" /> : <Fingerprint size={14} />}
                    {webauthnLoading ? 'Waiting for touch or phone scan…' : 'Register Key / Touch ID / Phone'}
                  </button>

                  <button
                    type="button"
                    onClick={() => { setMandateStep('intro'); setError('') }}
                    className="w-full py-1 text-xs text-slate-500 hover:text-slate-400 flex items-center justify-center gap-1 transition-colors">
                    <ArrowLeft size={12} /> Choose a different method
                  </button>
                </div>
              )}

              {/* Step: Show Backup Codes */}
              {mandateStep === 'show_codes' && (
                <div className="space-y-3">
                  <div className="p-2.5 bg-emerald-950/40 border border-emerald-800 rounded-lg">
                    <p className="text-emerald-300 text-xs font-semibold flex items-center gap-1.5">
                      <Check size={14} /> MFA Enrolled Successfully
                    </p>
                    <p className="text-emerald-400/80 text-[11px] mt-1">
                      Save these one-time recovery codes in a secure place. If you ever lose access to your device or key, you can use these to sign in.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-1.5 bg-slate-950 p-2.5 rounded-lg border border-slate-800 font-mono text-xs text-slate-300 text-center">
                    {backupCodes.map((c, i) => (
                      <span key={i} className="py-0.5">{c}</span>
                    ))}
                  </div>

                  <button
                    type="button"
                    onClick={copyCodes}
                    className="w-full py-1.5 border border-slate-700 hover:bg-slate-800 text-slate-300 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-colors">
                    {copiedCodes ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                    {copiedCodes ? 'Codes Copied to Clipboard' : 'Copy All Recovery Codes'}
                  </button>

                  <button
                    type="button"
                    onClick={finishMandatedLogin}
                    className="w-full py-2 bg-shield-600 hover:bg-shield-700 text-white rounded-lg text-sm font-medium transition-colors">
                    Continue to Dashboard
                  </button>
                </div>
              )}
            </div>
          ) : (
            /* 4. Standard Sign-In Form (Staff or Patron) */
            <div>

              {/* Staff / Patron tabs — only shown when both are enabled */}
              {showTabs && (
                <div className="flex gap-1 bg-slate-800 p-1 rounded-lg mb-5">
                  <button
                    onClick={() => { setTab('staff'); setError('') }}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-sm rounded-sm transition-colors ${tab === 'staff' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                  >
                    <Users size={13} /> {staffLabel}
                  </button>
                  <button
                    onClick={() => { setTab('patron'); setError('') }}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-sm rounded-sm transition-colors ${tab === 'patron' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
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
