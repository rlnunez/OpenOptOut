import { useEffect, useState } from 'react'
import { ScrollText, AlertTriangle, ExternalLink } from 'lucide-react'
import api from '../api'
import Markdown from '../components/Markdown'
import { LimitsText, NoticeText } from '../components/TermsGate'
import { tx, txn } from '../i18n/tx'
import { fmtDate } from '../i18n/format'

// Admin → Terms (super admins). The terms the people running this server
// offer to everyone who signs in (backend/core/terms.py). Saving changes asks
// everyone to accept them again.
export default function Terms() {
  const [cfg, setCfg] = useState(null)
  const [form, setForm] = useState({ operator: '', contact: '', text: '', enabled: false })
  const [preview, setPreview] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api.get('/terms/settings').then(r => {
    setCfg(r.data)
    setForm({ operator: r.data.operator || r.data.defaults.operator, contact: r.data.contact || r.data.defaults.contact,
              text: r.data.text, enabled: r.data.enabled })
  }).catch(e => setErr(e.response?.data?.detail || tx("Couldn't load the terms.")))
  useEffect(() => { load() }, [])

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const useTemplate = async () => {
    if (form.text && !confirm(tx("Replace what's in the box with the starting draft?"))) return
    const r = await api.get('/terms/template', { params: { operator: form.operator, contact: form.contact } })
    set('text', r.data.text)
  }
  const save = async (enabled) => {
    setBusy(true); setErr(''); setMsg('')
    try {
      const before = cfg?.version
      const r = await api.put('/terms/settings', { ...form, enabled })
      setCfg(r.data); setForm(f => ({ ...f, enabled: r.data.enabled }))
      setMsg(!r.data.enabled ? tx("Saved. The terms are turned off, so nobody is asked to accept them.")
        : r.data.version !== before ? tx("Saved. Everyone will be asked to accept the new terms the next time they sign in.")
        : tx("Saved. Nothing people see changed, so nobody is asked again."))
    } catch (e) { setErr(e.response?.data?.detail || tx("Couldn't save the terms.")) }
    finally { setBusy(false) }
  }

  if (!cfg) return <div className="p-6 text-slate-500 text-sm">{err || tx("Loading…")}</div>
  const todo = (form.text.match(/\[(?:Your organization|how to reach you)\]|\[(?:Say|Add) [^\]]*\]/g) || [])
  const field = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-hidden focus:border-shield-500"

  return (
    <div className="p-4 md:p-6 max-w-4xl space-y-5">
      <div>
        <h1 className="text-white text-xl font-semibold flex items-center gap-2"><ScrollText size={20} aria-hidden="true" />{tx("Terms")}</h1>
        <p className="text-slate-400 text-sm mt-1">{tx("What people are told before they use OpenOptOut here. Everything on this page is a draft that a lawyer hasn't reviewed yet; have yours checked before you rely on it.")}</p>
      </div>

      <section className="bg-slate-800 rounded-xl border border-slate-700/50 p-4 space-y-3">
        <h2 className="text-white font-medium">{tx("Your terms")}</h2>
        <p className="text-slate-400 text-sm">{tx("If you run OpenOptOut for other people, like a library's patrons, you're the one offering it to them. Write the terms you offer; when they're turned on, everyone is asked to accept them when they sign in, and again whenever you change them.")}</p>
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="block text-xs text-slate-400">{tx("Who runs this service")}
            <input value={form.operator} onChange={e => set('operator', e.target.value)} maxLength={200} className={`${field} mt-1`}
              placeholder={tx("e.g. Riverside Public Library")} />
          </label>
          <label className="block text-xs text-slate-400">{tx("How to reach you")}
            <input value={form.contact} onChange={e => set('contact', e.target.value)} maxLength={200} className={`${field} mt-1`}
              placeholder={tx("e.g. privacy@example.org")} />
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={useTemplate} className="px-3 py-1.5 text-sm border border-slate-600 rounded-lg text-slate-200 hover:bg-slate-700">{tx("Start from the draft")}</button>
          <button onClick={() => setPreview(p => !p)} aria-pressed={preview} className="px-3 py-1.5 text-sm border border-slate-600 rounded-lg text-slate-200 hover:bg-slate-700">
            {preview ? tx("Edit") : tx("Preview")}</button>
          <span className="text-xs text-slate-500">{tx("Headings start with ##, list items with -. Links look like [text](https://…).")}</span>
        </div>
        {preview
          ? <div className="border border-slate-700 rounded-lg p-3 bg-slate-950/40 text-sm text-slate-300"><Markdown source={form.text} /></div>
          : <textarea value={form.text} onChange={e => set('text', e.target.value)} rows={18} aria-label={tx("Your terms")}
              className={`${field} font-mono text-xs leading-relaxed`} />}
        {todo.length > 0 && (
          <p className="flex items-start gap-1.5 text-amber-300 text-sm"><AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
            {txn(todo.length, "{n} note in square brackets still needs filling in, like {first}. The terms can't be turned on until it's done.", "{n} notes in square brackets still need filling in, like {first}. The terms can't be turned on until they're done.", { first: todo[0] })}</p>
        )}
        {err && <p role="alert" className="text-red-400 text-sm">{err}</p>}
        {msg && <p role="status" className="text-emerald-400 text-sm">{msg}</p>}
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => save(true)} disabled={busy || !form.text.trim() || todo.length > 0}
            className="px-4 py-2 bg-shield-600 hover:bg-shield-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">
            {cfg.enabled ? tx("Save") : tx("Save and turn on")}</button>
          {cfg.enabled
            ? <button onClick={() => save(false)} disabled={busy} className="px-3 py-2 text-sm text-slate-300 hover:text-white">{tx("Turn off")}</button>
            : <button onClick={() => save(false)} disabled={busy} className="px-3 py-2 text-sm text-slate-300 hover:text-white">{tx("Save without turning on")}</button>}
          <span className="text-xs text-slate-400">
            {cfg.enabled
              ? tx("On. Version {v}, changed {date}. Accepted by {accepted} of {people} people who sign in.",
                  { v: cfg.version, date: cfg.updated_at ? fmtDate(cfg.updated_at) : '—', accepted: cfg.counts.accepted, people: cfg.counts.people })
              : tx("Off. Nobody is asked to accept them.")}
          </span>
        </div>
        {cfg.terms_url && (
          <p className="text-xs text-slate-400 flex items-center gap-1">
            <ExternalLink size={12} aria-hidden="true" />
            {tx("Branding also links to terms on another site: {url}. The Terms link on the sign-in page goes there when yours are off.", { url: cfg.terms_url })}
          </p>
        )}
      </section>

      <section className="bg-slate-800 rounded-xl border border-slate-700/50 p-4 space-y-3">
        <h2 className="text-white font-medium">{tx("What everyone is told anyway")}</h2>
        <p className="text-slate-400 text-sm">{tx("These come with OpenOptOut and are shown whether or not your own terms are on. They're translated into every language.")}</p>
        <details className="text-sm"><summary className="cursor-pointer text-slate-200">{tx("Admins, at first sign-in: what OpenOptOut can and can't do")}</summary>
          <div className="mt-3"><LimitsText /></div></details>
        <details className="text-sm"><summary className="cursor-pointer text-slate-200">{tx("Everyone else, at first sign-in: how OpenOptOut works for them")}</summary>
          <div className="mt-3"><NoticeText operator={form.operator} /></div></details>
        <p className="text-slate-400 text-sm">{tx("And when someone adds a person without their own sign-in, they confirm they're allowed to act for them: the person agreed, or they're the parent or legal guardian.")}</p>
      </section>
    </div>
  )
}

// /terms, public: what the sign-in page's Terms link opens.
export function PublicTerms() {
  const [t, setT] = useState(null)
  useEffect(() => { api.get('/terms/public').then(r => setT(r.data)).catch(() => setT({})) }, [])
  if (!t) return <div className="min-h-screen bg-slate-950 flex items-center justify-center"><p className="text-slate-500 text-sm">{tx("Loading…")}</p></div>
  return (
    <main id="main-content" className="min-h-screen bg-slate-950 p-4 md:p-8">
      <div className="max-w-3xl mx-auto bg-slate-900 border border-slate-700 rounded-2xl p-6 space-y-4">
        <h1 className="text-white text-xl font-semibold">{t.operator ? tx("Terms from {operator}", { operator: t.operator }) : tx("Terms for this server")}</h1>
        {t.enabled ? (
          <>
            {t.updated_at && <p className="text-xs text-slate-500">{tx("Last changed {date}", { date: fmtDate(t.updated_at) })}</p>}
            <div className="text-sm text-slate-300"><Markdown source={t.text} /></div>
          </>
        ) : t.terms_url ? (
          <p className="text-sm text-slate-300"><a href={t.terms_url} className="text-shield-400 hover:underline" rel="noopener noreferrer">{t.operator ? tx("Read the terms on {operator}'s site", { operator: t.operator }) : tx("Read the terms")}</a></p>
        ) : (
          <p className="text-sm text-slate-400">{tx("The people who run this server haven't published their own terms. Here's how OpenOptOut works:")}</p>
        )}
        {!t.enabled && <NoticeText operator={t.operator} />}
        <p className="text-xs text-slate-500"><a href="/login" className="hover:text-slate-300">{tx("Back to sign in")}</a></p>
      </div>
    </main>
  )
}
