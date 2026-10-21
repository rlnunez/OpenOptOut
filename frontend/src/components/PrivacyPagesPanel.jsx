import { useEffect, useState, useCallback } from 'react'
import { ShieldQuestion, ExternalLink, X, Check, RefreshCw } from 'lucide-react'
import api from '../api'
import { tx } from '../i18n/tx'
import { detailText } from '../errorMessage'

const KIND = {
  hosted_onetrust: 'OneTrust request form',
  hosted_trustarc: 'TrustArc request form',
  hosted_other: 'Hosted privacy form',
  request_form: 'Request form',
  optout_page: 'Opt-out page',
  policy: 'Privacy policy',
  email: 'Privacy email',
}

// Admin panel on the Brokers page: what the privacy-page finder found on
// brokers' own websites. Forms OpenOptOut can fill are used automatically;
// email addresses wait for an admin to approve them.
export default function PrivacyPagesPanel({ refreshKey }) {
  const [data, setData] = useState(null)
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    api.get('/privacy-pages').then(r => setData(r.data)).catch(() => setData({ pages: [] }))
  }, [])
  useEffect(() => { load() }, [load, refreshKey])
  useEffect(() => {
    if (!data?.running) return
    const t = setTimeout(load, 5000)
    return () => clearTimeout(t)
  }, [data, load])

  const act = async (p, what) => {
    setMsg('')
    try {
      const { data: d } = await api.post(`/privacy-pages/${p.id}/${what}`)
      if (d.message) setMsg(d.message)
      load()
    } catch (e) { setMsg(detailText(e) || tx("Couldn't save that. Please try again.")) }
  }

  if (!data) return null
  return (
    <section aria-labelledby="pp-h" className="mt-6 bg-slate-800 rounded-xl border border-slate-700/50 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 id="pp-h" className="text-slate-200 text-sm font-medium flex items-center gap-2">
          <ShieldQuestion size={15} className="text-shield-400" aria-hidden="true" />{" "}{tx("Privacy pages found on brokers' websites")}
        </h2>
        {data.running && <span className="text-xs text-slate-400 flex items-center gap-1" role="status"><RefreshCw size={12} className="animate-spin" aria-hidden="true" />{" "}{tx("Looking…")}</span>}
      </div>
      <p className="text-slate-400 text-xs mt-0.5">
        {tx("For brokers with no opt-out steps, OpenOptOut looks at their own website once a month (sending no personal data). Request forms it can fill are used automatically. Email addresses are only used after you approve them.")}
      </p>
      {msg && <p role="status" className="text-xs text-shield-300 mt-2">{msg}</p>}
      {data.pages.length === 0 ? (
        <p className="text-slate-500 text-sm mt-3">{tx("Nothing found yet. Use the search button next to a broker to look now.")}</p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-700/40">
          {data.pages.map(p => (
            <li key={p.id} className="py-2 flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <div className="text-sm text-slate-200">
                  <span className="font-medium">{p.broker_name}</span>
                  <span className="text-slate-400"> · {KIND[p.kind] || p.kind}</span>
                  {p.fillable && <span className="ms-2 text-[11px] text-emerald-300">{tx("filled automatically")}</span>}
                  {p.status === 'approved' && <span className="ms-2 text-[11px] text-emerald-300">{tx("approved")}</span>}
                </div>
                <div className="text-xs text-slate-500 break-all">{p.kind === 'email' ? p.url.replace('mailto:', '') : p.url}</div>
              </div>
              <div className="flex gap-2 shrink-0">
                {p.kind !== 'email' && (
                  <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-shield-400 hover:text-shield-300 text-xs flex items-center gap-1"
                    aria-label={tx("Open {broker_name}'s {v} in a new tab", { broker_name: p.broker_name, v: KIND[p.kind] || 'page' })}>
                    <ExternalLink size={12} aria-hidden="true" />{" "}{tx("Open")}
                  </a>
                )}
                {p.kind === 'email' && p.status !== 'approved' && (
                  <button onClick={() => act(p, 'approve-email')} className="text-emerald-300 hover:text-emerald-200 text-xs flex items-center gap-1">
                    <Check size={12} aria-hidden="true" />{" "}{tx("Use for email opt-outs")}
                  </button>
                )}
                <button onClick={() => act(p, 'dismiss')} className="text-slate-400 hover:text-red-300 text-xs flex items-center gap-1"
                  aria-label={tx("Dismiss this result for {broker_name}", { broker_name: p.broker_name })}>
                  <X size={12} aria-hidden="true" />{" "}{tx("Not it")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
