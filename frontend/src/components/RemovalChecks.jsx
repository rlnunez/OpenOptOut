import { useEffect, useState } from 'react'
import { ScanEye, RefreshCw } from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'
import { tx } from '../i18n/tx'

const VERDICT = {
  gone: { label: tx("Gone"), cls: 'text-emerald-300' },
  listed: { label: tx("Still up"), cls: 'text-red-300' },
  not_found: { label: tx("Not found"), cls: 'text-slate-300' },
  blocked: { label: tx("Site wouldn't let us look"), cls: 'text-amber-300' },
  unknown: { label: tx("Couldn't check"), cls: 'text-slate-400' },
}

// Dashboard card: automatic checks that removed listings stayed gone.
export default function RemovalChecks() {
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [msg, setMsg] = useState('')
  const load = () => api.get('/verification/summary').then(r => setData(r.data)).catch(() => {})
  useEffect(() => { load() }, [])

  const runNow = async () => {
    setMsg('')
    try { const { data: d } = await api.post('/verification/run'); setMsg(d.message); setTimeout(load, 60000) }
    catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't start the checks.")) }
  }

  if (!data) return null
  const c = data.counts
  return (
    <section aria-labelledby="rc-h" className="bg-slate-800 rounded-xl p-4 border border-slate-700/50 mb-6">
      <div className="flex items-center justify-between gap-2">
        <h2 id="rc-h" className="text-slate-400 text-xs uppercase tracking-wide flex items-center gap-1.5">
          <ScanEye size={13} aria-hidden="true" />{" "}{tx("Removal checks")}
        </h2>
        {can(user, 'scheduler.manage') && (
          <button onClick={runNow} className="text-xs text-shield-400 hover:text-shield-300 flex items-center gap-1">
            <RefreshCw size={12} aria-hidden="true" />{" "}{tx("Check now")}
          </button>
        )}
      </div>
      <p className="text-slate-400 text-xs mt-1">
        {data.enabled
          ? tx("OpenOptOut looks at each site again after an opt-out, and every month after that, to make sure the listing stayed gone. If it's back, the opt-out is sent again.")
          : tx("Automatic checks are turned off.")}
        {data.last_checked_at && tx("Last check: {v}.", { v: new Date(data.last_checked_at + 'Z').toLocaleString() })}
      </p>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3 text-xs">
        <div><dt className="text-slate-400">{tx("Checked: gone")}</dt><dd className="text-emerald-300 text-lg font-semibold">{c.gone}</dd></div>
        <div><dt className="text-slate-400">{tx("Still up (sending again)")}</dt><dd className="text-red-300 text-lg font-semibold">{c.listed}</dd></div>
        <div><dt className="text-slate-400">{tx("Not found in search")}</dt><dd className="text-slate-200 text-lg font-semibold">{c.not_found}</dd></div>
        <div><dt className="text-slate-400">{tx("Couldn't check")}</dt><dd className="text-amber-300 text-lg font-semibold">{c.blocked + c.unknown}</dd></div>
      </dl>
      {msg && <p role="status" className="text-xs text-shield-300 mt-2">{msg}</p>}
      {data.recent.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-700/40">
          {data.recent.slice(0, 6).map((r, i) => (
            <li key={i} className="py-1.5 flex items-baseline justify-between gap-2 text-xs">
              <span className="text-slate-300 truncate">{r.broker_name} · {r.member_name}
                <span className="text-slate-500"> — {r.detail}</span></span>
              <span className={`shrink-0 ${(VERDICT[r.verdict] || VERDICT.unknown).cls}`}>{(VERDICT[r.verdict] || VERDICT.unknown).label}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
