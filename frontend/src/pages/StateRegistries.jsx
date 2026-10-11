import { useEffect, useState, useCallback, useRef } from 'react'
import { Landmark, Upload, ExternalLink, AlertTriangle, RefreshCw, Power, PowerOff, Save, Activity, X } from 'lucide-react'
import api from '../api'

const inp = 'w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-shield-500'
const btn = 'inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm disabled:opacity-50'

// Confirmation for turning registry brokers on. The person must tick the box
// stating they understand the warning before the button works.
function EnableDialog({ warning, count, onCancel, onConfirm }) {
  const [ack, setAck] = useState(false)
  const boxRef = useRef(null)
  useEffect(() => { boxRef.current?.focus() }, [])
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onKeyDown={e => e.key === 'Escape' && onCancel()}>
      <div role="alertdialog" aria-modal="true" aria-labelledby="enable-title" aria-describedby="enable-warning"
        className="max-w-lg w-full bg-slate-900 border border-amber-700 rounded-xl p-5">
        <div className="flex items-start justify-between gap-2">
          <h2 id="enable-title" className="text-white font-semibold flex items-center gap-2">
            <AlertTriangle size={18} className="text-amber-400" aria-hidden="true" />
            Turn on {count === 'all' ? 'all registry brokers' : `${count} broker${count === 1 ? '' : 's'}`}?
          </h2>
          <button onClick={onCancel} className="text-slate-400 hover:text-white" aria-label="Cancel"><X size={16} /></button>
        </div>
        <p id="enable-warning" className="text-amber-100 text-sm mt-3 leading-relaxed">{warning}</p>
        <label className="flex items-start gap-2 mt-4 text-sm text-slate-200">
          <input ref={boxRef} type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} className="mt-0.5 accent-amber-500" />
          I understand, and I have a reason to think these brokers hold our family's data.
        </label>
        <div className="flex gap-2 mt-4">
          <button disabled={!ack} onClick={onConfirm} className={`${btn} bg-amber-600 hover:bg-amber-500 text-white font-medium`}>
            <Power size={14} aria-hidden="true" /> Turn on
          </button>
          <button onClick={onCancel} className={`${btn} border border-slate-700 text-slate-300`}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

function SourceCard({ src, onDone, setMsg }) {
  const [url, setUrl] = useState(src.url || '')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState('')
  const fileId = `reg-file-${src.state}`

  const send = async (kind) => {
    setBusy(kind)
    try {
      const fd = new FormData()
      if (file) fd.append('file', file)
      const { data } = await api.post(`/registry/${src.state}/${kind}`, fd)
      if (kind === 'preview') setPreview(data)
      else { setMsg(data.message); setPreview(null); setFile(null); onDone() }
    } catch (e) { setMsg(e.response?.data?.detail || 'Something went wrong reading the registry.') }
    finally { setBusy('') }
  }
  const saveUrl = async () => {
    try { await api.put(`/registry/sources/${src.state}`, { url }); setMsg(`Saved the ${src.label} download address.`); onDone() }
    catch (e) { setMsg(e.response?.data?.detail || "Couldn't save that address.") }
  }

  return (
    <li className="p-4 rounded-xl border border-slate-700 bg-slate-900/60">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div>
          <h3 className="text-white font-medium">{src.label}</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            {src.brokers} broker{src.brokers === 1 ? '' : 's'} from this registry
            {src.last_import_at ? ` · last imported ${new Date(src.last_import_at).toLocaleDateString()}` : ' · not imported yet'}
          </p>
        </div>
        <a href={src.page} target="_blank" rel="noopener noreferrer" className="text-shield-400 hover:text-shield-300 text-sm flex items-center gap-1">
          <ExternalLink size={13} aria-hidden="true" /> Open registry
        </a>
      </div>
      <p className="text-sm text-slate-300 mt-2">{src.how}</p>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor={fileId} className="block text-xs text-slate-400 mb-1">Upload the registry file (CSV{''} or Excel)</label>
          <input id={fileId} type="file" accept=".csv,.txt,.xlsx" onChange={e => { setFile(e.target.files?.[0] || null); setPreview(null) }}
            className="block w-full text-sm text-slate-300 file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-slate-700 file:text-slate-100" />
        </div>
        <div>
          <label htmlFor={`reg-url-${src.state}`} className="block text-xs text-slate-400 mb-1">
            Or download automatically each month from
          </label>
          <div className="flex gap-2">
            <input id={`reg-url-${src.state}`} className={inp} placeholder={src.suggested_url || 'https://…'} value={url} onChange={e => setUrl(e.target.value)} />
            <button onClick={saveUrl} className={`${btn} border border-slate-600 text-slate-200 shrink-0`} aria-label={`Save ${src.label} download address`}><Save size={14} aria-hidden="true" /></button>
          </div>
          {src.suggested_url && !src.url && (
            <button onClick={() => setUrl(src.suggested_url)} className="text-xs text-shield-400 underline mt-1">Use the address other tools use</button>
          )}
        </div>
      </div>

      <div className="flex gap-2 mt-3">
        <button disabled={!!busy || (!file && !src.url)} onClick={() => send('preview')} className={`${btn} bg-shield-600 hover:bg-shield-500 text-white`}>
          <Upload size={14} aria-hidden="true" /> {busy === 'preview' ? 'Reading…' : 'Preview import'}
        </button>
      </div>

      {preview && (
        <div className="mt-3 p-3 rounded-lg border border-slate-700 bg-slate-950/60 text-sm" aria-live="polite">
          <p className="text-slate-200">
            {preview.counts.rows} brokers in the file: <strong>{preview.counts.new}</strong> new (they'll be <strong>turned off</strong>),
            {' '}{preview.counts.matched} you already have, {preview.counts.no_longer_listed} no longer listed.
            {preview.rows_skipped > 0 && ` ${preview.rows_skipped} rows had no name or website and were skipped.`}
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Columns used: {Object.entries(preview.columns.used).map(([k, v]) => `${k} ← "${v}"`).join(', ')}
            {preview.columns.ignored.length > 0 && ` · ignored: ${preview.columns.ignored.slice(0, 8).join(', ')}${preview.columns.ignored.length > 8 ? '…' : ''}`}
          </p>
          {preview.new.length > 0 && (
            <details className="mt-2">
              <summary className="text-slate-300 cursor-pointer">Show new brokers</summary>
              <ul className="mt-1 max-h-48 overflow-auto text-xs text-slate-400 columns-1 sm:columns-2">
                {preview.new.map(n => <li key={n.domain}>{n.name} <span className="text-slate-600">({n.domain}{n.family ? ` · ${n.family}` : ''})</span></li>)}
              </ul>
            </details>
          )}
          <button disabled={!!busy} onClick={() => send('import')} className={`${btn} mt-3 bg-emerald-700 hover:bg-emerald-600 text-white`}>
            {busy === 'import' ? 'Importing…' : 'Import'}
          </button>
        </div>
      )}
    </li>
  )
}

export default function StateRegistries() {
  const [info, setInfo] = useState(null)
  const [brokers, setBrokers] = useState([])
  const [filter, setFilter] = useState({ state: '', enabled: '', search: '' })
  const [selected, setSelected] = useState(new Set())
  const [dialog, setDialog] = useState(null)   // null | 'selected' | 'all'
  const [msg, setMsg] = useState('')
  const [checking, setChecking] = useState(false)

  const load = useCallback(() => {
    api.get('/registry/sources').then(r => setInfo(r.data)).catch(() => setMsg("Couldn't load the registries."))
    const params = {}
    if (filter.state) params.state = filter.state
    if (filter.enabled !== '') params.enabled = filter.enabled
    if (filter.search) params.search = filter.search
    api.get('/registry/brokers', { params }).then(r => { setBrokers(r.data); setSelected(new Set()) }).catch(() => {})
  }, [filter])
  useEffect(() => { load() }, [load])

  const toggle = (id) => setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const enable = async () => {
    const body = dialog === 'all' ? { all_registry: true, acknowledge: true } : { broker_ids: [...selected], acknowledge: true }
    try { const { data } = await api.post('/registry/enable', body); setMsg(`Turned on ${data.enabled} broker(s).`) }
    catch (e) { setMsg(e.response?.data?.detail || "Couldn't turn them on.") }
    setDialog(null); load()
  }
  const disable = async () => {
    try { const { data } = await api.post('/registry/disable', { broker_ids: [...selected] }); setMsg(`Turned off ${data.disabled} broker(s).`) }
    catch { setMsg("Couldn't turn them off.") }
    load()
  }
  const checkSites = async () => {
    setChecking(true)
    try { const { data } = await api.post('/registry/check-sites'); setMsg(`Checked ${data.checked} sites; ${data.unreachable} didn't answer.`) }
    catch { setMsg("Couldn't run the site check.") }
    finally { setChecking(false); load() }
  }

  if (!info) return <div className="p-6 text-slate-400 text-sm">Loading…</div>
  const offRegistry = brokers.filter(b => b.origin === 'registry')

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2 mb-1">
        <Landmark size={20} className="text-shield-500" aria-hidden="true" /> State data broker registries
      </h1>
      <p className="text-slate-400 text-sm mb-4 max-w-3xl">
        California, Vermont, Texas and Oregon require data brokers to register. Importing these lists keeps
        OpenOptOut's broker list up to date. New brokers from a registry start <strong className="text-slate-200">turned off</strong>.
        A family member who finds a listing about themselves on one of them still gets an opt-out for it.
      </p>

      <div role="note" className="mb-5 p-3 rounded-lg border border-amber-700 bg-amber-950/30 text-sm text-amber-100 flex gap-2">
        <AlertTriangle size={16} className="shrink-0 mt-0.5 text-amber-400" aria-hidden="true" />
        <span>{info.warning}</span>
      </div>

      {msg && <p role="status" className="mb-3 text-sm text-shield-300">{msg}</p>}

      <section aria-labelledby="sources-h" className="mb-6">
        <h2 id="sources-h" className="text-white font-medium mb-2">Registries</h2>
        <ul className="grid gap-3 md:grid-cols-2">
          {info.sources.map(s => <SourceCard key={s.state} src={s} onDone={load} setMsg={setMsg} />)}
        </ul>
      </section>

      <section aria-labelledby="reg-brokers-h">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <h2 id="reg-brokers-h" className="text-white font-medium">
            Registry brokers <span className="text-slate-400 text-sm font-normal">({info.registry_brokers_on} of {info.registry_brokers} turned on)</span>
          </h2>
          <button onClick={checkSites} disabled={checking} className={`${btn} border border-slate-600 text-slate-200`}>
            <Activity size={14} aria-hidden="true" /> {checking ? 'Checking…' : 'Check for dead sites'}
          </button>
        </div>

        <div className="flex gap-2 flex-wrap mb-3">
          <label className="sr-only" htmlFor="rf-state">State</label>
          <select id="rf-state" className={inp + ' w-auto'} value={filter.state} onChange={e => setFilter(f => ({ ...f, state: e.target.value }))}>
            <option value="">All states</option>
            {info.sources.map(s => <option key={s.state} value={s.state}>{s.label}</option>)}
          </select>
          <label className="sr-only" htmlFor="rf-on">On or off</label>
          <select id="rf-on" className={inp + ' w-auto'} value={filter.enabled} onChange={e => setFilter(f => ({ ...f, enabled: e.target.value }))}>
            <option value="">On and off</option><option value="true">On</option><option value="false">Off</option>
          </select>
          <label className="sr-only" htmlFor="rf-search">Search brokers</label>
          <input id="rf-search" className={inp + ' w-48'} placeholder="Search…" value={filter.search} onChange={e => setFilter(f => ({ ...f, search: e.target.value }))} />
        </div>

        <div className="flex gap-2 flex-wrap mb-2">
          <button disabled={selected.size === 0} onClick={() => setDialog('selected')} className={`${btn} bg-amber-700 hover:bg-amber-600 text-white`}>
            <Power size={14} aria-hidden="true" /> Turn on selected ({selected.size})
          </button>
          <button disabled={selected.size === 0} onClick={disable} className={`${btn} border border-slate-600 text-slate-200`}>
            <PowerOff size={14} aria-hidden="true" /> Turn off selected
          </button>
          <button disabled={info.registry_brokers === info.registry_brokers_on} onClick={() => setDialog('all')} className={`${btn} border border-amber-800 text-amber-200`}>
            Turn on all registry brokers…
          </button>
        </div>

        <div className="overflow-x-auto rounded-lg border border-slate-700/60">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-slate-400 border-b border-slate-800">
              <th scope="col" className="p-2 w-8"><span className="sr-only">Select</span></th>
              <th scope="col" className="p-2 font-medium">Broker</th>
              <th scope="col" className="p-2 font-medium">Registered in</th>
              <th scope="col" className="p-2 font-medium">Status</th>
            </tr></thead>
            <tbody>
              {brokers.length === 0 ? (
                <tr><td colSpan={4} className="p-4 text-slate-500 text-center">No registry brokers yet. Import a registry above.</td></tr>
              ) : brokers.map(b => (
                <tr key={b.id} className="border-b border-slate-800/60">
                  <td className="p-2">
                    {b.origin === 'registry' && (
                      <input type="checkbox" checked={selected.has(b.id)} onChange={() => toggle(b.id)} aria-label={`Select ${b.name}`} className="accent-shield-500" />
                    )}
                  </td>
                  <td className="p-2">
                    <div className="text-slate-200">{b.name}</div>
                    <div className="text-xs text-slate-500 break-all">{b.website}{b.contact_email ? ` · ${b.contact_email}` : ''}</div>
                  </td>
                  <td className="p-2 text-slate-300">{b.states}</td>
                  <td className="p-2">
                    {b.defunct ? <span className="text-red-300">Site gone</span>
                      : b.enabled ? <span className="text-emerald-400">On</span>
                      : <span className="text-slate-400">Off</span>}
                    {b.origin !== 'registry' && <span className="block text-xs text-slate-500">Already in your broker list</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {offRegistry.length >= 200 && <p className="text-xs text-slate-500 mt-1">Showing the first 200. Use the filters to narrow the list.</p>}
      </section>

      {dialog && (
        <EnableDialog warning={info.warning} count={dialog === 'all' ? 'all' : selected.size}
          onCancel={() => setDialog(null)} onConfirm={enable} />
      )}
    </div>
  )
}
