import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { RefreshCw, Send, AlertCircle, CheckCircle, Clock, ShieldOff, Activity } from 'lucide-react'
import { RadialBarChart, RadialBar, ResponsiveContainer, Tooltip } from 'recharts'
import api from '../api'
import Badge from '../components/Badge'
import { useAuth } from '../hooks/useAuth'

function StatCard({ label, value, icon: Icon, color }) {
  return (
    <div className="bg-slate-800 rounded-xl p-4 border border-slate-700/50">
      <div className="flex items-center justify-between mb-2">
        <p className="text-slate-400 text-xs uppercase tracking-wide">{label}</p>
        <Icon size={15} className={color} />
      </div>
      <p className={`text-3xl font-semibold ${color}`}>{value ?? '—'}</p>
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const [stats, setStats] = useState(null)
  const [recheck, setRecheck] = useState([])
  const [loading, setLoading] = useState(true)
  const [unhealthy, setUnhealthy] = useState([])
  const [certAlerts, setCertAlerts] = useState([])
  const [hideHttpWarning, setHideHttpWarning] = useState(false)
  const [reverseProxy, setReverseProxy] = useState(null)   // 'managed' | 'external' | 'none' | 'unset' | null (loading)
  const [httpsStatus, setHttpsStatus] = useState(null)      // result of /cert-monitor/https-status
  const [httpsChecking, setHttpsChecking] = useState(false)
  const onPlainHttp = typeof window !== 'undefined' && window.location.protocol === 'http:' &&
    !['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname) &&
    reverseProxy !== 'external'   // an admin told us this server sits behind its own reverse proxy — take their word for it

  useEffect(() => {
    Promise.all([
      api.get('/brokers/stats'),
      api.get('/requests/recheck-due?limit=5'),
    ]).then(([s, r]) => {
      setStats(s.data)
      setRecheck(r.data)
    }).finally(() => setLoading(false))
  }, [])

  // Broker-health alert: pull brokers flagged for review so the admin is told
  // on the dashboard, not only if they happen to open the health page.
  useEffect(() => {
    if (user?.role !== 'super_admin') return
    api.get('/brokers/health/all?needs_review=true')
      .then(r => setUnhealthy(r.data))
      .catch(() => setUnhealthy([]))
  }, [user])

  // Certificate alerts (LDAP, SIP2, SAML IdP) from the daily check: shown to super
  // admins before sign-in breaks. SAML signing certs warn from 30 days out.
  useEffect(() => {
    if (user?.role !== 'super_admin') return
    api.get('/cert-monitor/alerts')
      .then(r => setCertAlerts(r.data.alerts || []))
      .catch(() => setCertAlerts([]))
  }, [user])

  // What the setup wizard was told about the reverse-proxy situation, so the
  // plain-HTTP nag below doesn't fight a proxy the admin already has in front.
  useEffect(() => {
    if (user?.role !== 'super_admin') return
    api.get('/wizard/state')
      .then(r => setReverseProxy(r.data.reverse_proxy || 'unset'))
      .catch(() => setReverseProxy('unset'))
  }, [user])

  // For the "managed" (built-in Caddy) path: a live, on-demand check of whether
  // HTTPS actually came up after running scripts/enable-https.ps1/.sh and
  // restarting — a real answer instead of guessing from the browser's own URL.
  const checkHttps = () => {
    setHttpsChecking(true)
    api.get('/cert-monitor/https-status')
      .then(r => setHttpsStatus(r.data))
      .catch(() => setHttpsStatus({ configured: false, level: 'error', message: 'Could not reach the check.' }))
      .finally(() => setHttpsChecking(false))
  }
  useEffect(() => {
    if (user?.role !== 'super_admin' || (reverseProxy !== 'managed' && reverseProxy !== 'native')) return
    checkHttps()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, reverseProxy])

  const progress = stats
    ? Math.round((stats.actioned / Math.max(stats.total_brokers, 1)) * 100)
    : 0

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">Dashboard</h1>
          <p className="text-slate-400 text-sm mt-0.5">Overview of your data removal campaign</p>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
            <RefreshCw size={13} /> Run scan
          </button>
          <button className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 transition-colors">
            <Send size={13} /> Send opt-outs
          </button>
        </div>
      </div>

      {/* Plain-HTTP warning — super admins, when reached from another machine */}
      {user?.role === 'super_admin' && onPlainHttp && !hideHttpWarning && (
        <div className="flex items-start gap-3 mb-4 px-4 py-3 rounded-xl border border-amber-800 bg-amber-900/20">
          <AlertCircle size={16} className="text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-amber-200 text-sm font-medium">This site isn't using HTTPS</p>
            <p className="text-slate-400 text-xs mt-0.5">
              Passwords cross the network unencrypted, and Google/Microsoft sign-in requires HTTPS.
              {reverseProxy === 'native'
                ? <> On the server, run <code className="text-slate-300">scripts/enable-https-native.sh</code> (Linux) or see the Windows steps in <code className="text-slate-300">docs/NATIVE_INSTALL.md</code>.</>
                : <> On the server, run <code className="text-slate-300">./scripts/enable-https.sh</code> (Linux/macOS)
              or <code className="text-slate-300">scripts\enable-https.ps1</code> (Windows) — see docs/HTTPS.md.</>}
            </p>
          </div>
          <button onClick={() => setHideHttpWarning(true)} className="text-slate-500 hover:text-slate-300 text-xs shrink-0">Hide</button>
        </div>
      )}

      {/* HTTPS setup status — for the "managed" (built-in Caddy) or "native" (certbot/
          win-acme) path chosen in the wizard. A live check, not a guess: PrivacyShield
          can't run docker/certbot/win-acme itself (the api process deliberately has no
          access to the host's Docker daemon, .env file, or OS-level service control —
          see docs/HTTPS.md), so this is the honest substitute: confirm whether the
          certificate actually came up after you ran the script and restarted. */}
      {user?.role === 'super_admin' && (reverseProxy === 'managed' || reverseProxy === 'native') && httpsStatus && httpsStatus.level !== 'ok' && (
        <div className={`flex items-start gap-3 mb-4 px-4 py-3 rounded-xl border ${
          httpsStatus.level === 'ok' ? 'border-emerald-800 bg-emerald-900/10'
            : httpsStatus.level === 'warning' ? 'border-amber-800 bg-amber-900/20'
            : httpsStatus.level === 'error' ? 'border-red-800 bg-red-900/20'
            : 'border-slate-700 bg-slate-800/40'}`}>
          {httpsStatus.level === 'ok'
            ? <CheckCircle size={16} className="text-emerald-400 shrink-0 mt-0.5" />
            : <AlertCircle size={16} className={`shrink-0 mt-0.5 ${httpsStatus.level === 'warning' ? 'text-amber-400' : httpsStatus.level === 'error' ? 'text-red-400' : 'text-slate-400'}`} />}
          <div className="flex-1 min-w-0">
            <p className={`text-sm font-medium ${
              httpsStatus.level === 'ok' ? 'text-emerald-200'
                : httpsStatus.level === 'warning' ? 'text-amber-200'
                : httpsStatus.level === 'error' ? 'text-red-200' : 'text-slate-300'}`}>
              {httpsStatus.configured
                ? (httpsStatus.level === 'ok' ? 'HTTPS is working' : 'HTTPS setup needs attention')
                : 'HTTPS setup not finished yet'}
            </p>
            <p className="text-slate-400 text-xs mt-0.5">{httpsStatus.message}</p>
          </div>
          <button onClick={checkHttps} disabled={httpsChecking}
            className="text-slate-500 hover:text-slate-300 text-xs shrink-0 disabled:opacity-50">
            {httpsChecking ? 'Checking…' : 'Check again'}
          </button>
        </div>
      )}


      {/* Certificate alerts — super admins only */}
      {certAlerts.map(a => {
        const warn = a.level === 'warning'
        return (
          <Link key={a.source} to="/branding"
            className={`flex items-start gap-3 mb-4 px-4 py-3 rounded-xl border transition-colors ${
              warn ? 'border-amber-800 bg-amber-900/20 hover:bg-amber-900/30'
                   : 'border-red-800 bg-red-900/20 hover:bg-red-900/30'}`}>
            <AlertCircle size={16} className={`${warn ? 'text-amber-400' : 'text-red-400'} shrink-0 mt-0.5`} />
            <div className="flex-1 min-w-0">
              <p className={`${warn ? 'text-amber-200' : 'text-red-200'} text-sm font-medium`}>
                {a.label} certificate needs attention
              </p>
              <p className="text-slate-400 text-xs mt-0.5">{a.message}</p>
            </div>
          </Link>
        )
      })}

      {/* Broker health alert — only shown to super admins when brokers need review */}
      {unhealthy.length > 0 && (
        <Link to="/broker-health"
          className="flex items-start gap-3 mb-6 px-4 py-3 rounded-xl border border-amber-800 bg-amber-900/20 hover:bg-amber-900/30 transition-colors">
          <Activity size={16} className="text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-amber-200 text-sm font-medium">
              {unhealthy.length} broker{unhealthy.length > 1 ? 's' : ''} need{unhealthy.length > 1 ? '' : 's'} review
            </p>
            <p className="text-amber-300/70 text-xs mt-0.5">
              {unhealthy.slice(0, 3).map(b => b.name).join(', ')}
              {unhealthy.length > 3 ? ` +${unhealthy.length - 3} more` : ''} — auto-disabled after repeated
              failures so they don't slow your runs. Tap to review.
            </p>
          </div>
        </Link>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <StatCard label="Total brokers"      value={stats?.total_brokers} icon={ShieldOff}     color="text-slate-300" />
        <StatCard label="Confirmed removed"  value={stats?.confirmed}     icon={CheckCircle}   color="text-emerald-400" />
        <StatCard label="Pending reply"      value={stats?.pending}       icon={Clock}         color="text-amber-400" />
        <StatCard label="Resistant / failed" value={stats?.resistant}     icon={AlertCircle}   color="text-red-400" />
      </div>

      {/* Progress + recheck row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">

        {/* Overall progress */}
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700/50">
          <p className="text-slate-400 text-xs uppercase tracking-wide mb-3">Overall progress</p>
          <div className="flex items-center gap-4">
            <div className="w-24 h-24">
              <ResponsiveContainer width="100%" height="100%">
                <RadialBarChart
                  cx="50%" cy="50%"
                  innerRadius="60%" outerRadius="90%"
                  startAngle={90} endAngle={-270}
                  data={[{ value: progress, fill: '#6366f1' }]}
                >
                  <RadialBar dataKey="value" cornerRadius={4} background={{ fill: '#1e293b' }} />
                </RadialBarChart>
              </ResponsiveContainer>
            </div>
            <div>
              <p className="text-white text-3xl font-semibold">{progress}%</p>
              <p className="text-slate-400 text-sm">{stats?.actioned ?? 0} of {stats?.total_brokers ?? 0} actioned</p>
              {stats?.recheck_due > 0 && (
                <p className="text-orange-400 text-xs mt-1">{stats.recheck_due} recheck{stats.recheck_due !== 1 ? 's' : ''} overdue</p>
              )}
            </div>
          </div>
        </div>

        {/* Recheck due */}
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700/50">
          <p className="text-slate-400 text-xs uppercase tracking-wide mb-3">Re-check queue</p>
          {recheck.length === 0 ? (
            <p className="text-slate-500 text-sm">No re-checks due — all clear.</p>
          ) : (
            <div className="space-y-2">
              {recheck.slice(0, 5).map(r => (
                <div key={r.id} className="flex items-center justify-between text-sm">
                  <span className="text-slate-300 truncate mr-2">{r.broker_name}</span>
                  <span className="text-orange-400 text-xs shrink-0">
                    {r.recheck_after
                      ? new Date(r.recheck_after) < new Date()
                        ? 'overdue'
                        : `${Math.ceil((new Date(r.recheck_after) - new Date()) / 86400000)}d`
                      : '—'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent requests table */}
      <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
          <p className="text-slate-300 text-sm font-medium">Recent activity</p>
          <a href="/brokers" className="text-shield-400 text-xs hover:underline">View all →</a>
        </div>
        <RecentRequests />
      </div>
    </div>
  )
}

function RecentRequests() {
  const [reqs, setReqs] = useState([])
  useEffect(() => {
    api.get('/requests?limit=8').then(r => setReqs(r.data))
  }, [])

  if (!reqs.length) return <p className="text-slate-500 text-sm p-4">No requests yet.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
      <thead>
        <tr className="text-slate-500 text-xs">
          <th className="text-left px-4 py-2 font-normal">Broker</th>
          <th className="text-left px-4 py-2 font-normal">Member</th>
          <th className="text-left px-4 py-2 font-normal">Status</th>
          <th className="text-left px-4 py-2 font-normal">Method</th>
          <th className="text-left px-4 py-2 font-normal">Re-check</th>
        </tr>
      </thead>
      <tbody>
        {reqs.map(r => (
          <tr key={r.id} className="border-t border-slate-700/50 hover:bg-slate-700/30 transition-colors">
            <td className="px-4 py-2.5 text-slate-200">{r.broker_name}</td>
            <td className="px-4 py-2.5 text-slate-400">{r.member_name}</td>
            <td className="px-4 py-2.5"><Badge value={r.status} /></td>
            <td className="px-4 py-2.5"><Badge value={r.method_used} /></td>
            <td className="px-4 py-2.5 text-slate-500 text-xs">
              {r.recheck_after ? new Date(r.recheck_after).toLocaleDateString() : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  )
}
