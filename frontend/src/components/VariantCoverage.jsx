import { useEffect, useState } from 'react'
import { Layers, ChevronDown, ChevronRight } from 'lucide-react'
import api from '../api'
import { tx, txn } from '../i18n/tx'

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
        {t.sent ? tx("Removed at {removed} of {sent} brokers they were sent to", { removed: t.removed, sent: t.sent }) : tx("Not sent to any broker yet")}
        {t.never_sent > 0 && t.sent > 0 && tx("· {never_sent} not sent anywhere yet", { never_sent: t.never_sent })}
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
        <Layers size={13} aria-hidden="true" />{" "}{tx("Removal by detail")}
      </h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <Line title={tx("Main details")} hint={tx("(full name, current address, phone)")} t={f.main} />
        <Line title={tx("Other details")} hint={tx("(other names, old addresses, numbers, emails)")} t={f.variants} />
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
                  {tx("main {v} ·", { v: m.main.percent_removed === null ? '—' : `${m.main.percent_removed}%` })}
                  {' '}{tx("variants {v}", { v: m.variants.percent_removed === null ? '—' : `${m.variants.percent_removed}%` })}
                </span>
              </button>
              {open === m.member_id && (
                <div className="overflow-x-auto mt-2">
                  <table className="w-full text-xs">
                    <thead><tr className="text-left text-slate-500">
                      <th scope="col" className="py-1 pr-2 font-medium">{tx("Detail")}</th>
                      <th scope="col" className="py-1 pr-2 font-medium">{tx("Type")}</th>
                      <th scope="col" className="py-1 pr-2 font-medium text-right">{tx("Sent to")}</th>
                      <th scope="col" className="py-1 font-medium text-right">{tx("Removed at")}</th>
                    </tr></thead>
                    <tbody>
                      {m.details.map(d => (
                        <tr key={d.identity_id} className="border-t border-slate-700/30">
                          <td className="py-1 pr-2 text-slate-200">{d.label}{d.group === 'main' && <span className="ml-1.5 text-[10px] text-shield-300">{tx("main")}</span>}</td>
                          <td className="py-1 pr-2 text-slate-400">{KIND[d.kind] || d.kind}</td>
                          <td className="py-1 pr-2 text-right text-slate-300">{d.brokers_sent}</td>
                          <td className={`py-1 text-right ${d.brokers_sent && d.brokers_removed === d.brokers_sent ? 'text-emerald-300' : 'text-slate-300'}`}>{d.brokers_removed}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {m.untracked_requests > 0 && (
                    <p className="text-xs text-slate-500 mt-1">
                      {txn(m.untracked_requests, "{n} earlier request didn't record which details it sent, so it isn't counted here.", "{n} earlier requests didn't record which details they sent, so they aren't counted here.")}
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
