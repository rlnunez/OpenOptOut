import { useEffect, useState, useCallback } from 'react'
import {
  Activity, RefreshCw, AlertTriangle, CheckCircle2, XCircle, Power,
  Clock, ShieldAlert, Search
} from 'lucide-react'
import api from '../api'

const REASON_LABEL = {
  timeout:        { label: 'Timeouts',        icon: Clock,        cls: 'text-amber-400' },
  form_not_found: { label: 'Form not found',  icon: XCircle,      cls: 'text-red-400' },
  captcha:        { label: 'CAPTCHA wall',    icon: ShieldAlert,  cls: 'text-purple-400' },
  error:          { label: 'Errors',          icon: AlertTriangle,cls: 'text-red-400' },
}

function fmtDate(s) {
  if (!s) return '—'
  const d = new Date(s)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function BrokerHealth() {
  const [rows, setRows]       = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter]   = useState('needs_review') // needs_review | disabled | all
  const [search, setSearch]   = useState('')
  const [busy, setBusy]       = useState(null) // broker_id currently toggling

  const load = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (filter === 'needs_review') params.set('needs_review', 'true')
    if (filter === 'disabled')     params.set('disabled_only', 'true')
    api.get(`/brokers/health/all?${params}`)
      .then(r => setRows(r.data))
      .finally(() => setLoading(false))
  }, [filter])

  useEffect(() => { load() }, [load])

  const toggle = async (broker, enable) => {
    setBusy(broker.broker_id)
    try {
      await api.post(`/brokers/${broker.broker_id}/${enable ? 'enable' : 'disable'}`)
      load()
    } catch (e) {
      // leave the row; a reload will show true state
    } finally {
      setBusy(null)
    }
  }

  const visible = rows.filter(r =>
    !search || r.name.toLowerCase().includes(search.toLowerCase()))

  const needsReviewCount = rows.filter(r => r.needs_review).length

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-start justify-between mb-1 flex-wrap gap-2">
        <div>
          <h1 className="text-white text-xl font-semibold flex items-center gap-2">
            <Activity size={20} className="text-shield-500" /> Broker health
          </h1>
          <p className="text-slate-400 text-sm mt-0.5">
            Brokers that have started failing are flagged here and automatically disabled so they
            don't slow or break your runs. Review, fix the add-on, then re-enable.
          </p>
        </div>
        <button onClick={load} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-2 mt-4 mb-4 flex-wrap">
        {[
          { key: 'needs_review', label: `Needs review${needsReviewCount ? ` (${needsReviewCount})` : ''}` },
          { key: 'disabled',     label: 'All disabled' },
          { key: 'all',          label: 'All brokers' },
        ].map(t => (
          <button key={t.key} onClick={() => setFilter(t.key)}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              filter === t.key
                ? 'border-shield-600 bg-shield-900/20 text-white'
                : 'border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-600'}`}>
            {t.label}
          </button>
        ))}
        <div className="relative ml-auto">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter by name"
            className="pl-8 pr-3 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 w-44" />
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm py-12 justify-center">
          <RefreshCw size={14} className="animate-spin" /> Loading broker health…
        </div>
      ) : visible.length === 0 ? (
        <div className="flex flex-col items-center gap-2 text-slate-500 py-12">
          <CheckCircle2 size={28} className="text-emerald-500/70" />
          <p className="text-sm">
            {filter === 'needs_review'
              ? 'No brokers need review — everything is running clean.'
              : 'No brokers match this view.'}
          </p>
        </div>
      ) : (
        <div className="bg-slate-800/40 rounded-xl border border-slate-700/50 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-xs border-b border-slate-700/50">
                  <th className="text-left px-4 py-3 font-normal">Broker</th>
                  <th className="text-left px-4 py-3 font-normal">State</th>
                  <th className="text-left px-4 py-3 font-normal">Last failure</th>
                  <th className="text-left px-4 py-3 font-normal">Success rate</th>
                  <th className="text-right px-4 py-3 font-normal">Action</th>
                </tr>
              </thead>
              <tbody>
                {visible.map(r => {
                  const reason = REASON_LABEL[r.last_failure_reason] || null
                  const ReasonIcon = reason?.icon
                  return (
                    <tr key={r.broker_id} className="border-b border-slate-800/60 last:border-0">
                      <td className="px-4 py-3">
                        <div className="text-slate-200">{r.name}</div>
                        {r.needs_review && (
                          <span className="inline-flex items-center gap-1 mt-0.5 text-[11px] text-amber-300">
                            <AlertTriangle size={10} /> flagged for review
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {r.enabled ? (
                          <span className="inline-flex items-center gap-1.5 text-emerald-300 text-xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Enabled
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-red-300 text-xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
                            {r.auto_disabled ? 'Auto-disabled' : 'Disabled'}
                          </span>
                        )}
                        {!r.enabled && r.auto_disabled_reason && (
                          <div className="text-slate-500 text-[11px] mt-0.5 max-w-xs">{r.auto_disabled_reason}</div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {r.last_failure_reason ? (
                          <div className="flex items-center gap-1.5">
                            {ReasonIcon && <ReasonIcon size={12} className={reason.cls} />}
                            <div>
                              <div className={`text-xs ${reason?.cls || 'text-slate-400'}`}>{reason?.label || r.last_failure_reason}</div>
                              <div className="text-slate-500 text-[11px]">{fmtDate(r.last_failure_at)}</div>
                              {r.last_failure_reason === 'captcha' && (
                                <div className="text-purple-300/80 text-[10px] mt-0.5">
                                  Solver: {r.captcha_plugin_id || 'default'}
                                </div>
                              )}
                            </div>
                          </div>
                        ) : (
                          <span className="text-slate-600 text-xs">none</span>
                        )}
                        {r.consecutive_failures > 0 && (
                          <div className="text-red-400/80 text-[11px] mt-0.5">
                            {r.consecutive_failures} in a row
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {r.success_rate != null ? (
                          <span className={`text-xs ${r.success_rate >= 80 ? 'text-emerald-300' : r.success_rate >= 50 ? 'text-amber-300' : 'text-red-300'}`}>
                            {r.success_rate}%
                          </span>
                        ) : (
                          <span className="text-slate-600 text-xs">—</span>
                        )}
                        <div className="text-slate-500 text-[11px] mt-0.5">
                          {r.total_successes}/{r.total_attempts} ok
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => toggle(r, !r.enabled)}
                          disabled={busy === r.broker_id}
                          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-colors disabled:opacity-40 ${
                            r.enabled
                              ? 'border-slate-700 text-slate-300 hover:bg-slate-800'
                              : 'border-emerald-800 bg-emerald-900/20 text-emerald-200 hover:bg-emerald-900/40'}`}>
                          {busy === r.broker_id
                            ? <RefreshCw size={12} className="animate-spin" />
                            : <Power size={12} />}
                          {r.enabled ? 'Disable' : 'Re-enable'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
