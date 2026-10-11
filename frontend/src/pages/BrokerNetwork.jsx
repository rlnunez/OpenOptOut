import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Share2, Layers } from 'lucide-react'
import api from '../api'

const CONF = {
  strong: { label: 'Strong', cls: 'text-red-300', hint: '3 or more opt-out addresses' },
  likely: { label: 'Likely', cls: 'text-amber-300', hint: '2 opt-out addresses' },
  possible: { label: 'Possible', cls: 'text-slate-300', hint: '1 opt-out address' },
  unknown_sender: { label: "Can't tell who", cls: 'text-slate-500', hint: 'sent from a free email service' },
}
const ORDER = { aggregators_first: 'Aggregators first', priority: 'By priority', fifo: 'Oldest first', easy_first: 'Easiest first' }

// Admin: which brokers pass people's opt-out email addresses on, and which
// brokers feed others (opted out of first).
export default function BrokerNetwork() {
  const [share, setShare] = useState(null)
  const [agg, setAgg] = useState(null)
  useEffect(() => {
    api.get('/broker-network/sharing').then(r => setShare(r.data)).catch(() => setShare({ edges: [], counts: {} }))
    api.get('/broker-network/aggregators').then(r => setAgg(r.data)).catch(() => setAgg({ ranking: [] }))
  }, [])

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2 mb-1">
        <Share2 size={20} className="text-shield-500" aria-hidden="true" /> Data sharing
      </h1>
      <p className="text-slate-400 text-sm mb-5">
        Every opt-out gets its own email address. When mail reaches that address from a company it was never given to,
        the broker (or someone it works with) passed it on.
      </p>

      <section aria-labelledby="sh-h" className="mb-8">
        <h2 id="sh-h" className="text-white font-medium mb-2">Who passed addresses on</h2>
        {!share ? <p className="text-slate-500 text-sm">Loading…</p> : share.edges.length === 0 ? (
          <p className="text-slate-400 text-sm">No signs of sharing yet. This fills in as brokers reply to opt-outs and other mail arrives.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-700/60">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-slate-400 text-xs border-b border-slate-700/60">
                <th scope="col" className="px-3 py-2 font-normal">Given to</th>
                <th scope="col" className="px-3 py-2 font-normal">Mail came from</th>
                <th scope="col" className="px-3 py-2 font-normal">Evidence</th>
                <th scope="col" className="px-3 py-2 font-normal">How sure</th>
              </tr></thead>
              <tbody>
                {share.edges.map((e, i) => (
                  <tr key={i} className="border-t border-slate-700/30">
                    <td className="px-3 py-2 text-slate-200">{e.from_name}{e.from_type === 'parent' && <span className="text-slate-500 text-xs"> (company)</span>}</td>
                    <td className="px-3 py-2 text-slate-200">
                      {e.free_email ? <span className="text-slate-400">a {e.to_domain} account</span> : (e.to_name || e.to_domain)}
                      {e.to_broker_id && <span className="text-slate-500 text-xs"> · known broker</span>}
                    </td>
                    <td className="px-3 py-2 text-slate-400 text-xs">{e.addresses} address{e.addresses === 1 ? '' : 'es'}, {e.members} {e.members === 1 ? 'person' : 'people'}</td>
                    <td className={`px-3 py-2 text-xs ${CONF[e.confidence].cls}`} title={CONF[e.confidence].hint}>{CONF[e.confidence].label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="ag-h">
        <h2 id="ag-h" className="text-white font-medium mb-1 flex items-center gap-2"><Layers size={16} className="text-shield-400" aria-hidden="true" /> Opted out of first</h2>
        <p className="text-slate-400 text-sm mb-2">
          Brokers that feed other brokers: data wholesalers, sites whose opt-out also clears others, big families of sites,
          and brokers seen sharing addresses. Opting out of them first leaves less for everyone else to copy.
          {agg?.dispatch_order && <> Current order: <span className="text-slate-200">{ORDER[agg.dispatch_order] || agg.dispatch_order}</span> (change it under <Link to="/settings" className="text-shield-400 hover:text-shield-300">Settings → Schedule</Link>).</>}
        </p>
        {!agg ? <p className="text-slate-500 text-sm">Loading…</p> : agg.ranking.length === 0 ? (
          <p className="text-slate-400 text-sm">None of your brokers are known to feed others yet.</p>
        ) : (
          <ol className="divide-y divide-slate-700/40 rounded-xl border border-slate-700/60">
            {agg.ranking.map((r, i) => (
              <li key={r.broker_id} className="px-3 py-2 flex items-start gap-3">
                <span className="text-slate-500 text-xs w-6 text-right shrink-0 mt-0.5">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-slate-200">{r.broker_name}{!r.enabled && <span className="text-xs text-slate-500"> (turned off)</span>}</div>
                  <ul className="text-xs text-slate-400 mt-0.5">{r.reasons.slice(0, 3).map((x, j) => <li key={j}>{x}</li>)}</ul>
                </div>
                <span className="text-xs text-shield-300 shrink-0" aria-label={`weight ${r.score}`}>{r.score}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  )
}
