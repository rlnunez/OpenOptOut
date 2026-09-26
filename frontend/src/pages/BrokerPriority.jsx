import { useEffect, useState, useCallback } from 'react'
import {
  ListOrdered, RefreshCw, Search, Wand2, AlertTriangle, Download, Upload,
  RotateCcw, CheckSquare, Square, X
} from 'lucide-react'
import api from '../api'

const PRIORITY_LABELS = { 1: 'Lowest', 2: 'Low', 3: 'Medium', 4: 'High', 5: 'Highest' }
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
    } catch { setMsg('Failed to set priority') }
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
      setMsg(`Set ${r.data.updated} broker(s) to ${PRIORITY_LABELS[bulkPriority]}`)
      clearSelection(); load()
    } catch { setMsg('Bulk set failed') }
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
    } catch { setMsg('Export failed') }
  }

  const importFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const r = await api.post('/brokers/priority/import', data)
      setMsg(`Imported: ${r.data.rankings_applied} ranking(s) applied` +
        (r.data.rules_found?.length ? `, ${r.data.rules_found.length} rule(s) found — open Rules to review/run them` : ''))
      load()
    } catch (err) {
      setMsg('Import failed: ' + (err.response?.data?.detail || err.message))
    } finally { e.target.value = '' }
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-start justify-between mb-1 flex-wrap gap-2">
        <div>
          <h1 className="text-white text-xl font-semibold flex items-center gap-2">
            <ListOrdered size={20} className="text-shield-500" /> Broker priority
          </h1>
          <p className="text-slate-400 text-sm mt-0.5">
            Priority (1–5) decides which brokers are submitted first within each person's daily
            limit. Set individually, in bulk, or with rules. Highest-exposure brokers default high.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => setShowRules(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-shield-200 border border-shield-700 bg-shield-900/20 rounded-lg hover:bg-shield-900/40">
            <Wand2 size={13} /> Rules
          </button>
          <button onClick={() => exportPriorities('both')}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
            <Download size={13} /> Export
          </button>
          <label className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 cursor-pointer">
            <Upload size={13} /> Import
            <input type="file" accept=".json" className="hidden" onChange={importFile} />
          </label>
          <button onClick={resetAll}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-400 border border-slate-700 rounded-lg hover:bg-slate-800">
            <RotateCcw size={13} /> Reset all
          </button>
        </div>
      </div>

      {msg && (
        <div className="mt-3 px-3 py-2 rounded-lg border border-slate-700 bg-slate-800/60 text-slate-300 text-xs flex items-center justify-between">
          <span>{msg}</span>
          <button onClick={() => setMsg('')} className="text-slate-500 hover:text-slate-300"><X size={13} /></button>
        </div>
      )}

      {/* Bulk bar */}
      <div className="flex items-center gap-2 mt-4 mb-3 flex-wrap">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter brokers"
            className="pl-8 pr-3 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 w-48" />
        </div>
        <button onClick={selected.size ? clearSelection : selectAllVisible}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
          {selected.size ? <Square size={12} /> : <CheckSquare size={12} />}
          {selected.size ? `Clear (${selected.size})` : 'Select all shown'}
        </button>
        {selected.size > 0 && (
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-slate-400 text-xs">Set {selected.size} to:</span>
            <select value={bulkPriority} onChange={e => setBulkPriority(+e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2 py-1.5">
              {[5,4,3,2,1].map(p => <option key={p} value={p}>{p} — {PRIORITY_LABELS[p]}</option>)}
            </select>
            <button onClick={bulkSet}
              className="px-3 py-1.5 bg-shield-600 hover:bg-shield-700 text-white text-sm rounded-lg">Apply</button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm py-12 justify-center">
          <RefreshCw size={14} className="animate-spin" /> Loading…
        </div>
      ) : (
        <div className="bg-slate-800/40 rounded-xl border border-slate-700/50 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-xs border-b border-slate-700/50">
                  <th className="w-8 px-3 py-3"></th>
                  <th className="text-left px-4 py-3 font-normal">Broker</th>
                  <th className="text-left px-4 py-3 font-normal">Status</th>
                  <th className="text-left px-4 py-3 font-normal">Priority</th>
                  <th className="text-left px-4 py-3 font-normal">Source</th>
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
                      <td className="px-4 py-2.5 text-slate-400 text-xs">{b.status}{b.is_property_broker ? ' · property' : ''}</td>
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
                      <td className="px-4 py-2.5 text-right">
                        <button onClick={() => resetOne(b)} title="Reset to default"
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
      setError(e.response?.data?.detail || 'Preview failed — a rule must match at least one attribute')
    } finally { setBusy(false) }
  }

  const doApply = async () => {
    setBusy(true)
    try {
      const r = await api.post('/brokers/priority/rule/apply', buildRule())
      onApplied(`Rule applied — ${r.data.changed} broker(s) changed`)
      onClose()
    } catch (e) {
      setError(e.response?.data?.detail || 'Apply failed')
    } finally { setBusy(false) }
  }

  const field = (label, key, options) => (
    <div>
      <label className="text-slate-400 text-xs block mb-1">{label}</label>
      <select value={rule[key]} onChange={e => { setRule({ ...rule, [key]: e.target.value }); setPreview(null) }}
        className="w-full bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2 py-1.5">
        <option value="">(any)</option>
        {options.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select>
    </div>
  )

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg max-h-[85vh] overflow-y-auto">
        <div className="px-5 py-4 border-b border-slate-700/50 flex items-center justify-between">
          <h2 className="text-white font-semibold flex items-center gap-2"><Wand2 size={16} className="text-shield-400" /> Priority rule</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-200"><X size={18} /></button>
        </div>
        <div className="px-5 py-4 space-y-3">
          <p className="text-slate-400 text-xs">
            A rule sets a priority on every broker matching the criteria below. Matching is AND across
            the fields you set; leave a field on "(any)" to ignore it. Preview first — running a rule
            overwrites existing priorities, including ones you set by hand.
          </p>

          <div>
            <label className="text-slate-400 text-xs block mb-1">Set matching brokers to priority</label>
            <select value={rule.set_priority} onChange={e => { setRule({ ...rule, set_priority: e.target.value }); setPreview(null) }}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2 py-1.5">
              {[5,4,3,2,1].map(p => <option key={p} value={p}>{p} — {PRIORITY_LABELS[p]}</option>)}
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {field('Broker status', 'status', [
              {v:'resistant',l:'resistant'},{v:'inconsistent',l:'inconsistent'},
              {v:'undetermined',l:'undetermined'},{v:'compliant',l:'compliant'}])}
            {field('Difficulty', 'difficulty', [
              {v:'easy',l:'easy'},{v:'medium',l:'medium'},{v:'hard',l:'hard'}])}
            {field('Method', 'method', [
              {v:'form',l:'form'},{v:'email',l:'email'},{v:'manual',l:'manual'},{v:'phone',l:'phone'}])}
            {field('Property broker', 'is_property_broker', [
              {v:'true',l:'yes'},{v:'false',l:'no'}])}
          </div>
          <div>
            <label className="text-slate-400 text-xs block mb-1">Name contains</label>
            <input value={rule.name_contains}
              onChange={e => { setRule({ ...rule, name_contains: e.target.value }); setPreview(null) }}
              placeholder="e.g. people" 
              className="w-full bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2 py-1.5 placeholder-slate-500" />
          </div>

          {error && <div className="px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs">{error}</div>}

          {preview && (
            <div className="px-3 py-3 rounded-lg border border-amber-800 bg-amber-900/15">
              <div className="flex items-start gap-2">
                <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
                <div className="text-amber-200 text-xs">
                  <p className="font-medium">This will change {preview.would_change} of {preview.total_matched} matched broker(s).</p>
                  {preview.overwrites_manual > 0 && (
                    <p className="text-amber-300/90 mt-1">
                      ⚠ {preview.overwrites_manual} of those were set <strong>manually</strong> and will be overwritten.
                    </p>
                  )}
                  <p className="text-amber-300/70 mt-1">
                    {preview.overwrites_rule_or_default} had rule/auto values.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
        <div className="px-5 py-4 border-t border-slate-700/50 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          {!preview ? (
            <button onClick={doPreview} disabled={busy}
              className="px-4 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-white text-sm rounded-lg">
              {busy ? 'Previewing…' : 'Preview'}
            </button>
          ) : (
            <button onClick={doApply} disabled={busy}
              className="px-4 py-1.5 bg-amber-700 hover:bg-amber-600 disabled:opacity-40 text-white text-sm rounded-lg">
              {busy ? 'Applying…' : `Apply — change ${preview.would_change}`}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
