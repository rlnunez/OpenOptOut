import { useEffect, useState } from 'react'
import { Snowflake, Printer, Copy, Check, ExternalLink } from 'lucide-react'
import api from '../api'

// Credit freeze letters. Built fresh from the person's saved details each time;
// Social Security numbers are never asked for or saved — the letter leaves a
// blank to write in by hand after printing.

function printLetter(title, text) {
  const w = window.open('', '_blank')
  if (!w) return false
  const esc = s => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))
  w.document.write(`<!doctype html><title>${esc(title)}</title>
    <body style="font:12pt/1.5 Georgia,serif;max-width:6.5in;margin:1in auto;white-space:pre-wrap">${esc(text)}</body>`)
  w.document.close(); w.focus(); w.print()
  return true
}

function LetterCard({ l, person }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try { await navigator.clipboard.writeText(l.letter); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { /* ignore */ }
  }
  return (
    <section aria-labelledby={`h-${l.key}`} className="bg-slate-800 rounded-xl border border-slate-700/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
        <h2 id={`h-${l.key}`} className="text-white font-medium">{l.bureau}</h2>
        <div className="flex gap-2">
          <button onClick={() => printLetter(`${l.bureau} freeze — ${person}`, l.letter)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700">
            <Printer size={13} aria-hidden="true" /> Print letter
          </button>
          <button onClick={copy}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-600 rounded-lg hover:bg-slate-700">
            {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />} {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>
      <p className="text-slate-300 text-sm mb-3">{l.note}</p>
      <div className="grid gap-3 sm:grid-cols-2 text-sm mb-3">
        <div>
          <p className="text-slate-400 text-xs uppercase tracking-wide mb-1">Mail it to</p>
          <address className="not-italic text-slate-200">{l.mail_to.map(x => <div key={x}>{x}</div>)}</address>
        </div>
        <div>
          <p className="text-slate-400 text-xs uppercase tracking-wide mb-1">Put copies of these in the envelope</p>
          <ul className="list-disc pl-5 text-slate-300 space-y-0.5">{l.enclose.map(x => <li key={x}>{x}</li>)}</ul>
        </div>
      </div>
      <div className="flex flex-wrap gap-3 text-sm">
        {l.online && <a href={l.online} target="_blank" rel="noopener noreferrer" className="text-shield-300 hover:underline inline-flex items-center gap-1">Do it online <ExternalLink size={12} aria-hidden="true" /></a>}
        {l.form && <a href={l.form} target="_blank" rel="noopener noreferrer" className="text-shield-300 hover:underline inline-flex items-center gap-1">Their form to include <ExternalLink size={12} aria-hidden="true" /></a>}
        <span className="text-slate-400">Phone: {l.phone}</span>
      </div>
      <details className="mt-3">
        <summary className="text-slate-400 text-sm cursor-pointer">Read the letter</summary>
        <pre className="mt-2 whitespace-pre-wrap text-slate-300 text-sm bg-slate-900 rounded-lg p-3 font-serif">{l.letter}</pre>
      </details>
    </section>
  )
}

export default function CreditFreeze() {
  const [members, setMembers] = useState([])
  const [who, setWho] = useState('')
  const [parent, setParent] = useState('')
  const [kind, setKind] = useState('')
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/family').then(r => {
      setMembers(r.data)
      if (r.data.length) setWho(String(r.data[0].id))
    }).catch(() => setError("Couldn't load your family. Please refresh the page."))
  }, [])

  useEffect(() => {
    if (!who) return
    const params = {}
    if (kind) params.kind = kind
    if (parent) params.requester_id = parent
    setError('')
    api.get(`/credit-freeze/${who}`, { params })
      .then(r => setData(r.data))
      .catch(e => setError(e.response?.data?.detail || "Couldn't build the letters."))
  }, [who, parent, kind])

  const minor = data?.kind === 'minor'
  const sel = 'bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-hidden focus:border-shield-500'

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2"><Snowflake size={18} aria-hidden="true" /> Freeze credit</h1>
      <p className="text-slate-400 text-sm mt-1 mb-4 max-w-2xl">
        A credit freeze stops anyone from opening new credit in someone's name. It's free, it doesn't hurt a credit
        score, and you can lift it any time. Do it with all three bureaus below. Children under 16 can only be
        frozen by a parent or guardian, by mail, and it's one of the best ways to stop child identity theft.
      </p>

      <div className="flex flex-wrap gap-3 items-end mb-4">
        <div>
          <label htmlFor="cf-who" className="block text-slate-300 text-sm mb-1">Who is it for?</label>
          <select id="cf-who" className={sel} value={who} onChange={e => { setWho(e.target.value); setKind('') }}>
            {members.map(m => <option key={m.id} value={m.id}>{m.full_name}{m.age != null ? ` (${m.age})` : ''}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="cf-kind" className="block text-slate-300 text-sm mb-1">Adult or child?</label>
          <select id="cf-kind" className={sel} value={kind || data?.kind || ''} onChange={e => setKind(e.target.value)}>
            <option value="adult">Adult (16 or older)</option>
            <option value="minor">Child under 16</option>
          </select>
        </div>
        {minor && (
          <div>
            <label htmlFor="cf-parent" className="block text-slate-300 text-sm mb-1">Parent or guardian sending it</label>
            <select id="cf-parent" className={sel} value={parent} onChange={e => setParent(e.target.value)}>
              <option value="">I'll write it in</option>
              {members.filter(m => String(m.id) !== who).map(m => <option key={m.id} value={m.id}>{m.full_name}</option>)}
            </select>
          </div>
        )}
      </div>

      <div className="mb-4 px-3 py-2.5 rounded-lg border border-amber-700/60 bg-amber-950/20 text-amber-200 text-sm" role="note">
        We never save Social Security numbers. The letters leave a blank. Write the number in by hand after printing.
        {minor && ' Don\'t have a birthday saved? Add it on Your details, or write it in.'}
      </div>

      {error && <p role="alert" className="text-red-400 text-sm mb-4">{error}</p>}

      {data && (
        <div className="space-y-4">
          {data.letters.map(l => <LetterCard key={l.key} l={l} person={data.person} />)}
          <section aria-labelledby="h-other" className="bg-slate-800 rounded-xl border border-slate-700/50 p-4">
            <h2 id="h-other" className="text-white font-medium mb-1">Smaller agencies worth freezing too</h2>
            <p className="text-slate-400 text-sm mb-2">Banks, phone companies and insurers check these. Each is free to freeze.</p>
            <ul className="space-y-1.5 text-sm">
              {data.other_agencies.map(a => <li key={a.name}><span className="text-slate-200">{a.name}</span> <span className="text-slate-400">— {a.how}</span></li>)}
            </ul>
          </section>
          <p className="text-slate-500 text-xs">Bureau addresses last checked {data.checked}. Check the bureau's website if a letter comes back.</p>
        </div>
      )}
    </div>
  )
}
