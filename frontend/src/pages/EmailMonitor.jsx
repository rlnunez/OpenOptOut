import { useEffect, useState, useCallback } from 'react'
import {
  Mail, RefreshCw, Check, X, Clock, Inbox,
  AlertCircle, Link, LinkOff, Play
} from 'lucide-react'
import api from '../api'
import { useAuth } from '../hooks/useAuth'
import Badge from '../components/Badge'

function StatusDot({ ok }) {
  return <span className={`w-2 h-2 rounded-full inline-block ${ok ? 'bg-emerald-400' : 'bg-slate-600'}`} />
}

function StatCard({ label, value, icon: Icon, color = 'text-slate-300' }) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4">
      <div className="flex items-center justify-between mb-1">
        <p className="text-slate-500 text-xs uppercase tracking-wide">{label}</p>
        <Icon size={13} className={color} />
      </div>
      <p className={`text-2xl font-semibold ${color}`}>{value ?? '—'}</p>
    </div>
  )
}

function EmailRow({ log }) {
  const [expanded, setExpanded] = useState(false)
  const matched = !!log.matched_key
  return (
    <div className="border-t border-slate-700/30">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-700/20 transition-colors text-left"
      >
        <span className={`shrink-0 ${matched ? 'text-emerald-400' : log.direction === 'sent' ? 'text-blue-400' : 'text-slate-600'}`}>
          {log.direction === 'sent' ? <Mail size={13} /> : matched ? <Check size={13} /> : <AlertCircle size={13} />}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-slate-200 text-sm truncate">{log.subject || '(no subject)'}</p>
          {matched && (
            <p className="text-slate-500 text-xs truncate">
              {log.broker_name && <span className="text-emerald-500">{log.broker_name}</span>}
              {log.member_name && <span className="text-slate-600"> · {log.member_name}</span>}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {log.direction === 'received' && (
            matched
              ? <span className="text-xs text-emerald-400 border border-emerald-800 bg-emerald-900/20 px-2 py-0.5 rounded">matched</span>
              : <span className="text-xs text-slate-500 border border-slate-700 px-2 py-0.5 rounded">unmatched</span>
          )}
          {log.direction === 'sent' && (
            <span className="text-xs text-blue-400 border border-blue-800 bg-blue-900/20 px-2 py-0.5 rounded">sent</span>
          )}
          <span className="text-slate-600 text-xs">{new Date(log.received_at).toLocaleString()}</span>
        </div>
      </button>
      {expanded && log.body_snippet && (
        <div className="px-4 pb-3 ml-7">
          <pre className="text-slate-500 text-xs font-mono whitespace-pre-wrap bg-slate-900 rounded-lg p-3 border border-slate-700 max-h-32 overflow-y-auto">
            {log.body_snippet}
          </pre>
          {log.matched_key && (
            <p className="text-slate-600 text-xs mt-1 font-mono">Key: {log.matched_key}</p>
          )}
        </div>
      )}
    </div>
  )
}

function PollHistory({ history }) {
  if (!history.length) return null
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden mt-4">
      <div className="px-4 py-3 border-b border-slate-700/50">
        <p className="text-slate-300 text-sm font-medium">Recent poll history</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-600 border-b border-slate-700/30">
            <th className="text-left px-4 py-2 font-normal">Time</th>
            <th className="text-left px-4 py-2 font-normal">Status</th>
            <th className="text-left px-4 py-2 font-normal">Matched</th>
            <th className="text-left px-4 py-2 font-normal">Duration</th>
          </tr>
        </thead>
        <tbody>
          {history.map(r => {
            const dur = r.finished_at
              ? Math.round((new Date(r.finished_at) - new Date(r.started_at)) / 1000)
              : null
            return (
              <tr key={r.id} className="border-t border-slate-700/20 hover:bg-slate-700/10">
                <td className="px-4 py-2 text-slate-400">{new Date(r.started_at).toLocaleString()}</td>
                <td className="px-4 py-2">
                  <span className={r.status === 'done' ? 'text-emerald-400' : r.status === 'error' ? 'text-red-400' : 'text-amber-400'}>
                    {r.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-slate-300">{r.emails_matched}</td>
                <td className="px-4 py-2 text-slate-500">{dur != null ? `${dur}s` : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      </div>
    </div>
  )
}

export default function EmailMonitor() {
  const { user }   = useAuth()
  const [status,   setStatus]   = useState(null)
  const [logs,     setLogs]     = useState([])
  const [history,  setHistory]  = useState([])
  const [loading,  setLoading]  = useState(true)
  const [polling,  setPolling]  = useState(false)
  const [filter,   setFilter]   = useState('all')  // 'all' | 'matched' | 'unmatched' | 'sent'
  const isAdmin = user?.role === 'super_admin'

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([
      api.get('/email-monitor/status'),
      api.get('/email-monitor/logs?limit=50'),
      api.get('/email-monitor/poll-history?limit=10'),
    ]).then(([s, l, h]) => {
      setStatus(s.data); setLogs(l.data); setHistory(h.data)
    }).finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 30s
  useEffect(() => {
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [load])

  const triggerPoll = async () => {
    setPolling(true)
    try {
      await api.post('/email-monitor/poll')
      setTimeout(load, 3000)
    } finally { setPolling(false) }
  }

  const filteredLogs = logs.filter(l => {
    if (filter === 'matched')   return l.direction === 'received' && l.matched_key
    if (filter === 'unmatched') return l.direction === 'received' && !l.matched_key
    if (filter === 'sent')      return l.direction === 'sent'
    return true
  })

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">Email monitor</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            Tracking confirmation emails from data brokers
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
            <RefreshCw size={13} /> Refresh
          </button>
          {isAdmin && (
            <button onClick={triggerPoll} disabled={polling || !status?.configured}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 disabled:opacity-40 transition-colors">
              {polling ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
              {polling ? 'Polling…' : 'Poll now'}
            </button>
          )}
        </div>
      </div>

      {loading && <p className="text-slate-500 text-sm">Loading…</p>}

      {!loading && (
        <>
          {/* Connection status banner */}
          {!status?.configured && (
            <div className="mb-4 flex items-center gap-2 px-4 py-3 bg-amber-900/20 border border-amber-800 rounded-xl">
              <AlertCircle size={14} className="text-amber-400 shrink-0" />
              <p className="text-amber-300 text-sm">
                Email not configured. Go to <a href="/settings" className="underline hover:text-amber-200">Settings → Email</a> to set up your IMAP inbox.
              </p>
            </div>
          )}

          {status?.configured && (
            <div className="mb-4 flex items-center gap-3 px-4 py-3 bg-slate-800 border border-slate-700/50 rounded-xl">
              <StatusDot ok={status.last_poll_status === 'done'} />
              <div className="flex-1">
                <p className="text-slate-200 text-sm">
                  <span className="font-medium">{status.imap_user}</span>
                  <span className="text-slate-500"> on {status.imap_host}</span>
                </p>
                <p className="text-slate-500 text-xs">
                  Polls every {status.poll_interval_minutes}m
                  {status.last_poll && ` · last poll ${new Date(status.last_poll).toLocaleString()}`}
                </p>
              </div>
              <span className={`text-xs border px-2 py-0.5 rounded ${
                status.last_poll_status === 'done' ? 'text-emerald-400 border-emerald-800 bg-emerald-900/20'
                : status.last_poll_status === 'error' ? 'text-red-400 border-red-800 bg-red-900/20'
                : 'text-slate-500 border-slate-700'
              }`}>
                {status.last_poll_status ?? 'never polled'}
              </span>
            </div>
          )}

          {/* Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
            <StatCard label="Confirmations matched" value={status?.total_matched}   icon={Check}    color="text-emerald-400" />
            <StatCard label="Unmatched received"    value={status?.total_unmatched} icon={AlertCircle} color="text-amber-400" />
            <StatCard label="Poll interval"         value={status?.configured ? `${status.poll_interval_minutes}m` : 'off'} icon={Clock} />
          </div>

          {/* Log table */}
          <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
              <p className="text-slate-300 text-sm font-medium">Email log</p>
              <div className="flex gap-1 bg-slate-900 p-1 rounded-lg">
                {[
                  { key: 'all',       label: `All (${logs.length})` },
                  { key: 'matched',   label: `Matched (${logs.filter(l => l.direction==='received' && l.matched_key).length})` },
                  { key: 'unmatched', label: `Unmatched (${logs.filter(l => l.direction==='received' && !l.matched_key).length})` },
                  { key: 'sent',      label: `Sent (${logs.filter(l => l.direction==='sent').length})` },
                ].map(f => (
                  <button key={f.key} onClick={() => setFilter(f.key)}
                    className={`px-2.5 py-1 text-xs rounded transition-colors ${
                      filter === f.key ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'
                    }`}>{f.label}</button>
                ))}
              </div>
            </div>
            {filteredLogs.length === 0 ? (
              <div className="text-center py-10">
                <Inbox size={24} className="text-slate-700 mx-auto mb-2" />
                <p className="text-slate-500 text-sm">No emails yet</p>
                <p className="text-slate-600 text-xs mt-1">
                  {status?.configured ? 'Emails will appear here after the next poll.' : 'Configure your email inbox in Settings first.'}
                </p>
              </div>
            ) : (
              filteredLogs.map(l => <EmailRow key={l.id} log={l} />)
            )}
          </div>

          <PollHistory history={history} />
        </>
      )}
    </div>
  )
}
