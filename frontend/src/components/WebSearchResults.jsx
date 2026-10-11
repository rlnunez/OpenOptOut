import { useEffect, useState, useCallback, useRef } from 'react'
import { Globe2, RefreshCw, Check, X, ExternalLink, ChevronDown, ChevronRight } from 'lucide-react'
import api from '../api'

const WHY = {
  phone: 'shows one of the saved phone numbers',
  address: 'shows a saved street address',
  email: 'shows a saved email address',
  'name+city': 'shows the name and city',
  name: 'shows the name',
}

// Results of the server-side web search for one family member: run it, then
// review what it found. Strong matches on known brokers were already added.
export default function WebSearchResults({ memberId, memberName, onAdded }) {
  const [status, setStatus] = useState(null)
  const [hits, setHits] = useState([])
  const [run, setRun] = useState({ running: false })
  const [msg, setMsg] = useState('')
  const [showAdded, setShowAdded] = useState(false)
  const timer = useRef(null)

  const load = useCallback(() => {
    if (!memberId) return
    api.get(`/web-search/hits/${memberId}`).then(r => {
      setHits(r.data.hits); setRun(r.data.run || { running: false })
      if (r.data.run?.running) { timer.current = setTimeout(load, 4000) }
      else if (r.data.run?.stats) {
        const st = r.data.run.stats
        setMsg(`Search finished: ${st.new} new page${st.new === 1 ? '' : 's'} found, ${st.added} added to removals automatically.`
          + (st.errors?.length ? ` Some searches failed: ${st.errors[0]}` : ''))
        onAdded && st.added && onAdded()
      } else if (r.data.run?.error) setMsg(r.data.run.error)
    }).catch(() => {})
  }, [memberId])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { api.get('/web-search/status').then(r => setStatus(r.data)).catch(() => setStatus({ available: false })) }, [])
  useEffect(() => { setMsg(''); load(); return () => clearTimeout(timer.current) }, [load])

  if (!status || !memberId) return null
  if (!status.available) {
    return <p className="text-xs text-slate-500 mt-3">Automatic web search isn't turned on. An administrator can set it up under Web search.</p>
  }

  const start = async () => {
    setMsg('')
    try { await api.post(`/web-search/run/${memberId}`); setRun({ running: true }); timer.current = setTimeout(load, 3000) }
    catch (e) { setMsg(e.response?.data?.detail || "Couldn't start the search.") }
  }
  const act = async (h, kind) => {
    try {
      if (kind === 'add') { const { data } = await api.post(`/web-search/hits/${h.id}/add`); setMsg(data.message); onAdded && onAdded() }
      else { await api.post(`/web-search/hits/${h.id}/dismiss`, { reason: 'not_me' }); setMsg("Got it — that page won't be shown again.") }
      load()
    } catch (e) { setMsg(e.response?.data?.detail || "Couldn't save that.") }
  }

  const review = hits.filter(h => h.status === 'new')
  const added = hits.filter(h => h.status === 'added')

  return (
    <div className="mt-5 pt-4 border-t border-slate-700/50">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-slate-200 font-medium text-sm flex items-center gap-2">
          <Globe2 size={15} className="text-shield-500" aria-hidden="true" /> Automatic web search
        </h3>
        <button onClick={start} disabled={run.running}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-shield-600 hover:bg-shield-500 text-white text-sm disabled:opacity-50">
          <RefreshCw size={13} className={run.running ? 'animate-spin' : ''} aria-hidden="true" />
          {run.running ? 'Searching…' : 'Search the web now'}
        </button>
      </div>
      <p className="text-xs text-slate-500 mt-1">{status.privacy_note}</p>
      {msg && <p role="status" className="text-sm text-shield-300 mt-2">{msg}</p>}

      {review.length > 0 && (
        <>
          <p className="text-sm text-slate-300 mt-3">Is this {memberName || 'you'}? ({review.length})</p>
          <ul className="mt-1 divide-y divide-slate-700/40">
            {review.map(h => (
              <li key={h.id} className="py-2.5 flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0 flex-1">
                  <a href={h.url} target="_blank" rel="noopener noreferrer" className="text-sm text-shield-300 hover:text-shield-200 flex items-center gap-1 break-all">
                    <ExternalLink size={12} className="shrink-0" aria-hidden="true" />{h.title || h.url}
                  </a>
                  <div className="text-xs text-slate-500">
                    {h.broker_name ? `${h.broker_name} · ` : `${h.domain} · `}
                    {h.strength === 'strong' ? 'Strong match: ' : h.strength === 'medium' ? 'Likely: ' : 'Possible: '}
                    {WHY[h.matched_on] || 'turned up in a search'}
                  </div>
                  {h.snippet && <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">{h.snippet}</p>}
                </div>
                <div className="flex gap-2 shrink-0">
                  <button onClick={() => act(h, 'add')} className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white text-xs"
                    aria-label={`That's ${memberName || 'me'}: add ${h.domain} to removals`}>
                    <Check size={13} aria-hidden="true" /> That's {memberName ? memberName.split(' ')[0] : 'me'}
                  </button>
                  <button onClick={() => act(h, 'dismiss')} className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-600 text-slate-300 text-xs"
                    aria-label={`Not ${memberName || 'me'}: hide this result`}>
                    <X size={13} aria-hidden="true" /> Not {memberName ? memberName.split(' ')[0] : 'me'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      {review.length === 0 && !run.running && hits.length > 0 && (
        <p className="text-sm text-slate-400 mt-3">Nothing waiting for review.</p>
      )}

      {added.length > 0 && (
        <div className="mt-3">
          <button type="button" onClick={() => setShowAdded(v => !v)} aria-expanded={showAdded} className="text-sm text-slate-300 flex items-center gap-1">
            {showAdded ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
            Added to removals ({added.length})
          </button>
          {showAdded && (
            <ul className="mt-1 text-xs text-slate-400 space-y-1">
              {added.map(h => <li key={h.id} className="break-all">{h.broker_name || h.domain} — {h.url}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
