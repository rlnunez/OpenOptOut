import { useEffect, useState } from 'react'
import {
  CalendarClock, AlertTriangle, Clock, CheckCircle,
  RotateCcw, AlarmClock, ChevronDown, Filter, RefreshCw
} from 'lucide-react'
import api from '../api'
import Badge from '../components/Badge'

// ── Helpers ───────────────────────────────────────────────────────────────────

function daysLabel(days) {
  if (days === null || days === undefined) return '—'
  if (days < 0)  return { text: `${Math.abs(days)} day${Math.abs(days) === 1 ? '' : 's'} late`, cls: 'text-red-400' }
  if (days === 0) return { text: 'today',  cls: 'text-orange-400' }
  const t = `in ${days} day${days === 1 ? '' : 's'}`
  if (days <= 7)  return { text: t, cls: 'text-amber-400' }
  if (days <= 30) return { text: t, cls: 'text-yellow-400' }
  return               { text: t, cls: 'text-slate-400' }
}

function UrgencyBar({ days }) {
  const pct = days <= 0 ? 100 : Math.max(0, Math.min(100, 100 - (days / 90) * 100))
  const color = days <= 0 ? 'bg-red-500' : days <= 7 ? 'bg-orange-500' : days <= 30 ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <div className="h-1 w-16 bg-slate-700 rounded-full overflow-hidden">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

// ── Row component ─────────────────────────────────────────────────────────────

function RecheckRow({ req, onRequeue, onSnooze }) {
  const [acting, setActing] = useState(false)
  const label = daysLabel(req.days_until_recheck)

  const requeue = async () => {
    setActing(true)
    try { await onRequeue(req.id) } finally { setActing(false) }
  }

  return (
    <tr className="border-t border-slate-700/30 hover:bg-slate-700/20 transition-colors group">
      <td className="px-4 py-3">
        <p className="text-slate-200 text-sm font-medium">{req.broker_name}</p>
        {req.listing_url && (
          <a href={req.listing_url} target="_blank" rel="noopener noreferrer"
            className="text-slate-600 text-xs hover:text-shield-400 transition-colors truncate block max-w-48">
            {req.listing_url}
          </a>
        )}
      </td>
      <td className="px-4 py-3">
        <span className="text-slate-400 text-sm">{req.member_name}</span>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <UrgencyBar days={req.days_until_recheck} />
          <span className={`text-xs font-mono ${typeof label === 'object' ? label.cls : 'text-slate-400'}`}>
            {typeof label === 'object' ? label.text : label}
          </span>
        </div>
      </td>
      <td className="px-4 py-3">
        <Badge value={req.broker_difficulty} />
      </td>
      <td className="px-4 py-3 text-slate-500 text-xs">
        {req.confirmed_at ? new Date(req.confirmed_at).toLocaleDateString() : '—'}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1">
          <button onClick={requeue} disabled={acting} title="Send the opt-out again"
            className="flex items-center gap-1 px-2 py-1 text-xs text-shield-400 border border-shield-800 bg-shield-900/20 rounded-sm hover:bg-shield-800/30 transition-colors disabled:opacity-40">
            {acting ? <RefreshCw size={10} className="animate-spin" /> : <RotateCcw size={10} />}
            Send again
          </button>
          <SnoozeMenu reqId={req.id} onSnooze={onSnooze} />
        </div>
      </td>
    </tr>
  )
}

function SnoozeMenu({ reqId, onSnooze }) {
  const [open, setOpen] = useState(false)
  const options = [
    { days: 7,  label: '7 days' },
    { days: 30, label: '30 days' },
    { days: 60, label: '60 days' },
    { days: 90, label: '90 days' },
  ]
  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 px-2 py-1 text-xs text-slate-400 border border-slate-700 rounded-sm hover:bg-slate-700 transition-colors">
        <AlarmClock size={10} aria-hidden="true" /> Check later <ChevronDown size={9} aria-hidden="true" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-lg z-10 min-w-28 overflow-hidden">
          {options.map(o => (
            <button key={o.days}
              onClick={() => { onSnooze(reqId, o.days); setOpen(false) }}
              className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 transition-colors">
              In {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Summary cards ─────────────────────────────────────────────────────────────

function SummaryCard({ label, value, icon: Icon, color }) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4">
      <div className="flex items-center justify-between mb-1">
        <p className="text-slate-500 text-xs uppercase tracking-wide">{label}</p>
        <Icon size={13} className={color} />
      </div>
      <p className={`text-2xl font-semibold ${color}`}>{value}</p>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Scheduled() {
  const [overdue,   setOverdue]   = useState([])
  const [upcoming,  setUpcoming]  = useState([])
  const [loading,   setLoading]   = useState(true)
  const [tab,       setTab]       = useState('overdue')   // 'overdue' | 'upcoming'
  const [daysAhead, setDaysAhead] = useState(30)
  const [memberFilter, setMemberFilter] = useState('')

  const load = () => {
    setLoading(true)
    Promise.all([
      api.get('/requests/recheck-due'),
      api.get(`/requests/recheck-upcoming?days_ahead=${daysAhead}`),
    ]).then(([od, up]) => {
      setOverdue(od.data)
      setUpcoming(up.data)
    }).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [daysAhead])

  const requeue = async id => {
    await api.post(`/requests/${id}/requeue`)
    load()
  }

  const snooze = async (id, days) => {
    await api.post(`/requests/${id}/snooze`, { days })
    load()
  }

  const members = [...new Set([...overdue, ...upcoming].map(r => r.member_name))].sort()

  const filterRows = rows =>
    memberFilter ? rows.filter(r => r.member_name === memberFilter) : rows

  const rows = tab === 'overdue' ? filterRows(overdue) : filterRows(upcoming)

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">Check again</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            Brokers often put people back. These removals are due for another look (OpenOptOut checks most of them automatically).
          </p>
        </div>
        <button onClick={load} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <SummaryCard label="Due now"        value={overdue.length}  icon={AlertTriangle} color="text-red-400" />
        <SummaryCard label={`Due in the next ${daysAhead} days`} value={upcoming.length} icon={Clock} color="text-amber-400" />
        <SummaryCard label="Removals shown" value={overdue.length + upcoming.length} icon={CheckCircle} color="text-emerald-400" />
      </div>

      {/* Tabs + filters */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex gap-1 bg-slate-800 p-1 rounded-lg border border-slate-700/50 flex-wrap">
          {[
            { key: 'overdue',  label: `Due now (${overdue.length})` },
            { key: 'upcoming', label: `Coming up (${upcoming.length})` },
          ].map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                tab === t.key ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}>
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Days ahead selector (upcoming only) */}
          {tab === 'upcoming' && (
            <select value={daysAhead} onChange={e => setDaysAhead(parseInt(e.target.value))}
              className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-300 focus:outline-hidden">
              <option value={7}>Next 7 days</option>
              <option value={30}>Next 30 days</option>
              <option value={60}>Next 60 days</option>
              <option value={90}>Next 90 days</option>
            </select>
          )}

          {/* Member filter */}
          {members.length > 1 && (
            <select value={memberFilter} onChange={e => setMemberFilter(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-300 focus:outline-hidden">
              <option value="">Everyone</option>
              {members.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
        {loading ? (
          <p className="text-slate-500 text-sm p-6">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="text-center py-12">
            <CalendarClock size={28} className="text-slate-700 mx-auto mb-2" />
            <p className="text-slate-400 text-sm">
              {tab === 'overdue' ? 'Nothing is due right now.' : `Nothing is due in the next ${daysAhead} days.`}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 text-xs border-b border-slate-700/50">
                <th className="text-left px-4 py-3 font-normal">Site</th>
                <th className="text-left px-4 py-3 font-normal">Person</th>
                <th className="text-left px-4 py-3 font-normal">
                  {tab === 'overdue' ? 'Late by' : 'Due'}
                </th>
                <th className="text-left px-4 py-3 font-normal">Difficulty</th>
                <th className="text-left px-4 py-3 font-normal">Removed on</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <RecheckRow key={r.id} req={r} onRequeue={requeue} onSnooze={snooze} />
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>

      {rows.length > 0 && tab === 'overdue' && (
        <div className="mt-3 flex justify-end">
          <button
            onClick={async () => {
              if (!confirm(`Send all ${rows.length} opt-outs that are due again?`)) return
              await Promise.all(rows.map(r => api.post(`/requests/${r.id}/requeue`)))
              load()
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-shield-400 border border-shield-800 bg-shield-900/20 rounded-lg hover:bg-shield-800/30 transition-colors">
            <RotateCcw size={13} aria-hidden="true" /> Send all due ones again
          </button>
        </div>
      )}
    </div>
  )
}
