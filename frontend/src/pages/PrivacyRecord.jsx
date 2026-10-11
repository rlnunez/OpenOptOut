import { useEffect, useState } from 'react'
import { FileLock2, Download, AlertTriangle, Trash2 } from 'lucide-react'
import api from '../api'
import { tx, txn, txr } from '../i18n/tx'

// OpenOptOut's own record of the personal data it keeps (GDPR Article 30
// style), its protection and retention, staff access, and tools for answering
// a person's request to see or delete their data.

const card = 'bg-slate-800 rounded-xl border border-slate-700/50 p-4 mb-4'
const fmt = d => d ? new Date(d).toLocaleString() : '—'

export default function PrivacyRecord() {
  const [rec, setRec] = useState(null)
  const [log, setLog] = useState([])
  const [people, setPeople] = useState([])
  const [who, setWho] = useState('')
  const [msg, setMsg] = useState('')

  const load = () => {
    api.get('/privacy/record').then(r => setRec(r.data)).catch(e => setMsg(e.response?.data?.detail || tx("Couldn't load the record.")))
    api.get('/privacy/access-log', { params: { limit: 200 } }).then(r => setLog(r.data)).catch(() => {})
  }
  useEffect(() => {
    load()
    api.get('/family').then(r => setPeople(r.data)).catch(() => {})
  }, [])

  const exportPerson = async () => {
    if (!who) return
    try {
      const r = await api.get(`/privacy/export/${who}`, { responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a'); a.href = url; a.download = `openoptout-person-${who}.json`; a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      load()
    } catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't export that person's data.")) }
  }

  const purge = async () => {
    setMsg('')
    try {
      const { data } = await api.post('/privacy/purge')
      const n = Object.values(data.removed).reduce((a, b) => a + b, 0)
      setMsg(txn(n, "Done. {n} old record removed.", "Done. {n} old records removed.")); load()
    } catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't run it.")) }
  }

  const downloadRecord = () => {
    const blob = new Blob([JSON.stringify(rec, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'openoptout-privacy-record.json'; a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h1 className="text-white text-xl font-semibold flex items-center gap-2"><FileLock2 size={18} aria-hidden="true" />{" "}{tx("Privacy record")}</h1>
          <p className="text-slate-400 text-sm mt-1 max-w-2xl">
            {tx("What personal data this OpenOptOut keeps, why, how it's protected and for how long, and who looked at it. Use it as your record of processing under GDPR Article 30, and to answer requests under the CCPA and GDPR.")}
          </p>
        </div>
        {rec && <button onClick={downloadRecord} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-700">
          <Download size={13} aria-hidden="true" />{" "}{tx("Download the record")}</button>}
      </div>
      {msg && <p role="status" className="text-slate-200 text-sm mb-3">{msg}</p>}
      {!rec && !msg && <p className="text-slate-400 text-sm">{tx("Loading…")}</p>}

      {rec && (
        <>
          {rec.warnings.length > 0 && (
            <div className="mb-4 px-3 py-2.5 rounded-lg border border-amber-700/60 bg-amber-950/20" role="note">
              {rec.warnings.map(w => <p key={w} className="text-amber-200 text-sm flex gap-1.5"><AlertTriangle size={14} className="shrink-0 mt-0.5" aria-hidden="true" />{w}</p>)}
            </div>
          )}

          <section aria-labelledby="h-inv" className={`${card} overflow-x-auto`}>
            <h2 id="h-inv" className="text-white font-medium mb-2">{tx("What's kept")}</h2>
            <table className="w-full text-sm">
              <thead><tr className="text-slate-400 text-xs text-left">
                {[tx("Data"), tx("Why"), tx("How it is protected"), tx("Kept for"), tx("Where")].map(h => <th key={h} scope="col" className="py-1 pr-3 font-normal">{h}</th>)}
              </tr></thead>
              <tbody>{rec.inventory.map(r => (
                <tr key={r.key} className="border-t border-slate-700/40 align-top">
                  <th scope="row" className="py-1.5 pr-3 text-left text-slate-200 font-normal">{r.what}</th>
                  <td className="py-1.5 pr-3 text-slate-300">{r.why}</td>
                  <td className="py-1.5 pr-3 text-slate-300">{tx("Encrypted:")}{" "}{r.encrypted}</td>
                  <td className="py-1.5 pr-3 text-slate-300">{r.kept}</td>
                  <td className="py-1.5 text-slate-500 text-xs font-mono">{r.tables.join(', ')}</td>
                </tr>))}</tbody>
            </table>
            <p className="text-slate-400 text-sm mt-3">{tx("Never kept: {v}.", { v: rec.never_stored.join(', ') })}</p>
          </section>

          <section aria-labelledby="h-state" className={card}>
            <h2 id="h-state" className="text-white font-medium mb-2">{tx("Right now")}</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              {Object.entries(rec.counts).map(([k, v]) => (
                <div key={k}><p className="text-white text-lg font-semibold">{v}</p><p className="text-slate-400 text-xs">{k.replace('_', ' ')}</p></div>
              ))}
            </div>
            <p className="text-slate-300 text-sm mt-3">
              {txr("Database file encrypted: <0/> ({database_type}) · Personal details encrypted: <1/> · Logs kept for", [<strong>{rec.encryption.database ? 'yes' : 'no'}</strong>, <strong>{rec.encryption.fields ? 'yes' : 'no'}</strong>], { database_type: rec.encryption.database_type })}{" "}<strong>{rec.retention_days}{" "}{tx("days")}</strong>{" "}{tx("(change in Settings → Privacy & data)")}
            </p>
            <div className="flex flex-wrap items-center gap-3 mt-2">
              <p className="text-slate-400 text-xs">{tx("Last clean-up:")}{" "}{rec.last_purge ? fmt(rec.last_purge.at) : tx("not yet")}</p>
              <button onClick={purge} className="flex items-center gap-1.5 px-3 py-1 text-xs text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-700">
                <Trash2 size={12} aria-hidden="true" />{" "}{tx("Clean up now")}</button>
            </div>
          </section>

          <section aria-labelledby="h-req" className={card}>
            <h2 id="h-req" className="text-white font-medium mb-1">{tx("Answer a request")}</h2>
            <p className="text-slate-400 text-sm mb-2">
              {tx("When someone asks what you hold about them, download it here and send it to them. To delete someone, remove their account under Admin panel; everything about them goes with it. Both are recorded below.")}
            </p>
            <div className="flex flex-wrap gap-2 items-center">
              <label htmlFor="req-who" className="sr-only">{tx("Person")}</label>
              <select id="req-who" value={who} onChange={e => setWho(e.target.value)}
                className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200">
                <option value="">{tx("Choose a person…")}</option>
                {people.map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
              </select>
              <button onClick={exportPerson} disabled={!who}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 disabled:opacity-40">
                <Download size={13} aria-hidden="true" />{" "}{tx("Download their data")}</button>
            </div>
          </section>

          <section aria-labelledby="h-log" className={`${card} overflow-x-auto`}>
            <h2 id="h-log" className="text-white font-medium mb-2">{tx("Who looked at whose details")}</h2>
            {log.length === 0 ? <p className="text-slate-400 text-sm">{tx("Nothing recorded yet. Staff viewing, changing, downloading or removing someone else's details shows up here.")}</p> : (
              <table className="w-full text-sm">
                <thead><tr className="text-slate-400 text-xs text-left">
                  {[tx("When"), tx("Who"), tx("Did"), tx("Whose"), tx("What")].map(h => <th key={h} scope="col" className="py-1 pr-3 font-normal">{h}</th>)}
                </tr></thead>
                <tbody>{log.map((e, i) => (
                  <tr key={i} className="border-t border-slate-700/40">
                    <td className="py-1 pr-3 text-slate-400">{fmt(e.at)}</td>
                    <td className="py-1 pr-3 text-slate-200">{e.who}</td>
                    <td className="py-1 pr-3 text-slate-300">{({ view: 'viewed', edit: 'changed', export: 'downloaded', delete: 'removed' })[e.action] || e.action}</td>
                    <td className="py-1 pr-3 text-slate-200">{e.person}</td>
                    <td className="py-1 text-slate-400">{e.detail}</td>
                  </tr>))}</tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  )
}
