import { useEffect, useState, useCallback } from 'react'
import {
  ListOrdered, RefreshCw, Search, Wand2, AlertTriangle, Download, Upload,
  RotateCcw, CheckSquare, Square, X
} from 'lucide-react'
import api from '../api'
import { tx, txr } from '../i18n/tx'
import { detailText } from '../errorMessage'
import Modal from '../components/Modal'

const PRIORITY_LABELS = { 1: tx("Lowest"), 2: tx("Low"), 3: tx("Medium"), 4: tx("High"), 5: tx("Highest") }
const PRIORITY_COLORS = {
  1: 'text-slate-400', 2: 'text-sky-400', 3: 'text-slate-200',
  4: 'text-amber-400', 5: 'text-red-400',
}
const SOURCE_LABEL = { manual: 'manual', rule: 'rule', default: 'auto' }

export default function BrokerPriority() {
  const [brokers, setBrokers] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch]   = useState('')
  const [selected, setSelected] = useState(new Set())
  const [bulkPriority, setBulkPriority] = useState(4)
  const [showRules, setShowRules] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    api.get('/brokers').then(r => setBrokers(r.data)).finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])

  const visible = brokers.filter(b =>
    !search || b.name.toLowerCase().includes(search.toLowerCase()))

  const setPriority = async (broker, priority) => {
    try {
      await api.patch(`/brokers/${broker.broker_id ?? broker.id}/priority`, { priority })
      load()
    } catch { setMsg(tx("Couldn't change the priority. Please try again.")) }
  }

  const toggleSelect = (id) => {
    setSelected(prev => {
      const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n
    })
  }
  const selectAllVisible = () => {
    setSelected(new Set(visible.map(b => b.broker_id ?? b.id)))
  }
  const clearSelection = () => setSelected(new Set())

  const bulkSet = async () => {
    if (selected.size === 0) return
    try {
      const r = await api.post('/brokers/priority/bulk-set',
        { broker_ids: [...selected], priority: bulkPriority })
      setMsg(tx("Set {updated} broker(s) to {v}", { updated: r.data.updated, v: PRIORITY_LABELS[bulkPriority] }))
      clearSelection(); load()
    } catch { setMsg(tx("Bulk set failed")) }
  }

  const resetOne = async (broker) => {
    try {
      await api.post(`/brokers/${broker.broker_id ?? broker.id}/priority/reset`)
      load()
    } catch { setMsg('Reset failed') }
  }

  const resetAll = async () => {
    if (!window.confirm('Reset ALL brokers to their auto-derived default priority? This clears every manual and rule value.')) return
    try {
      const r = await api.post('/brokers/priority/reset-all')
      setMsg(`Reset ${r.data.reset} broker(s) to default`); load()
    } catch { setMsg('Reset-all failed') }
  }

  const exportPriorities = async (kind) => {
    try {
      const r = await api.get(`/brokers/priority/export?kind=${kind}`)
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `broker-priority-${kind}.json`; a.click()
      URL.revokeObjectURL(url)
    } catch { setMsg(tx("Export failed")) }
  }

  const importFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const r = await api.post('/brokers/priority/import', data)
      setMsg(tx("Imported: {rankings_applied} ranking(s) applied", { rankings_applied: r.data.rankings_applied }) +
        (r.data.rules_found?.length ? tx(", {length} rule(s) found — open Rules to review/run them", { length: r.data.rules_found.length }) : ''))
      load()
    } catch (err) {
      setMsg(tx("Couldn't import that file:") + (detailText(err) || tx("check it is the right format.")))
    } finally { e.target.value = '' }
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-start justify-between mb-1 flex-wrap gap-2">
        <div>
          <h1 className="text-white text-xl font-semibold flex items-center gap-2">
            <ListOrdered size={20} className="text-shield-500" />{" "}{tx("Broker priority")}
          </h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {tx("Priority (1–5) decides which brokers are submitted first within each person's daily limit. Set individually, in bulk, or with rules. Highest-exposure brokers default high.")}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => setShowRules(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-shield-200 border border-shield-700 bg-shield-900/20 rounded-lg hover:bg-shield-900/40">
            <Wand2 size={13} />{" "}{tx("Rules")}
          </button>
          <button onClick={() => exportPriorities('both')}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
            <Download size={13} />{" "}{tx("Export")}
          </button>
          <label className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 cursor-pointer">
            <Upload size={13} />{" "}{tx("Import")}
            <input type="file" accept=".json" className="hidden" onChange={importFile} />
          </label>
          <button onClick={resetAll}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-400 border border-slate-700 rounded-lg hover:bg-slate-800">
            <RotateCcw size={13} />{" "}{tx("Reset all")}
          </button>
        </div>
      </div>

      {msg && (
        <div className="mt-3 px-3 py-2 rounded-lg border border-slate-700 bg-slate-800/60 text-slate-300 text-xs flex items-center justify-between">
          <span>{msg}</span>
          <button onClick={() => setMsg('')} aria-label={tx("Dismiss")} className="text-slate-500 hover:text-slate-300"><X size={13} /></button>
        </div>
      )}

      {/* Bulk bar */}
      <div className="flex items-center gap-2 mt-4 mb-3 flex-wrap">
        <div className="relative">
          <Search size={13} className="absolute start-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder={tx("Filter brokers")}
            className="ps-8 pe-3 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 w-48" />
        </div>
        <button onClick={selected.size ? clearSelection : selectAllVisible}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
          {selected.size ? <Square size={12} /> : <CheckSquare size={12} />}
          {selected.size ? tx("Clear ({size})", { size: selected.size }) : tx("Select all shown")}
        </button>
        {selected.size > 0 && (
          <div className="flex items-center gap-2 ms-auto">
            <span className="text-slate-400 text-xs">{tx("Set {size} to:", { size: selected.size })}</span>
            <select value={bulkPriority} onChange={e => setBulkPriority(+e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2 py-1.5">
              {[5,4,3,2,1].map(p => <option key={p} value={p}>{p} — {PRIORITY_LABELS[p]}</option>)}
            </select>
            <button onClick={bulkSet}
              className="px-3 py-1.5 bg-shield-600 hover:bg-shield-700 text-white text-sm rounded-lg">{tx("Apply")}</button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm py-12 justify-center">
          <RefreshCw size={14} className="animate-spin" />{" "}{tx("Loading…")}
        </div>
      ) : (
        <div className="bg-slate-800/40 rounded-xl border border-slate-700/50 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-xs border-b border-slate-700/50">
                  <th className="w-8 px-3 py-3"></th>
                  <th className="text-start px-4 py-3 font-normal">{tx("Broker")}</th>
                  <th className="text-start px-4 py-3 font-normal">{tx("Status")}</th>
                  <th className="text-start px-4 py-3 font-normal">{tx("Priority")}</th>
                  <th className="text-start px-4 py-3 font-normal">{tx("Source")}</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {visible.map(b => {
                  const id = b.broker_id ?? b.id
                  const sel = selected.has(id)
                  return (
                    <tr key={id} className="border-b border-slate-800/60 last:border-0">
                      <td className="px-3 py-2.5">
                        <button onClick={() => toggleSelect(id)} className="text-slate-500 hover:text-slate-300">
                          {sel ? <CheckSquare size={15} className="text-shield-400" /> : <Square size={15} />}
                        </button>
                      </td>
                      <td className="px-4 py-2.5 text-slate-200">{b.name}</td>
                      <td className="px-4 py-2.5 text-slate-400 text-xs">{b.status}{b.is_property_broker ? tx("· property") : ''}</td>
                      <td className="px-4 py-2.5">
                        <select
                          value={b.priority ?? 3}
                          onChange={e => setPriority(b, +e.target.value)}
                          className={`bg-slate-800 border border-slate-700 rounded-lg text-sm px-2 py-1 ${PRIORITY_COLORS[b.priority ?? 3]}`}>
                          {[5,4,3,2,1].map(p => <option key={p} value={p}>{p} — {PRIORITY_LABELS[p]}</option>)}
                        </select>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`text-xs ${b.priority_source === 'manual' ? 'text-amber-300' : b.priority_source === 'rule' ? 'text-sky-300' : 'text-slate-500'}`}>
                          {SOURCE_LABEL[b.priority_source] || 'auto'}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-end">
                        <button onClick={() => resetOne(b)} title={tx("Reset to default")}
                          className="text-slate-500 hover:text-slate-300"><RotateCcw size={13} /></button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showRules && <RulesModal onClose={() => setShowRules(false)} onApplied={(m) => { setMsg(m); load() }} />}
    </div>
  )
}

function RulesModal({ onClose, onApplied }) {
  const [rule, setRule] = useState({
    set_priority: 5, status: '', difficulty: '', method: '', is_property_broker: '', name_contains: '',
  })
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const buildRule = () => {
    const r = { set_priority: +rule.set_priority }
    if (rule.status) r.status = rule.status
    if (rule.difficulty) r.difficulty = rule.difficulty
    if (rule.method) r.method = rule.method
    if (rule.is_property_broker !== '') r.is_property_broker = rule.is_property_broker === 'true'
    if (rule.name_contains) r.name_contains = rule.name_contains
    return r
  }

  const doPreview = async () => {
    setError(''); setBusy(true)
    try {
      const r = await api.post('/brokers/priority/rule/preview', buildRule())
      setPreview(r.data)
    } catch (e) {
      setError(detailText(e) || tx("Preview failed — a rule must match at least one attribute"))
    } finally { setBusy(false) }
  }

  const doApply = async () => {
    setBusy(true)
    try {
      const r = await api.post('/brokers/priority/rule/apply', buildRule())
      onApplied(tx("Rule applied — {changed} broker(s) changed", { changed: r.data.changed }))
      onClose()
    } catch (e) {
      setError(detailText(e) || tx("Apply failed"))
    } finally { setBusy(false) }
  }

  const field = (label, key, options) => (
    <div>
      <label className="text-slate-400 text-xs block mb-1">{label}</label>
      <select value={rule[key]} onChange={e => { setRule({ ...rule, [key]: e.target.value }); setPreview(null) }}
        className="w-full bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2 py-1.5">
        <option value="">{tx("(any)")}</option>
        {options.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select>
    </div>
  )

  return (
    <Modal
      title={
        <span className="flex items-center gap-2">
          <Wand2 size={16} className="text-shield-400" />
          {" "}
          {tx("Priority rule")}
        </span>
      }
      onClose={onClose}
      maxWidth="max-w-lg"
      className="p-0 overflow-hidden flex flex-col max-h-[85vh]"
    >
      <div className="px-5 py-4 space-y-3 overflow-y-auto flex-1">
          <p className="text-slate-400 text-xs">
            {tx("A rule sets a priority on every broker matching the criteria below. Matching is AND across the fields you set; leave a field on \"(any)\" to ignore it. Preview first — running a rule overwrites existing priorities, including ones you set by hand.")}
          </p>

          <div>
            <label className="text-slate-400 text-xs block mb-1">{tx("Set matching brokers to priority")}</label>
            <select value={rule.set_priority} onChange={e => { setRule({ ...rule, set_priority: e.target.value }); setPreview(null) }}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2 py-1.5">
              {[5,4,3,2,1].map(p => <option key={p} value={p}>{p} — {PRIORITY_LABELS[p]}</option>)}
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {field(tx("Broker status"), 'status', [
              {v:'resistant',l:'resistant'},{v:'inconsistent',l:'inconsistent'},
              {v:'undetermined',l:'undetermined'},{v:'compliant',l:'compliant'}])}
            {field(tx("Difficulty"), 'difficulty', [
              {v:'easy',l:'easy'},{v:'medium',l:'medium'},{v:'hard',l:'hard'}])}
            {field(tx("Method"), 'method', [
              {v:'form',l:'form'},{v:'email',l:'email'},{v:'manual',l:'manual'},{v:'phone',l:'phone'}])}
            {field(tx("Property broker"), 'is_property_broker', [
              {v:'true',l:'yes'},{v:'false',l:'no'}])}
          </div>
          <div>
            <label className="text-slate-400 text-xs block mb-1">{tx("Name contains")}</label>
            <input value={rule.name_contains}
              onChange={e => { setRule({ ...rule, name_contains: e.target.value }); setPreview(null) }}
              placeholder={tx("e.g. people")} 
              className="w-full bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2 py-1.5 placeholder-slate-500" />
          </div>

          {error && <div className="px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs">{error}</div>}

          {preview && (
            <div className="px-3 py-3 rounded-lg border border-amber-800 bg-amber-900/15">
              <div className="flex items-start gap-2">
                <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
                <div className="text-amber-200 text-xs">
                  <p className="font-medium">{tx("This will change {would_change} of {total_matched} matched broker(s).", { would_change: preview.would_change, total_matched: preview.total_matched })}</p>
                  {preview.overwrites_manual > 0 && (
                    <p className="text-amber-300/90 mt-1">
                      {txr("⚠ {overwrites_manual} of those were set <0>manually</0> and will be overwritten.", [<strong />], { overwrites_manual: preview.overwrites_manual })}
                    </p>
                  )}
                  <p className="text-amber-300/70 mt-1">
                    {tx("{overwrites_rule_or_default} had rule/auto values.", { overwrites_rule_or_default: preview.overwrites_rule_or_default })}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
        <div className="px-5 py-4 border-t border-slate-700/50 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-slate-400 hover:text-slate-200">{tx("Cancel")}</button>
          {!preview ? (
            <button onClick={doPreview} disabled={busy}
              className="px-4 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-white text-sm rounded-lg">
              {busy ? tx("Previewing…") : tx("Preview")}
            </button>
          ) : (
            <button onClick={doApply} disabled={busy}
              className="px-4 py-1.5 bg-amber-700 hover:bg-amber-600 disabled:opacity-40 text-white text-sm rounded-lg">
              {busy ? tx("Applying…") : tx("Apply — change {would_change}", { would_change: preview.would_change })}
            </button>
          )}
        </div>
    </Modal>
  )
}
