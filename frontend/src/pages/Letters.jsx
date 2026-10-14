import { useCallback, useEffect, useMemo, useState } from 'react'
import { FileText, Eye, X, AlertTriangle, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import api from '../api'
import { tx, txn, txr, activeLanguage } from '../i18n/tx'

// Opt-out letters: the wording sent to brokers by email. Each letter is a
// plugin (Plugins page: add, replace or turn one off). Here an admin reads
// them, previews them with made-up details, and picks a different letter for
// a broker or parent company when the automatic choice isn't right.

const card = 'bg-slate-800 rounded-xl border border-slate-700/50 p-4 mb-4'
const sel = 'bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-200 max-w-full'

const SOURCE = {
  admin:      () => tx("Chosen here"),
  addon:      () => tx("Chosen by the broker's add-on"),
  addon_text: () => tx("The broker's add-on has its own wording"),
  automatic:  () => tx("Automatic"),
}

function displayNames(type) {
  const lang = activeLanguage() === 'pirate' ? 'en' : activeLanguage()
  try { return new Intl.DisplayNames([lang], { type }) } catch { return null }
}

function placeName(code, regions) {
  if (code === '*') return tx("Any other country")
  if (code === 'EU') return tx("European Union")
  if (code === 'EEA') return tx("European Economic Area")
  const [c, sub] = String(code).split('-')
  let name = c
  try { name = regions?.of(c === 'UK' ? 'GB' : c) || c } catch { /* code as is */ }
  return sub ? `${name} (${sub})` : name
}

function Preview({ letter, onClose }) {
  const [lang, setLang] = useState('')
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const languages = displayNames('language')
  useEffect(() => {
    setErr('')
    api.get(`/letters/${letter.id}/preview`, { params: { language: lang } })
      .then(r => setData(r.data)).catch(e => setErr(e.response?.data?.detail || tx("Couldn't show the letter.")))
  }, [letter.id, lang])
  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-2 md:p-6" role="dialog" aria-modal="true" aria-labelledby="lp-h">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-3xl max-h-[92vh] overflow-y-auto p-5">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <h2 id="lp-h" className="text-white font-semibold">{letter.title}</h2>
            <p className="text-slate-400 text-xs mt-0.5">{tx("Filled in with made-up details (Jordan Example). This is exactly what a broker would get.")}</p>
          </div>
          <button onClick={onClose} aria-label={tx("Close")} className="p-1.5 text-slate-400 hover:text-white"><X size={18} /></button>
        </div>
        {letter.languages.length > 1 && (
          <div className="mb-3">
            <label htmlFor="lp-lang" className="text-slate-400 text-xs me-2">{tx("Language")}</label>
            <select id="lp-lang" className={sel} value={lang || data?.language || ''} onChange={e => setLang(e.target.value)}>
              {letter.languages.map(l => <option key={l} value={l}>{languages?.of(l) || l}</option>)}
            </select>
          </div>
        )}
        {err && <p role="alert" className="text-red-300 text-sm">{err}</p>}
        {data && (
          <div lang={data.language} dir="auto">
            <p className="text-slate-400 text-xs">{tx("Subject")}</p>
            <p className="text-slate-100 text-sm mb-3">{data.subject}</p>
            <pre className="whitespace-pre-wrap text-slate-200 text-sm bg-slate-950 border border-slate-800 rounded-lg p-3" style={{ fontFamily: 'inherit' }}>{data.body}</pre>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Letters() {
  const [data, setData] = useState(null)
  const [msg, setMsg] = useState('')
  const [preview, setPreview] = useState(null)
  const [tab, setTab] = useState('brokers')
  const [filter, setFilter] = useState('')
  const regions = useMemo(() => displayNames('region'), [])
  const languages = useMemo(() => displayNames('language'), [])

  const load = useCallback(() => {
    api.get('/letters').then(r => setData(r.data)).catch(e => setMsg(e.response?.data?.detail || tx("Couldn't load the letters.")))
  }, [])
  useEffect(() => { load() }, [load])

  const byId = useMemo(() => Object.fromEntries((data?.letters || []).map(l => [l.id, l])), [data])
  const title = id => byId[id]?.title || id

  const assign = async (row, letterId) => {
    setMsg('')
    try {
      const { data: updated } = await api.put('/letters/assign', { kind: row.kind, id: row.id, letter_id: letterId })
      setData(d => ({ ...d, [row.kind === 'broker' ? 'brokers' : 'parents']: d[row.kind === 'broker' ? 'brokers' : 'parents'].map(r => r.id === row.id ? updated : r) }))
      setMsg(tx("Saved. {name} now gets: {letter}.", { name: row.name, letter: title(updated.uses) || tx("its add-on's own wording") }))
    } catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't save that.")) }
  }

  if (!data) return <div className="p-6 text-slate-400 text-sm">{msg || tx("Loading…")}</div>

  const rows = (tab === 'brokers' ? data.brokers : data.parents)
    .filter(r => !filter || r.name.toLowerCase().includes(filter.toLowerCase()))
  const usable = data.letters.filter(l => l.enabled)

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2"><FileText size={18} aria-hidden="true" />{" "}{tx("Opt-out letters")}</h1>
      <p className="text-slate-400 text-sm mt-1 mb-4">{tx("The wording OpenOptOut emails to brokers. Each broker gets the letter for the law where it is, unless you pick a different one below.")}</p>

      <div className="flex items-start gap-2 px-3 py-2.5 mb-4 bg-amber-900/20 border border-amber-800 rounded-lg">
        <AlertTriangle size={14} className="text-amber-300 shrink-0 mt-0.5" aria-hidden="true" />
        <p className="text-amber-200 text-xs">{tx("Every built-in letter is a draft that no lawyer has reviewed yet. Read a letter before relying on it, and see each letter's notes for what a lawyer should check.")}</p>
      </div>
      {msg && <p role="status" className="text-slate-200 text-sm mb-3">{msg}</p>}

      <section aria-labelledby="h-letters" className={card}>
        <h2 id="h-letters" className="text-white font-medium mb-1">{tx("Letters")}</h2>
        <p className="text-slate-400 text-xs mb-3">
          {txr("Each letter is a plugin. Add your own, replace a built-in one, or turn one off on the <0>Plugins page</0>.", [<Link to="/plugins" className="text-shield-300 hover:underline" />])}
        </p>
        <ul className="space-y-2">
          {data.letters.map(l => (
            <li key={l.id} className={`rounded-lg border border-slate-700 bg-slate-900/50 p-3 ${l.enabled ? '' : 'opacity-60'}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-slate-100 text-sm font-medium">{l.title}</p>
                  <p className="text-slate-400 text-xs">{l.law}</p>
                  <div className="flex flex-wrap gap-1.5 mt-1.5 text-[11px]">
                    <span className={`px-1.5 py-0.5 rounded border ${l.review_status === 'reviewed' ? 'text-emerald-300 border-emerald-700' : 'text-amber-300 border-amber-700'}`}>
                      {l.review_status === 'reviewed' ? tx("Reviewed by a lawyer") : tx("Draft")}</span>
                    <span className="px-1.5 py-0.5 rounded border text-slate-300 border-slate-600">{l.built_in ? tx("Built in") : tx("Added")}</span>
                    {!l.enabled && <span className="px-1.5 py-0.5 rounded border text-slate-300 border-slate-600">{tx("Turned off")}</span>}
                    {l.deadline_days > 0 && <span className="px-1.5 py-0.5 rounded border text-slate-300 border-slate-600">{txn(l.deadline_days, "Answer due in {n} day", "Answer due in {n} days")}</span>}
                  </div>
                  <p className="text-slate-400 text-xs mt-1.5">
                    {tx("For:")}{" "}{[...new Set((l.jurisdictions.length ? l.jurisdictions : ['*']).map(c => placeName(c, regions)))].slice(0, 6).join(', ')}
                    {l.jurisdictions.length > 6 ? ` ${tx("+{v} more", { v: l.jurisdictions.length - 6 })}` : ''}
                    {l.residents_of?.length ? ` · ${tx("people living in: {v}", { v: l.residents_of.join(', ') })}` : ''}
                  </p>
                  <p className="text-slate-400 text-xs">{tx("Languages:")}{" "}{l.languages.map(c => languages?.of(c) || c).join(', ')}</p>
                  <p className="text-slate-500 text-xs">{txn(l.used_by, "Used for {n} broker or parent company", "Used for {n} brokers and parent companies")}</p>
                </div>
                <button onClick={() => setPreview(l)} className="px-2.5 py-1.5 text-xs text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-700 flex items-center gap-1.5">
                  <Eye size={13} aria-hidden="true" />{tx("Preview")}</button>
              </div>
              {l.review_note && (
                <details className="mt-2">
                  <summary className="text-slate-400 text-xs cursor-pointer">{tx("What a lawyer should check")}</summary>
                  <p className="text-slate-400 text-xs mt-1" dir="ltr" lang="en">{l.review_note}</p>
                </details>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="h-assign" className={card}>
        <h2 id="h-assign" className="text-white font-medium mb-1">{tx("Which letter each broker gets")}</h2>
        <p className="text-slate-400 text-xs mb-3">{tx("Automatic picks the letter for the law where the broker is, and for US brokers, where the person lives. Pick a letter to send that one instead, whatever the broker's add-on says.")}</p>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <div role="tablist" aria-label={tx("Show")} className="flex gap-1">
            {[['brokers', tx("Brokers")], ['parents', tx("Parent companies")]].map(([k, label]) => (
              <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                className={`px-3 py-1.5 text-sm rounded-lg border ${tab === k ? 'border-shield-600 text-shield-200 bg-shield-900/20' : 'border-slate-700 text-slate-300 hover:bg-slate-700'}`}>{label}</button>
            ))}
          </div>
          <div className="relative ms-auto">
            <Search size={13} className="absolute start-2.5 top-2.5 text-slate-500" aria-hidden="true" />
            <label htmlFor="lt-filter" className="sr-only">{tx("Filter by name")}</label>
            <input id="lt-filter" value={filter} onChange={e => setFilter(e.target.value)} placeholder={tx("Filter by name")}
              className="bg-slate-900 border border-slate-700 rounded-lg ps-8 pe-3 py-1.5 text-sm text-slate-200" />
          </div>
        </div>
        {rows.length === 0 ? <p className="text-slate-400 text-sm">{tx("Nothing to show.")}</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-start text-slate-400 text-xs">
                <th scope="col" className="py-1.5 pe-3 font-medium text-start">{tab === 'brokers' ? tx("Broker") : tx("Parent company")}</th>
                <th scope="col" className="py-1.5 pe-3 font-medium text-start">{tx("Where")}</th>
                <th scope="col" className="py-1.5 font-medium text-start">{tx("Letter")}</th>
              </tr></thead>
              <tbody>
                {rows.map(r => {
                  return (
                    <tr key={`${r.kind}-${r.id}`} className="border-t border-slate-700/60 align-top">
                      <td className="py-2 pe-3 text-slate-200" dir="auto">{r.name}</td>
                      <td className="py-2 pe-3 text-slate-400 text-xs">{placeName(r.jurisdiction, regions)}</td>
                      <td className="py-2">
                        <label htmlFor={`lt-${r.kind}-${r.id}`} className="sr-only">{tx("Letter for {name}", { name: r.name })}</label>
                        <select id={`lt-${r.kind}-${r.id}`} className={sel} value={r.chosen} onChange={e => assign(r, e.target.value)}>
                          <option value="">{r.automatic_source === 'addon_text' ? tx("Automatic: the add-on's own wording")
                            : tx("Automatic: {letter}", { letter: title(r.automatic) })}</option>
                          {usable.map(l => <option key={l.id} value={l.id}>{l.title}</option>)}
                        </select>
                        <p className="text-slate-500 text-xs mt-1">
                          {(SOURCE[r.source] || SOURCE.automatic)()}
                          {!r.chosen && r.by_state?.length > 0 && ` · ${tx("people living in a covered state get: {letter}", { letter: r.by_state.map(title).join(', ') })}`}
                        </p>
                        {r.missing && <p className="text-amber-300 text-xs mt-1">{tx("The letter picked for this one ({v}) isn't available, so the automatic one is used.", { v: r.missing })}</p>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {preview && <Preview letter={preview} onClose={() => setPreview(null)} />}
    </div>
  )
}
