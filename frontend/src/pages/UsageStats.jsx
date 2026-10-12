import { useCallback, useEffect, useState } from 'react'
import { BarChart3, CheckCircle2, XCircle, Copy, Plus, Trash2, PlayCircle } from 'lucide-react'
import api from '../api'
import { tx, txn } from '../i18n/tx'
import { fmtDateTime } from '../i18n/format'

// Usage statistics (super admins): monthly counts that library and campus
// systems collect over the COUNTER API (SUSHI), per library system and branch
// (backend/core/sushi.py). Counts only; never names or details.

const card = 'bg-slate-800 rounded-xl border border-slate-700/50 p-4 mb-4'
const inp = 'w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500'
const lbl = 'block text-slate-400 text-xs mb-1'
const btn = 'px-3 py-1.5 text-sm rounded-lg border border-slate-600 text-slate-200 hover:bg-slate-700 inline-flex items-center gap-1.5 disabled:opacity-40'
const primary = 'px-3 py-1.5 text-sm rounded-lg bg-shield-600 hover:bg-shield-700 text-white inline-flex items-center gap-1.5 disabled:opacity-40'

function Copyable({ text, label }) {
  const [done, setDone] = useState(false)
  return (
    <div className="flex flex-wrap items-center gap-2">
      <code className="text-slate-200 text-xs bg-slate-950 border border-slate-800 rounded px-2 py-1 break-all" dir="ltr">{text}</code>
      <button className={btn} aria-label={tx("Copy {v}", { v: label })}
        onClick={() => { try { navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500) } catch { /* select it by hand */ } }}>
        <Copy size={12} aria-hidden="true" />{done ? tx("Copied") : tx("Copy")}</button>
    </div>
  )
}

export default function UsageStats() {
  const [d, setD] = useState(null)
  const [form, setForm] = useState(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [newH, setNewH] = useState({ name: '', customer: '*' })
  const [made, setMade] = useState(null)        // {harvester, api_key}, shown once
  const [test, setTest] = useState(null)

  const load = useCallback(() => api.get('/sushi-admin').then(r => {
    setD(r.data); setForm({ platform: r.data.platform, namespace: r.data.namespace, registry_record: r.data.registry_record })
  }).catch(e => setErr(e.response?.data?.detail || tx("Couldn't load usage statistics."))), [])
  useEffect(() => { load() }, [load])

  const put = async (body, ok) => {
    setBusy(true); setErr(''); setMsg('')
    try { const r = await api.put('/sushi-admin', body); setD(r.data); setMsg(ok) }
    catch (e) { setErr(e.response?.data?.detail || tx("Couldn't save.")) }
    finally { setBusy(false) }
  }
  const addHarvester = async () => {
    setErr(''); setMade(null)
    try {
      const r = await api.post('/sushi-admin/harvesters', { name: newH.name, customers: [newH.customer] })
      setMade(r.data); setNewH({ name: '', customer: '*' }); load()
    } catch (e) { setErr(e.response?.data?.detail || tx("Couldn't add the harvester.")) }
  }
  const remove = async (h) => {
    if (!confirm(tx("Remove {name}? It won't be able to collect reports any more.", { name: h.name }))) return
    await api.delete(`/sushi-admin/harvesters/${h.id}`); load()
  }
  const runTest = async () => {
    setTest({ running: true })
    try { const r = await api.post('/sushi-admin/self-test'); setTest(r.data) }
    catch (e) { setTest({ error: e.response?.data?.detail || tx("The self-test couldn't run.") }) }
  }

  if (!d || !form) return <div className="p-6 text-slate-500 text-sm">{err || tx("Loading…")}</div>
  const base = `${window.location.origin}/api/sushi`
  const name = id => id === '*' ? tx("Every institution") : (d.customers.find(c => c.id === id)?.name || id)

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2 mb-1">
        <BarChart3 size={20} className="text-shield-500" aria-hidden="true" />{tx("Usage statistics (SUSHI)")}
      </h1>
      <p className="text-slate-400 text-sm mb-4">{tx("Library and campus systems can collect monthly usage from OpenOptOut the way they do from journal platforms: COUNTER reports over SUSHI, per library system and branch. Counts only, never anyone's name or details. SUSHI-compatible, not COUNTER-audited.")}</p>
      {err && <p role="alert" className="text-red-400 text-sm mb-3">{err}</p>}
      {msg && <p role="status" className="text-emerald-400 text-sm mb-3">{msg}</p>}

      <section className={card} aria-labelledby="sushi-service">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h2 id="sushi-service" className="text-white font-medium">{tx("The service")}</h2>
          <button className={d.enabled ? btn : primary} disabled={busy}
            onClick={() => put({ enabled: !d.enabled }, d.enabled ? tx("Turned off. Harvesters get \"Service Not Available\".") : tx("Turned on."))}>
            {d.enabled ? tx("Turn off") : tx("Turn on")}</button>
        </div>
        <p className="text-sm mb-3">
          {d.enabled
            ? <span className="text-emerald-400">{tx("On. Harvesters with a key can collect reports.")}</span>
            : <span className="text-slate-400">{tx("Off. Only the public status page answers.")}</span>}
        </p>
        <p className={lbl}>{tx("Address to give your harvester (SUSHI base URL)")}</p>
        <Copyable text={base} label={tx("SUSHI base URL")} />
        <p className="text-slate-500 text-xs mt-1">{tx("The COUNTER API must be reached over HTTPS. Reports cover whole months, up to the last complete one.")}</p>
        <div className="grid sm:grid-cols-3 gap-3 mt-4">
          <label className={lbl}>{tx("Platform name")}
            <input className={`${inp} mt-1`} value={form.platform} maxLength={100} onChange={e => setForm({ ...form, platform: e.target.value })} /></label>
          <label className={lbl}>{tx("Namespace for custom reports")}
            <input className={`${inp} mt-1`} value={form.namespace} maxLength={17} dir="ltr" onChange={e => setForm({ ...form, namespace: e.target.value })} /></label>
          <label className={lbl}>{tx("COUNTER Registry address (optional)")}
            <input className={`${inp} mt-1`} value={form.registry_record} dir="ltr" placeholder="https://registry.countermetrics.org/…"
              onChange={e => setForm({ ...form, registry_record: e.target.value })} /></label>
        </div>
        <button className={`${primary} mt-3`} disabled={busy} onClick={() => put(form, tx("Saved."))}>{tx("Save")}</button>
      </section>

      <section className={card} aria-labelledby="sushi-what">
        <h2 id="sushi-what" className="text-white font-medium mb-2">{tx("Reports and institutions")}</h2>
        <ul className="text-sm text-slate-300 space-y-1 mb-3">
          <li><strong className="text-slate-100">PR</strong>, <strong className="text-slate-100">PR_P1</strong>: {tx("searches for people's listings on data-broker sites, as Searches_Platform.")}</li>
          <li><strong className="text-slate-100">{d.namespace}:OO1</strong>: {tx("people added, listing searches, listings found, opt-out requests sent and removals confirmed.")}</li>
        </ul>
        <p className="text-slate-400 text-xs mb-2">
          {d.first_month ? tx("Months available: {first} to {last}.", { first: d.first_month, last: d.last_month }) : tx("No months with data yet.")}
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-slate-500 text-xs border-b border-slate-700/50">
              <th className="text-start py-2 pe-3 font-normal">{tx("Customer ID")}</th>
              <th className="text-start py-2 font-normal">{tx("Institution")}</th></tr></thead>
            <tbody>{d.customers.map(c => (
              <tr key={c.id} className="border-t border-slate-700/30">
                <td className="py-1.5 pe-3"><code className="text-xs text-slate-200" dir="ltr">{c.id}</code></td>
                <td className="py-1.5 text-slate-300">{c.name}</td></tr>))}</tbody>
          </table>
        </div>
        <p className="text-slate-500 text-xs mt-2">{tx("\"all\" is the whole server. A person counts for the branch of their account; people added by a parent count for the parent's branch.")}</p>
      </section>

      <section className={card} aria-labelledby="sushi-harvesters">
        <h2 id="sushi-harvesters" className="text-white font-medium mb-2">{tx("Harvesters")}</h2>
        <p className="text-slate-400 text-xs mb-3">{tx("Each system that collects reports gets its own requestor ID and API key, so you can remove one without affecting the others.")}</p>
        {d.harvesters.length > 0 && (
          <ul className="divide-y divide-slate-700/40 mb-3">
            {d.harvesters.map(h => (
              <li key={h.id} className="py-2 flex flex-wrap items-center gap-3 text-sm">
                <span className="text-slate-100 font-medium">{h.name}</span>
                <code className="text-xs text-slate-400" dir="ltr">{h.requestor_id}</code>
                <span className="text-xs text-slate-400">{h.customers.map(name).join(', ')}</span>
                <span className="text-xs text-slate-500">{h.last_used ? tx("Last collected {when}", { when: fmtDateTime(h.last_used + 'Z') }) : tx("Hasn't collected yet")}</span>
                <button className={`${btn} ms-auto`} onClick={() => remove(h)} aria-label={tx("Remove {name}", { name: h.name })}>
                  <Trash2 size={12} aria-hidden="true" />{tx("Remove")}</button>
              </li>))}
          </ul>
        )}
        <div className="flex flex-wrap items-end gap-2">
          <label className={`${lbl} flex-1 min-w-[180px]`}>{tx("Name")}
            <input className={`${inp} mt-1`} value={newH.name} maxLength={100} placeholder={tx("e.g. Celus, or the university's ERM")}
              onChange={e => setNewH({ ...newH, name: e.target.value })} /></label>
          <label className={`${lbl} min-w-[180px]`}>{tx("Institutions it may see")}
            <select className={`${inp} mt-1`} value={newH.customer} onChange={e => setNewH({ ...newH, customer: e.target.value })}>
              <option value="*">{tx("Every institution")}</option>
              {d.customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select></label>
          <button className={primary} disabled={!newH.name.trim()} onClick={addHarvester}><Plus size={14} aria-hidden="true" />{tx("Add a harvester")}</button>
        </div>
        {made && (
          <div className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 space-y-2">
            <p className="text-amber-200 text-xs">{tx("Copy the API key now; it isn't shown again. Give the harvester all three: the base URL, the requestor ID and the API key, plus a customer ID from the table above.")}</p>
            <p className={lbl}>{tx("Requestor ID")}</p><Copyable text={made.harvester.requestor_id} label={tx("Requestor ID")} />
            <p className={lbl}>{tx("API key")}</p><Copyable text={made.api_key} label={tx("API key")} />
          </div>
        )}
      </section>

      <section className={card} aria-labelledby="sushi-test">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
          <h2 id="sushi-test" className="text-white font-medium">{tx("Test it")}</h2>
          <button className={primary} onClick={runTest} disabled={test?.running}><PlayCircle size={14} aria-hidden="true" />
            {test?.running ? tx("Testing…") : tx("Run the self-test")}</button>
        </div>
        <p className="text-slate-400 text-xs mb-2">{tx("Asks this server what a library's harvester would ask, with a throwaway key, and checks every answer against COUNTER Release 5.1: credentials, report list, report shape, dates and error codes.")}</p>
        {test?.error && <p role="alert" className="text-red-400 text-sm">{test.error}</p>}
        {test?.results && (
          <div role="status">
            <p className={`text-sm mb-2 ${test.ok ? 'text-emerald-400' : 'text-red-400'}`}>
              {txn(test.results.filter(r => r.ok).length, "{n} of {total} check passed.", "{n} of {total} checks passed.", { total: test.results.length })}
              {!test.enabled && <span className="text-amber-300 ms-2">{tx("The service is off, so harvesters can't collect yet.")}</span>}
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
        <p className="text-slate-400 text-xs mt-4 mb-1">{tx("To test from outside, the way a harvester reaches the server (run it on any computer with the OpenOptOut files and Python):")}</p>
        <Copyable text={`python3 scripts/sushi-harvest-test.py ${base} --requestor-id <requestor ID> --api-key <API key> --save sushi-reports`} label={tx("Test command")} />
        <p className="text-slate-500 text-xs mt-1">{tx("--save keeps each report, to upload to the COUNTER Validator for an independent check.")}</p>
      </section>
    </div>
  )
}
