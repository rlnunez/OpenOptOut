import { useEffect, useState } from 'react'
import { Download, RefreshCw, Users, Send, CheckCircle, TrendingUp } from 'lucide-react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import api from '../api'
import { downloadReport } from '../components/PrivacyScore'
import { useAuth, can } from '../hooks/useAuth'
import { tx } from '../i18n/tx'
import { fmtDate } from '../i18n/format'

function StatCard({ label, value, sub, icon: Icon, color = 'text-slate-300' }) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4">
      <div className="flex items-center justify-between mb-1">
        <p className="text-slate-500 text-xs uppercase tracking-wide">{label}</p>
        <Icon size={13} className={color} />
      </div>
      <p className={`text-2xl font-semibold ${color}`}>{value ?? '—'}</p>
      {sub && <p className="text-slate-600 text-xs mt-1">{sub}</p>}
    </div>
  )
}

const CHART_THEME = {
  grid:      '#334155',
  text:      '#94a3b8',
  sent:      '#6366f1',
  confirmed: '#10b981',
  users:     '#0ea5e9',
}

function ChartCard({ title, children }) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4 mb-4">
      <p className="text-slate-300 text-sm font-medium mb-4">{title}</p>
      {children}
    </div>
  )
}

export default function Reporting() {
  const { user } = useAuth()
  // The server lists only members this user can already open; say so here.
  const fullMemberList = can(user, 'consortium.cross_system')
  const canNameMembers = can(user, 'members.view_all', 'members.edit_all', 'consortium.cross_system')
  const [summary,    setSummary]    = useState(null)
  const [enrollments, setEnrollments] = useState([])
  const [optouts,    setOptouts]    = useState([])
  const [compliance, setCompliance] = useState([])
  const [perMember,  setPerMember]  = useState([])
  const [health,     setHealth]     = useState({})
  const [loading,    setLoading]    = useState(true)
  const [months,     setMonths]     = useState(12)

  const load = () => {
    setLoading(true)
    Promise.all([
      api.get('/reporting/summary'),
      api.get(`/reporting/enrollments-over-time?months=${months}`),
      api.get(`/reporting/optouts-over-time?months=${months}`),
      api.get('/reporting/broker-compliance?limit=20'),
      api.get('/reporting/per-member'),
      api.get('/reporting/scheduler-health'),
    ]).then(([s, e, o, c, m, h]) => {
      setSummary(s.data); setEnrollments(e.data); setOptouts(o.data)
      setCompliance(c.data); setPerMember(m.data); setHealth(h.data)
    }).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [months])

  const exportCSV = () => {
    const rows = [
      [tx("Person"), tx("Total"), tx("Removed"), tx("Waiting"), tx("Didn't work"), tx("Removed %")],
      ...perMember.map(m => [m.member, m.total, m.confirmed, m.pending, m.failed, `${m.rate}%`]),
    ]
    const csv  = rows.map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const a    = document.createElement('a')
    a.href     = URL.createObjectURL(blob)
    a.download = `openoptout-report-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">{tx("Usage reporting")}</h1>
          <p className="text-slate-400 text-sm mt-0.5">{tx("Institutional metrics for administrators and managers")}</p>
        </div>
        <div className="flex gap-2">
          <select value={months} onChange={e => setMonths(parseInt(e.target.value))}
            aria-label={tx("Time range")}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-300 focus:outline-hidden">
            <option value={3}>{tx("Last 3 months")}</option>
            <option value={6}>{tx("Last 6 months")}</option>
            <option value={12}>{tx("Last 12 months")}</option>
            <option value={24}>{tx("Last 24 months")}</option>
          </select>
          <button onClick={load} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
            <RefreshCw size={13} />{" "}{tx("Refresh")}
          </button>
          <button onClick={exportCSV} className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 transition-colors">
            <Download size={13} />{" "}{tx("Export CSV")}
          </button>
          <button onClick={() => downloadReport('all').catch(() => alert(tx("Couldn't make the report. Please try again.")))}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
            <Download size={13} />{" "}{tx("Removal report (PDF)")}
          </button>
        </div>
      </div>

      {loading && <p className="text-slate-500 text-sm">{tx("Loading…")}</p>}

      {!loading && summary && (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
            <StatCard label={tx("Total users")}       value={summary.total_users}      icon={Users}       color="text-slate-300"   sub={tx("+{month_new_users} this month", { month_new_users: summary.month_new_users })} />
            <StatCard label={tx("Opt-outs sent")}     value={summary.total_sent}       icon={Send}        color="text-shield-400"  sub={tx("{month_sent} this month", { month_sent: summary.month_sent })} />
            <StatCard label={tx("Confirmed removed")} value={summary.total_confirmed}  icon={CheckCircle} color="text-emerald-400" sub={tx("{success_rate}% success rate", { success_rate: summary.success_rate })} />
            <StatCard label={tx("Brokers tracked")}   value={summary.total_brokers}    icon={TrendingUp}  color="text-amber-400"   sub={`${summary.total_pending} pending`} />
          </div>

          {/* Enrollment trend */}
          {enrollments.length > 0 && (
            <ChartCard title={tx("User enrollments over time")}>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={enrollments}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
                  <XAxis dataKey="month" tick={{ fill: CHART_THEME.text, fontSize: 11 }} />
                  <YAxis tick={{ fill: CHART_THEME.text, fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }} />
                  <Bar dataKey="enrollments" fill={CHART_THEME.users} radius={[3,3,0,0]} name="New users" />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* Opt-out trend */}
          {optouts.length > 0 && (
            <ChartCard title={tx("Opt-outs sent vs confirmed")}>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={optouts}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
                  <XAxis dataKey="month" tick={{ fill: CHART_THEME.text, fontSize: 11 }} />
                  <YAxis tick={{ fill: CHART_THEME.text, fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 12, color: CHART_THEME.text }} />
                  <Line type="monotone" dataKey="sent"      stroke={CHART_THEME.sent}      strokeWidth={2} dot={false} name="Sent" />
                  <Line type="monotone" dataKey="confirmed" stroke={CHART_THEME.confirmed}  strokeWidth={2} dot={false} name="Confirmed" />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* Broker compliance */}
          {compliance.length > 0 && (
            <ChartCard title={tx("Broker compliance rates (top 20 by volume)")}>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={compliance} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} tick={{ fill: CHART_THEME.text, fontSize: 10 }}
                    tickFormatter={v => `${v}%`} />
                  <YAxis type="category" dataKey="broker" tick={{ fill: CHART_THEME.text, fontSize: 10 }} width={140} />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                    formatter={(v, n, p) => [`${v}% (${p.payload.confirmed}/${p.payload.total})`, 'Compliance']}
                  />
                  <Bar dataKey="rate" fill={CHART_THEME.confirmed} radius={[0,3,3,0]} name="Compliance %" />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* Per-member table */}
          <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden mb-4">
            <div className="px-4 py-3 border-b border-slate-700/50 flex items-center justify-between">
              <p className="text-slate-300 text-sm font-medium">{tx("Per-member summary")}</p>
              <p className="text-slate-500 text-xs">{perMember.length} {perMember.length === 1 ? 'member' : 'members'}</p>
            </div>
            {!fullMemberList && (
              <p className="px-4 py-2 text-slate-500 text-xs border-b border-slate-700/50">
                {canNameMembers
                  ? tx("Showing only members you have access to.")
                  : tx("Showing only your own and shared profiles. Listing other members needs the “View all members' data” permission.")}
              </p>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-xs border-b border-slate-700/30">
                  <th className="text-start px-4 py-2 font-normal">{tx("Person")}</th>
                  <th className="text-start px-4 py-2 font-normal">{tx("Total")}</th>
                  <th className="text-start px-4 py-2 font-normal">{tx("Removed")}</th>
                  <th className="text-start px-4 py-2 font-normal">{tx("Waiting")}</th>
                  <th className="text-start px-4 py-2 font-normal">{tx("Didn't work")}</th>
                  <th className="text-start px-4 py-2 font-normal">{tx("Removed %")}</th>
                </tr>
              </thead>
              <tbody>
                {perMember.map((m, i) => (
                  <tr key={i} className="border-t border-slate-700/20 hover:bg-slate-700/10">
                    <td className="px-4 py-2.5 text-slate-200">{m.member}</td>
                    <td className="px-4 py-2.5 text-slate-400">{m.total}</td>
                    <td className="px-4 py-2.5 text-emerald-400">{m.confirmed}</td>
                    <td className="px-4 py-2.5 text-amber-400">{m.pending}</td>
                    <td className="px-4 py-2.5 text-red-400">{m.failed}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                          <div className="h-full bg-emerald-500 rounded-full"
                            style={{ width: `${m.rate}%` }} />
                        </div>
                        <span className="text-slate-300 text-xs">{m.rate}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
                {perMember.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-6 text-center text-slate-500 text-sm">{tx("No members to show.")}</td></tr>
                )}
              </tbody>
            </table>
            </div>
          </div>

          {/* Scheduler health */}
          {Object.keys(health).length > 0 && (
            <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4">
              <p className="text-slate-300 text-sm font-medium mb-3">{tx("Scheduler health (last 30 days)")}</p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {Object.entries(health).map(([type, h]) => (
                  <div key={type} className="bg-slate-900 rounded-lg px-3 py-2.5">
                    <p className="text-slate-500 text-xs capitalize mb-1">{type.replace('_', ' ')}</p>
                    <p className="text-slate-200 text-sm font-medium">{h.total}{" "}{tx("runs")}</p>
                    <div className="flex gap-2 text-xs mt-1">
                      <span className="text-emerald-400">{h.ok}{" "}{tx("ok")}</span>
                      {h.error > 0 && <span className="text-red-400">{h.error}{" "}{tx("err")}</span>}
                    </div>
                    {h.last_run && <p className="text-slate-700 text-xs mt-1">{fmtDate(h.last_run)}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
