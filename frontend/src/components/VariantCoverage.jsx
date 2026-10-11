import { useEffect, useState } from 'react'
import { Layers, ChevronDown, ChevronRight } from 'lucide-react'
import api from '../api'

const KIND = { name: 'Name', address: 'Address', phone: 'Phone', email: 'Email' }

function Line({ title, hint, t }) {
  const pct = t.percent_removed
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-slate-200 text-sm">{title} <span className="text-slate-500 text-xs">{hint}</span></span>
        <span className="text-sm font-semibold text-emerald-300">{pct === null ? '—' : `${pct}%`}</span>
      </div>
      <div className="mt-1.5 h-2 rounded-full bg-slate-700 overflow-hidden" role="img"
        aria-label={`${title}: removed at ${t.removed} of ${t.sent} brokers they were sent to`}>
        <div className="h-full bg-emerald-500" style={{ width: `${pct || 0}%` }} />
      </div>
      <p className="text-xs text-slate-400 mt-1">
        {t.sent ? `Removed at ${t.removed} of ${t.sent} brokers they were sent to` : 'Not sent to any broker yet'}
        {t.never_sent > 0 && t.sent > 0 && ` · ${t.never_sent} not sent anywhere yet`}
      </p>
    </div>
  )
}

// Dashboard card: how far removal has reached for the main details (full
// name, current address, phone) versus every other saved variant.
export default function VariantCoverage() {
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(null)   // member_id whose details are expanded

  useEffect(() => { api.get('/variants/report').then(r => setData(r.data)).catch(() => {}) }, [])
  if (!data || data.members.length === 0) return null
  const f = data.family

  return (
    <section aria-labelledby="variants-h" className="bg-slate-800 rounded-xl p-4 border border-slate-700/50 mb-6">
      <h2 id="variants-h" className="text-slate-400 text-xs uppercase tracking-wide mb-3 flex items-center gap-1.5">
        <Layers size={13} aria-hidden="true" /> Removal by detail
      </h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <Line title="Main details" hint="(full name, current address, phone)" t={f.main} />
        <Line title="Other variants" hint="(other names, old addresses, numbers, emails)" t={f.variants} />
      </div>

      {data.members.length > 0 && (
        <ul className="mt-4 divide-y divide-slate-700/40">
          {data.members.map(m => (
            <li key={m.member_id} className="py-2">
              <button type="button" onClick={() => setOpen(open === m.member_id ? null : m.member_id)}
                aria-expanded={open === m.member_id} className="w-full flex items-center justify-between gap-2 text-left">
                <span className="flex items-center gap-1.5 text-sm text-slate-200">
                  {open === m.member_id ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
                  {m.member_name}
                </span>
                <span className="text-xs text-slate-400">
                  main {m.main.percent_removed === null ? '—' : `${m.main.percent_removed}%`} ·
                  {' '}variants {m.variants.percent_removed === null ? '—' : `${m.variants.percent_removed}%`}
                </span>
              </button>
              {open === m.member_id && (
                <div className="overflow-x-auto mt-2">
                  <table className="w-full text-xs">
                    <thead><tr className="text-left text-slate-500">
                      <th scope="col" className="py-1 pr-2 font-medium">Detail</th>
                      <th scope="col" className="py-1 pr-2 font-medium">Type</th>
                      <th scope="col" className="py-1 pr-2 font-medium text-right">Sent to</th>
                      <th scope="col" className="py-1 font-medium text-right">Removed at</th>
                    </tr></thead>
                    <tbody>
                      {m.details.map(d => (
                        <tr key={d.identity_id} className="border-t border-slate-700/30">
                          <td className="py-1 pr-2 text-slate-200">{d.label}{d.group === 'main' && <span className="ml-1.5 text-[10px] text-shield-300">main</span>}</td>
                          <td className="py-1 pr-2 text-slate-400">{KIND[d.kind] || d.kind}</td>
                          <td className="py-1 pr-2 text-right text-slate-300">{d.brokers_sent}</td>
                          <td className={`py-1 text-right ${d.brokers_sent && d.brokers_removed === d.brokers_sent ? 'text-emerald-300' : 'text-slate-300'}`}>{d.brokers_removed}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {m.untracked_requests > 0 && (
                    <p className="text-xs text-slate-500 mt-1">
                      {m.untracked_requests} earlier request{m.untracked_requests === 1 ? '' : 's'} didn't record which details {m.untracked_requests === 1 ? 'it' : 'they'} sent, so {m.untracked_requests === 1 ? "it isn't" : "they aren't"} counted here.
                    </p>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
