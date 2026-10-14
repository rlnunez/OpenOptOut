import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { MousePointerClick } from 'lucide-react'
import api from '../api'
import { tx, txr } from '../i18n/tx'

// Email Monitor card: broker confirmation links — how many are waiting to be
// clicked, clicked, or need a person — and (for admins) the auto-click switch.
export default function ConfirmLinksCard({ isAdmin }) {
  const [sum, setSum] = useState(null)
  const [s, setS] = useState(null)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.get('/confirm-links/summary').then(r => setSum(r.data)).catch(() => {})
    if (isAdmin) api.get('/confirm-links/settings').then(r => setS(r.data)).catch(() => {})
  }, [isAdmin])

  const save = async (next) => {
    setS(next); setMsg('')
    try { await api.put('/confirm-links/settings', next); setMsg(tx("Saved.")) }
    catch { setMsg(tx("Couldn't save. Please try again.")) }
  }

  if (!sum) return null
  return (
    <section aria-labelledby="cl-h" className="mb-5 bg-slate-800 rounded-xl border border-slate-700/50 p-4">
      <h2 id="cl-h" className="text-slate-200 text-sm font-medium flex items-center gap-2">
        <MousePointerClick size={15} className="text-shield-400" aria-hidden="true" />{" "}{tx("Confirmation links")}
      </h2>
      <p className="text-slate-400 text-xs mt-0.5">
        {tx("Some brokers email a link that has to be clicked before they remove anything. OpenOptOut clicks it for you when the link goes to that broker's own website, and only counts the opt-out as done once the page accepts it.")}
      </p>
      <dl className="grid grid-cols-3 gap-2 mt-3 text-xs">
        <div><dt className="text-slate-400">{tx("Waiting to click")}</dt><dd className="text-sky-300 text-lg font-semibold">{sum.pending}</dd></div>
        <div><dt className="text-slate-400">{tx("Clicked")}</dt><dd className="text-emerald-300 text-lg font-semibold">{sum.clicked + sum.done}</dd></div>
        <div><dt className="text-slate-400">{tx("Need you")}</dt><dd className="text-amber-300 text-lg font-semibold">{sum.needs_person}</dd></div>
      </dl>
      {sum.needs_person > 0 && (
        <Link to="/checklist" className="inline-block mt-2 text-sm text-shield-400 hover:text-shield-300 underline">
          {tx("Open the checklist to finish {v}", { v: sum.needs_person === 1 ? 'it' : 'them' })}
        </Link>
      )}
      {isAdmin && s && (
        <div className="mt-3 pt-3 border-t border-slate-700/50 space-y-2">
          <label className="flex items-start gap-2 text-sm text-slate-200">
            <input type="checkbox" checked={s.auto_click} onChange={e => save({ ...s, auto_click: e.target.checked })}
              className="mt-0.5 accent-shield-500" />
            {tx("Click confirmation links automatically")}
          </label>
          <label className="flex items-start gap-2 text-sm text-slate-200">
            <input type="checkbox" checked={s.use_browser} disabled={!s.auto_click}
              onChange={e => save({ ...s, use_browser: e.target.checked })} className="mt-0.5 accent-shield-500" />
            <span>{txr("Press the \"Confirm\" button when a page has one <0>(opens the page in a hidden browser)</0>", [<span className="text-slate-400 text-xs" />])}</span>
          </label>
          {msg && <p role="status" className="text-xs text-shield-300">{msg}</p>}
        </div>
      )}
    </section>
  )
}
