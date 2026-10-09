import { useEffect, useState, useRef } from 'react'
import {
  Database, RefreshCw, AlertTriangle, CheckCircle,
  Info, ArrowRight, Play, Clock, HardDrive, Table,
  ChevronDown, ChevronRight, Copy, ExternalLink,
  Lock, Key, Shield, FileKey, CheckCircle2, XCircle
} from 'lucide-react'
import api from '../api'
import { useAuth } from '../hooks/useAuth'

const inp = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"

function RecommendationPill({ rec }) {
  const styles = {
    warning: 'bg-amber-900/20 border-amber-800 text-amber-300',
    info:    'bg-blue-900/20  border-blue-800  text-blue-300',
    error:   'bg-red-900/20   border-red-800   text-red-300',
  }
  const icons = { warning: AlertTriangle, info: Info, error: AlertTriangle }
  const Icon  = icons[rec.level] ?? Info
  return (
    <div className={`flex items-start gap-2 px-3 py-2.5 rounded-lg border text-sm ${styles[rec.level] ?? styles.info}`}>
      <Icon size={13} className="shrink-0 mt-0.5" />
      <p>{rec.message}</p>
    </div>
  )
}

function StatCard({ label, value, sub, icon: Icon, color = 'text-slate-300' }) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4">
      <div className="flex items-center justify-between mb-1">
        <p className="text-slate-500 text-xs uppercase tracking-wide">{label}</p>
        {Icon && <Icon size={13} className={color} />}
      </div>
      <p className={`text-xl font-semibold ${color}`}>{value ?? '—'}</p>
      {sub && <p className="text-slate-600 text-xs mt-1">{sub}</p>}
    </div>
  )
}

function TableRow({ table }) {
  const [open, setOpen] = useState(false)
  const size = table.size_bytes
    ? table.size_bytes > 1_048_576
      ? `${(table.size_bytes / 1_048_576).toFixed(1)} MB`
      : `${Math.round(table.size_bytes / 1024)} KB`
    : null

  return (
    <>
      <tr className="border-t border-slate-700/30 hover:bg-slate-700/10 cursor-pointer"
        onClick={() => setOpen(o => !o)}>
        <td className="px-4 py-2.5 text-slate-200 text-sm font-mono flex items-center gap-2">
          {open ? <ChevronDown size={12} className="text-slate-500" /> : <ChevronRight size={12} className="text-slate-500" />}
          {table.name}
        </td>
        <td className="px-4 py-2.5 text-slate-300 text-sm text-right">{table.row_count?.toLocaleString() ?? '—'}</td>
        <td className="px-4 py-2.5 text-slate-500 text-sm text-right">{size ?? '—'}</td>
      </tr>
      {open && (
        <tr className="bg-slate-900/30">
          <td colSpan={3} className="px-8 py-2">
            <p className="text-slate-600 text-xs">Columns: {table.columns.join(', ')}</p>
          </td>
        </tr>
      )}
    </>
  )
}

// ── Migration tool ────────────────────────────────────────────────────────────

function MigrationTool() {
  const [targetUrl, setTargetUrl]   = useState('')
  const [status, setStatus]         = useState(null)
  const [running, setRunning]       = useState(false)
  const [confirmed, setConfirmed]   = useState(false)
  const logRef = useRef(null)

  const fetchStatus = async () => {
    const { data } = await api.get('/database/migration-status')
    setStatus(data)
    if (data.running) setRunning(true)
    else setRunning(false)
  }

  useEffect(() => {
    fetchStatus()
    const t = setInterval(() => {
      if (running) fetchStatus()
    }, 2000)
    return () => clearInterval(t)
  }, [running])

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [status?.progress])

  const startMigration = async () => {
    if (!targetUrl.trim() || !confirmed) return
    setRunning(true)
    try {
      await api.post(`/database/migrate-to-postgres?target_url=${encodeURIComponent(targetUrl)}`)
      fetchStatus()
    } catch (err) {
      alert(err.response?.data?.detail ?? 'Migration failed to start')
      setRunning(false)
    }
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-700/50 flex items-center gap-2.5">
        <ArrowRight size={15} className="text-shield-400" />
        <div>
          <p className="text-slate-200 text-sm font-medium">Migrate to PostgreSQL</p>
          <p className="text-slate-500 text-xs mt-0.5">Copy all data from SQLite to a Postgres database</p>
        </div>
      </div>
      <div className="px-5 py-4 space-y-4">
        {status?.done && (
          <div className="flex items-start gap-2 px-3 py-2.5 bg-emerald-900/20 border border-emerald-800 rounded-lg text-emerald-300 text-sm">
            <CheckCircle size={13} className="shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Migration complete — {status.total_rows?.toLocaleString()} rows copied</p>
              <p className="text-xs mt-1 text-emerald-500">Update DATABASE_URL in .env and restart the container.</p>
            </div>
          </div>
        )}

        {!status?.done && (
          <>
            <div>
              <label className="text-slate-400 text-xs mb-1 block">Target PostgreSQL connection string</label>
              <input value={targetUrl} onChange={e => setTargetUrl(e.target.value)}
                placeholder="postgresql://user:password@host:5432/openoptout"
                className={inp} disabled={running} />
              <p className="text-slate-600 text-xs mt-1">
                The target database must exist and be empty. The schema will be created automatically.
              </p>
            </div>

            <div className="bg-slate-900 rounded-lg px-3 py-2.5 text-xs space-y-1">
              <p className="text-slate-400 font-medium">Before migrating:</p>
              <p className="text-slate-500">✓ Create an empty Postgres database</p>
              <p className="text-slate-500">✓ Stop any running opt-out jobs (Settings → Scheduler → disable)</p>
              <p className="text-slate-500">✓ Take a backup of your SQLite file</p>
              <p className="text-slate-500">✓ Test the connection string below</p>
            </div>

            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}
                className="w-3.5 h-3.5 rounded-sm accent-shield-500" disabled={running} />
              <span className="text-slate-300 text-sm">I have backed up my SQLite database and the target Postgres DB is empty</span>
            </label>

            <button onClick={startMigration} disabled={running || !targetUrl.trim() || !confirmed}
              className="flex items-center gap-1.5 px-4 py-2 bg-shield-600 text-white text-sm rounded-lg hover:bg-shield-700 disabled:opacity-40 transition-colors">
              {running ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
              {running ? 'Migrating…' : 'Start migration'}
            </button>
          </>
        )}

        {status?.progress?.length > 0 && (
          <div>
            <p className="text-slate-500 text-xs mb-1.5 uppercase tracking-wide">Migration log</p>
            <div ref={logRef}
              className="bg-slate-900 border border-slate-700 rounded-lg p-3 h-48 overflow-y-auto font-mono text-xs text-slate-400 space-y-0.5">
              {status.progress.map((line, i) => (
                <p key={i} className={line.includes('ERROR') ? 'text-red-400' : line.includes('complete') ? 'text-emerald-400' : ''}>
                  {line}
                </p>
              ))}
              {running && <p className="text-shield-400 animate-pulse">▌</p>}
            </div>
            {status.error && (
              <p className="text-red-400 text-xs mt-2">Error: {status.error}</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Enterprise connection config ──────────────────────────────────────────────

function SecretStatusPill({ ok, label }) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      {ok ? <CheckCircle2 size={12} className="text-emerald-400" /> : <XCircle size={12} className="text-slate-600" />}
      <span className={ok ? 'text-slate-300' : 'text-slate-600'}>{label}</span>
    </div>
  )
}

// readOnly: managers with 'Database status' can see the connection settings;
// testing and changing them stays with super admins.
function ConnectionConfig({ readOnly = false }) {
  const [config, setConfig]         = useState(null)
  const [methods, setMethods]       = useState({})
  const [secretStatus, setSecretStatus] = useState({})
  const [saving, setSaving]         = useState(false)
  const [testing, setTesting]       = useState(false)
  const [testResult, setTestResult] = useState(null)

  useEffect(() => {
    api.get('/database/connection-config').then(r => {
      setConfig(r.data.config)
      setMethods(r.data.auth_methods)
      setSecretStatus(r.data.secret_status)
    }).catch(() => {})
  }, [])

  if (!config) return <p className="text-slate-500 text-sm">Loading…</p>

  const save = async () => {
    setSaving(true)
    try { await api.patch('/database/connection-config', config) }
    finally { setSaving(false) }
  }

  const test = async () => {
    setTesting(true); setTestResult(null)
    try {
      const { data } = await api.post('/database/connection-config/test')
      setTestResult(data)
    } finally { setTesting(false) }
  }

  const method = methods[config.auth_method] || {}
  const needsCerts = ['client_cert', 'cert_and_password'].includes(config.auth_method)
  const needsPassword = ['password', 'ssl_password', 'cert_and_password'].includes(config.auth_method)
  const needsIAM = config.auth_method?.startsWith('iam_')
  const needsCA = ['verify-ca', 'verify-full'].includes(config.sslmode)

  return (
    <div className="space-y-4">
      {/* Security notice */}
      <div className="flex items-start gap-2 px-3 py-2.5 bg-blue-900/10 border border-blue-800 rounded-lg">
        <Shield size={13} className="text-blue-400 shrink-0 mt-0.5" />
        <p className="text-blue-300 text-xs">
          Secrets (passwords, private keys, certificates) are never stored here. They come from
          environment variables or mounted files controlled outside the application. This screen
          configures only <em>how</em> to connect and <em>where</em> to find those secrets.
        </p>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <div onClick={() => setConfig(c => ({...c, enabled: !c.enabled}))}
          className={`w-9 h-5 rounded-full transition-colors cursor-pointer relative ${config.enabled ? 'bg-shield-600' : 'bg-slate-700'}`}>
          <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${config.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </div>
        <span className="text-slate-300 text-sm">Use structured connection config (instead of DATABASE_URL)</span>
      </label>

      {config.enabled && (
        <>
          {/* Auth method picker */}
          <div>
            <label className="text-slate-400 text-xs mb-1 block">Authentication method</label>
            <div className="relative">
              <select value={config.auth_method} onChange={e => setConfig(c => ({...c, auth_method: e.target.value}))}
                className={inp + ' appearance-none pr-8'}>
                {Object.entries(methods).map(([key, m]) => (
                  <option key={key} value={key}>{m.label}</option>
                ))}
              </select>
              <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
            </div>
            {method.note && (
              <p className="text-slate-500 text-xs mt-1.5 bg-slate-900 rounded-lg px-3 py-2">{method.note}</p>
            )}
          </div>

          {/* Connection basics */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Host"><input value={config.host || ''} onChange={e => setConfig(c => ({...c, host: e.target.value}))} placeholder="db.internal.example.org" className={inp} /></Field>
            <Field label="Port"><input type="number" value={config.port || 5432} onChange={e => setConfig(c => ({...c, port: parseInt(e.target.value)}))} className={inp} /></Field>
            <Field label="Database name"><input value={config.dbname || ''} onChange={e => setConfig(c => ({...c, dbname: e.target.value}))} placeholder="openoptout" className={inp} /></Field>
            <Field label="Username"><input value={config.user || ''} onChange={e => setConfig(c => ({...c, user: e.target.value}))} placeholder="openoptout_svc" className={inp} /></Field>
          </div>

          {/* SSL mode */}
          <Field label="SSL mode" hint="verify-full is strongest; requires a CA certificate">
            <div className="relative">
              <select value={config.sslmode} onChange={e => setConfig(c => ({...c, sslmode: e.target.value}))}
                className={inp + ' appearance-none pr-8'}>
                <option value="disable">disable — no encryption (not recommended)</option>
                <option value="allow">allow</option>
                <option value="prefer">prefer</option>
                <option value="require">require — encrypt, no cert check</option>
                <option value="verify-ca">verify-ca — encrypt + verify CA</option>
                <option value="verify-full">verify-full — encrypt + verify CA + hostname</option>
              </select>
              <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
            </div>
          </Field>

          {/* Certificate file paths */}
          {(needsCA || needsCerts) && (
            <div className="bg-slate-900 rounded-lg p-3 space-y-3">
              <div className="flex items-center gap-1.5">
                <FileKey size={12} className="text-slate-400" />
                <p className="text-slate-400 text-xs font-medium">Certificate file paths</p>
                <span className="text-slate-600 text-xs">— mount these read-only</span>
              </div>
              {needsCA && (
                <Field label="CA certificate path" hint="PEM file used to verify the server certificate">
                  <input value={config.sslrootcert || ''} onChange={e => setConfig(c => ({...c, sslrootcert: e.target.value}))}
                    placeholder="/certs/ca.pem" className={inp} />
                </Field>
              )}
              {needsCerts && (
                <>
                  <Field label="Client certificate path">
                    <input value={config.sslcert || ''} onChange={e => setConfig(c => ({...c, sslcert: e.target.value}))}
                      placeholder="/certs/client-cert.pem" className={inp} />
                  </Field>
                  <Field label="Client private key path" hint="Must be chmod 600, owned by the app user">
                    <input value={config.sslkey || ''} onChange={e => setConfig(c => ({...c, sslkey: e.target.value}))}
                      placeholder="/certs/client-key.pem" className={inp} />
                  </Field>
                </>
              )}
            </div>
          )}

          {/* IAM region */}
          {needsIAM && (
            <Field label="IAM region" hint="Cloud region for IAM token generation">
              <input value={config.iam_region || ''} onChange={e => setConfig(c => ({...c, iam_region: e.target.value}))}
                placeholder="us-east-1" className={inp} />
            </Field>
          )}

          {/* Secret status */}
          <div className="bg-slate-900 rounded-lg p-3">
            <div className="flex items-center gap-1.5 mb-2">
              <Lock size={12} className="text-slate-400" />
              <p className="text-slate-400 text-xs font-medium">Detected secrets</p>
              <span className="text-slate-600 text-xs">— from env vars & mounted files</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {needsPassword && (
                <>
                  <SecretStatusPill ok={secretStatus.db_password_env}  label="DB_PASSWORD (env)" />
                  <SecretStatusPill ok={secretStatus.db_password_file} label="DB_PASSWORD_FILE" />
                </>
              )}
              {needsCA    && <SecretStatusPill ok={secretStatus.sslrootcert_exists} label="CA cert file exists" />}
              {needsCerts && <SecretStatusPill ok={secretStatus.sslcert_exists}     label="Client cert exists" />}
              {needsCerts && <SecretStatusPill ok={secretStatus.sslkey_exists}      label="Client key exists" />}
            </div>
            {needsPassword && !secretStatus.db_password_env && !secretStatus.db_password_file && (
              <p className="text-amber-400 text-xs mt-2">
                No password secret detected. Set DB_PASSWORD or DB_PASSWORD_FILE before connecting.
              </p>
            )}
          </div>

          {/* Test result */}
          {testResult && (
            <div className={`px-3 py-2.5 rounded-lg border text-sm ${testResult.connected ? 'border-emerald-800 bg-emerald-900/10 text-emerald-300' : 'border-red-800 bg-red-900/10 text-red-300'}`}>
              {testResult.connected ? (
                <div>
                  <p className="font-medium">✓ Connected to PostgreSQL {testResult.server_version}</p>
                  {testResult.ssl_active && <p className="text-xs mt-0.5">TLS active: {testResult.ssl_version}</p>}
                </div>
              ) : (
                <p>✗ {testResult.error || testResult.message}</p>
              )}
            </div>
          )}

          {/* Actions */}
          {!readOnly && <>
          <div className="flex gap-2 justify-end">
            <button onClick={test} disabled={testing}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors disabled:opacity-40">
              {testing ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
              {testing ? 'Testing…' : 'Test connection'}
            </button>
            <button onClick={save} disabled={saving}
              className="flex items-center gap-1.5 px-4 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 disabled:opacity-40 transition-colors">
              {saving ? <RefreshCw size={13} className="animate-spin" /> : null}
              {saving ? 'Saving…' : 'Save config'}
            </button>
          </div>
          <p className="text-slate-600 text-xs text-right">Restart the container for changes to take effect.</p>
          </>}
          {readOnly && <p className="text-slate-600 text-xs text-right">Only a super admin can test or change the connection.</p>}
        </>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DatabaseAdmin() {
  const { user } = useAuth()
  const isSuper = user?.role === 'super_admin'   // migrating and changing the connection
  const [health,  setHealth]  = useState(null)
  const [tables,  setTables]  = useState([])
  const [loading, setLoading] = useState(true)
  const [tab,     setTab]     = useState('health')

  const load = () => {
    setLoading(true)
    Promise.all([
      api.get('/database/health'),
      api.get('/database/tables'),
    ]).then(([h, t]) => {
      setHealth(h.data); setTables(t.data)
    }).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const isSQLite  = health?.db_type === 'sqlite'
  const isPG      = health?.db_type === 'postgres'
  const connected = health?.connected

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">Database</h1>
          <p className="text-slate-400 text-sm mt-0.5">Health, statistics, and migration tools</p>
        </div>
        <button onClick={load} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {loading && <p className="text-slate-500 text-sm">Loading…</p>}

      {!loading && health && (
        <>
          {/* Connection status */}
          <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border mb-5 ${connected ? 'border-emerald-800 bg-emerald-900/10' : 'border-red-800 bg-red-900/10'}`}>
            <span className={`w-2.5 h-2.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
            <div className="flex-1">
              <p className={`text-sm font-medium ${connected ? 'text-emerald-300' : 'text-red-300'}`}>
                {connected ? 'Connected' : 'Connection failed'} — {health.db_type === 'postgres' ? 'PostgreSQL' : 'SQLite'}
                {health.sqlcipher && ' + SQLCipher'}
              </p>
              <p className="text-slate-500 text-xs">
                {health.ping_ms != null && `Ping: ${health.ping_ms}ms`}
                {health.file_size_mb != null && ` · File: ${health.file_size_mb}MB`}
                {health.pg_size && ` · Size: ${health.pg_size}`}
              </p>
            </div>
            <div className="flex gap-2 text-xs">
              <span className={`px-2 py-0.5 rounded-sm border ${health.field_encryption ? 'text-emerald-400 border-emerald-800 bg-emerald-900/20' : 'text-slate-500 border-slate-700'}`}>
                {health.field_encryption ? '🔒 field enc' : 'field enc off'}
              </span>
            </div>
          </div>

          {/* Recommendations */}
          {health.recommendations?.length > 0 && (
            <div className="space-y-2 mb-5">
              {health.recommendations.map((r, i) => <RecommendationPill key={i} rec={r} />)}
            </div>
          )}

          {/* KPI cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
            <StatCard label="Users"       value={health.table_counts?.users?.toLocaleString()}              icon={Database} />
            <StatCard label="Members"     value={health.table_counts?.family_members?.toLocaleString()}     icon={Database} />
            <StatCard label="Opt-outs"    value={health.table_counts?.removal_requests?.toLocaleString()}   icon={Database} color="text-shield-400" />
            <StatCard label="Brokers"     value={health.table_counts?.brokers?.toLocaleString()}            icon={Database} color="text-amber-400" />
          </div>

          {/* Connection pool (Postgres only) */}
          {isPG && Object.keys(health.pool || {}).length > 0 && (
            <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4 mb-5">
              <p className="text-slate-400 text-xs uppercase tracking-wide mb-3">Connection pool</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                {Object.entries(health.pool).map(([k, v]) => (
                  <div key={k} className="bg-slate-900 rounded-lg px-3 py-2">
                    <p className="text-slate-200 text-lg font-semibold">{v}</p>
                    <p className="text-slate-600 text-xs">{k.replace('_', ' ')}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tabs */}
          <div className="flex gap-1 bg-slate-800 p-1 rounded-lg border border-slate-700/50 mb-4 w-fit">
            {[
              { key: 'tables',     label: 'Tables' },
              { key: 'connection', label: 'Connection' },
              ...(isSQLite && isSuper ? [{ key: 'migrate', label: 'Migrate to Postgres' }] : []),
            ].map(t => (
              <button key={t.key} onClick={() => setTab(t.key)}
                className={`px-3 py-1.5 text-sm rounded-sm transition-colors ${tab === t.key ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'}`}>
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'tables' && (
            <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-500 text-xs border-b border-slate-700/50">
                    <th className="text-left px-4 py-3 font-normal">Table</th>
                    <th className="text-right px-4 py-3 font-normal">Rows</th>
                    <th className="text-right px-4 py-3 font-normal">Size</th>
                  </tr>
                </thead>
                <tbody>
                  {tables.map(t => <TableRow key={t.name} table={t} />)}
                </tbody>
              </table>
              </div>
            </div>
          )}

          {tab === 'connection' && (
            <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-5">
              <ConnectionConfig readOnly={!isSuper} />
            </div>
          )}

          {tab === 'migrate' && <MigrationTool />}
        </>
      )}
    </div>
  )
}
