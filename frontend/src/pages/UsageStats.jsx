import { useCallback, useEffect, useState } from 'react'
import { BarChart3, CheckCircle2, XCircle, Copy, Plus, Trash2, PlayCircle } from 'lucide-react'
import api from '../api'
import { tx, txn } from '../i18n/tx'
import { fmtDateTime } from '../i18n/format'
import { detailText } from '../errorMessage'

// Usage statistics (super admins): a web service a library's own scripts call
// to pull counts into a data mart like LibInsight, a data warehouse or a data lake
// (backend/core/usage_stats.py). Counts only; never names or details.

const card = 'bg-slate-800 rounded-xl border border-slate-700/50 p-4 mb-4'
const inp = 'w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500'
const lbl = 'block text-slate-400 text-xs mb-1'
const btn = 'px-3 py-1.5 text-sm rounded-lg border border-slate-600 text-slate-200 hover:bg-slate-700 inline-flex items-center gap-1.5 disabled:opacity-40'
const primary = 'px-3 py-1.5 text-sm rounded-lg bg-shield-600 hover:bg-shield-700 text-white inline-flex items-center gap-1.5 disabled:opacity-40'

function Copyable({ text, label }) {
  const [done, setDone] = useState(false)
  return (
    <div className="flex flex-wrap items-center gap-2">
      <code className="text-slate-200 text-xs bg-slate-950 border border-slate-800 rounded px-2 py-1 break-all whitespace-pre-wrap" dir="ltr">{text}</code>
      <button className={btn} aria-label={tx("Copy {v}", { v: label })}
        onClick={() => { try { navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500) } catch { /* select it by hand */ } }}>
        <Copy size={12} aria-hidden="true" />{done ? tx("Copied") : tx("Copy")}</button>
    </div>
  )
}

const METRIC_LABELS = () => ({
  people_added: tx("People whose details were added."),
  listing_searches: tx("A person's listings looked for on one broker on one day."),
  listings_found: tx("A person found on a broker for the first time."),
  optout_requests_sent: tx("Opt-out requests sent. A request sent again counts on its latest date."),
  removals_confirmed: tx("Removals confirmed."),
})

export default function UsageStats() {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [newKey, setNewKey] = useState({ name: '', institution: '*' })
  const [made, setMade] = useState(null)        // {client, key}, shown once
  const [test, setTest] = useState(null)

  const load = useCallback(() => api.get('/stats-admin').then(r => setD(r.data))
    .catch(e => setErr(detailText(e) || tx("Couldn't load usage statistics."))), [])
  useEffect(() => { load() }, [load])

  const toggle = async () => {
    setBusy(true); setErr(''); setMsg('')
    try {
      const r = await api.put('/stats-admin', { enabled: !d.enabled }); setD(r.data)
      setMsg(r.data.enabled ? tx("Turned on.") : tx("Turned off. Scripts get \"turned off\" until you turn it back on."))
    } catch (e) { setErr(detailText(e) || tx("Couldn't save.")) }
    finally { setBusy(false) }
  }
  const addKey = async () => {
    setErr(''); setMade(null)
    try {
      const r = await api.post('/stats-admin/keys', { name: newKey.name, institutions: [newKey.institution] })
      setMade(r.data); setNewKey({ name: '', institution: '*' }); load()
    } catch (e) { setErr(detailText(e) || tx("Couldn't make the key.")) }
  }
  const remove = async (c) => {
    if (!confirm(tx("Remove the key {name}? Scripts using it will stop working.", { name: c.name }))) return
    await api.delete(`/stats-admin/keys/${c.id}`); load()
  }
  const runTest = async () => {
    setTest({ running: true })
    try { const r = await api.post('/stats-admin/self-test'); setTest(r.data) }
    catch (e) { setTest({ error: detailText(e) || tx("The self-test couldn't run.") }) }
  }

  if (!d) return <div className="p-6 text-slate-500 text-sm">{err || tx("Loading…")}</div>
  const base = `${window.location.origin}/api/stats`
  const instName = id => id === '*' ? tx("Every institution") : (d.institutions.find(i => i.id === id)?.name || id)
  const labels = METRIC_LABELS()
  const example = `curl -H "Authorization: Bearer $OPENOPTOUT_STATS_KEY" \\\n  "${base}/v1/usage?from=2026-09-01&to=2026-09-30&granularity=day&institution=*&format=csv"`

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2 mb-1">
        <BarChart3 size={20} className="text-shield-500" aria-hidden="true" />{tx("Usage statistics")}
      </h1>
      <p className="text-slate-400 text-sm mb-4">{tx("A web service your own scripts call to pull OpenOptOut's numbers into a data mart like LibInsight, a data warehouse or a data lake: daily, weekly or monthly counts, or totals, for any dates, per library system and branch. Counts only, never anyone's name or details.")}</p>
      {err && <p role="alert" className="text-red-400 text-sm mb-3">{err}</p>}
      {msg && <p role="status" className="text-emerald-400 text-sm mb-3">{msg}</p>}

      <section className={card} aria-labelledby="stats-service">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h2 id="stats-service" className="text-white font-medium">{tx("The service")}</h2>
          <button className={d.enabled ? btn : primary} disabled={busy} onClick={toggle}>{d.enabled ? tx("Turn off") : tx("Turn on")}</button>
        </div>
        <p className="text-sm mb-3">
          {d.enabled ? <span className="text-emerald-400">{tx("On. Scripts with a key can pull counts.")}</span>
                     : <span className="text-slate-400">{tx("Off. Only the public status answers.")}</span>}
        </p>
        <p className={lbl}>{tx("Base address")}</p>
        <Copyable text={base} label={tx("Base address")} />
        <p className="text-slate-500 text-xs mt-1">{tx("Send the key in a header: Authorization: Bearer <key>. Use HTTPS, so the key can't be read on the way.")}</p>
        <p className={`${lbl} mt-3`}>{tx("Example: September by day, every institution, as CSV")}</p>
        <Copyable text={example} label={tx("Example")} />
        <p className="text-slate-500 text-xs mt-1">{tx("granularity can be day, week, month or total. institution can be one id, several separated by commas, or * for all. format can be json or csv. Dates are UTC days; today's counts are marked complete=false.")}</p>
      </section>

      <section className={card} aria-labelledby="stats-what">
        <h2 id="stats-what" className="text-white font-medium mb-2">{tx("What's counted")}</h2>
        <dl className="text-sm space-y-1 mb-4">
          {d.metrics.map(m => (
            <div key={m.name} className="flex flex-wrap gap-x-2">
              <dt><code className="text-xs text-slate-200" dir="ltr">{m.name}</code></dt>
              <dd className="text-slate-400">{labels[m.name] || m.description}</dd>
            </div>))}
        </dl>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-slate-500 text-xs border-b border-slate-700/50">
              <th className="text-start py-2 pe-3 font-normal">{tx("Institution id")}</th>
              <th className="text-start py-2 font-normal">{tx("Institution")}</th></tr></thead>
            <tbody>{d.institutions.map(i => (
              <tr key={i.id} className="border-t border-slate-700/30">
                <td className="py-1.5 pe-3"><code className="text-xs text-slate-200" dir="ltr">{i.id}</code></td>
                <td className="py-1.5 text-slate-300">{i.name}</td></tr>))}</tbody>
          </table>
        </div>
        <p className="text-slate-500 text-xs mt-2">{tx("\"all\" is the whole server. A person counts for the branch of their account; people added by a parent count for the parent's branch.")}</p>
      </section>

      <section className={card} aria-labelledby="stats-keys">
        <h2 id="stats-keys" className="text-white font-medium mb-2">{tx("Keys")}</h2>
        <p className="text-slate-400 text-xs mb-3">{tx("Give each script or system its own key, so you can remove one without affecting the others.")}</p>
        {d.clients.length > 0 && (
          <ul className="divide-y divide-slate-700/40 mb-3">
            {d.clients.map(c => (
              <li key={c.id} className="py-2 flex flex-wrap items-center gap-3 text-sm">
                <span className="text-slate-100 font-medium">{c.name}</span>
                <span className="text-xs text-slate-400">{c.institutions.map(instName).join(', ')}</span>
                <span className="text-xs text-slate-500">{c.last_used ? tx("Last used {when}", { when: fmtDateTime(c.last_used + 'Z') }) : tx("Not used yet")}</span>
                <button className={`${btn} ms-auto`} onClick={() => remove(c)} aria-label={tx("Remove {name}", { name: c.name })}>
                  <Trash2 size={12} aria-hidden="true" />{tx("Remove")}</button>
              </li>))}
          </ul>
        )}
        <div className="flex flex-wrap items-end gap-2">
          <label className={`${lbl} flex-1 min-w-[180px]`}>{tx("Name")}
            <input className={`${inp} mt-1`} value={newKey.name} maxLength={100} placeholder={tx("e.g. Nightly warehouse load")}
              onChange={e => setNewKey({ ...newKey, name: e.target.value })} /></label>
          <label className={`${lbl} min-w-[180px]`}>{tx("Institutions it may see")}
            <select className={`${inp} mt-1`} value={newKey.institution} onChange={e => setNewKey({ ...newKey, institution: e.target.value })}>
              <option value="*">{tx("Every institution")}</option>
              {d.institutions.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select></label>
          <button className={primary} disabled={!newKey.name.trim()} onClick={addKey}><Plus size={14} aria-hidden="true" />{tx("Make a key")}</button>
        </div>
        {made && (
          <div className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 space-y-2">
            <p className="text-amber-200 text-xs">{tx("Copy the key now; it isn't shown again. Keep it out of scripts you share: an environment variable such as OPENOPTOUT_STATS_KEY is a good place.")}</p>
            <Copyable text={made.key} label={tx("Key")} />
          </div>
        )}
      </section>

      <section className={card} aria-labelledby="stats-test">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
          <h2 id="stats-test" className="text-white font-medium">{tx("Test it")}</h2>
          <button className={primary} onClick={runTest} disabled={test?.running}><PlayCircle size={14} aria-hidden="true" />
            {test?.running ? tx("Testing…") : tx("Run the self-test")}</button>
        </div>
        <p className="text-slate-400 text-xs mb-2">{tx("Calls this server the way a script would, with a throwaway key, and checks every answer: keys, institutions, daily rows, totals that add up, CSV, and refusals for bad requests.")}</p>
        {test?.error && <p role="alert" className="text-red-400 text-sm">{test.error}</p>}
        {test?.results && (
          <div role="status">
            <p className={`text-sm mb-2 ${test.ok ? 'text-emerald-400' : 'text-red-400'}`}>
              {txn(test.results.filter(r => r.ok).length, "{n} of {total} check passed.", "{n} of {total} checks passed.", { total: test.results.length })}
              {!test.enabled && <span className="text-amber-300 ms-2">{tx("The service is off, so scripts can't pull counts yet.")}</span>}
            </p>
            <ul className="space-y-1">
              {test.results.map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  {r.ok ? <CheckCircle2 size={14} className="text-emerald-400 mt-0.5 shrink-0" aria-label={tx("Passed")} />
                        : <XCircle size={14} className="text-red-400 mt-0.5 shrink-0" aria-label={tx("Failed")} />}
                  <span className="text-slate-200">{tx(r.text, r.vars)}</span>
                  <span className="text-slate-500 text-xs mt-0.5" dir="ltr">{r.detail}</span>
                </li>))}
            </ul>
          </div>
        )}
        <p className="text-slate-400 text-xs mt-4 mb-1">{tx("To test from another computer, the way your scripts will reach the server:")}</p>
        <Copyable text={`OPENOPTOUT_STATS_KEY='<key>' python3 scripts/stats-api-test.py ${base}`} label={tx("Test command")} />
        <p className="text-slate-500 text-xs mt-2">{tx("examples/stats-bridge/pull_usage.py is a starting script: it collects each new day and saves CSV and JSON Lines files, ready to load into a data mart like LibInsight, a warehouse or a lake.")}</p>
      </section>
    </div>
  )
}
