import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ShieldCheck, CreditCard, Users, Key, Smartphone, Fingerprint, Lock,
  ShieldAlert, Copy, Check, ArrowLeft, RefreshCw, ChevronRight, Clock, Mail,
  BookOpen, Eye, Sun, Moon, Laptop, Globe, Type, Palette, Compass, Sliders, ToggleLeft, ToggleRight
} from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { useBranding } from '../hooks/useBranding'
import { useAccessibility } from '../context/AccessibilityContext'
import { useLanguage } from '../i18n/LanguageContext'
import api from '../api'
import { performWebAuthnAuthenticate, performWebAuthnRegister } from '../utils/webauthn'
import { tx } from '../i18n/tx'
import FontSizeSlider from '../components/FontSizeSlider'
import { detailText } from '../errorMessage'

const inp = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"

export default function Login() {
  const { login, completeMfaLogin } = useAuth()
  const { branding } = useBranding()
  const { language, setLanguage, availableLanguages, isRTL } = useLanguage()
  const {
    theme, setTheme, highContrast, setHighContrast,
    dyslexicFont, setDyslexicFont, fontSize, setFontSize,
    reducedMotion, setReducedMotion, enhancedTargets, setEnhancedTargets
  } = useAccessibility()
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
  const [mandateKeyName, setMandateKeyName]   = useState('My security key')
  const [backupCodes, setBackupCodes]         = useState([])
  const [pendingToken, setPendingToken]       = useState(null)
  const [copiedCodes, setCopiedCodes]         = useState(false)
  const [copiedSecret, setCopiedSecret]       = useState(false)

  // First-run Setup: 'usability' (language & accessibility) -> 'account' (admin credentials) -> 'mfa' (skippable MFA)
  const [setupStep, setSetupStep]               = useState('usability') // 'usability' | 'account' | 'mfa'
  const [setupMfaMode, setSetupMfaMode]         = useState('choose')  // 'choose' | 'totp' | 'webauthn' | 'codes'
  const [setupTotpData, setSetupTotpData]       = useState(null)
  const [setupTotpCode, setSetupTotpCode]       = useState('')
  const [setupKeyName, setSetupKeyName]         = useState('My security key')
  const [setupBackupCodes, setSetupBackupCodes] = useState([])
  const [setupCopiedCodes, setSetupCopiedCodes] = useState(false)
  const [setupCopiedSecret, setSetupCopiedSecret] = useState(false)

  // Passwordless authentication state
  const [passwordless, setPasswordless] = useState({
    enabled: false,
    allow_passkey: true,
    allow_magic_link: true,
    enforce_passwordless_local: false,
  })
  const [staffAuthMode, setStaffAuthMode] = useState('password') // 'password' | 'passkey' | 'magic_link_request' | 'magic_link_verify'
  const [magicLinkToken, setMagicLinkToken] = useState('')
  const [magicLinkCode, setMagicLinkCode] = useState('')
  const [magicLinkMessage, setMagicLinkMessage] = useState('')

  // Role-based session duration and Remember Me policy
  const [sessionPolicy, setSessionPolicy] = useState({
    remember_me_enabled: true,
  })
  const [rememberStaff, setRememberStaff] = useState(false)
  const [rememberPatron, setRememberPatron] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem('saved_login_email')
    if (saved) {
      setEmail(saved)
      setRememberStaff(true)
    }
  }, [])

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
      setSaml(ap.saml_enabled ? { label: ap.saml_label || tx("Single sign-on") } : null)
      if (ap.session_policy) {
        setSessionPolicy(ap.session_policy)
      }
      if (ap.passwordless) {
        setPasswordless(ap.passwordless)
        if (ap.passwordless.enabled && ap.passwordless.enforce_passwordless_local) {
          setStaffAuthMode(ap.passwordless.allow_passkey !== false ? 'passkey' : 'magic_link_request')
        }
      }
    }).catch(() => {}).finally(() => setLoadingProviders(false))
  }, [])

  // Is there a public sign-up page? (Admin → Branding → Registration)
  const [signupOpen, setSignupOpen] = useState(false)
  useEffect(() => {
    api.get('/auth/signup-info').then(r => setSignupOpen(!!r.data.signup)).catch(() => {})
  }, [])

  // Keep tab in sync if branding changes
  useEffect(() => {
    if (!showStaff && showPatron) setTab('patron')
    if (showStaff && !showPatron) setTab('staff')
  }, [showStaff, showPatron])

  // After a password or an email code: ask for the second factor, or for MFA
  // set-up, when the server says so. Returns true if it did.
  const askSecondStep = res => {
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
      return true
    }
    if (res?.mfa_mandated) {
      setMfaMandate({
        ticket: res.mfa_ticket,
        message: res.detail || res.message,
        allowedMethods: res.allowed_methods || { totp: true, webauthn: true, backup_codes: true },
      })
      setMandateStep('intro')
      return true
    }
    return false
  }

  const submitStaff = async e => {
    e.preventDefault(); setError(''); setLoading(true)
    if (rememberStaff && email.trim()) {
      localStorage.setItem('saved_login_email', email.trim())
    } else {
      localStorage.removeItem('saved_login_email')
    }
    try {
      const res = await login(email, password, rememberStaff)
      if (askSecondStep(res)) return
      navigate('/')
    } catch (err) {
      // 429 = too many failed attempts; the server says how long to wait
      setError(err.response?.status === 429 ? detailText(err) : tx("That email and password don't match. Check them and try again."))
    } finally {
      setLoading(false)
    }
  }

  const handlePasswordlessPasskey = async e => {
    if (e) e.preventDefault()
    setError('')
    setLoading(true)
    if (rememberStaff && email.trim()) {
      localStorage.setItem('saved_login_email', email.trim())
    }
    try {
      const { data: optData } = await api.post('/auth/passwordless/options', {
        email: email.trim() || null,
        remember_me: rememberStaff,
      })
      const credential = await performWebAuthnAuthenticate(optData.options)
      const { data: loginRes } = await api.post('/auth/passwordless/verify', {
        ticket: optData.ticket,
        credential,
        remember_me: rememberStaff,
      })
      await completeMfaLogin(loginRes.access_token)
      navigate('/')
    } catch (err) {
      const msg = detailText(err) || err.message || tx("Couldn't sign in with your passkey. Try again, or use your password.")
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleRequestMagicLink = async e => {
    if (e) e.preventDefault()
    if (!email.trim()) {
      setError(tx("Type your email address and we will send you a sign-in code."))
      return
    }
    setError('')
    setLoading(true)
    try {
      const { data } = await api.post('/auth/passwordless/magic-link/request', {
        email: email.trim(),
      })
      setMagicLinkToken(data.token || '')
      setMagicLinkMessage(data.message || tx("We sent a 6-digit sign-in code to your email."))
      setStaffAuthMode('magic_link_verify')
    } catch (err) {
      setError(detailText(err) || tx("Couldn't send the sign-in code. Please try again in a minute."))
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyMagicLink = async e => {
    if (e) e.preventDefault()
    if (!magicLinkCode.trim()) {
      setError(tx("Type the 6-digit code from the email."))
      return
    }
    setError('')
    setLoading(true)
    if (rememberStaff && email.trim()) {
      localStorage.setItem('saved_login_email', email.trim())
    }
    try {
      const { data } = await api.post('/auth/passwordless/magic-link/verify', {
        token: magicLinkToken,
        code: magicLinkCode.trim(),
        remember_me: rememberStaff,
      })
      if (askSecondStep(data)) return
      await completeMfaLogin(data.access_token)
      navigate('/')
    } catch (err) {
      setError(detailText(err) || tx("That code didn't work. It may be mistyped or too old. Ask for a new one."))
    } finally {
      setLoading(false)
    }
  }


  const submitPatron = async e => {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const { data } = await api.post('/auth/sip2/login', { barcode, pin, remember_me: rememberPatron })
      localStorage.setItem('token', data.access_token)
      window.location.href = '/'
    } catch (err) {
      setError(detailText(err) ?? tx("Couldn't sign in with that library card. Check the number and PIN."))
    } finally { setLoading(false) }
  }

  const oidcLogin = provider => { window.location.href = `/api/auth/oidc/${provider}/login` }

  // First-run: create the initial administrator, then log them straight in.
  const [setupName, setSetupName] = useState(() => sessionStorage.getItem('setup_draft_name') || '')
  const [setupConfirm, setSetupConfirm] = useState('')
  const [setSystemDefaultLanguage, setSetSystemDefaultLanguage] = useState(true)

  // Keep setup draft in sessionStorage so language switch reload doesn't wipe them
  useEffect(() => {
    if (setupName) sessionStorage.setItem('setup_draft_name', setupName)
  }, [setupName])
  useEffect(() => {
    if (email) sessionStorage.setItem('setup_draft_email', email)
  }, [email])

  const submitSetup = async e => {
    e.preventDefault(); setError('')
    if (password.length < 12) { setError(tx("Use a password of at least 12 characters")); return }
    if (password !== setupConfirm) { setError(tx("The two passwords don't match.")); return }
    setLoading(true)
    try {
      await api.post('/auth/register', {
        email,
        full_name: setupName,
        password,
        preferred_language: language,
        set_system_default_language: setSystemDefaultLanguage,
        accessibility_settings: {
          theme,
          high_contrast: highContrast,
          dyslexic_font: dyslexicFont,
          font_size: fontSize,
          reduced_motion: reducedMotion,
          enhanced_targets: enhancedTargets,
        }
      })
      sessionStorage.removeItem('setup_draft_name')
      sessionStorage.removeItem('setup_draft_email')
      await login(email, password)   // first user is created as super_admin
      try {
        await api.post('/i18n/user/preference', {
          language,
          accessibility_settings: {
            theme,
            high_contrast: highContrast,
            dyslexic_font: dyslexicFont,
            font_size: fontSize,
            reduced_motion: reducedMotion,
            enhanced_targets: enhancedTargets,
          }
        })
      } catch (prefErr) {
        // Non-fatal if offline
      }
      // Transition to Step 2: MFA setup for Super Admin (skippable)
      setSetupStep('mfa')
      setSetupMfaMode('choose')
    } catch (err) {
      setError(detailText(err) || tx("Couldn't create the admin account. Please try again."))
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
      setError(detailText(err) || tx("Couldn't start setting up the code app. Please try again."))
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
      setError(detailText(err) || tx("That code didn't work. Codes change every 30 seconds, so use the newest one."))
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
        name: setupKeyName.trim() || 'My security key',
      })
      setSetupBackupCodes(regData.backup_codes || [])
      setSetupMfaMode('codes')
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        setError(tx("The security key step was cancelled or took too long. Try again."))
      } else {
        setError(detailText(err) || err.message || tx("Couldn't add the security key. Please try again."))
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
      setError(detailText(err) || tx("That code didn't work. Codes change every 30 seconds, so use the newest one."))
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
      setError(detailText(err) || tx("That backup code didn't work. Each one works only once."))
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
        setError(tx("The security key step was cancelled or took too long. Try again."))
      } else {
        setError(detailText(err) || err.message || tx("Couldn't sign in with the security key. Try again, or use another way."))
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
      setError(detailText(err) || tx("Couldn't start setting up the code app. Please try again."))
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
      setError(detailText(err) || tx("That code didn't work. Codes change every 30 seconds, so use the newest one."))
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
        key_name: mandateKeyName || 'My security key'
      }, {
        headers: { 'X-MFA-Ticket': mfaMandate.ticket }
      })
      setBackupCodes(regData.backup_codes || [])
      setPendingToken(regData.access_token)
      setMandateStep('show_codes')
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        setError(tx("The security key step was cancelled or took too long. Try again."))
      } else {
        setError(detailText(err) || err.message || tx("Couldn't add the security key. Please try again."))
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
  const tagline      = branding?.tagline        || tx("Your personal data removal service")
  const staffLabel   = branding?.staff_tab_label  || 'Staff'
  const patronLabel  = branding?.patron_tab_label || tx("Library Card")
  const staffWelcome = branding?.staff_welcome  || branding?.welcome_message
  const patronWelcome= branding?.patron_welcome || branding?.welcome_message

  const showTabs = showStaff && showPatron

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4 relative">
      {/* Quick Accessibility Bar */}
      <div className="absolute top-4 end-4 flex items-center gap-2 z-10">
        <button
          type="button"
          onClick={() => setDyslexicFont(!dyslexicFont)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition-colors ${
            dyslexicFont
              ? 'bg-purple-500/20 text-purple-300 border-purple-500/50'
              : 'bg-slate-900/80 text-slate-400 border-slate-800 hover:text-white'
          }`}
          aria-pressed={dyslexicFont}
          title={tx("Dyslexia-Friendly Font (OpenDyslexic)")}
        >
          <BookOpen size={13} className={dyslexicFont ? 'text-purple-400' : 'text-slate-400'} />
          <span>{tx("Dyslexia Font")}</span>
        </button>

        <button
          type="button"
          onClick={() => setHighContrast(!highContrast)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition-colors ${
            highContrast
              ? 'bg-yellow-400/20 text-yellow-300 border-yellow-400/50'
              : 'bg-slate-900/80 text-slate-400 border-slate-800 hover:text-white'
          }`}
          aria-pressed={highContrast}
          title={tx("High Contrast Mode (WCAG 2.2 AAA)")}
        >
          <Eye size={13} className={highContrast ? 'text-yellow-400' : 'text-slate-400'} />
          <span>{tx("Contrast")}</span>
        </button>
      </div>

      <div className={`w-full transition-all duration-200 ${needsSetup ? 'max-w-xl' : 'max-w-sm'}`}>

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
            <div className="text-center text-slate-500 text-sm py-6">{tx("Loading…")}</div>
          ) : needsSetup ? (
            setupStep === 'usability' ? (
              <div>
                <div className="flex items-center justify-between mb-3 text-xs text-slate-400">
                  <span className="font-semibold text-shield-400">{tx("Step 1 of 3")}</span>
                  <span>{tx("Welcome & Display Options")}</span>
                </div>
                <div className="mb-5">
                  <h2 className="text-white font-semibold text-base">{tx("Welcome to OpenOptOut")}</h2>
                  <p className="text-slate-400 text-xs mt-1">
                    {tx("Personalize your display, language, and accessibility preferences. These take effect immediately.")}
                  </p>
                </div>

                {/* 1. System Language & System Default */}
                <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-950/60 space-y-2.5 mb-4">
                  <div className="flex items-center justify-between">
                    <label htmlFor="setup-language" className="text-xs font-semibold text-white flex items-center gap-1.5">
                      <Globe size={14} className="text-shield-400" />
                      <span>{tx("System Language")}</span>
                    </label>
                    {isRTL && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 font-mono">
                        {tx("RTL")}
                      </span>
                    )}
                  </div>
                  <select
                    id="setup-language"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-hidden focus:border-shield-500"
                  >
                    {availableLanguages.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.native_name} ({lang.name}){lang.is_rtl ? ' — RTL' : ''}
                      </option>
                    ))}
                  </select>
                  <label className="flex items-start gap-2 cursor-pointer pt-0.5">
                    <input
                      type="checkbox"
                      checked={setSystemDefaultLanguage}
                      onChange={(e) => setSetSystemDefaultLanguage(e.target.checked)}
                      className="mt-0.5 rounded border-slate-700 text-shield-600 focus:ring-shield-500 bg-slate-900 cursor-pointer"
                    />
                    <div className="text-xs">
                      <span className="font-medium text-slate-200">{tx("Set as default language for the rest of the system")}</span>
                      <p className="text-slate-400 text-[11px] mt-0.5">
                        {tx("New users, patron portals, and automated notifications will default to this language.")}
                      </p>
                    </div>
                  </label>
                </div>

                {/* 2. Color Theme Selection */}
                <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-950/60 space-y-2 mb-4">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-white flex items-center gap-1.5">
                      <Palette size={14} className="text-shield-400" />
                      <span>{tx("Color Theme")}</span>
                    </label>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                    {[
                      { id: 'dark', label: tx("Dark"), icon: Moon, desc: tx("Deep black") },
                      { id: 'dark-ada', label: tx("Dark (ADA)"), icon: Eye, desc: tx("AAA 21:1 contrast") },
                      { id: 'light', label: tx("Light"), icon: Sun, desc: tx("Crisp white") },
                      { id: 'light-ada', label: tx("Light (ADA)"), icon: Eye, desc: tx("AAA high contrast") },
                      { id: 'space', label: tx("Space Explorer"), icon: Compass, desc: tx("Cosmic amber") },
                      { id: 'space-ada', label: tx("Space (ADA)"), icon: Eye, desc: tx("AAA high contrast") },
                      { id: 'gray', label: tx("Gray"), icon: Sliders, desc: tx("Slate neutral") },
                      { id: 'system', label: tx("System"), icon: Laptop, desc: tx("Auto match") },
                    ].map((item) => {
                      const Icon = item.icon
                      const isActive = theme === item.id
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => setTheme(item.id)}
                          className={`p-2 rounded-xl border text-center flex flex-col items-center gap-1 transition-all ${
                            isActive
                              ? 'border-shield-500 bg-shield-500/10 text-white ring-1 ring-shield-500/50 font-semibold'
                              : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:text-white hover:border-slate-700'
                          }`}
                        >
                          <Icon size={14} className={isActive ? 'text-shield-400' : 'text-slate-400'} />
                          <span className="text-xs">{item.label}</span>
                          <span className="text-[10px] text-slate-400 opacity-80">{item.desc}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* 3. High Contrast Checkbox */}
                <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-950/60 flex items-start gap-2.5 mb-4">
                  <input
                    type="checkbox"
                    id="setup-high-contrast"
                    checked={highContrast}
                    onChange={(e) => setHighContrast(e.target.checked)}
                    className="mt-0.5 w-4 h-4 rounded text-shield-600 focus:ring-yellow-400 border-slate-700 bg-slate-900 cursor-pointer"
                  />
                  <div className="space-y-0.5 flex-1">
                    <label htmlFor="setup-high-contrast" className="text-xs font-semibold text-white flex items-center gap-2 cursor-pointer">
                      <span>{tx("Make High Contrast (WCAG 2.2 AAA)")}</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-yellow-400/20 text-yellow-300 font-mono">{tx("AAA 7:1+")}</span>
                    </label>
                    <p className="text-[11px] text-slate-400 leading-normal">
                      {tx("Enforces maximum contrast (21:1) adapting to your chosen theme. Light theme renders crisp black-on-white; dark theme renders vivid white-on-black; space explorer renders high-contrast amber with 2px high-visibility borders.")}
                    </p>
                  </div>
                </div>

                {/* 4. Dyslexia-Friendly Typography */}
                <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-950/60 space-y-2 mb-4">
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5 pe-2">
                      <div className="flex items-center gap-1.5">
                        <BookOpen size={14} className="text-purple-400" />
                        <span className="text-xs font-semibold text-white">{tx("Dyslexia-Friendly Font (OpenDyslexic)")}</span>
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 font-mono">{"OpenDyslexic"}</span>
                      </div>
                      <p className="text-[11px] text-slate-400 leading-normal">
                        {tx("Switches typography across the platform to OpenDyslexic with weighted bottoms to enhance reading flow.")}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setDyslexicFont(!dyslexicFont)}
                      className="p-1 text-slate-400 hover:text-white shrink-0 focus-visible:outline-2 focus-visible:outline-shield-400"
                      aria-label={tx("Dyslexia-Friendly Font (OpenDyslexic)")}
                    >
                      {dyslexicFont ? <ToggleRight size={22} className="text-purple-400" /> : <ToggleLeft size={22} className="text-slate-600" />}
                    </button>
                  </div>
                  {dyslexicFont && (
                    <div className="p-2 rounded-lg border border-purple-500/30 bg-purple-950/20 text-xs text-purple-200" style={{ fontFamily: "'OpenDyslexic', system-ui, sans-serif" }}>
                      {tx("OpenDyslexic typography is active. Letters have unique heavy bottoms to prevent flipping and confusion.")}
                    </div>
                  )}
                </div>

                {/* 5. Font Size Scaling */}
                <FontSizeSlider
                  id="login-font-size-slider"
                  color="shield"
                  showPreview={true}
                  className="mb-6"
                />

                {/* Continue to Account Setup */}
                <button
                  type="button"
                  onClick={() => setSetupStep('account')}
                  className="w-full bg-shield-600 hover:bg-shield-700 text-white text-sm rounded-lg py-2.5 flex items-center justify-center gap-1.5 font-medium transition-colors shadow-xs"
                >
                  <span>{tx("Continue")}</span>
                  <ChevronRight size={16} />
                </button>
              </div>
            ) : setupStep === 'account' ? (
              <div>
                <button
                  type="button"
                  onClick={() => setSetupStep('usability')}
                  className="text-xs text-slate-400 hover:text-white flex items-center gap-1 mb-3 transition-colors"
                >
                  <ArrowLeft size={13} />
                  <span>{tx("Back to display options")}</span>
                </button>
                <div className="flex items-center justify-between mb-3 text-xs text-slate-400">
                  <span className="font-semibold text-shield-400">{tx("Step 2 of 3")}</span>
                  <span>{tx("Administrator Account")}</span>
                </div>
                <div className="mb-5">
                  <h2 className="text-white font-semibold text-base">{tx("Create Administrator Account")}</h2>
                  <p className="text-slate-400 text-xs mt-1">
                    {tx("No accounts exist yet. Create the administrator account below. This first account has full super-admin access; you can add more users afterward.")}
                  </p>
                </div>
                <form onSubmit={submitSetup} className="space-y-3">
                  <input className={inp} placeholder={tx("Your name")} value={setupName}
                    onChange={e => setSetupName(e.target.value)} required />
                  <input className={inp} type="email" placeholder={tx("Admin email")} value={email}
                    onChange={e => setEmail(e.target.value)} required />
                  <input className={inp} type="password" placeholder={tx("Password (min 12 characters)")}
                    value={password} onChange={e => setPw(e.target.value)} required />
                  <input className={inp} type="password" placeholder={tx("Confirm password")}
                    value={setupConfirm} onChange={e => setSetupConfirm(e.target.value)} required />

                  {error && <p className="text-red-400 text-xs">{error}</p>}
                  <button type="submit" disabled={loading}
                    className="w-full bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-sm rounded-lg py-2.5 flex items-center justify-center gap-1.5 font-medium transition-colors">
                    {loading ? tx("Creating account…") : <><span>{tx("Create administrator account")}</span><ChevronRight size={15} /></>}
                  </button>
                </form>
              </div>
            ) : (
              /* Step 3: Super Admin MFA Setup (Optional / Skippable) */
              <div className="space-y-4">
                <div className="flex items-center justify-between text-xs pb-1 border-b border-slate-800">
                  <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
                    <Check size={13} />
                    <span>{tx("Step 2: Account Created")}</span>
                  </div>
                  <span className="text-shield-400 font-semibold">{tx("Step 3 of 3: MFA Setup (Optional)")}</span>
                </div>

                <div>
                  <h2 className="text-white font-semibold text-sm flex items-center gap-2">
                    <Lock size={15} className="text-shield-400" />{" "}{tx("Protect Your Super Admin Account")}
                  </h2>
                  <p className="text-slate-400 text-xs mt-1">
                    {tx("Super Admin accounts control all system data and policies. You can set up at least one MFA method now, or skip and set it up within your 3-day compliance window.")}
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
                          <p className="text-slate-200 text-xs font-semibold">{tx("Authenticator App (TOTP)")}</p>
                          <p className="text-slate-400 text-[11px] mt-0.5">
                            {tx("Google Authenticator, Yubico Authenticator, 1Password, or Bitwarden on your mobile phone.")}
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={startSetupTotp}
                        disabled={loading}
                        className="w-full bg-slate-700 hover:bg-slate-600 text-white text-xs py-2 px-3 rounded-lg flex items-center justify-center gap-1.5 font-medium transition-colors">
                        {loading ? <RefreshCw size={12} className="animate-spin" /> : <Smartphone size={12} />}
                        {tx("Set up Authenticator App")}
                      </button>
                    </div>

                    {/* Option 2: WebAuthn / Security Key */}
                    <div className="p-3 bg-slate-800/80 border border-slate-700/80 rounded-xl space-y-2.5">
                      <div className="flex items-start gap-2.5">
                        <div className="p-2 bg-slate-900 text-emerald-400 rounded-lg shrink-0 mt-0.5">
                          <Fingerprint size={16} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-slate-200 text-xs font-semibold">{tx("Security Key & Biometrics")}</p>
                          <p className="text-slate-400 text-[11px] mt-0.5">
                            {tx("YubiKey, Titan Key, Mac Touch ID, Windows Hello, or mobile Face ID / Android via QR code.")}
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => { setError(''); setSetupMfaMode('webauthn') }}
                        className="w-full bg-slate-700 hover:bg-slate-600 text-white text-xs py-2 px-3 rounded-lg flex items-center justify-center gap-1.5 font-medium transition-colors">
                        <Fingerprint size={12} />
                        {tx("Register Security Key or Biometrics")}
                      </button>
                    </div>

                    {/* Compliance Grace Notice & Skip Button */}
                    <div className="pt-2 border-t border-slate-800 space-y-2">
                      <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
                        <Clock size={12} className="text-slate-400 shrink-0" />
                        <span>{tx("You have a 3-day grace period to configure this later in Settings.")}</span>
                      </div>
                      <button
                        type="button"
                        onClick={skipSetupMfa}
                        className="w-full border border-slate-700 hover:border-slate-600 bg-slate-800/60 hover:bg-slate-800 text-slate-300 hover:text-white text-xs py-2 px-3 rounded-lg flex items-center justify-center gap-1 font-medium transition-colors">
                        <span>{tx("Skip for now")}</span>
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
                        <ArrowLeft size={12} />{" "}{tx("Back to options")}
                      </button>
                      <button
                        type="button"
                        onClick={skipSetupMfa}
                        className="text-slate-500 hover:text-slate-300 text-xs">
                        {tx("Skip for now")}
                      </button>
                    </div>

                    {setupTotpData && (
                      <div className="space-y-3">
                        <div className="p-3 bg-slate-800/90 border border-slate-700 rounded-lg space-y-1.5">
                          <label className="text-[11px] font-medium text-slate-400">{tx("Secret Key (Base32)")}</label>
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
                            {tx("Enter this key in your authenticator app (Google Authenticator, Yubico Authenticator).")}
                          </p>
                        </div>

                        <form onSubmit={handleActivateSetupTotp} className="space-y-3">
                          <div>
                            <label className="text-[11px] font-medium text-slate-400 block mb-1">{tx("Enter 6-digit verification code")}</label>
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
                            {tx("Verify & Enable Authenticator")}
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
                        <ArrowLeft size={12} />{" "}{tx("Back to options")}
                      </button>
                      <button
                        type="button"
                        onClick={skipSetupMfa}
                        className="text-slate-500 hover:text-slate-300 text-xs">
                        {tx("Skip for now")}
                      </button>
                    </div>

                    <div className="space-y-3">
                      <div>
                        <label className="text-[11px] font-medium text-slate-400 block mb-1">{tx("Key or Device Label")}</label>
                        <input
                          className={inp}
                          placeholder={tx("e.g. My YubiKey, or Mac fingerprint")}
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
                        {tx("Tap Security Key or Touch Sensor")}
                      </button>
                      <p className="text-slate-500 text-[11px] text-center">
                        {tx("When prompted, touch your YubiKey or authenticate with Mac Touch ID / Face ID.")}
                      </p>
                    </div>
                  </div>
                )}

                {setupMfaMode === 'codes' && (
                  <div className="space-y-3 pt-1">
                    <div className="p-3 bg-emerald-950/30 border border-emerald-800 rounded-lg text-emerald-300 text-xs flex items-center gap-2">
                      <ShieldCheck size={16} className="text-emerald-400 shrink-0" />
                      <span className="font-semibold">{tx("MFA Successfully Configured!")}</span>
                    </div>

                    <div className="p-3 bg-slate-800/90 border border-slate-700 rounded-lg space-y-2">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-semibold text-slate-300">{tx("Backup Recovery Codes")}</label>
                        <button
                          type="button"
                          onClick={copySetupCodes}
                          className="text-xs text-shield-400 hover:text-shield-300 flex items-center gap-1 font-medium">
                          {setupCopiedCodes ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                          {setupCopiedCodes ? tx("Copied!") : tx("Copy all")}
                        </button>
                      </div>
                      <p className="text-slate-400 text-[11px]">
                        {tx("Save these one-time codes in a safe place. They will let you access your account if your authenticator is lost.")}
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
                      <span>{tx("Complete Setup & Continue")}</span>
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
                <h2 className="text-white font-semibold text-sm">{tx("Two-Factor Authentication")}</h2>
              </div>
              <p className="text-slate-400 text-xs mb-4">
                {tx("Verify your identity to complete sign-in.")}
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
                    <Fingerprint size={13} />{" "}{tx("Key / Touch ID")}
                  </button>
                )}
                {mfaChallenge.totpEnabled && (
                  <button
                    type="button"
                    onClick={() => { setMfaMethod('totp'); setError('') }}
                    className={`flex-1 py-1.5 rounded-sm flex items-center justify-center gap-1.5 transition-colors ${mfaMethod === 'totp' ? 'bg-slate-700 text-white font-medium' : 'text-slate-400 hover:text-slate-200'}`}>
                    <Smartphone size={13} />{" "}{tx("Authenticator")}
                  </button>
                )}
                {mfaChallenge.hasBackupCodes && (
                  <button
                    type="button"
                    onClick={() => { setMfaMethod('backup'); setError('') }}
                    className={`flex-1 py-1.5 rounded-sm flex items-center justify-center gap-1.5 transition-colors ${mfaMethod === 'backup' ? 'bg-slate-700 text-white font-medium' : 'text-slate-400 hover:text-slate-200'}`}>
                    <Key size={13} />{" "}{tx("Backup")}
                  </button>
                )}
              </div>

              {/* WebAuthn Mode */}
              {mfaMethod === 'webauthn' && (
                <div className="space-y-3">
                  <div className="p-3 bg-slate-800/80 rounded-lg border border-slate-700/60 text-center">
                    <Fingerprint size={28} className="mx-auto text-shield-400 mb-2" />
                    <p className="text-slate-300 text-xs font-medium">{tx("Security Key, Biometrics, or Phone")}</p>
                    <p className="text-slate-500 text-[11px] mt-1">{tx("Touch YubiKey, use Mac Touch ID, or scan QR code with iPhone (Face ID) / Android")}</p>
                  </div>
                  <button
                    type="button"
                    onClick={handleTriggerWebAuthn}
                    disabled={webauthnLoading}
                    className="w-full py-2.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2">
                    {webauthnLoading ? <RefreshCw size={14} className="animate-spin" /> : <Fingerprint size={14} />}
                    {webauthnLoading ? tx("Waiting for touch or phone scan…") : tx("Use a security key, fingerprint or phone")}
                  </button>
                </div>
              )}

              {/* TOTP Mode */}
              {mfaMethod === 'totp' && (
                <form onSubmit={handleVerifyTotp} className="space-y-3">
                  <div>
                    <label className="text-slate-400 text-xs mb-1 block">{tx("6-digit Authenticator Code")}</label>
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
                    {loading ? tx("Verifying…") : tx("Check code")}
                  </button>
                </form>
              )}

              {/* Backup Code Mode */}
              {mfaMethod === 'backup' && (
                <form onSubmit={handleVerifyBackup} className="space-y-3">
                  <div>
                    <label className="text-slate-400 text-xs mb-1 block">{tx("8-character Backup Recovery Code")}</label>
                    <input
                      type="text"
                      autoFocus
                      placeholder={tx("e.g. 9b4f2a1c")}
                      value={backupCode}
                      onChange={e => setBackupCode(e.target.value.toLowerCase())}
                      className={`${inp} text-center font-mono tracking-wider`}
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={loading || !backupCode.trim()}
                    className="w-full py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                    {loading ? tx("Verifying…") : tx("Use backup code")}
                  </button>
                </form>
              )}

              <button
                type="button"
                onClick={() => { setMfaChallenge(null); setError('') }}
                className="w-full mt-3 py-1.5 text-xs text-slate-500 hover:text-slate-400 flex items-center justify-center gap-1 transition-colors">
                <ArrowLeft size={12} />{" "}{tx("Cancel and return to sign in")}
              </button>
            </div>
          ) : mfaMandate ? (
            /* 3. Mandated Setup Wizard (Mandated after 3 days of install) */
            <div>
              <div className="flex items-center gap-2 mb-2">
                <ShieldAlert size={16} className="text-amber-400" />
                <h2 className="text-white font-semibold text-sm">{tx("MFA Setup Mandated")}</h2>
              </div>
              <p className="text-slate-400 text-xs mb-4">
                {tx("Multi-Factor Authentication is required for administrator accounts after 3 days of installation. Please configure an authentication method to continue.")}
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
                      className="w-full p-3 bg-slate-800 hover:bg-slate-750 border border-slate-700 rounded-xl text-start transition-colors flex items-center gap-3">
                      <div className="p-2 bg-shield-500/10 text-shield-400 rounded-lg shrink-0">
                        <Smartphone size={18} />
                      </div>
                      <div>
                        <p className="text-slate-200 text-xs font-medium">{tx("Authenticator App (TOTP)")}</p>
                        <p className="text-slate-500 text-[11px] mt-0.5">{tx("Google Authenticator, 1Password, Yubico")}</p>
                      </div>
                    </button>
                  )}

                  {mfaMandate?.allowedMethods?.webauthn !== false && (
                    <button
                      type="button"
                      onClick={() => setMandateStep('setup_webauthn')}
                      className="w-full p-3 bg-slate-800 hover:bg-slate-750 border border-slate-700 rounded-xl text-start transition-colors flex items-center gap-3">
                      <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg shrink-0">
                        <Fingerprint size={18} />
                      </div>
                      <div>
                        <p className="text-slate-200 text-xs font-medium">{tx("Security Key / Touch ID / Phone (WebAuthn)")}</p>
                        <p className="text-slate-500 text-[11px] mt-0.5">{tx("YubiKey, Mac Touch ID, iPhone Face ID, Android")}</p>
                      </div>
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => { setMfaMandate(null); setError('') }}
                    className="w-full mt-2 py-1.5 text-xs text-slate-500 hover:text-slate-400 flex items-center justify-center gap-1 transition-colors">
                    <ArrowLeft size={12} />{" "}{tx("Back to sign in")}
                  </button>
                </div>
              )}

              {/* Step: Setup TOTP */}
              {mandateStep === 'setup_totp' && mandateTotpData && (
                <div className="space-y-3">
                  <div>
                    <label className="text-slate-400 text-xs mb-1 block">{tx("Secret Key")}</label>
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
                      {tx("Enter this key in your authenticator app or password manager.")}
                    </p>
                  </div>

                  <form onSubmit={handleActivateMandateTotp} className="space-y-3">
                    <div>
                      <label className="text-slate-400 text-xs mb-1 block">{tx("Enter 6-digit code to verify")}</label>
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
                      {loading ? tx("Activating…") : tx("Turn it on")}
                    </button>
                  </form>

                  <button
                    type="button"
                    onClick={() => { setMandateStep('intro'); setError('') }}
                    className="w-full py-1 text-xs text-slate-500 hover:text-slate-400 flex items-center justify-center gap-1 transition-colors">
                    <ArrowLeft size={12} />{" "}{tx("Choose a different method")}
                  </button>
                </div>
              )}

              {/* Step: Setup WebAuthn */}
              {mandateStep === 'setup_webauthn' && (
                <div className="space-y-3">
                  <div>
                    <label className="text-slate-400 text-xs mb-1 block">{tx("Key or Device Name")}</label>
                    <input
                      type="text"
                      value={mandateKeyName}
                      onChange={e => setMandateKeyName(e.target.value)}
                      placeholder={tx("e.g. My YubiKey, or Mac fingerprint")}
                      className={inp}
                    />
                  </div>

                  <div className="p-3 bg-slate-800/80 rounded-lg border border-slate-700/60 text-center">
                    <Fingerprint size={28} className="mx-auto text-emerald-400 mb-2" />
                    <p className="text-slate-300 text-xs font-medium">{tx("Ready to register hardware")}</p>
                    <p className="text-slate-500 text-[11px] mt-1">
                      {tx("Click below, then touch your YubiKey, use Mac Touch ID, or scan the on-screen QR code with your iPhone (Face ID) or Android phone.")}
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={handleRegisterMandateWebAuthn}
                    disabled={webauthnLoading}
                    className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2">
                    {webauthnLoading ? <RefreshCw size={14} className="animate-spin" /> : <Fingerprint size={14} />}
                    {webauthnLoading ? tx("Waiting for touch or phone scan…") : tx("Add a security key, fingerprint or phone")}
                  </button>

                  <button
                    type="button"
                    onClick={() => { setMandateStep('intro'); setError('') }}
                    className="w-full py-1 text-xs text-slate-500 hover:text-slate-400 flex items-center justify-center gap-1 transition-colors">
                    <ArrowLeft size={12} />{" "}{tx("Choose a different method")}
                  </button>
                </div>
              )}

              {/* Step: Show Backup Codes */}
              {mandateStep === 'show_codes' && (
                <div className="space-y-3">
                  <div className="p-2.5 bg-emerald-950/40 border border-emerald-800 rounded-lg">
                    <p className="text-emerald-300 text-xs font-semibold flex items-center gap-1.5">
                      <Check size={14} />{" "}{tx("MFA Enrolled Successfully")}
                    </p>
                    <p className="text-emerald-400/80 text-[11px] mt-1">
                      {tx("Save these one-time recovery codes in a secure place. If you ever lose access to your device or key, you can use these to sign in.")}
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
                    {copiedCodes ? tx("Codes copied") : tx("Copy all backup codes")}
                  </button>

                  <button
                    type="button"
                    onClick={finishMandatedLogin}
                    className="w-full py-2 bg-shield-600 hover:bg-shield-700 text-white rounded-lg text-sm font-medium transition-colors">
                    {tx("Continue to Dashboard")}
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
                          {tx("Sign in with {label}", { label: saml.label })}
                        </button>
                      )}
                      {oidcProviders.map(p => (
                        <button key={p.key} onClick={() => oidcLogin(p.key)}
                          className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-slate-700 rounded-lg text-slate-300 text-sm hover:bg-slate-800 transition-colors">
                          {tx("Sign in with {label}", { label: p.label })}
                        </button>
                      ))}
                      <div className="flex items-center gap-2 my-3">
                        <div className="flex-1 h-px bg-slate-800" />
                        <span className="text-slate-600 text-xs">{tx("or local sign-in")}</span>
                        <div className="flex-1 h-px bg-slate-800" />
                      </div>
                    </div>
                  )}

                  {/* Passwordless enforcement notice */}
                  {passwordless.enabled && passwordless.enforce_passwordless_local && (
                    <div className="mb-3 px-3 py-2 bg-shield-950/40 border border-shield-800/80 rounded-lg text-shield-300 text-xs flex items-center gap-2">
                      <Fingerprint size={15} className="text-shield-400 shrink-0" />
                      <span>{tx("Passwordless authentication required for local accounts.")}</span>
                    </div>
                  )}

                  {/* 1. Magic Link 6-digit Code Entry */}
                  {staffAuthMode === 'magic_link_verify' ? (
                    <form onSubmit={handleVerifyMagicLink} className="space-y-3">
                      <div className="text-center space-y-1 mb-2">
                        <p className="text-slate-300 text-xs font-medium">{tx("Verification Code Sent")}</p>
                        <p className="text-slate-500 text-[11px]">{magicLinkMessage}</p>
                      </div>
                      <div>
                        <label className="text-slate-400 text-xs mb-1 block">{tx("6-digit sign-in code")}</label>
                        <input
                          type="text"
                          inputMode="numeric"
                          pattern="[0-9]*"
                          maxLength={6}
                          placeholder="000000"
                          value={magicLinkCode}
                          onChange={e => setMagicLinkCode(e.target.value)}
                          className={`${inp} text-center font-mono tracking-widest text-lg`}
                          autoComplete="one-time-code"
                          autoFocus
                          required
                        />
                      </div>
                      <button
                        type="submit"
                        disabled={loading || magicLinkCode.trim().length !== 6}
                        className="w-full py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2">
                        {loading ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
                        {tx("Verify & Sign In")}
                      </button>
                      <button
                        type="button"
                        onClick={() => { setError(''); setStaffAuthMode(passwordless.enforce_passwordless_local ? 'passkey' : 'password') }}
                        className="w-full py-1 text-xs text-slate-500 hover:text-slate-400 flex items-center justify-center gap-1 transition-colors">
                        <ArrowLeft size={12} />{" "}{tx("Back")}
                      </button>
                    </form>
                  ) : staffAuthMode === 'magic_link_request' ? (
                    /* 2. Magic Link Request Form */
                    <form onSubmit={handleRequestMagicLink} className="space-y-3">
                      <div>
                        <label className="text-slate-400 text-xs mb-1 block">{tx("Account Email")}</label>
                        <input
                          type="email"
                          value={email}
                          onChange={e => setEmail(e.target.value)}
                          required
                          className={inp}
                          placeholder="you@example.com"
                          autoFocus
                        />
                      </div>
                      <button
                        type="submit"
                        disabled={loading || !email.trim()}
                        className="w-full py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2">
                        {loading ? <RefreshCw size={14} className="animate-spin" /> : <Mail size={14} />}
                        {tx("Send Sign-In Code")}
                      </button>
                      <div className="flex items-center justify-between pt-1 text-xs">
                        {passwordless.allow_passkey && (
                          <button
                            type="button"
                            onClick={() => { setError(''); setStaffAuthMode('passkey') }}
                            className="text-shield-400 hover:text-shield-300">
                            {tx("Sign in with Passkey instead")}
                          </button>
                        )}
                        {!passwordless.enforce_passwordless_local && (
                          <button
                            type="button"
                            onClick={() => { setError(''); setStaffAuthMode('password') }}
                            className="text-slate-500 hover:text-slate-400">
                            {tx("Use password")}
                          </button>
                        )}
                      </div>
                    </form>
                  ) : passwordless.enabled && passwordless.enforce_passwordless_local ? (
                    /* 3. Enforced Passwordless (Passkey is primary) */
                    <div className="space-y-3">
                      <div>
                        <label className="text-slate-400 text-xs mb-1 block">{tx("Account Email")}</label>
                        <input
                          type="email"
                          value={email}
                          onChange={e => setEmail(e.target.value)}
                          className={inp}
                          placeholder={tx("you@example.com (or leave empty for resident Passkey)")}
                          autoComplete="username webauthn"
                          autoFocus
                        />
                      </div>
                      {sessionPolicy?.remember_me_enabled !== false && (
                        <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-slate-300 pt-1">
                          <input
                            type="checkbox"
                            checked={rememberStaff}
                            onChange={e => setRememberStaff(e.target.checked)}
                            className="rounded border-slate-700 bg-slate-900 text-shield-600 focus:ring-shield-500"
                          />
                          <span>{tx("Remember my email on this device")}</span>
                        </label>
                      )}
                      {passwordless.allow_passkey && (
                        <button
                          type="button"
                          onClick={handlePasswordlessPasskey}
                          disabled={loading}
                          className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2">
                          {loading ? <RefreshCw size={14} className="animate-spin" /> : <Fingerprint size={16} />}
                          {tx("Sign In with Passkey / Security Key")}
                        </button>
                      )}
                      {passwordless.allow_magic_link && (
                        <button
                          type="button"
                          onClick={() => { setError(''); setStaffAuthMode('magic_link_request') }}
                          className="w-full py-2 bg-slate-800 hover:bg-slate-750 border border-slate-700 text-slate-300 rounded-lg text-xs font-medium transition-colors flex items-center justify-center gap-2">
                          <Mail size={14} />{" "}{tx("Send sign-in code to email instead")}
                        </button>
                      )}
                    </div>
                  ) : (
                    /* 4. Password Form with Optional Passwordless Options */
                    <>
                      <form onSubmit={submitStaff} className="space-y-3">
                        <div>
                          <label className="text-slate-400 text-xs mb-1 block">{tx("Email")}</label>
                          <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                            required className={inp} placeholder="you@example.com" autoFocus />
                        </div>
                        <div>
                          <label className="text-slate-400 text-xs mb-1 block">{tx("Password")}</label>
                          <input type="password" value={password} onChange={e => setPw(e.target.value)}
                            required className={inp} />
                        </div>
                        {sessionPolicy?.remember_me_enabled !== false && (
                          <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-slate-300 pt-1">
                            <input
                              type="checkbox"
                              checked={rememberStaff}
                              onChange={e => setRememberStaff(e.target.checked)}
                              className="rounded border-slate-700 bg-slate-900 text-shield-600 focus:ring-shield-500"
                            />
                            <span>{tx("Remember my email on this device")}</span>
                          </label>
                        )}
                        <button type="submit" disabled={loading}
                          className="w-full py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                          {loading ? tx("Signing in…") : tx("Sign in")}
                        </button>
                      </form>

                      {passwordless.enabled && (passwordless.allow_passkey || passwordless.allow_magic_link) && (
                        <div className="mt-4 pt-3 border-t border-slate-800 space-y-2">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-slate-500 text-[11px] font-medium uppercase tracking-wider">{tx("Passwordless options")}</span>
                          </div>
                          {passwordless.allow_passkey && (
                            <button
                              type="button"
                              onClick={handlePasswordlessPasskey}
                              disabled={loading}
                              className="w-full py-2 bg-slate-800 hover:bg-slate-750 border border-slate-700 text-slate-200 rounded-lg text-xs font-medium transition-colors flex items-center justify-center gap-2">
                              {loading ? <RefreshCw size={13} className="animate-spin" /> : <Fingerprint size={14} className="text-emerald-400" />}
                              {tx("Sign in with Passkey / Security Key")}
                            </button>
                          )}
                          {passwordless.allow_magic_link && (
                            <button
                              type="button"
                              onClick={() => { setError(''); setStaffAuthMode('magic_link_request') }}
                              className="w-full py-1.5 text-xs text-slate-400 hover:text-slate-200 flex items-center justify-center gap-1.5 transition-colors">
                              <Mail size={13} />{" "}{tx("Email me a one-time sign-in code")}
                            </button>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </>
              )}


              {/* ── Patron tab ── */}
              {tab === 'patron' && (
                <form onSubmit={submitPatron} className="space-y-3">
                  <div>
                    <label className="text-slate-400 text-xs mb-1 block">{tx("Library card number")}</label>
                    <input value={barcode} onChange={e => setBarcode(e.target.value)}
                      required className={inp} placeholder={tx("Enter your barcode")} autoFocus
                      inputMode="numeric" />
                  </div>
                  <div>
                    <label className="text-slate-400 text-xs mb-1 block">{tx("PIN")}</label>
                    <input type="password" value={pin} onChange={e => setPin(e.target.value)}
                      required className={inp} placeholder={tx("Library PIN")}
                      inputMode="numeric" />
                  </div>
                  {sessionPolicy?.remember_me_enabled !== false && (
                    <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-slate-300 pt-1">
                      <input
                        type="checkbox"
                        checked={rememberPatron}
                        onChange={e => setRememberPatron(e.target.checked)}
                        className="rounded border-slate-700 bg-slate-900 text-shield-600 focus:ring-shield-500"
                      />
                      <span>{tx("Keep me signed in on this device")}</span>
                    </label>
                  )}
                  <button type="submit" disabled={loading || !sip2Enabled}
                    className="w-full py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors">
                    {loading ? tx("Signing in…") : tx("Sign in with library card")}
                  </button>
                  {!loadingProviders && !sip2Enabled && (
                    <p className="text-amber-400 text-xs text-center">
                      {tx("Library card login is not yet configured. Contact your administrator.")}
                    </p>
                  )}
                </form>
              )}

              {signupOpen && (
                <p className="mt-4 text-center text-sm text-slate-400">
                  {tx("New here?")}{" "}
                  <a href="/signup" className="text-shield-400 hover:text-shield-300 font-medium">{tx("Create an account")}</a>
                </p>
              )}

              {/* Footer */}
              <div className="mt-4 flex items-center justify-between text-xs text-slate-600">
                <a href="/terms" className="hover:text-slate-400">{tx("Terms")}</a>
                {branding?.contact_email
                  ? <a href={`mailto:${branding.contact_email}`} className="hover:text-slate-400">{branding.contact_email}</a>
                  : <span>{tx("Contact your administrator for access")}</span>}
              </div>
            </div>
          )}
        </div>

        {branding?.show_powered_by && (
          <p className="text-center text-slate-700 text-xs mt-4">{tx("Powered by OpenOptOut")}</p>
        )}
      </div>
    </div>
  )
}
