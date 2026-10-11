import { useEffect, useState, useCallback } from 'react'
import {
  Wand2, RefreshCw, CheckCircle2, XCircle, Undo2, Download, Play, ChevronDown, ChevronUp,
  AlertTriangle, KeyRound, Server, Trash2, ArrowUp, ArrowDown, Search, ShieldCheck,
} from 'lucide-react'
import api from '../api'
import { useAuth } from '../hooks/useAuth'
import { tx } from '../i18n/tx'

const STATUS = {
  queued:           { label: () => tx("Waiting"),             cls: 'text-slate-300 border-slate-600' },
  drafting:         { label: () => tx("Working on it"),       cls: 'text-sky-300 border-sky-700' },
  failed:           { label: () => tx("Couldn't make steps"), cls: 'text-red-300 border-red-800' },
  rehearsal_failed: { label: () => tx("Rehearsal stopped"),   cls: 'text-amber-300 border-amber-700' },
  ready:            { label: () => tx("Ready to check"),      cls: 'text-sky-300 border-sky-700' },
  applied:          { label: () => tx("Fixed automatically"), cls: 'text-emerald-300 border-emerald-700' },
  approved:         { label: () => tx("In use"),              cls: 'text-emerald-300 border-emerald-700' },
  rejected:         { label: () => tx("Rejected"),            cls: 'text-slate-400 border-slate-700' },
  reverted:         { label: () => tx("Undone"),              cls: 'text-slate-400 border-slate-700' },
  superseded:       { label: () => tx("Replaced"),            cls: 'text-slate-400 border-slate-700' },
}
const VIEWS = {
  look: ['ready', 'rehearsal_failed', 'failed', 'queued', 'drafting'],
  inuse: ['applied', 'approved'],
  all: null,
}

function sourceLabel(d, settings) {
  if (d.source === 'rules') return tx("Built-in rules")
  const p = settings?.providers?.[d.source]
  if (p) return p.label
  const l = settings?.local?.find(x => x.pid === d.source)
  return l ? l.name : (d.source || '—')
}

function when(s) {
  return s ? new Date(s + (s.endsWith('Z') ? '' : 'Z')).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''
}

export default function SpecHelpers() {
  const { user } = useAuth()
  const isSuper = user?.role === 'super_admin'
  const [drafts, setDrafts] = useState(null)
  const [view, setView] = useState('look')
  const [settings, setSettings] = useState(null)
  const [msg, setMsg] = useState('')
  const [open, setOpen] = useState(null)

  const load = useCallback(() => {
    const st = VIEWS[view]
    api.get('/spec-helpers/drafts', { params: st ? { status: st.join(',') } : {} })
      .then(r => setDrafts(r.data)).catch(() => setMsg(tx("Couldn't load the drafts.")))
  }, [view])
  const loadSettings = useCallback(() => {
    if (isSuper) api.get('/spec-helpers/settings').then(r => setSettings(r.data)).catch(() => {})
  }, [isSuper])
  useEffect(() => { load() }, [load])
  useEffect(() => { loadSettings() }, [loadSettings])
  useEffect(() => {   // refresh while something is being worked on
    if (!drafts?.some(d => d.status === 'queued' || d.status === 'drafting')) return
    const t = setInterval(load, 8000)
    return () => clearInterval(t)
  }, [drafts, load])

  const act = async (d, what) => {
    setMsg('')
    try {
      const r = await api.post(`/spec-helpers/drafts/${d.id}/${what}`)
      if (r.data?.message) setMsg(r.data.message)
      load()
    } catch (e) { setMsg(e.response?.data?.detail || tx("That didn't work.")) }
  }
  const exportZip = async (d) => {
    try {
      const r = await api.get(`/spec-helpers/drafts/${d.id}/export`, { responseType: 'blob' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(r.data); a.download = `${d.broker}-steps.zip`.replace(/\s+/g, '-'); a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) { setMsg(tx("Couldn't build the plugin file.")) }
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2">
        <Wand2 size={20} className="text-shield-500" aria-hidden="true" />{" "}{tx("Automatic broker steps")}
      </h1>
      <p className="text-slate-400 text-sm mt-1 max-w-3xl">
        {tx("When a broker changes its page and the opt-out steps stop working, OpenOptOut tries to fix them. With an AI helper connected, it can also draft steps for brokers nobody has written steps for. Every draft is rehearsed with made-up details and stops before the final click, so nothing is sent while trying it.")}
      </p>
      <p className="text-slate-500 text-xs mt-2 flex items-start gap-1.5 max-w-3xl">
        <ShieldCheck size={14} className="text-emerald-400 shrink-0 mt-px" aria-hidden="true" />
        {tx("A helper only sees the broker's public opt-out page and its current steps. OpenOptOut checks every request for your family's saved details and refuses to send one that contains any.")}
      </p>

      {msg && <div role="status" className="mt-4 px-3 py-2 rounded-lg border border-slate-700 bg-slate-800/60 text-slate-200 text-sm">{msg}</div>}

      <StartBox onStarted={(m) => { setMsg(m); setView('look'); setTimeout(load, 1500) }} settings={settings} />

      <div className="flex items-center gap-2 mt-6 mb-3 flex-wrap" role="tablist">
        {[['look', tx("Needs a look")], ['inuse', tx("In use")], ['all', tx("Everything")]].map(([k, label]) => (
          <button key={k} role="tab" aria-selected={view === k} onClick={() => setView(k)}
            className={`px-3 py-1.5 rounded-lg text-sm border ${view === k ? 'border-shield-600 bg-shield-900/20 text-white' : 'border-slate-700 text-slate-400 hover:text-slate-200'}`}>
            {label}
          </button>
        ))}
        <button onClick={load} className="ms-auto flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
          <RefreshCw size={13} aria-hidden="true" />{" "}{tx("Refresh")}
        </button>
      </div>

      {drafts === null ? (
        <p className="text-slate-500 text-sm py-8 text-center">{tx("Loading…")}</p>
      ) : drafts.length === 0 ? (
        <p className="text-slate-500 text-sm py-8 text-center">{view === 'inuse' ? tx("No automatic steps are in use.") : tx("Nothing to look at right now.")}</p>
      ) : (
        <ul className="space-y-3">
          {drafts.map(d => (
            <DraftCard key={d.id} d={d} settings={settings} open={open === d.id}
              onToggle={() => setOpen(open === d.id ? null : d.id)} act={act} exportZip={exportZip} />
          ))}
        </ul>
      )}

      {isSuper && settings && <HelperSettings settings={settings} onSaved={(s, m) => { setSettings(s); setMsg(m || tx("Saved.")) }} setMsg={setMsg} />}
    </div>
  )
}

function DraftCard({ d, settings, open, onToggle, act, exportZip }) {
  const st = STATUS[d.status] || STATUS.queued
  const [detail, setDetail] = useState(null)
  const [shot, setShot] = useState(null)
  useEffect(() => {
    if (!open) return
    api.get(`/spec-helpers/drafts/${d.id}`).then(r => setDetail(r.data)).catch(() => {})
    if (d.has_screenshot) {
      api.get(`/spec-helpers/drafts/${d.id}/screenshot`, { responseType: 'blob' })
        .then(r => setShot(URL.createObjectURL(r.data))).catch(() => {})
    }
  }, [open, d.id, d.has_screenshot])
  useEffect(() => () => { if (shot) URL.revokeObjectURL(shot) }, [shot])

  return (
    <li className="bg-slate-800/40 rounded-xl border border-slate-700/50 px-4 py-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-slate-100 font-medium">{d.broker}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${st.cls}`}>{st.label()}</span>
            <span className="text-xs text-slate-400">{d.kind === 'new' ? tx("New steps") : tx("Fix")}</span>
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {tx("Made by {source} · {when}", { source: sourceLabel(d, settings), when: when(d.created_at) })}
          </div>
          {d.rehearsal?.detail && (
            <div className="text-sm text-slate-300 mt-1">{tx("Rehearsal: {detail}", { detail: tx(d.rehearsal.detail) })}</div>
          )}
          {d.status === 'failed' && d.reason && <div className="text-sm text-red-300 mt-1 whitespace-pre-line">{d.reason.trim()}</div>}
          {d.warnings?.map((w, i) => (
            <div key={i} className="text-xs text-amber-300 mt-1 flex items-start gap-1"><AlertTriangle size={12} className="mt-px shrink-0" aria-hidden="true" />{tx(w)}</div>
          ))}
        </div>
        <div className="flex gap-2 flex-wrap items-center">
          {['ready', 'rehearsal_failed'].includes(d.status) && (
            <button onClick={() => act(d, 'approve')} className="flex items-center gap-1 px-2.5 py-1 text-xs text-emerald-200 bg-emerald-900/40 border border-emerald-700 rounded-lg hover:bg-emerald-900/70">
              <CheckCircle2 size={12} aria-hidden="true" />{" "}{tx("Approve")}
            </button>
          )}
          {['ready', 'rehearsal_failed', 'failed'].includes(d.status) && (
            <button onClick={() => act(d, 'reject')} className="flex items-center gap-1 px-2.5 py-1 text-xs text-slate-300 border border-slate-600 rounded-lg hover:bg-slate-800">
              <XCircle size={12} aria-hidden="true" />{" "}{tx("Reject")}
            </button>
          )}
          {['applied', 'approved'].includes(d.status) && (
            <button onClick={() => act(d, 'revert')} className="flex items-center gap-1 px-2.5 py-1 text-xs text-amber-200 border border-amber-700 rounded-lg hover:bg-amber-900/30">
              <Undo2 size={12} aria-hidden="true" />{" "}{tx("Undo")}
            </button>
          )}
          {['failed', 'rehearsal_failed', 'rejected', 'reverted'].includes(d.status) && (
            <button onClick={() => act(d, 'retry')} className="flex items-center gap-1 px-2.5 py-1 text-xs text-sky-200 border border-sky-700 rounded-lg hover:bg-sky-900/30">
              <RefreshCw size={12} aria-hidden="true" />{" "}{tx("Try again")}
            </button>
          )}
          {['ready', 'applied', 'approved'].includes(d.status) && (
            <button onClick={() => exportZip(d)} className="flex items-center gap-1 px-2.5 py-1 text-xs text-slate-300 border border-slate-600 rounded-lg hover:bg-slate-800"
              title={tx("Download these steps as a broker plugin, to share or contribute")}>
              <Download size={12} aria-hidden="true" />{" "}{tx("Save as plugin")}
            </button>
          )}
          <button onClick={onToggle} aria-expanded={open} className="flex items-center gap-1 px-2.5 py-1 text-xs text-slate-300 border border-slate-600 rounded-lg hover:bg-slate-800">
            {open ? <ChevronUp size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />}{" "}{open ? tx("Hide details") : tx("Details")}
          </button>
        </div>
      </div>

      {open && detail && (
        <div className="mt-3 border-t border-slate-700/50 pt-3 space-y-3 text-sm">
          {detail.notes && (
            <div>
              <div className="text-slate-400 text-xs mb-1">{tx("Notes from the helper")}</div>
              <p className="text-slate-300 whitespace-pre-line">{detail.notes}</p>
            </div>
          )}
          {detail.changes?.length > 0 && (
            <div>
              <div className="text-slate-400 text-xs mb-1">{tx("What changed")}</div>
              <ul className="space-y-1">
                {detail.changes.map((c, i) => (
                  <li key={i} className="text-slate-300 text-xs font-mono break-all">
                    {tx("Step {n}", { n: c.step })}: {c.change === 'changed'
                      ? c.fields.map(f => `${f}: ${JSON.stringify(c.before[f] ?? '')} → ${JSON.stringify(c.after[f] ?? '')}`).join('; ')
                      : c.change === 'added' ? tx("added") : tx("removed")}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {detail.steps?.length > 0 && (
            <div>
              <div className="text-slate-400 text-xs mb-1">{tx("Steps")}</div>
              <ol className="space-y-0.5 text-xs font-mono text-slate-300 break-all">
                {detail.steps.map((s, i) => (
                  <li key={i} className={detail.rehearsal?.failed === i ? 'text-amber-300' : (detail.rehearsal?.stop === i ? 'text-sky-300' : '')}>
                    {s.words}{detail.rehearsal?.stop === i ? `  ← ${tx("final click: checked, not pressed")}` : ''}
                    {detail.rehearsal?.failed === i ? `  ← ${tx("stopped here")}` : ''}
                  </li>
                ))}
              </ol>
            </div>
          )}
          {shot && (
            <figure>
              <figcaption className="text-slate-400 text-xs mb-1">{tx("The page at the end of the rehearsal, filled in with made-up details")}</figcaption>
              <img src={shot} alt={tx("Rehearsal of {broker}'s opt-out page", { broker: d.broker })} className="rounded-lg border border-slate-700 max-w-full" />
            </figure>
          )}
        </div>
      )}
    </li>
  )
}

function StartBox({ onStarted, settings }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [broker, setBroker] = useState(null)
  const [provider, setProvider] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!q || (broker && q === broker.name)) { setResults([]); return }
    const t = setTimeout(() => {
      api.get('/brokers', { params: { search: q, limit: 8 } }).then(r => setResults(r.data)).catch(() => {})
    }, 250)
    return () => clearTimeout(t)
  }, [q, broker])

  const helpers = settings ? [
    ...settings.order.filter(p => settings.providers[p]?.enabled).map(p => ({ pid: p, label: settings.providers[p].label })),
    ...settings.local.filter(l => l.enabled).map(l => ({ pid: l.pid, label: l.name })),
  ] : []

  const start = async (what) => {
    if (!broker) return
    setBusy(true); setErr('')
    try {
      const r = await api.post(`/spec-helpers/brokers/${broker.id}/${what}`, provider ? { provider } : {})
      onStarted(r.data.message)
    } catch (e) { setErr(e.response?.data?.detail || tx("That didn't work.")) }
    finally { setBusy(false) }
  }

  return (
    <section className="mt-5 bg-slate-800/40 rounded-xl border border-slate-700/50 px-4 py-3" aria-labelledby="start-h">
      <h2 id="start-h" className="text-slate-100 font-medium text-sm">{tx("Draft or fix steps for one broker")}</h2>
      <div className="flex gap-2 mt-2 flex-wrap items-start">
        <div className="relative">
          <label className="sr-only" htmlFor="broker-q">{tx("Broker")}</label>
          <Search size={13} className="absolute start-2.5 top-2.5 text-slate-500" aria-hidden="true" />
          <input id="broker-q" value={q} onChange={e => { setQ(e.target.value); setBroker(null) }}
            placeholder={tx("Find a broker")} autoComplete="off"
            className="ps-8 pe-3 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 w-64" />
          {results.length > 0 && (
            <ul className="absolute z-10 mt-1 w-64 bg-slate-900 border border-slate-700 rounded-lg overflow-hidden">
              {results.map(b => (
                <li key={b.id}>
                  <button onClick={() => { setBroker(b); setQ(b.name); setResults([]) }}
                    className="w-full text-start px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800">{b.name}</button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {helpers.length > 1 && (
          <select value={provider} onChange={e => setProvider(e.target.value)} aria-label={tx("Which helper")}
            className="py-1.5 px-2 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-200">
            <option value="">{tx("Any helper, in order")}</option>
            {helpers.map(h => <option key={h.pid} value={h.pid}>{h.label}</option>)}
          </select>
        )}
        <button disabled={!broker || busy} onClick={() => start('draft')}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg">
          <Wand2 size={13} aria-hidden="true" />{" "}{tx("Draft new steps")}
        </button>
        <button disabled={!broker || busy} onClick={() => start('repair')}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-200 border border-slate-600 hover:bg-slate-800 disabled:opacity-40 rounded-lg">
          <Play size={13} aria-hidden="true" />{" "}{tx("Rehearse and fix")}
        </button>
      </div>
      <p className="text-slate-500 text-xs mt-2">
        {tx("Drafting new steps needs an AI helper. Fixing tries the built-in rules first, which need no helper.")}
      </p>
      {err && <p role="alert" className="text-red-300 text-sm mt-2">{err}</p>}
    </section>
  )
}

function HelperSettings({ settings, onSaved, setMsg }) {
  const saveOpts = async (patch) => {
    try { onSaved((await api.put('/spec-helpers/settings', patch)).data) }
    catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't save.")) }
  }
  const move = (pid, dir) => {
    const o = [...settings.order]; const i = o.indexOf(pid); const j = i + dir
    if (i < 0 || j < 0 || j >= o.length) return
    ;[o[i], o[j]] = [o[j], o[i]]
    saveOpts({ order: o })
  }
  const nameOf = (pid) => settings.providers[pid]?.label || settings.local.find(l => l.pid === pid)?.name || pid

  return (
    <section className="mt-8" aria-labelledby="helpers-h">
      <h2 id="helpers-h" className="text-white font-semibold">{tx("AI helpers")}</h2>
      <p className="text-slate-400 text-sm mt-1 max-w-3xl">
        {tx("Connect any of these with your own account. A helper is only asked when the built-in rules can't fix a broker's steps, or to draft steps for a new broker.")}
      </p>

      <div className="mt-3 bg-slate-800/40 rounded-xl border border-slate-700/50 px-4 py-3 space-y-2 text-sm">
        <Toggle checked={settings.repair_broken_steps} onChange={v => saveOpts({ repair_broken_steps: v })}
          label={tx("Try to fix steps when a broker's page changes")} />
        <Toggle checked={settings.auto_apply_repairs} onChange={v => saveOpts({ auto_apply_repairs: v })}
          label={tx("Use a fix straight away when it only finds a moved field or button and its rehearsal passed (you'll get a notice and can undo it)")} />
        <Toggle checked={settings.draft_new_brokers} onChange={v => saveOpts({ draft_new_brokers: v })}
          label={tx("Each day, draft steps for one broker that has none (they wait for your approval)")} />
        <label className="flex items-center gap-2 text-slate-300 flex-wrap">
          {tx("Online helper requests per month, at most")}
          <input type="number" min="0" max="10000" defaultValue={settings.monthly_limit}
            onBlur={e => Number(e.target.value) !== settings.monthly_limit && saveOpts({ monthly_limit: Number(e.target.value) })}
            className="w-24 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 px-2 py-1" />
          <span className="text-slate-500 text-xs">{tx("{n} used this month; your own model isn't counted", { n: settings.calls_this_month })}</span>
        </label>
      </div>

      <div className="grid md:grid-cols-3 gap-3 mt-3">
        {Object.entries(settings.providers).map(([pid, p]) => (
          <ProviderCard key={pid} pid={pid} p={p} onSaved={onSaved} setMsg={setMsg} />
        ))}
      </div>

      <LocalModels settings={settings} onSaved={onSaved} setMsg={setMsg} />

      {settings.order.length > 1 && (
        <div className="mt-4">
          <h3 className="text-slate-200 text-sm font-medium">{tx("Order helpers are tried in")}</h3>
          <ol className="mt-1 space-y-1">
            {settings.order.map((pid, i) => (
              <li key={pid} className="flex items-center gap-2 text-sm text-slate-300">
                <span className="w-5 text-slate-500">{i + 1}.</span>{nameOf(pid)}
                <button onClick={() => move(pid, -1)} disabled={i === 0} aria-label={tx("Move {name} up", { name: nameOf(pid) })} className="p-1 text-slate-400 hover:text-white disabled:opacity-30"><ArrowUp size={13} /></button>
                <button onClick={() => move(pid, 1)} disabled={i === settings.order.length - 1} aria-label={tx("Move {name} down", { name: nameOf(pid) })} className="p-1 text-slate-400 hover:text-white disabled:opacity-30"><ArrowDown size={13} /></button>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}

function Toggle({ checked, onChange, label }) {
  return (
    <label className="flex items-start gap-2 text-slate-300 cursor-pointer">
      <input type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} className="mt-1 accent-shield-600" />
      <span>{label}</span>
    </label>
  )
}

function ProviderCard({ pid, p, onSaved, setMsg }) {
  const [key, setKey] = useState('')
  const [model, setModel] = useState(p.model)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const save = async (patch) => {
    setBusy(true)
    try { onSaved((await api.put(`/spec-helpers/providers/${pid}`, patch)).data); setKey('') }
    catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't save.")) }
    finally { setBusy(false) }
  }
  const test = async () => {
    setBusy(true); setResult(null)
    try { setResult((await api.post(`/spec-helpers/providers/${pid}/test`)).data) }
    catch (e) { setResult({ ok: false, message: e.response?.data?.detail || tx("That didn't work.") }) }
    finally { setBusy(false) }
  }
  return (
    <div className="bg-slate-800/40 rounded-xl border border-slate-700/50 px-4 py-3 text-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-slate-100 font-medium flex items-center gap-1.5"><KeyRound size={14} className="text-shield-500" aria-hidden="true" />{p.label}</h3>
        <Toggle checked={p.enabled} onChange={v => save({ enabled: v })} label={<span className="text-xs text-slate-400"><span aria-hidden="true">{tx("On")}</span><span className="sr-only">{tx("Use {name}", { name: p.label })}</span></span>} />
      </div>
      <p className="text-slate-500 text-xs mt-1">{tx(p.key_help)}</p>
      <label className="block mt-2 text-slate-400 text-xs" htmlFor={`key-${pid}`}>{tx("API key")}</label>
      <input id={`key-${pid}`} type="password" value={key} onChange={e => setKey(e.target.value)} autoComplete="off"
        placeholder={p.has_key ? tx("Saved — type to replace") : tx("Paste the key")}
        className="w-full mt-0.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 px-2 py-1 placeholder-slate-500" />
      <label className="block mt-2 text-slate-400 text-xs" htmlFor={`model-${pid}`}>{tx("Model")}</label>
      <input id={`model-${pid}`} list={`models-${pid}`} value={model} onChange={e => setModel(e.target.value)}
        className="w-full mt-0.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 px-2 py-1" />
      <datalist id={`models-${pid}`}>{p.suggested_models.map(m => <option key={m} value={m} />)}</datalist>
      <p className="text-slate-500 text-xs mt-1">{tx("Sends to {host}", { host: p.host })}</p>
      <div className="flex gap-2 mt-2 flex-wrap">
        <button disabled={busy} onClick={() => save({ model, ...(key ? { api_key: key } : {}) })}
          className="px-2.5 py-1 text-xs bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg">{tx("Save")}</button>
        <button disabled={busy || !p.has_key} onClick={test}
          className="px-2.5 py-1 text-xs text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-800 disabled:opacity-40">{tx("Test")}</button>
        {p.has_key && (
          <button disabled={busy} onClick={() => save({ api_key: '' })}
            className="px-2.5 py-1 text-xs text-red-300 border border-red-900 rounded-lg hover:bg-red-950/40">{tx("Remove key")}</button>
        )}
      </div>
      {result && <p role="status" className={`text-xs mt-2 ${result.ok ? 'text-emerald-300' : 'text-red-300'}`}>{result.message}</p>}
    </div>
  )
}

function LocalModels({ settings, onSaved, setMsg }) {
  const blank = { name: '', base_url: '', model: '', api_key: '' }
  const [form, setForm] = useState(null)
  const [results, setResults] = useState({})
  const save = async () => {
    try {
      const body = { ...form, enabled: true }
      if (!body.api_key) delete body.api_key
      const r = form.id ? await api.put(`/spec-helpers/local/${form.id}`, body) : await api.post('/spec-helpers/local', body)
      onSaved(r.data); setForm(null)
    } catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't save.")) }
  }
  const remove = async (l) => {
    if (!window.confirm(tx("Remove the connection to {name}?", { name: l.name }))) return
    onSaved((await api.delete(`/spec-helpers/local/${l.id}`)).data)
  }
  const toggle = async (l, enabled) => {
    try {
      onSaved((await api.put(`/spec-helpers/local/${l.id}`, { name: l.name, base_url: l.base_url, model: l.model, enabled })).data)
    } catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't save.")) }
  }
  const test = async (l) => {
    setResults({ ...results, [l.id]: { message: tx("Asking your model… this can take a while.") } })
    try { const r = (await api.post(`/spec-helpers/providers/${encodeURIComponent(l.pid)}/test`)).data; setResults(x => ({ ...x, [l.id]: r })) }
    catch (e) { setResults(x => ({ ...x, [l.id]: { ok: false, message: tx("That didn't work.") } })) }
  }
  const field = (key, label, placeholder, type = 'text') => (
    <label className="block text-slate-400 text-xs">
      {label}
      <input type={type} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} placeholder={placeholder}
        autoComplete="off" className="w-full mt-0.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 px-2 py-1 text-sm placeholder-slate-500" />
    </label>
  )
  return (
    <div className="mt-4 bg-slate-800/40 rounded-xl border border-slate-700/50 px-4 py-3 text-sm">
      <h3 className="text-slate-100 font-medium flex items-center gap-1.5"><Server size={14} className="text-shield-500" aria-hidden="true" />{tx("Your own model")}</h3>
      <p className="text-slate-500 text-xs mt-1 max-w-3xl">
        {tx("Use a model running on this computer or another one on your network: LM Studio, Ollama, llama.cpp, vLLM, or anything else that offers the OpenAI chat API. Nothing leaves your network, and it isn't counted against the monthly limit. If OpenOptOut runs in Docker, use host.docker.internal or the computer's network address instead of localhost.")}
      </p>
      {settings.local.length > 0 && (
        <ul className="mt-2 space-y-2">
          {settings.local.map(l => (
            <li key={l.id} className="flex items-start justify-between gap-2 flex-wrap border-t border-slate-700/40 pt-2">
              <div>
                <div className="text-slate-200">{l.name} <span className="text-slate-500 text-xs">· {l.model}</span></div>
                <div className="text-slate-500 text-xs font-mono">{l.base_url}</div>
                {results[l.id] && <p role="status" className={`text-xs mt-1 ${results[l.id].ok ? 'text-emerald-300' : results[l.id].ok === false ? 'text-red-300' : 'text-slate-400'}`}>{results[l.id].message}</p>}
              </div>
              <div className="flex gap-2 items-center">
                <Toggle checked={l.enabled} onChange={v => toggle(l, v)} label={<span className="text-xs text-slate-400"><span aria-hidden="true">{tx("On")}</span><span className="sr-only">{tx("Use {name}", { name: l.name })}</span></span>} />
                <button onClick={() => test(l)} className="px-2.5 py-1 text-xs text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-800">{tx("Test")}</button>
                <button onClick={() => setForm({ id: l.id, name: l.name, base_url: l.base_url, model: l.model, api_key: '' })} className="px-2.5 py-1 text-xs text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-800">{tx("Edit")}</button>
                <button onClick={() => remove(l)} aria-label={tx("Remove {name}", { name: l.name })} className="p-1 text-red-300 hover:text-red-200"><Trash2 size={13} /></button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {form ? (
        <div className="grid sm:grid-cols-2 gap-2 mt-3">
          {field('name', tx("Name"), 'LM Studio')}
          {field('base_url', tx("Address"), 'http://localhost:1234/v1')}
          {field('model', tx("Model name, as your server lists it"), 'qwen3-coder-30b')}
          {field('api_key', tx("API key, if your server needs one"), '', 'password')}
          <div className="sm:col-span-2 flex gap-2">
            <button onClick={save} className="px-3 py-1.5 text-xs bg-shield-600 hover:bg-shield-700 text-white rounded-lg">{tx("Save")}</button>
            <button onClick={() => setForm(null)} className="px-3 py-1.5 text-xs text-slate-300">{tx("Cancel")}</button>
          </div>
        </div>
      ) : (
        <button onClick={() => setForm(blank)} className="mt-3 px-3 py-1.5 text-xs text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-800">{tx("Add your own model")}</button>
      )}
    </div>
  )
}
