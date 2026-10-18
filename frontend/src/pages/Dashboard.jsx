import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { RefreshCw, Send, AlertCircle, CheckCircle, Clock, ShieldOff, Activity, ShieldAlert } from 'lucide-react'
import { RadialBarChart, RadialBar, ResponsiveContainer, Tooltip } from 'recharts'
import api from '../api'
import Badge from '../components/Badge'
import VariantCoverage from '../components/VariantCoverage'
import RemovalChecks from '../components/RemovalChecks'
import PrivacyScore from '../components/PrivacyScore'
import { useAuth, can } from '../hooks/useAuth'
import { tx, txn, txr } from '../i18n/tx'
import { fmtDate } from '../i18n/format'

function StatCard({ label, value, icon: Icon, color }) {
  return (
    <div className="bg-slate-800 rounded-xl p-4 border border-slate-700/50 min-w-0">
      <div className="flex items-center justify-between gap-2 mb-2">
        <p className="text-slate-400 text-xs uppercase tracking-wide break-words">{label}</p>
        <Icon size={15} className={`${color} shrink-0`} />
      </div>
      <p className={`text-3xl font-semibold break-words ${color}`}>{value ?? '—'}</p>
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
  const [pendingCaptchas, setPendingCaptchas] = useState(0)
  const onPlainHttp = typeof window !== 'undefined' && window.location.protocol === 'http:' &&
    !['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname) &&
    reverseProxy !== 'external'   // an admin told us this server sits behind its own reverse proxy — take their word for it

  useEffect(() => {
    Promise.all([
      api.get('/brokers/stats'),
      api.get('/requests/recheck-due?limit=5'),
      api.get('/captcha/stats').catch(() => ({ data: { pending: 0 } })),
    ]).then(([s, r, c]) => {
      setStats(s.data)
      setRecheck(r.data)
      setPendingCaptchas(c.data?.pending || 0)
    }).finally(() => setLoading(false))
  }, [])

  // Broker-health alert: pull brokers flagged for review so the admin is told
  // on the dashboard, not only if they happen to open the health page.
  useEffect(() => {
    if (!can(user, 'brokers.manage')) return
    api.get('/brokers/health/all?needs_review=true')
      .then(r => setUnhealthy(r.data))
      .catch(() => setUnhealthy([]))
  }, [user])

  // Certificate alerts (LDAP, SIP2, SAML IdP) from the daily check: shown to super
  // admins before sign-in breaks. SAML signing certs warn from 30 days out.
  useEffect(() => {
    if (!can(user, 'certificates.view')) return
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

  // For the "managed" (built-in Caddy or Traefik) path: a live, on-demand check of whether
  // HTTPS actually came up after running scripts/enable-https.ps1/.sh and
  // restarting — a real answer instead of guessing from the browser's own URL.
  const checkHttps = () => {
    setHttpsChecking(true)
    api.get('/cert-monitor/https-status')
      .then(r => setHttpsStatus(r.data))
      .catch(() => setHttpsStatus({ configured: false, level: 'error', message: tx("Could not reach the check.") }))
      .finally(() => setHttpsChecking(false))
  }
  useEffect(() => {
    if (user?.role !== 'super_admin' || (reverseProxy !== 'managed' && reverseProxy !== 'native')) return
    checkHttps()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, reverseProxy])

  const [runMsg, setRunMsg] = useState('')
  const sendNow = async () => {
    setRunMsg('')
    try {
      await api.post('/scheduler/trigger/optout')
      setRunMsg(tx("Sending opt-outs now. This can take a few minutes; the numbers below update as replies come in."))
    } catch (e) { setRunMsg(e.response?.data?.detail || tx("Couldn't start sending. Please try again.")) }
  }

  const progress = stats
    ? Math.round((stats.actioned / Math.max(stats.total_brokers, 1)) * 100)
    : 0

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">{tx("Dashboard")}</h1>
          <p className="text-slate-400 text-sm mt-0.5">{tx("How far your family's information has been removed")}</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Link to="/discovery" className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
            <RefreshCw size={13} aria-hidden="true" />{" "}{tx("Find listings")}
          </Link>
          {can(user, 'scheduler.manage') && (
            <button onClick={sendNow} className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 transition-colors">
              <Send size={13} aria-hidden="true" />{" "}{tx("Send opt-outs now")}
            </button>
          )}
        </div>
      </div>
      {runMsg && <p role="status" className="mb-4 text-sm text-shield-300">{runMsg}</p>}

      {/* Plain-HTTP warning — super admins, when reached from another machine */}
      {user?.role === 'super_admin' && onPlainHttp && !hideHttpWarning && (
        <div className="flex items-start gap-3 mb-4 px-4 py-3 rounded-xl border border-amber-800 bg-amber-900/20">
          <AlertCircle size={16} className="text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-amber-200 text-sm font-medium">{tx("This site isn't using HTTPS")}</p>
            <p className="text-slate-400 text-xs mt-0.5">
              {tx("Passwords cross the network unencrypted, and Google/Microsoft sign-in requires HTTPS.")}
              {reverseProxy === 'native'
                ? <>{" "}{txr("On the server, run <0>scripts/enable-https-native.sh</0> (Linux) or see the Windows steps in <1>docs/admin/native-install.md</1>.", [<code className="text-slate-300" />, <code className="text-slate-300" />])}</>
                : <>{" "}{txr("On the server, run <0>./scripts/enable-https.sh</0> (Linux/macOS) or <1>scripts\\enable-https.ps1</1> (Windows) — see docs/admin/https.md.", [<code className="text-slate-300" />, <code className="text-slate-300" />])}</>}
            </p>
          </div>
          <button onClick={() => setHideHttpWarning(true)} className="text-slate-500 hover:text-slate-300 text-xs shrink-0">{tx("Hide")}</button>
        </div>
      )}

      {/* HTTPS setup status — for the "managed" (built-in Caddy/Traefik) or "native" (certbot/
          win-acme) path chosen in the wizard. A live check, not a guess: OpenOptOut
          can't run docker/certbot/win-acme itself (the api process deliberately has no
          access to the host's Docker daemon, .env file, or OS-level service control —
          see docs/admin/https.md), so this is the honest substitute: confirm whether the
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
                ? (httpsStatus.level === 'ok' ? tx("HTTPS is working") : tx("HTTPS setup needs attention"))
                : tx("HTTPS setup not finished yet")}
            </p>
            <p className="text-slate-400 text-xs mt-0.5">{httpsStatus.message}</p>
          </div>
          <button onClick={checkHttps} disabled={httpsChecking}
            className="text-slate-500 hover:text-slate-300 text-xs shrink-0 disabled:opacity-50">
            {httpsChecking ? tx("Checking…") : tx("Check again")}
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
                {tx("{label} certificate needs attention", { label: a.label })}
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
              {txn(unhealthy.length, "{n} broker needs review", "{n} brokers need review")}
            </p>
            <p className="text-amber-300/70 text-xs mt-0.5">
              {unhealthy.slice(0, 3).map(b => b.name).join(', ')}
              {unhealthy.length > 3 ? tx("and {v} more", { v: unhealthy.length - 3 }) : ''}{tx(": turned off after failing several times in a row, so they don't hold up everyone else. Open to check them.")}
            </p>
          </div>
        </Link>
      )}

      {/* CAPTCHA / Human-in-the-loop alert — shown when opt-outs are paused for challenges */}
      {pendingCaptchas > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6 px-4 py-3 rounded-xl border border-amber-800 bg-amber-950/30">
          <div className="flex items-center gap-2.5 min-w-0">
            <ShieldAlert size={18} className="text-amber-400 shrink-0" />
            <div>
              <p className="text-amber-200 text-sm font-medium">
                {txn(pendingCaptchas, "{n} opt-out is waiting for someone to solve a CAPTCHA", "{n} opt-outs are waiting for someone to solve a CAPTCHA")}
              </p>
              <p className="text-slate-400 text-xs">
                {tx("The site asked to prove a person is there (\"I'm not a robot\"). Solve it, or finish the opt-out yourself.")}
              </p>
            </div>
          </div>
          <Link
            to="/captcha"
            className="px-3 py-1.5 text-xs font-medium text-amber-200 bg-amber-900/40 border border-amber-700/60 rounded-lg hover:bg-amber-900/60 transition-colors shrink-0"
          >
            {tx("Open CAPTCHAs →")}
          </Link>
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <StatCard label={tx("Sites we check")}     value={stats?.total_brokers} icon={ShieldOff}     color="text-slate-300" />
        <StatCard label={tx("Removed")}            value={stats?.confirmed}     icon={CheckCircle}   color="text-emerald-400" />
        <StatCard label={tx("Waiting for a reply")} value={stats?.pending}      icon={Clock}         color="text-amber-400" />
        <StatCard label={tx("Refused or didn't work")} value={stats?.resistant} icon={AlertCircle}   color="text-red-400" />
      </div>

      <PrivacyScore />
      <VariantCoverage />
      <RemovalChecks />

      {/* Progress + recheck row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">

        {/* Overall progress */}
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700/50">
          <p className="text-slate-400 text-xs uppercase tracking-wide mb-3">{tx("Overall progress")}</p>
          <div className="flex flex-wrap items-center gap-4">
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
              <p className="text-slate-400 text-sm">{stats?.actioned ?? 0}{" "}{tx("of {v} sites asked to remove you", { v: stats?.total_brokers ?? 0 })}</p>
              {stats?.recheck_due > 0 && (
                <p className="text-orange-400 text-xs mt-1">{txn(stats.recheck_due, "{n} site to check again", "{n} sites to check again")}</p>
              )}
            </div>
          </div>
        </div>

        {/* Recheck due */}
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700/50">
          <p className="text-slate-400 text-xs uppercase tracking-wide mb-3">{tx("Coming up: check again")}</p>
          {recheck.length === 0 ? (
            <p className="text-slate-500 text-sm">{tx("Nothing to check again yet.")}</p>
          ) : (
            <div className="space-y-2">
              {recheck.slice(0, 5).map(r => (
                <div key={r.id} className="flex items-center justify-between text-sm">
                  <span className="text-slate-300 truncate me-2">{r.broker_name}</span>
                  <span className="text-orange-400 text-xs shrink-0">
                    {r.recheck_after
                      ? new Date(r.recheck_after) < new Date()
                        ? 'now'
                        : tx("in {n} days", { n: Math.ceil((new Date(r.recheck_after) - new Date()) / 86400000) })
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
          <p className="text-slate-300 text-sm font-medium">{tx("Recent activity")}</p>
          <a href="/brokers" className="text-shield-400 text-xs hover:underline">{tx("View all →")}</a>
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

  if (!reqs.length) return <p className="text-slate-500 text-sm p-4">{tx("Nothing has been sent yet.")}</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
      <thead>
        <tr className="text-slate-500 text-xs">
          <th className="text-start px-4 py-2 font-normal">{tx("Site")}</th>
          <th className="text-start px-4 py-2 font-normal">{tx("Person")}</th>
          <th className="text-start px-4 py-2 font-normal">{tx("Where it's at")}</th>
          <th className="text-start px-4 py-2 font-normal">{tx("How")}</th>
          <th className="text-start px-4 py-2 font-normal">{tx("Check again")}</th>
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
              {fmtDate(r.recheck_after)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  )
}
