import { useEffect, useState } from 'react'
import { Link2, ExternalLink, ChevronDown, ChevronRight, Search, CheckCircle2, AlertTriangle } from 'lucide-react'
import api from '../api'
import WebSearchResults from './WebSearchResults'

const inp = 'w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-shield-500'

// "Find your listings": ready-made searches from the member's identity vault,
// and a box to paste a listing someone found. Searches open in the person's own
// browser; OpenOptOut never visits them or the pasted address.
export default function FindListings({ memberId, memberName, onAdded }) {
  const [plan, setPlan] = useState(null)
  const [open, setOpen] = useState({ web: true, brokers: false })
  const [url, setUrl] = useState('')
  const [preview, setPreview] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setPlan(null); setResult(null); setError(''); setUrl(''); setPreview(null)
    if (!memberId) return
    api.get(`/listings/plan/${memberId}`).then(r => setPlan(r.data)).catch(() => setPlan({ queries: [], brokers: [] }))
  }, [memberId])

  // Show which site we'd match as the person types/pastes.
  useEffect(() => {
    setPreview(null)
    if (!url.trim() || url.trim().length < 8) return
    const t = setTimeout(() => {
      api.post('/listings/resolve', { url }).then(r => setPreview(r.data)).catch(() => setPreview(null))
    }, 400)
    return () => clearTimeout(t)
  }, [url])

  const add = async (e) => {
    e.preventDefault()
    setError(''); setResult(null); setBusy(true)
    try {
      const { data } = await api.post(`/listings/${memberId}`, { url })
      setResult(data); setUrl(''); setPreview(null)
      onAdded && onAdded()
    } catch (err) {
      setError(err.response?.data?.detail || "Couldn't add that listing. Please check the address and try again.")
    } finally { setBusy(false) }
  }

  if (!memberId) return null
  const Toggle = ({ k, children }) => (
    <button type="button" onClick={() => setOpen(o => ({ ...o, [k]: !o[k] }))} aria-expanded={open[k]}
      className="flex items-center gap-1.5 text-slate-200 font-medium text-sm">
      {open[k] ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}{children}
    </button>
  )

  return (
    <section aria-labelledby="find-listings" className="mb-6 p-4 rounded-xl border border-slate-700/50 bg-slate-800/60">
      <h2 id="find-listings" className="text-white font-medium flex items-center gap-2">
        <Search size={16} className="text-shield-500" aria-hidden="true" /> Find your listings
      </h2>
      <p className="text-slate-400 text-sm mt-1 mb-4">
        These searches use {memberName ? `${memberName}'s` : 'your'} saved names, phone numbers and addresses.
        They open in your browser. If you find a page about {memberName || 'you'}, copy its web address and paste it below.
      </p>

      <form onSubmit={add} className="mb-4" aria-describedby="listing-help">
        <label htmlFor="listing-url" className="block text-sm text-slate-300 mb-1">Paste a page that shows {memberName ? `${memberName}'s` : 'your'} information</label>
        <div className="flex gap-2 flex-col sm:flex-row">
          <input id="listing-url" type="url" inputMode="url" className={inp} placeholder="https://www.example.com/people/jane-doe/..."
            value={url} onChange={e => setUrl(e.target.value)} required />
          <button type="submit" disabled={busy || !url.trim()}
            className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-shield-600 hover:bg-shield-500 text-white text-sm font-medium disabled:opacity-50 shrink-0">
            <Link2 size={14} aria-hidden="true" /> {busy ? 'Adding…' : 'Add to removals'}
          </button>
        </div>
        <p id="listing-help" className="text-xs text-slate-500 mt-1" aria-live="polite">
          {preview
            ? (preview.broker_name
                ? <>This is <span className="text-slate-300">{preview.broker_name}</span>{preview.note ? ` — ${preview.note}` : ''}.</>
                : <>OpenOptOut doesn't know {preview.domain} yet. You can still add it; it will go on your checklist.</>)
            : 'OpenOptOut works out which site it is from the address. It never visits the page.'}
        </p>
      </form>

      {result && (
        <p role="status" className={`mb-4 text-sm flex gap-2 ${result.state === 'new_broker' ? 'text-amber-200' : 'text-emerald-300'}`}>
          {result.state === 'new_broker' ? <AlertTriangle size={16} className="shrink-0 mt-0.5" aria-hidden="true" /> : <CheckCircle2 size={16} className="shrink-0 mt-0.5" aria-hidden="true" />}
          {result.message}
        </p>
      )}
      {error && <p role="alert" className="mb-4 text-sm text-red-300">{error}</p>}

      {!plan ? <p className="text-slate-500 text-sm">Loading searches…</p> : (
        <>
          <div className="mb-3">
            <Toggle k="web">Search the web ({plan.queries.length})</Toggle>
            {open.web && (
              plan.queries.length === 0
                ? <p className="text-slate-400 text-sm mt-2">Add names, phone numbers or addresses on the Your details page to get searches here.</p>
                : <ul className="mt-2 divide-y divide-slate-700/40">
                    {plan.queries.map(q => (
                      <li key={q.query} className="py-2 flex items-start justify-between gap-3 flex-wrap">
                        <div className="min-w-0">
                          <div className="text-sm text-slate-200">{q.label}</div>
                          <div className="text-xs text-slate-500 break-all">{q.query}</div>
                        </div>
                        <div className="flex gap-3 text-sm shrink-0">
                          {Object.entries(q.links).map(([engine, href]) => (
                            <a key={engine} href={href} target="_blank" rel="noopener noreferrer"
                              className="text-shield-400 hover:text-shield-300 flex items-center gap-1"
                              aria-label={`Search ${engine} for ${q.label.toLowerCase()} (opens a new tab)`}>
                              <ExternalLink size={12} aria-hidden="true" />{engine === 'duckduckgo' ? 'DuckDuckGo' : engine[0].toUpperCase() + engine.slice(1)}
                            </a>
                          ))}
                        </div>
                      </li>
                    ))}
                  </ul>
            )}
          </div>
          <div>
            <Toggle k="brokers">Search each broker site ({plan.brokers.length})</Toggle>
            {open.brokers && (
              <ul className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-6">
                {plan.brokers.map(b => (
                  <li key={b.broker_id} className="py-1.5 flex items-center justify-between gap-2 border-b border-slate-700/30">
                    <span className="text-sm text-slate-200 truncate">{b.broker_name}</span>
                    <a href={b.search_url} target="_blank" rel="noopener noreferrer"
                      className="text-shield-400 hover:text-shield-300 text-sm flex items-center gap-1 shrink-0"
                      aria-label={`Search ${b.broker_name} (opens a new tab)`}>
                      <ExternalLink size={12} aria-hidden="true" />{b.kind === 'broker_search' ? 'Search site' : 'Search web'}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}

      <WebSearchResults memberId={memberId} memberName={memberName} onAdded={onAdded} />
    </section>
  )
}
