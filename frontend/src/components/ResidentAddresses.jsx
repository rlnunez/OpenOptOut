import { useEffect, useState } from 'react'
import { Upload, Download, Search, Trash2, AlertTriangle } from 'lucide-react'
import api from '../api'
import { tx, txn } from '../i18n/tx'
import { fmtDateTime, fmtNumber } from '../i18n/format'
import { detailText } from '../errorMessage'

const inp = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"
const small = "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border border-slate-600 text-slate-300 hover:text-white hover:border-slate-500 disabled:opacity-50"

// Admin → Branding → Registration: the community's address list for
// residents-only sign-up (backend/routers/resident_addresses.py).
export default function ResidentAddresses() {
  const [sum, setSum] = useState(null)
  const [file, setFile] = useState(null)
  const [replace, setReplace] = useState(true)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState('')
  const [test, setTest] = useState({ street: '', unit: '', zip: '' })
  const [testResult, setTestResult] = useState(null)

  const load = () => api.get('/resident-addresses').then(r => setSum(r.data)).catch(() => {})
  useEffect(() => { load() }, [])

  const upload = async e => {
    e.preventDefault()
    if (!file) return
    setBusy(true); setErr(''); setResult(null)
    const body = new FormData()
    body.append('file', file)
    body.append('replace', replace ? 'true' : 'false')
    try {
      const { data } = await api.post('/resident-addresses/upload', body)
      setResult(data); setSum(data.summary); setFile(null); e.target.reset()
    } catch (e2) {
      setErr(detailText(e2) || tx("Couldn't read the file."))
    } finally { setBusy(false) }
  }

  const example = async () => {
    const r = await api.get('/resident-addresses/example.csv', { responseType: 'blob' })
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a')
    a.href = url; a.download = 'addresses-example.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  const check = async e => {
    e.preventDefault(); setTestResult(null)
    const { data } = await api.post('/resident-addresses/check', test)
    setTestResult(data)
  }

  const removeAll = async () => {
    if (!confirm(tx("Remove the whole address list? People who already have accounts keep them, but nobody new can sign up until you upload a list again."))) return
    await api.delete('/resident-addresses'); setResult(null); load()
  }

  // The server's reasons for a row it couldn't use, in the admin's language.
  const REASONS = {
    "Start the street address with the house or building number.": tx("Start the street address with the house or building number."),
    "Add the street name after the number.": tx("Add the street name after the number."),
    "Add the 5-digit ZIP code.": tx("Add the 5-digit ZIP code."),
  }

  const STATUS = {
    ok: tx("On the list. Someone at this address can sign up."),
    unit_needed: tx("The list has units for this building. The person will be asked for theirs."),
    unit_not_found: tx("This building is on the list, but not this unit."),
    not_found: tx("Not on the list."),
    unclear: tx("That address isn't complete. Add the house number, street and ZIP code."),
  }

  return (
    <div className="border-t border-slate-700/50 pt-4 space-y-4">
      <div>
        <p className="text-slate-400 text-xs font-medium uppercase tracking-wide mb-1">{tx("Address list")}</p>
        {sum && (sum.addresses > 0 ? (
          <p className="text-slate-300 text-sm">
            {txn(sum.addresses, "{n} address on the list", "{n} addresses on the list", { n: fmtNumber(sum.addresses) })}
            {" · "}{txn(sum.accounts, "{n} account made at them", "{n} accounts made at them", { n: fmtNumber(sum.accounts) })}
            {sum.updated_at && <span className="text-slate-500">{" · "}{tx("updated {when}", { when: fmtDateTime(sum.updated_at) })}</span>}
          </p>
        ) : (
          <p className="text-amber-300 text-sm flex items-center gap-1.5">
            <AlertTriangle size={14} aria-hidden="true" />{tx("No list yet. Until you upload one, nobody can sign up.")}
          </p>
        ))}
      </div>

      <form onSubmit={upload} className="space-y-2">
        <p className="text-slate-500 text-xs">
          {tx("Upload a CSV file with one address per row: address, unit, city, state and zip columns, or house_number and street_name. A row without a unit stands for the whole building. An optional branch column puts new accounts in that branch. Your county's mapping or property office can usually give you an export.")}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="ra-file">{tx("Address list file")}</label>
          <input id="ra-file" type="file" accept=".csv,text/csv" onChange={e => setFile(e.target.files?.[0] || null)}
            className="text-sm text-slate-300 file:me-3 file:rounded-lg file:border-0 file:bg-slate-700 file:px-3 file:py-1.5 file:text-slate-200" />
          <button type="button" onClick={example} className={small}><Download size={13} aria-hidden="true" />{tx("Example file")}</button>
        </div>
        <fieldset className="flex flex-wrap gap-4 text-sm text-slate-300">
          <legend className="sr-only">{tx("What to do with the file")}</legend>
          <label className="flex items-center gap-2"><input type="radio" checked={replace} onChange={() => setReplace(true)} />{tx("Replace the list")}</label>
          <label className="flex items-center gap-2"><input type="radio" checked={!replace} onChange={() => setReplace(false)} />{tx("Add to the list")}</label>
        </fieldset>
        <button type="submit" disabled={!file || busy} className={small}><Upload size={13} aria-hidden="true" />{busy ? tx("Uploading…") : tx("Upload")}</button>
        {err && <p role="alert" className="text-red-400 text-sm">{err}</p>}
        {result && (
          <div role="status" className="text-sm text-slate-300 space-y-1">
            <p>{txn(result.added, "Added {n} address.", "Added {n} addresses.", { n: fmtNumber(result.added) })}
              {result.already_listed > 0 && <>{" "}{txn(result.already_listed, "{n} was already on the list.", "{n} were already on the list.", { n: fmtNumber(result.already_listed) })}</>}
            </p>
            {result.skipped > 0 && (
              <details className="text-amber-300">
                <summary className="cursor-pointer">{txn(result.skipped, "{n} row couldn't be used.", "{n} rows couldn't be used.", { n: fmtNumber(result.skipped) })}</summary>
                <ul className="mt-1 ms-4 list-disc text-slate-400 text-xs">
                  {result.problems.map(p => <li key={p.line}>{tx("Row {line}: {reason}", { line: fmtNumber(p.line), reason: REASONS[p.reason] || p.reason })}</li>)}
                </ul>
              </details>
            )}
          </div>
        )}
      </form>

      {sum?.addresses > 0 && (
        <form onSubmit={check} className="space-y-2">
          <p className="text-slate-400 text-xs">{tx("Try an address the way the sign-up page will check it.")}</p>
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_8rem_7rem_auto] gap-2">
            <input aria-label={tx("Street address")} className={inp} placeholder={tx("Street address")} value={test.street} onChange={e => setTest(t => ({ ...t, street: e.target.value }))} required />
            <input aria-label={tx("Unit")} className={inp} placeholder={tx("Unit")} value={test.unit} onChange={e => setTest(t => ({ ...t, unit: e.target.value }))} />
            <input aria-label={tx("ZIP code")} className={inp} placeholder={tx("ZIP code")} value={test.zip} onChange={e => setTest(t => ({ ...t, zip: e.target.value }))} required />
            <button type="submit" className={small}><Search size={13} aria-hidden="true" />{tx("Check")}</button>
          </div>
          {testResult && (
            <p role="status" className={`text-sm ${testResult.status === 'ok' ? 'text-green-400' : 'text-amber-300'}`}>
              {STATUS[testResult.status]}
              {testResult.status === 'ok' && <>{" "}{txn(testResult.accounts, "{n} account here so far.", "{n} accounts here so far.", { n: fmtNumber(testResult.accounts) })}</>}
            </p>
          )}
        </form>
      )}

      {sum?.addresses > 0 && (
        <button type="button" onClick={removeAll} className="flex items-center gap-1.5 text-sm text-red-400 hover:text-red-300">
          <Trash2 size={13} aria-hidden="true" />{tx("Remove the list")}
        </button>
      )}
    </div>
  )
}
