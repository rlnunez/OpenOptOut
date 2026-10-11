import { useEffect, useState } from 'react'
import { Gavel, Download, Bell } from 'lucide-react'
import api from '../api'
import { tx } from '../i18n/tx'

// Which sites missed the time the law gives them to answer, and which put
// details back after removing them. Limited to the people you can see.

const fmt = d => d ? new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'
const VERDICT = {
  overdue: [tx("No answer, past due"), 'text-red-300'],
  late: [tx("Answered late"), 'text-amber-300'],
  on_time: [tx("On time"), 'text-emerald-300'],
  waiting: [tx("Still within the deadline"), 'text-slate-300'],
  no_deadline: [tx("No legal deadline on record"), 'text-slate-400'],
}

function Toggle({ id, checked, onChange, children }) {
  return (
    <label htmlFor={id} className="flex items-start gap-2 cursor-pointer">
      <input id={id} type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)}
        className="mt-1 w-4 h-4 accent-shield-500" />
      <span className="text-slate-200 text-sm">{children}</span>
    </label>
  )
}

export default function DeadlineReport() {
  const [rep, setRep] = useState(null)
  const [prefs, setPrefs] = useState(null)
  const [problemsOnly, setProblemsOnly] = useState(true)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')

  useEffect(() => {
    api.get('/compliance/report').then(r => setRep(r.data)).catch(e => setError(e.response?.data?.detail || tx("Couldn't load the report.")))
    api.get('/compliance/notices').then(r => setPrefs(r.data)).catch(() => {})
  }, [])

  const setPref = async (k, v) => {
    setSaved('')
    try {
      const { data } = await api.patch('/compliance/notices', { [k]: v })
      setPrefs(data); setSaved('Saved.')
    } catch { setSaved(tx("Couldn't save that. Please try again.")) }
  }

  const download = async () => {
    try {
      const r = await api.get('/compliance/report.csv', { responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a'); a.href = url; a.download = 'deadline-report.csv'; a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch { setError(tx("Couldn't download the file.")) }
  }

  const rows = rep ? rep.rows.filter(r => !problemsOnly || r.verdict === 'overdue' || r.verdict === 'late' || r.found_again) : []
  const card = 'bg-slate-800 rounded-xl border border-slate-700/50 p-4'

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2"><Gavel size={18} aria-hidden="true" />{" "}{tx("Deadline report")}</h1>
      <p className="text-slate-400 text-sm mt-1 mb-4 max-w-2xl">
        {tx("Privacy laws give sites a set number of days to answer a removal request (45 under California's law, 30 under Europe's). This shows which sites missed it, and which put details back after removing them. You only see the people you have access to.")}
      </p>

      {prefs && (
        <section aria-labelledby="h-notices" className={`${card} mb-4`}>
          <h2 id="h-notices" className="text-white font-medium flex items-center gap-2 mb-2"><Bell size={15} aria-hidden="true" />{" "}{tx("Email me when…")}</h2>
          <div className="space-y-2">
            <Toggle id="n-over" checked={prefs.overdue} onChange={v => setPref('overdue', v)}>{tx("a site misses its deadline for someone in my family")}</Toggle>
            <Toggle id="n-re" checked={prefs.relisted} onChange={v => setPref('relisted', v)}>{tx("a site puts our details back after removing them")}</Toggle>
          </div>
          <p className="text-slate-500 text-xs mt-2">{tx("Sent to")}{" "}{prefs.email || tx("your account email")}{tx(", once a day at most, and only once for each problem.")}
            {saved && <span className="text-slate-300" role="status"> {saved}</span>}</p>
        </section>
      )}

      {error && <p role="alert" className="text-red-400 text-sm mb-4">{error}</p>}
      {!rep && !error && <p className="text-slate-400 text-sm">{tx("Loading…")}</p>}

      {rep && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            {[[tx("No answer, past due"), rep.totals.overdue, 'text-red-300'], [tx("Answered late"), rep.totals.late, 'text-amber-300'],
              [tx("Put back after removal"), rep.totals.relisted, 'text-amber-300'], [tx("On time"), rep.totals.on_time, 'text-emerald-300']].map(([l, n, c]) => (
              <div key={l} className={card}><p className={`text-2xl font-semibold ${c}`}>{n}</p><p className="text-slate-400 text-xs">{l}</p></div>
            ))}
          </div>

          <section aria-labelledby="h-sites" className={`${card} mb-4 overflow-x-auto`}>
            <h2 id="h-sites" className="text-white font-medium mb-2">{tx("By site")}</h2>
            {rep.sites.length === 0 ? <p className="text-slate-400 text-sm">{tx("Nothing has been sent yet.")}</p> : (
              <table className="w-full text-sm">
                <thead><tr className="text-slate-400 text-xs text-start">
                  <th scope="col" className="py-1 pe-3 font-normal">{tx("Site")}</th>
                  <th scope="col" className="py-1 pe-3 font-normal">{tx("Days allowed")}</th>
                  <th scope="col" className="py-1 pe-3 font-normal">{tx("Requests")}</th>
                  <th scope="col" className="py-1 pe-3 font-normal">{tx("Past due")}</th>
                  <th scope="col" className="py-1 pe-3 font-normal">{tx("Late")}</th>
                  <th scope="col" className="py-1 pe-3 font-normal">{tx("Put back")}</th>
                  <th scope="col" className="py-1 font-normal">{tx("Usual days to remove")}</th>
                </tr></thead>
                <tbody>{rep.sites.map(s => (
                  <tr key={s.site} className="border-t border-slate-700/40">
                    <th scope="row" className="py-1.5 pe-3 text-start text-slate-200 font-normal">{s.site}</th>
                    <td className="py-1.5 pe-3 text-slate-300">{s.response_days || '—'}</td>
                    <td className="py-1.5 pe-3 text-slate-300">{s.rounds}</td>
                    <td className={`py-1.5 pe-3 ${s.overdue ? 'text-red-300' : 'text-slate-500'}`}>{s.overdue}</td>
                    <td className={`py-1.5 pe-3 ${s.late ? 'text-amber-300' : 'text-slate-500'}`}>{s.late}</td>
                    <td className={`py-1.5 pe-3 ${s.relisted ? 'text-amber-300' : 'text-slate-500'}`}>{s.relisted}</td>
                    <td className="py-1.5 text-slate-300">{s.median_days_to_remove ?? '—'}</td>
                  </tr>))}</tbody>
              </table>
            )}
          </section>

          <section aria-labelledby="h-rows" className={`${card} overflow-x-auto`}>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <h2 id="h-rows" className="text-white font-medium">{tx("Each request")}</h2>
              <div className="flex items-center gap-3">
                <Toggle id="only" checked={problemsOnly} onChange={setProblemsOnly}>{tx("Only problems")}</Toggle>
                <button onClick={download} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-700">
                  <Download size={13} aria-hidden="true" />{" "}{tx("Download for a complaint")}
                </button>
              </div>
            </div>
            {rows.length === 0 ? <p className="text-slate-400 text-sm">{problemsOnly ? tx("No problems. Every site has answered on time so far.") : tx("Nothing yet.")}</p> : (
              <table className="w-full text-sm">
                <thead><tr className="text-slate-400 text-xs text-start">
                  {[tx("Site"), tx("Person"), tx("Sent"), tx("Due"), tx("Replied"), tx("Removed"), tx("Found again"), tx("Result")].map(h => <th key={h} scope="col" className="py-1 pe-3 font-normal">{h}</th>)}
                </tr></thead>
                <tbody>{rows.map(r => {
                  const [label, cls] = VERDICT[r.verdict] || [r.verdict, 'text-slate-300']
                  return (
                    <tr key={`${r.request_id}-${r.round}`} className="border-t border-slate-700/40">
                      <td className="py-1.5 pe-3 text-slate-200">{r.site}{r.round > 1 ? <span className="text-slate-500">{" "}{tx("(round {round})", { round: r.round })}</span> : ''}</td>
                      <td className="py-1.5 pe-3 text-slate-300">{r.person}</td>
                      <td className="py-1.5 pe-3 text-slate-300">{fmt(r.sent)}</td>
                      <td className="py-1.5 pe-3 text-slate-300">{fmt(r.due)}</td>
                      <td className="py-1.5 pe-3 text-slate-300">{fmt(r.replied)}</td>
                      <td className="py-1.5 pe-3 text-slate-300">{fmt(r.removed)}</td>
                      <td className={`py-1.5 pe-3 ${r.found_again ? 'text-amber-300' : 'text-slate-500'}`}>{fmt(r.found_again)}</td>
                      <td className={`py-1.5 ${cls}`}>{label}</td>
                    </tr>)
                })}</tbody>
              </table>
            )}
            <p className="text-slate-500 text-xs mt-3">{tx("To complain: California residents can file with the California Privacy Protection Agency (cppa.ca.gov); others with their state attorney general, or in the EU and UK with their data protection authority. Attach the downloaded file.")}</p>
          </section>
        </>
      )}
    </div>
  )
}
