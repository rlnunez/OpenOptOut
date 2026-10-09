import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Terminal, RefreshCw, Download, Search, AlertCircle,
  Pause, Play, Trash2, Sliders, Shield
} from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'

const LEVEL_COLORS = {
  DEBUG:    'text-slate-400 bg-slate-800/60 border-slate-700/50',
  INFO:     'text-sky-300 bg-sky-950/60 border-sky-800/40',
  WARNING:  'text-amber-300 bg-amber-950/60 border-amber-800/40',
  ERROR:    'text-rose-300 bg-rose-950/60 border-rose-800/40',
  CRITICAL: 'text-red-200 bg-red-950/90 border-red-700',
}

const COMMON_SUBSYSTEMS = [
  { value: '', label: 'All Subsystems' },
  { value: 'core.auth', label: 'Auth & SSO' },
  { value: 'core.scheduler', label: 'Scheduler' },
  { value: 'core.optout', label: 'Opt-out Engine' },
  { value: 'plugins', label: 'Plugins' },
  { value: 'core.cert_monitor', label: 'Cert Monitor' },
  { value: 'consortium', label: 'Consortium' },
  { value: 'uvicorn', label: 'API Server' },
]

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

export default function SystemLogs() {
  const { user } = useAuth()
  const canManage = can(user, 'logs.manage')

  const [logs, setLogs]             = useState([])
  const [loading, setLoading]       = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [levelFilter, setLevelFilter] = useState('')
  const [loggerFilter, setLoggerFilter] = useState('')
  const [search, setSearch]         = useState('')
  const [limit, setLimit]           = useState(200)
  const [activeLevel, setActiveLevel] = useState('INFO')
  const [fileInfo, setFileInfo]     = useState(null)
  const [updatingLevel, setUpdatingLevel] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)

  const consoleBottomRef = useRef(null)

  const fetchLogs = useCallback(async (isPolling = false) => {
    if (!isPolling) setLoading(true)
    try {
      const params = new URLSearchParams()
      if (levelFilter)  params.set('level', levelFilter)
      if (loggerFilter) params.set('logger', loggerFilter)
      if (search)       params.set('search', search)
      params.set('limit', String(limit))

      const res = await api.get(`/logs?${params.toString()}`)
      setLogs(res.data.entries || [])
      setActiveLevel(res.data.active_level || 'INFO')
      setFileInfo(res.data.file_info || null)
    } catch (err) {
      console.error('Failed to load system logs:', err)
    } finally {
      if (!isPolling) setLoading(false)
    }
  }, [levelFilter, loggerFilter, search, limit])

  useEffect(() => {
    fetchLogs(false)
  }, [fetchLogs])

  // Auto-refresh interval (every 3 seconds when enabled)
  useEffect(() => {
    if (!autoRefresh) return
    const timer = setInterval(() => {
      fetchLogs(true)
    }, 3000)
    return () => clearInterval(timer)
  }, [autoRefresh, fetchLogs])

  // Scroll to bottom when new logs arrive if autoScroll is enabled
  useEffect(() => {
    if (autoScroll && consoleBottomRef.current) {
      consoleBottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  const handleLevelChange = async (newLevel) => {
    if (!canManage || updatingLevel) return
    setUpdatingLevel(true)
    try {
      const res = await api.post('/logs/level', { level: newLevel })
      setActiveLevel(res.data.level)
      fetchLogs(false)
    } catch (err) {
      console.error('Failed to change log verbosity:', err)
    } finally {
      setUpdatingLevel(false)
    }
  }

  const handleDownload = async () => {
    if (downloading) return
    setDownloading(true)
    try {
      const res = await api.get('/logs/download', { responseType: 'blob' })
      const blob = new Blob([res.data], { type: 'text/plain' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `openoptout-diagnostics-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.log`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Failed to download log archive:', err)
    } finally {
      setDownloading(false)
    }
  }

  const handleClearBuffer = async () => {
    if (!canManage) return
    if (!window.confirm('Clear the in-memory log buffer? (Disk log file will be preserved)')) return
    try {
      await api.post('/logs/clear-buffer')
      setLogs([])
    } catch (err) {
      console.error('Failed to clear log buffer:', err)
    }
  }

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto flex flex-col h-[calc(100vh-4rem)]">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 gap-4 border-b border-slate-800 shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <Terminal className="text-shield-400" size={24} />
            <h1 className="text-xl font-bold text-white">Operational Visibility & Diagnostics</h1>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Real-time diagnostic logs across background workers, authentication providers, and plugins.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Dynamic Verbosity Selector */}
          <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-sm px-2.5 py-1 text-xs text-slate-300">
            <Sliders size={14} className="text-slate-400" />
            <span className="text-slate-400">Verbosity:</span>
            {canManage ? (
              <select
                value={activeLevel}
                onChange={(e) => handleLevelChange(e.target.value)}
                disabled={updatingLevel}
                className="bg-slate-950 border border-slate-700 text-white rounded-sm px-1.5 py-0.5 text-xs font-mono focus:outline-hidden focus:border-shield-500"
              >
                <option value="DEBUG">DEBUG</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
              </select>
            ) : (
              <span className="font-mono text-white font-medium">{activeLevel}</span>
            )}
          </div>

          {/* Auto-Refresh Toggle */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-colors ${
              autoRefresh
                ? 'bg-emerald-950/60 border-emerald-800/60 text-emerald-300 hover:bg-emerald-900/60'
                : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'
            }`}
            title={autoRefresh ? 'Pause live tail' : 'Resume live tail'}
          >
            {autoRefresh ? <Pause size={13} /> : <Play size={13} />}
            <span>{autoRefresh ? 'Live' : 'Paused'}</span>
          </button>

          {/* Refresh Now */}
          <button
            onClick={() => fetchLogs(false)}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
            title="Refresh now"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>

          {/* Download Logs */}
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-xs font-medium bg-shield-600 hover:bg-shield-500 text-white transition-colors"
            title="Download full diagnostic log file"
          >
            <Download size={13} />
            <span>{downloading ? 'Exporting…' : 'Export File'}</span>
          </button>

          {/* Clear Buffer */}
          {canManage && (
            <button
              onClick={handleClearBuffer}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-sm text-xs text-slate-400 hover:text-rose-400 hover:bg-rose-950/40 border border-transparent hover:border-rose-900/50 transition-colors"
              title="Clear in-memory buffer"
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 py-3 shrink-0">
        <div className="flex flex-wrap items-center gap-2">
          {/* Keyword Search */}
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search log messages…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-slate-900 border border-slate-800 text-xs text-white rounded-sm pl-8 pr-3 py-1.5 w-56 focus:outline-hidden focus:border-shield-500 placeholder-slate-500"
            />
          </div>

          {/* Level Filter */}
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-xs text-slate-300 rounded-sm px-2.5 py-1.5 focus:outline-hidden focus:border-shield-500"
          >
            <option value="">All Levels</option>
            <option value="DEBUG">DEBUG & higher</option>
            <option value="INFO">INFO & higher</option>
            <option value="WARNING">WARNING & higher</option>
            <option value="ERROR">ERROR & higher</option>
          </select>

          {/* Subsystem Filter */}
          <select
            value={loggerFilter}
            onChange={(e) => setLoggerFilter(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-xs text-slate-300 rounded-sm px-2.5 py-1.5 focus:outline-hidden focus:border-shield-500"
          >
            {COMMON_SUBSYSTEMS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>

          {/* Limit Filter */}
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="bg-slate-900 border border-slate-800 text-xs text-slate-300 rounded-sm px-2 py-1.5 focus:outline-hidden focus:border-shield-500"
          >
            <option value={100}>Last 100 lines</option>
            <option value={200}>Last 200 lines</option>
            <option value={500}>Last 500 lines</option>
            <option value={1000}>Last 1000 lines</option>
          </select>
        </div>

        {/* Status Indicators */}
        <div className="flex items-center gap-3 text-xs text-slate-400">
          <span>{logs.length} entries shown</span>
          {fileInfo && fileInfo.exists && (
            <span className="hidden sm:inline border-l border-slate-800 pl-3">
              Disk log: <span className="font-mono text-slate-300">{formatBytes(fileInfo.size_bytes)}</span>
            </span>
          )}
          <label className="flex items-center gap-1.5 cursor-pointer border-l border-slate-800 pl-3">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded-sm bg-slate-900 border-slate-800 text-shield-600 focus:ring-0"
            />
            <span>Auto-scroll</span>
          </label>
        </div>
      </div>

      {/* Terminal Log Console */}
      <div className="flex-1 bg-slate-950 border border-slate-800 rounded-lg overflow-hidden flex flex-col min-h-0 font-mono text-xs">
        <div className="bg-slate-900/80 px-4 py-2 border-b border-slate-800 flex items-center justify-between text-slate-400 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
            <span className="ml-2 text-slate-400 text-[11px]">openoptout-diagnostics.log</span>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <Shield size={12} />
            <span>Credentials & PII auto-redacted</span>
          </div>
        </div>

        <div className="flex-1 p-3 overflow-y-auto space-y-1 selection:bg-shield-600/40">
          {logs.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-2 py-12">
              <Terminal size={32} className="opacity-40" />
              <p>No log records matching criteria</p>
            </div>
          ) : (
            logs.map((entry) => {
              const levelCls = LEVEL_COLORS[entry.level] || 'text-slate-400 bg-slate-900 border-slate-800'
              return (
                <div key={entry.id} className="flex items-start gap-2 hover:bg-slate-900/40 px-1 py-0.5 rounded-sm leading-relaxed">
                  <span className="text-slate-500 select-none shrink-0 text-[11px]">
                    {entry.timestamp.replace(' UTC', '')}
                  </span>
                  <span className={`px-1.5 py-0.2 rounded-sm text-[10px] uppercase font-bold border shrink-0 ${levelCls}`}>
                    {entry.level}
                  </span>
                  <span className="text-shield-400/80 shrink-0 max-w-[140px] truncate" title={entry.logger}>
                    [{entry.logger}]
                  </span>
                  <span className="text-slate-200 wrap-break-word flex-1">
                    {entry.message}
                  </span>
                </div>
              )
            })
          )}
          <div ref={consoleBottomRef} />
        </div>
      </div>
    </div>
  )
}
