import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Server, Cpu, Activity, RefreshCw, AlertTriangle, CheckCircle2,
  Clock, HardDrive, Layers, Power, PowerOff, ShieldAlert,
  Search, Trash2, ArrowUpRight, Gauge
} from 'lucide-react'
import api from '../api'

function fmtUptime(seconds) {
  if (!seconds || seconds <= 0) return '< 1m'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

export default function WorkerFleet() {
  const [workers, setWorkers] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [filter, setFilter] = useState('all') // all | online | busy | draining | offline
  const [search, setSearch] = useState('')
  const [actionBusy, setActionBusy] = useState(null)
  const [banner, setBanner] = useState(null)

  const timerRef = useRef(null)

  const loadData = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true)
    try {
      const [workersRes, statsRes] = await Promise.all([
        api.get('/workers?timeout_seconds=30'),
        api.get('/workers/stats?timeout_seconds=30'),
      ])
      setWorkers(workersRes.data || [])
      setStats(statsRes.data || null)
    } catch (err) {
      console.error('Failed to load worker fleet data:', err)
    } finally {
      if (showLoader) setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData(true)
  }, [loadData])

  useEffect(() => {
    if (autoRefresh) {
      timerRef.current = setInterval(() => loadData(false), 5000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [autoRefresh, loadData])

  const handleDrain = async (workerId, currentStatus) => {
    const isCurrentlyDraining = currentStatus === 'draining'
    setActionBusy(workerId)
    try {
      await api.post(`/workers/${workerId}/drain`, { drain: !isCurrentlyDraining })
      setBanner({
        type: 'success',
        msg: `Worker '${workerId}' drain instruction set to ${!isCurrentlyDraining}.`,
      })
      await loadData(false)
    } catch (err) {
      setBanner({
        type: 'error',
        msg: `Failed to update drain signal for ${workerId}: ${err?.response?.data?.detail || err.message}`,
      })
    } finally {
      setActionBusy(null)
    }
  }

  const handleDeregister = async (workerId) => {
    if (!window.confirm(`Deregister worker node '${workerId}' from the fleet registry?`)) return
    setActionBusy(workerId)
    try {
      await api.delete(`/workers/${workerId}`)
      setBanner({
        type: 'success',
        msg: `Worker '${workerId}' successfully removed from fleet registry.`,
      })
      await loadData(false)
    } catch (err) {
      setBanner({
        type: 'error',
        msg: `Failed to deregister worker: ${err?.response?.data?.detail || err.message}`,
      })
    } finally {
      setActionBusy(null)
    }
  }

  const handleReclaimLeases = async () => {
    setActionBusy('reclaim')
    try {
      const res = await api.post('/workers/reclaim', { lease_timeout_seconds: 300.0, max_retries: 3 })
      const rep = res.data?.report || {}
      setBanner({
        type: 'success',
        msg: `Lease sweep complete: ${rep.inspected || 0} inspected, ${rep.reclaimed_retried || 0} retried, ${rep.reclaimed_dead_lettered || 0} dead-lettered.`,
      })
      await loadData(false)
    } catch (err) {
      setBanner({
        type: 'error',
        msg: `Lease reclamation failed: ${err?.response?.data?.detail || err.message}`,
      })
    } finally {
      setActionBusy(null)
    }
  }

  const filteredWorkers = workers.filter((w) => {
    if (filter !== 'all' && w.status !== filter) return false
    if (search) {
      const q = search.toLowerCase()
      const matchId = (w.worker_id || '').toLowerCase().includes(q)
      const matchHost = (w.hostname || '').toLowerCase().includes(q)
      if (!matchId && !matchHost) return false
    }
    return true
  })

  const queueDepths = stats?.queue_depths || {}
  const totalQueueDepth = typeof queueDepths === 'object' ? (queueDepths.total || 0) : 0
  const dlqCount = queueDepths.dead_letter || 0
  const inFlightCount = stats?.in_flight_count || 0

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-white flex items-center gap-2.5">
            <Server className="text-shield-400" size={24} />
            Worker Fleet & Telemetry
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Real-time control plane visibility into distributed browser worker nodes, capacity utilization, and queue depths.
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <label className="flex items-center gap-2 text-xs text-slate-300 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg cursor-pointer hover:bg-slate-800/60 transition-colors">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded-sm bg-slate-800 border-slate-700 text-shield-500 focus:ring-0"
            />
            Auto-refresh (5s)
          </label>

          <button
            onClick={() => loadData(true)}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg transition-colors"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>

          <button
            onClick={handleReclaimLeases}
            disabled={actionBusy === 'reclaim'}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-300 bg-amber-950/40 hover:bg-amber-900/60 border border-amber-800/60 rounded-lg transition-colors"
            title="Scan and reclaim orphaned leases from unresponsive or crashed workers"
          >
            <Layers size={13} />
            {actionBusy === 'reclaim' ? 'Sweeping...' : 'Reclaim Stalled Leases'}
          </button>
        </div>
      </div>

      {/* Banner */}
      {banner && (
        <div
          className={`p-3 rounded-lg text-sm flex items-center justify-between border ${
            banner.type === 'error'
              ? 'bg-red-950/40 border-red-800 text-red-300'
              : 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
          }`}
        >
          <span>{banner.msg}</span>
          <button
            onClick={() => setBanner(null)}
            className="text-xs opacity-70 hover:opacity-100 ml-4 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Metric Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Active Nodes */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs uppercase tracking-wider font-semibold">Active Nodes</span>
            <Server size={18} className="text-sky-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">
              {stats?.online_nodes ?? 0}
            </span>
            <span className="text-xs text-slate-400">
              / {stats?.total_nodes ?? 0} registered
            </span>
          </div>
          <div className="mt-2 text-xs flex items-center gap-1.5 text-emerald-400">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            {stats?.online_nodes ? `${stats.online_nodes} online & operational` : 'No active workers'}
          </div>
        </div>

        {/* Slot Capacity & Utilization */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs uppercase tracking-wider font-semibold">Slot Utilization</span>
            <Gauge size={18} className="text-indigo-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">
              {stats?.active_slots ?? 0}
            </span>
            <span className="text-xs text-slate-400">
              / {stats?.total_slots ?? 0} concurrent slots
            </span>
          </div>
          <div className="mt-2">
            <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-indigo-500 h-1.5 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, stats?.utilization_pct || 0)}%` }}
              />
            </div>
            <span className="text-[11px] text-slate-400 mt-1 block">
              {stats?.utilization_pct ?? 0}% fleet load ({stats?.idle_slots ?? 0} slots idle)
            </span>
          </div>
        </div>

        {/* Fleet Task Throughput */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs uppercase tracking-wider font-semibold">Total Processed</span>
            <Activity size={18} className="text-emerald-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">
              {stats?.total_jobs_completed ?? 0}
            </span>
            <span className="text-xs text-emerald-400 font-medium">completed</span>
          </div>
          <div className="mt-2 text-xs text-slate-400 flex items-center justify-between">
            <span>Failures: {stats?.total_jobs_failed ?? 0}</span>
            <span className="text-slate-500">Uptime aggregated</span>
          </div>
        </div>

        {/* Queue Backlog */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs uppercase tracking-wider font-semibold">Queue Backlog</span>
            <Layers size={18} className="text-amber-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">
              {totalQueueDepth}
            </span>
            <span className="text-xs text-slate-400">pending tasks</span>
          </div>
          <div className="mt-2 text-xs flex items-center justify-between">
            <span className="text-cyan-400">{inFlightCount} in-flight</span>
            {dlqCount > 0 ? (
              <span className="text-red-400 font-semibold flex items-center gap-1">
                <AlertTriangle size={12} /> {dlqCount} in DLQ
              </span>
            ) : (
              <span className="text-slate-500">DLQ empty</span>
            )}
          </div>
        </div>
      </div>

      {/* Queue Channel Backlog Details */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4">
        <h2 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
          <Layers size={16} className="text-slate-400" />
          Distributed Queue Channels
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-3">
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
            <span className="text-[11px] text-red-400 uppercase font-semibold block">Critical</span>
            <span className="text-lg font-bold text-white mt-1 block">
              {queueDepths.removal_critical || 0}
            </span>
            <span className="text-[10px] text-slate-500">Priority removal</span>
          </div>

          <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
            <span className="text-[11px] text-amber-400 uppercase font-semibold block">High</span>
            <span className="text-lg font-bold text-white mt-1 block">
              {queueDepths.removal_high || 0}
            </span>
            <span className="text-[10px] text-slate-500">Removal</span>
          </div>

          <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
            <span className="text-[11px] text-sky-400 uppercase font-semibold block">Normal</span>
            <span className="text-lg font-bold text-white mt-1 block">
              {queueDepths.removal_normal || 0}
            </span>
            <span className="text-[10px] text-slate-500">Standard batch</span>
          </div>

          <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
            <span className="text-[11px] text-purple-400 uppercase font-semibold block">Discovery</span>
            <span className="text-lg font-bold text-white mt-1 block">
              {queueDepths.discovery || 0}
            </span>
            <span className="text-[10px] text-slate-500">Query crawler</span>
          </div>

          <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
            <span className="text-[11px] text-yellow-400 uppercase font-semibold block">Retry</span>
            <span className="text-lg font-bold text-white mt-1 block">
              {queueDepths.retry || 0}
            </span>
            <span className="text-[10px] text-slate-500">Transient retry</span>
          </div>

          <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
            <span className="text-[11px] text-emerald-400 uppercase font-semibold block">Results</span>
            <span className="text-lg font-bold text-white mt-1 block">
              {stats?.results_depth || 0}
            </span>
            <span className="text-[10px] text-slate-500">Pending ingestion</span>
          </div>

          <div className={`rounded-lg p-3 border ${dlqCount > 0 ? 'bg-red-950/30 border-red-800/60' : 'bg-slate-950/60 border-slate-800/80'}`}>
            <span className={`text-[11px] uppercase font-semibold block ${dlqCount > 0 ? 'text-red-400' : 'text-slate-400'}`}>
              Dead Letter
            </span>
            <span className={`text-lg font-bold mt-1 block ${dlqCount > 0 ? 'text-red-300' : 'text-white'}`}>
              {dlqCount}
            </span>
            <span className="text-[10px] text-slate-500">Exhausted/Tampered</span>
          </div>
        </div>
      </div>

      {/* Worker Fleet Nodes Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        {/* Table Filters & Search */}
        <div className="p-4 border-b border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 flex-wrap">
            {['all', 'online', 'busy', 'draining', 'offline'].map((st) => (
              <button
                key={st}
                onClick={() => setFilter(st)}
                className={`px-3 py-1 text-xs rounded-md capitalize font-medium transition-colors ${
                  filter === st
                    ? 'bg-shield-600 text-white'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              placeholder="Search worker ID or host..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-lg pl-8 pr-3 py-1.5 w-full sm:w-60 focus:outline-hidden focus:border-shield-500"
            />
          </div>
        </div>

        {/* Table Content */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 font-semibold border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Worker Node</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Active Slots</th>
                <th className="py-3 px-4">Throughput</th>
                <th className="py-3 px-4">Host Telemetry</th>
                <th className="py-3 px-4">Uptime & Heartbeat</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {filteredWorkers.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500">
                    No worker nodes matching current filter or search criteria.
                  </td>
                </tr>
              ) : (
                filteredWorkers.map((w) => {
                  const isBusy = actionBusy === w.worker_id
                  const isOffline = w.status === 'offline'
                  const isDraining = w.status === 'draining'
                  const telemetry = w.telemetry || {}

                  return (
                    <tr key={w.worker_id} className="hover:bg-slate-800/30 transition-colors">
                      {/* Node ID */}
                      <td className="py-3 px-4">
                        <div className="font-semibold text-slate-200 flex items-center gap-1.5">
                          <Cpu size={14} className="text-slate-400" />
                          <span>{w.worker_id}</span>
                        </div>
                        <div className="text-[11px] text-slate-500 mt-0.5">
                          {w.hostname || 'unknown-host'}
                        </div>
                        {w.tags && w.tags.length > 0 && (
                          <div className="flex gap-1 mt-1 flex-wrap">
                            {w.tags.map((tag) => (
                              <span
                                key={tag}
                                className="text-[9px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded-sm"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>

                      {/* Status */}
                      <td className="py-3 px-4">
                        {w.status === 'online' && (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-950/60 text-emerald-400 border border-emerald-800/60">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                            Online
                          </span>
                        )}
                        {w.status === 'busy' && (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-indigo-950/60 text-indigo-400 border border-indigo-800/60">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
                            Busy (At Max)
                          </span>
                        )}
                        {w.status === 'draining' && (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-950/60 text-amber-400 border border-amber-800/60">
                            <PowerOff size={11} />
                            Draining
                          </span>
                        )}
                        {w.status === 'offline' && (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-800 text-slate-400 border border-slate-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
                            Offline
                          </span>
                        )}
                      </td>

                      {/* Slots */}
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-200">
                            {w.active_jobs || 0} / {w.concurrency || 1}
                          </span>
                        </div>
                        <div className="w-24 bg-slate-800 rounded-full h-1 mt-1 overflow-hidden">
                          <div
                            className="bg-shield-500 h-1 rounded-full"
                            style={{
                              width: `${Math.min(100, ((w.active_jobs || 0) / (w.concurrency || 1)) * 100)}%`,
                            }}
                          />
                        </div>
                      </td>

                      {/* Throughput */}
                      <td className="py-3 px-4">
                        <span className="text-emerald-400 font-medium">{w.jobs_completed || 0} ok</span>
                        {w.jobs_failed > 0 && (
                          <span className="text-red-400 ml-2">{w.jobs_failed} failed</span>
                        )}
                      </td>

                      {/* Host Telemetry */}
                      <td className="py-3 px-4 text-slate-400">
                        <div>{telemetry.platform || 'Linux'} {telemetry.cpu_count ? `(${telemetry.cpu_count} vCPU)` : ''}</div>
                        {telemetry.load_avg_1m !== undefined && (
                          <div className="text-[10px] text-slate-500 mt-0.5">
                            Load: {telemetry.load_avg_1m} / {telemetry.load_avg_5m}
                          </div>
                        )}
                        {telemetry.mem_total_mb && (
                          <div className="text-[10px] text-slate-500">
                            RAM: {telemetry.mem_used_pct}% of {Math.round(telemetry.mem_total_mb / 1024)}GB
                          </div>
                        )}
                      </td>

                      {/* Uptime & Heartbeat */}
                      <td className="py-3 px-4">
                        <div className="text-slate-300 flex items-center gap-1">
                          <Clock size={11} className="text-slate-500" />
                          <span>{fmtUptime(w.uptime_seconds)}</span>
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          Ping: {w.heartbeat_age_seconds !== undefined ? `${w.heartbeat_age_seconds}s ago` : 'just now'}
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {!isOffline && (
                            <button
                              onClick={() => handleDrain(w.worker_id, w.status)}
                              disabled={isBusy}
                              className={`p-1.5 rounded transition-colors text-xs flex items-center gap-1 ${
                                isDraining
                                  ? 'bg-amber-900/40 text-amber-300 hover:bg-amber-900/60'
                                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                              }`}
                              title={isDraining ? 'Cancel drain signal' : 'Signal worker to drain and exit'}
                            >
                              <Power size={13} />
                              <span className="hidden sm:inline">{isDraining ? 'Resume' : 'Drain'}</span>
                            </button>
                          )}

                          {isOffline && (
                            <button
                              onClick={() => handleDeregister(w.worker_id)}
                              disabled={isBusy}
                              className="p-1.5 rounded-sm bg-red-950/30 text-red-400 hover:bg-red-900/50 transition-colors text-xs flex items-center gap-1"
                              title="Deregister offline node"
                            >
                              <Trash2 size={13} />
                              <span className="hidden sm:inline">Prune</span>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
