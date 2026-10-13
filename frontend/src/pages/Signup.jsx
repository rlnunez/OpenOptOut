import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ShieldCheck, Home, Mail, UserPlus, AlertTriangle } from 'lucide-react'
import api from '../api'
import { useAuth } from '../hooks/useAuth'
import { useBranding } from '../hooks/useBranding'
import { tx } from '../i18n/tx'

const inp = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"
const btn = "w-full py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"

function Field({ id, label, hint, children }) {
  return (
    <div>
      <label htmlFor={id} className="block text-slate-300 text-xs font-medium mb-1">{label}</label>
      {children}
      {hint && <p className="text-slate-500 text-xs mt-1">{hint}</p>}
    </div>
  )
}

function Card({ name, branding, children }) {
  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="flex flex-col items-center mb-6">
          {branding?.logo_url
            ? <img src={branding.logo_url} alt={name} className="h-12 object-contain mb-3" />
            : <ShieldCheck size={28} className="text-shield-500 mb-2" aria-hidden="true" />}
          <h1 className="text-white font-semibold text-lg">{tx("Create an account")}</h1>
          <p className="text-slate-500 text-xs mt-0.5">{name}</p>
        </div>
        <div className="bg-slate-900 rounded-2xl border border-slate-800 p-6">{children}</div>
        <p className="text-center text-slate-500 text-xs mt-4">
          {tx("Already have an account?")}{" "}
          <Link to="/login" className="text-shield-400 hover:text-shield-300">{tx("Sign in")}</Link>
        </p>
      </div>
    </div>
  )
}

// The server's reasons, in the person's language.
function addressMessage(data) {
  const byReason = {
    unit_needed: tx("Add your apartment or unit number."),
    unit_not_found: tx("We couldn't find that unit number at this address. Check it and try again."),
    not_found: tx("We couldn't find that address on the list of homes this service is for."),
    full: tx("This home already has as many accounts as this service allows."),
  }
  const unclear = {
    "Start the street address with the house or building number.": tx("Start the street address with the house or building number."),
    "Add the street name after the number.": tx("Add the street name after the number."),
    "Add the 5-digit ZIP code.": tx("Add the 5-digit ZIP code."),
  }
  return byReason[data.reason] || unclear[data.message] || data.message
}

// Public sign-up page (backend/routers/auth.py: /signup-info, /signup/address,
// /signup/email-code, /register). With the residents-only address check on,
// the home address comes first and must be on the community's list.
export default function Signup() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const { branding } = useBranding()
  const name = branding?.system_name || 'OpenOptOut'

  const [info, setInfo] = useState(null)
  const [step, setStep] = useState('address')
  const [addr, setAddr] = useState({ street: '', unit: '', city: '', state: '', zip: '' })
  const [addressToken, setAddressToken] = useState('')
  const [email, setEmail] = useState('')
  const [emailToken, setEmailToken] = useState('')
  const [form, setForm] = useState({ code: '', full_name: '', password: '', confirm: '', invite_code: '' })
  const [error, setError] = useState('')
  const [help, setHelp] = useState('')
  const [sentMsg, setSentMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get('/auth/signup-info').then(r => {
      setInfo(r.data)
      setStep(r.data.address_check ? 'address' : 'email')
    }).catch(() => setInfo({ signup: false }))
  }, [])

  const steps = info?.address_check ? ['address', 'email', 'details'] : ['email', 'details']
  const stepNo = steps.indexOf(step) + 1
  const setA = (k, v) => setAddr(a => ({ ...a, [k]: v }))
  const setF = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const checkAddress = async e => {
    e.preventDefault(); setError(''); setHelp(''); setBusy(true)
    try {
      const { data } = await api.post('/auth/signup/address', addr)
      if (data.ok) { setAddressToken(data.token); setStep('email') }
      else { setError(addressMessage(data)); setHelp(data.help || '') }
    } catch (err) {
      setError(err.response?.status === 429 ? tx("Too many tries. Wait a minute and try again.")
        : (err.response?.data?.detail || tx("Couldn't check the address. Try again in a minute.")))
    } finally { setBusy(false) }
  }

  const sendCode = async e => {
    e.preventDefault(); setError(''); setBusy(true)
    try {
      const { data } = await api.post('/auth/signup/email-code', { email: email.trim() })
      setEmailToken(data.token); setSentMsg(tx("We sent a 6-digit code to that email. It expires in 15 minutes.")); setStep('details')
    } catch (err) {
      setError(err.response?.status === 429 ? tx("Too many tries. Wait a minute and try again.")
        : (err.response?.data?.detail || tx("Couldn't send the code. Check the email address and try again.")))
    } finally { setBusy(false) }
  }

  const create = async e => {
    e.preventDefault(); setError('')
    if (form.password.length < 8) { setError(tx("Use a password of at least 8 characters")); return }
    if (form.password !== form.confirm) { setError(tx("The two passwords don't match.")); return }
    setBusy(true)
    try {
      await api.post('/auth/register', {
        email: email.trim(), full_name: form.full_name, password: form.password,
        invite_code: form.invite_code || null,
        email_token: emailToken, email_code: form.code.trim(),
        address_token: addressToken || null,
      })
      await login(email.trim(), form.password)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || tx("Couldn't create the account. Check the details and try again."))
    } finally { setBusy(false) }
  }

  if (!info) return <Card name={name} branding={branding}><p className="text-slate-500 text-sm text-center">{tx("Loading…")}</p></Card>
  if (!info.signup) return (
    <Card name={name} branding={branding}><p className="text-slate-300 text-sm">{tx("This service doesn't take sign-ups here. Ask the people who run it how to join.")}</p></Card>
  )
  if (!info.can_email) return (
    <Card name={name} branding={branding}><p className="text-slate-300 text-sm">{tx("New accounts can't be made right now because this server can't send email yet. Please try again later, or ask the people who run it.")}</p></Card>
  )

  const errorBox = error && (
    <div role="alert" className="flex gap-2 items-start bg-red-900/20 border border-red-800/50 rounded-lg p-3 text-sm text-red-300">
      <AlertTriangle size={15} className="shrink-0 mt-0.5" aria-hidden="true" />
      <div>
        <p>{error}</p>
        {help && <p className="text-slate-300 mt-1">{tx("Questions? {help}", { help })}</p>}
      </div>
    </div>
  )

  return (
    <Card name={name} branding={branding}>
      <p className="text-shield-400 text-xs font-semibold mb-3">{tx("Step {n} of {total}", { n: stepNo, total: steps.length })}</p>

      {step === 'address' && (
        <form onSubmit={checkAddress} className="space-y-3">
          <div className="flex items-center gap-2 text-white text-sm font-semibold"><Home size={16} aria-hidden="true" />{tx("Your home address")}</div>
          <p className="text-slate-400 text-xs">{tx("This service is for people who live in our community. Enter the address where you live now.")}</p>
          <Field id="su-street" label={tx("Street address")}>
            <input id="su-street" className={inp} autoComplete="address-line1" required value={addr.street} onChange={e => setA('street', e.target.value)} placeholder={tx("e.g. 123 Main Street")} />
          </Field>
          <Field id="su-unit" label={tx("Apartment or unit (if you have one)")}>
            <input id="su-unit" className={inp} autoComplete="address-line2" value={addr.unit} onChange={e => setA('unit', e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field id="su-city" label={tx("City")}>
              <input id="su-city" className={inp} autoComplete="address-level2" value={addr.city} onChange={e => setA('city', e.target.value)} />
            </Field>
            <Field id="su-state" label={tx("State")}>
              <input id="su-state" className={inp} autoComplete="address-level1" value={addr.state} onChange={e => setA('state', e.target.value)} />
            </Field>
          </div>
          <Field id="su-zip" label={tx("ZIP code")}>
            <input id="su-zip" className={inp} autoComplete="postal-code" inputMode="numeric" required value={addr.zip} onChange={e => setA('zip', e.target.value)} />
          </Field>
          {errorBox}
          <button type="submit" disabled={busy} className={btn}>{busy ? tx("Checking…") : tx("Continue")}</button>
        </form>
      )}

      {step === 'email' && (
        <form onSubmit={sendCode} className="space-y-3">
          <div className="flex items-center gap-2 text-white text-sm font-semibold"><Mail size={16} aria-hidden="true" />{tx("Your email")}</div>
          {info.address_check && <p className="text-green-400 text-xs">{tx("Your address is on the list.")}</p>}
          <p className="text-slate-400 text-xs">{tx("We'll send a 6-digit code to this email to make sure it's yours.")}</p>
          <Field id="su-email" label={tx("Email")}>
            <input id="su-email" type="email" className={inp} autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} />
          </Field>
          {errorBox}
          <button type="submit" disabled={busy} className={btn}>{busy ? tx("Sending…") : tx("Send the code")}</button>
        </form>
      )}

      {step === 'details' && (
        <form onSubmit={create} className="space-y-3">
          <div className="flex items-center gap-2 text-white text-sm font-semibold"><UserPlus size={16} aria-hidden="true" />{tx("Finish your account")}</div>
          {sentMsg && <p className="text-slate-400 text-xs">{sentMsg}</p>}
          <Field id="su-code" label={tx("Code from the email")}>
            <input id="su-code" className={inp} inputMode="numeric" autoComplete="one-time-code" required value={form.code} onChange={e => setF('code', e.target.value)} />
          </Field>
          <Field id="su-name" label={tx("Your name")}>
            <input id="su-name" className={inp} autoComplete="name" required value={form.full_name} onChange={e => setF('full_name', e.target.value)} />
          </Field>
          <Field id="su-pw" label={tx("Password (min 8 characters)")}>
            <input id="su-pw" type="password" className={inp} autoComplete="new-password" required value={form.password} onChange={e => setF('password', e.target.value)} />
          </Field>
          <Field id="su-pw2" label={tx("Confirm password")}>
            <input id="su-pw2" type="password" className={inp} autoComplete="new-password" required value={form.confirm} onChange={e => setF('confirm', e.target.value)} />
          </Field>
          {info.invite_required && (
            <Field id="su-invite" label={tx("Invite code")}>
              <input id="su-invite" className={inp} required value={form.invite_code} onChange={e => setF('invite_code', e.target.value)} />
            </Field>
          )}
          {errorBox}
          <button type="submit" disabled={busy} className={btn}>{busy ? tx("Creating…") : tx("Create account")}</button>
          <button type="button" onClick={() => { setStep('email'); setError('') }} className="w-full text-slate-400 hover:text-slate-200 text-xs">
            {tx("Didn't get the code? Send it again")}
          </button>
        </form>
      )}
    </Card>
  )
}
