import { useCallback, useEffect, useState } from 'react'
import { Activity, CheckCircle2, XCircle, Bell, ScrollText, Copy, Plus, Trash2, Send, KeyRound } from 'lucide-react'
import api from '../api'
import { useAuth } from '../hooks/useAuth'
import { tx, txn } from '../i18n/tx'
import { fmtDateTime, fmtNumber } from '../i18n/format'
import { detailText } from '../errorMessage'

// Monitoring and alerts (super admins): health checks and the addresses a
// monitoring tool polls, webhook notifications, and log forwarding. Nothing
// sent from here names anyone (core/webhooks.py, core/log_forwarding.py).

const card = 'bg-slate-800 rounded-xl border border-slate-700/50 p-4 mb-4'
const inp = 'w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500'
const lbl = 'block text-slate-400 text-xs mb-1'
const btn = 'px-3 py-1.5 text-sm rounded-lg border border-slate-600 text-slate-200 hover:bg-slate-700 flex items-center gap-1.5 disabled:opacity-40'
const primary = 'px-3 py-1.5 text-sm rounded-lg bg-shield-600 hover:bg-shield-700 text-white disabled:opacity-40'

const EVENT_LABELS = () => ({
  run_finished: tx("Opt-outs were sent"),
  needs_you: tx("Something waits for a person (Checklist or CAPTCHA)"),
  broker_turned_off: tx("A broker was turned off after failing"),
  listing_back: tx("Listings came back after removal"),
  backup_failed: tx("A backup didn't work"),
  certificate_expiring: tx("A certificate needs attention"),
  plugin_turned_off: tx("A plugin kept crashing and was turned off"),
  health_problem: tx("A health check fails"),
  health_ok: tx("Every health check passes again"),
})

const HOOK_HELP = () => ({
  ntfy: tx("The topic address, for example https://ntfy.sh/your-topic. Add an access token if the topic is protected."),
  gotify: tx("Your Gotify server's /message address, for example https://gotify.example.org/message, and an app token."),
  slack: tx("An incoming webhook address from Slack (Apps → Incoming Webhooks)."),
  teams: tx("A Teams Workflows webhook address (\"Post to a channel when a webhook request is received\")."),
  discord: tx("A channel webhook address (Channel settings → Integrations → Webhooks)."),
  homeassistant: tx("A Home Assistant webhook trigger address, for example http://homeassistant.local:8123/api/webhook/your-id."),
  json: tx("Any address that accepts a JSON POST. With a secret, each message is signed (X-OpenOptOut-Signature)."),
})

const SECRET_LABEL = kind => ({
  ntfy: tx("Access token (optional)"), gotify: tx("App token"), json: tx("Signing secret (optional)"),
}[kind])

function Copyable({ text, label }) {
  const [done, setDone] = useState(false)
  return (
    <div className="flex items-center gap-2">
      <code className="text-slate-200 text-xs bg-slate-950 border border-slate-800 rounded px-2 py-1 break-all" dir="ltr">{text}</code>
      <button className={btn} aria-label={tx("Copy {v}", { v: label })}
        onClick={() => { try { navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500) } catch { /* select it by hand */ } }}>
        <Copy size={12} aria-hidden="true" />{done ? tx("Copied") : tx("Copy")}</button>
    </div>
  )
}

function Health({ settings, reload }) {
  const [r, setR] = useState(null)
  const [token, setToken] = useState('')
  useEffect(() => {
    fetch('/api/health/ready').then(x => x.json()).then(setR).catch(() => setR({ status: 'problem', checks: [] }))
  }, [])
  const origin = window.location.origin
  const makeToken = async () => { const { data } = await api.post('/observability/metrics-token'); setToken(data.token); reload() }
  const dropToken = async () => { await api.delete('/observability/metrics-token'); setToken(''); reload() }
  return (
    <section aria-labelledby="h-health" className={card}>
      <h2 id="h-health" className="text-white font-medium mb-1 flex items-center gap-2"><Activity size={15} aria-hidden="true" />{tx("Health")}</h2>
      <p className="text-slate-400 text-xs mb-3">{tx("Checked every five minutes. Webhooks hear when something starts failing and when it's fixed.")}</p>
      {r && (
        <ul className="space-y-1.5 mb-4">
          {r.checks.map(c => (
            <li key={c.name} className="flex items-start gap-2 text-sm">
              {c.ok ? <CheckCircle2 size={15} className="text-emerald-400 shrink-0 mt-0.5" aria-hidden="true" /> : <XCircle size={15} className="text-red-400 shrink-0 mt-0.5" aria-hidden="true" />}
              <span><span className="text-slate-100">{tx(c.label)}</span>{" "}<span className="text-slate-400">— {c.ok ? tx("OK") : tx("Problem")}: {c.text ? tx(c.text, c.vars) : c.detail}</span></span>
            </li>
          ))}
        </ul>
      )}
      <h3 className="text-slate-200 text-sm font-medium mb-1">{tx("For your monitoring tool")}</h3>
      <p className="text-slate-400 text-xs mb-2">{tx("Uptime Kuma, Zabbix or Nagios can check the first two addresses. Prometheus or Grafana can read the third with the token. None of them shows anyone's details.")}</p>
      <div className="space-y-2 mb-3">
        <div><p className={lbl}>{tx("Is it running?")}</p><Copyable text={`${origin}/api/health`} label={tx("Is it running?")} /></div>
        <div><p className={lbl}>{tx("Is everything working? (answers 503 when a check fails)")}</p><Copyable text={`${origin}/api/health/ready`} label={tx("Health checks")} /></div>
        <div><p className={lbl}>{tx("Metrics (Prometheus)")}</p><Copyable text={`${origin}/api/metrics`} label={tx("Metrics (Prometheus)")} /></div>
      </div>
      {token ? (
        <div className="rounded-lg border border-amber-700 bg-amber-900/20 p-3">
          <p className="text-amber-200 text-xs mb-2">{tx("Copy this token now; it isn't shown again. Send it as: Authorization: Bearer <token>.")}</p>
          <Copyable text={token} label={tx("Metrics token")} />
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button className={btn} onClick={makeToken}><KeyRound size={13} aria-hidden="true" />{settings.has_metrics_token ? tx("Make a new metrics token") : tx("Make a metrics token")}</button>
          {settings.has_metrics_token && <button className={btn} onClick={dropToken}><Trash2 size={13} aria-hidden="true" />{tx("Remove the token")}</button>}
        </div>
      )}
    </section>
  )
}

function WebhookForm({ hook, settings, onDone, onCancel }) {
  const [f, setF] = useState(hook ? { ...hook, url: '', secret: undefined } : { kind: 'ntfy', name: '', url: '', events: settings.default_events, enabled: true })
  const [err, setErr] = useState('')
  const set = k => e => setF(x => ({ ...x, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  const toggle = ev => setF(x => ({ ...x, events: x.events.includes(ev) ? x.events.filter(e => e !== ev) : [...x.events, ev] }))
  const save = async () => {
    setErr('')
    const body = { kind: f.kind, name: f.name, events: f.events, enabled: f.enabled }
    if (f.url) body.url = f.url
    if (f.secret !== undefined) body.secret = f.secret
    try { await api.put(hook ? `/observability/webhooks/${hook.id}` : '/observability/webhooks', body); onDone() }
    catch (e) { setErr(detailText(e) || tx("Couldn't save that.")) }
  }
  const labels = EVENT_LABELS()
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3 space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div><label htmlFor="wh-kind" className={lbl}>{tx("Service")}</label>
          <select id="wh-kind" className={inp} value={f.kind} onChange={set('kind')} disabled={!!hook}>
            {Object.entries(settings.webhook_kinds).map(([k, v]) => <option key={k} value={k}>{k === 'json' ? tx("Other (JSON)") : v}</option>)}
          </select></div>
        <div><label htmlFor="wh-name" className={lbl}>{tx("Name (for you)")}</label>
          <input id="wh-name" className={inp} value={f.name} onChange={set('name')} placeholder={tx("For example: Family phone")} /></div>
      </div>
      <div><label htmlFor="wh-url" className={lbl}>{tx("Address")}</label>
        <input id="wh-url" className={inp} type="url" dir="ltr" autoComplete="off" value={f.url} onChange={set('url')}
          placeholder={hook ? tx("Leave empty to keep {v}", { v: hook.host }) : 'https://'} />
        <p className="text-slate-500 text-xs mt-1">{HOOK_HELP()[f.kind]}</p></div>
      {SECRET_LABEL(f.kind) && (
        <div><label htmlFor="wh-secret" className={lbl}>{SECRET_LABEL(f.kind)}</label>
          <input id="wh-secret" className={inp} type="password" autoComplete="off" value={f.secret ?? ''}
            onChange={set('secret')} placeholder={hook?.has_secret ? tx("Saved. Type to replace it.") : ''} /></div>
      )}
      <fieldset>
        <legend className={lbl}>{tx("Send a message when")}</legend>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          {Object.keys(labels).map(ev => (
            <label key={ev} className="flex items-start gap-2 text-sm text-slate-200">
              <input type="checkbox" className="mt-0.5 w-4 h-4 accent-shield-500" checked={f.events.includes(ev)} onChange={() => toggle(ev)} />{labels[ev]}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="flex items-center gap-2 text-sm text-slate-200"><input type="checkbox" className="w-4 h-4 accent-shield-500" checked={f.enabled} onChange={set('enabled')} />{tx("Turned on")}</label>
      {err && <p role="alert" className="text-red-300 text-sm">{err}</p>}
      <div className="flex gap-2"><button className={primary} onClick={save}>{tx("Save")}</button><button className={btn} onClick={onCancel}>{tx("Cancel")}</button></div>
    </div>
  )
}

function LogForm({ dest, settings, onDone, onCancel }) {
  const [f, setF] = useState(dest ? { ...dest, token: undefined } : { kind: 'syslog', name: '', host: '', port: 514, transport: 'udp', endpoint: '', level: 'INFO', enabled: true, verify_tls: true })
  const [err, setErr] = useState('')
  const set = k => e => setF(x => ({ ...x, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  const save = async () => {
    setErr('')
    const body = { kind: f.kind, name: f.name, level: f.level, enabled: f.enabled, verify_tls: f.verify_tls }
    if (f.kind === 'syslog') Object.assign(body, { host: f.host, port: Number(f.port) || undefined, transport: f.transport })
    else body.endpoint = f.endpoint
    if (f.token !== undefined) body.token = f.token
    try { await api.put(dest ? `/observability/log-forwarding/${dest.id}` : '/observability/log-forwarding', body); onDone() }
    catch (e) { setErr(detailText(e) || tx("Couldn't save that.")) }
  }
  const tokenLabel = { otlp: tx("Bearer token (optional)"), loki: tx("Bearer token (optional)"), splunk_hec: tx("HEC token") }[f.kind]
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3 space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div><label htmlFor="lf-kind" className={lbl}>{tx("Kind of log server")}</label>
          <select id="lf-kind" className={inp} value={f.kind} onChange={set('kind')} disabled={!!dest}>
            {Object.entries(settings.log_kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></div>
        <div><label htmlFor="lf-name" className={lbl}>{tx("Name (for you)")}</label>
          <input id="lf-name" className={inp} value={f.name} onChange={set('name')} placeholder={tx("For example: Graylog")} /></div>
      </div>
      {f.kind === 'syslog' ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="sm:col-span-2"><label htmlFor="lf-host" className={lbl}>{tx("Server name or address")}</label>
            <input id="lf-host" className={inp} dir="ltr" value={f.host} onChange={set('host')} placeholder="logs.example.org" /></div>
          <div><label htmlFor="lf-port" className={lbl}>{tx("Port")}</label>
            <input id="lf-port" className={inp} dir="ltr" type="number" value={f.port ?? ''} onChange={set('port')} /></div>
          <div><label htmlFor="lf-transport" className={lbl}>{tx("Connection")}</label>
            <select id="lf-transport" className={inp} value={f.transport} onChange={set('transport')}>
              <option value="udp">{tx("UDP (usual port 514)")}</option>
              <option value="tcp">{tx("TCP (usual port 514)")}</option>
              <option value="tls">{tx("TLS, encrypted (usual port 6514)")}</option>
            </select></div>
        </div>
      ) : (
        <div><label htmlFor="lf-endpoint" className={lbl}>{tx("Address")}</label>
          <input id="lf-endpoint" className={inp} dir="ltr" type="url" value={f.endpoint} onChange={set('endpoint')}
            placeholder={{ otlp: 'https://collector.example.org:4318', loki: 'https://loki.example.org', splunk_hec: 'https://splunk.example.org:8088' }[f.kind]} /></div>
      )}
      {tokenLabel && (
        <div><label htmlFor="lf-token" className={lbl}>{tokenLabel}</label>
          <input id="lf-token" className={inp} type="password" autoComplete="off" value={f.token ?? ''} onChange={set('token')}
            placeholder={dest?.has_token ? tx("Saved. Type to replace it.") : ''} /></div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div><label htmlFor="lf-level" className={lbl}>{tx("Which lines")}</label>
          <select id="lf-level" className={inp} value={f.level} onChange={set('level')}>
            <option value="DEBUG">{tx("Everything, including debugging")}</option>
            <option value="INFO">{tx("Information, warnings and errors")}</option>
            <option value="WARNING">{tx("Warnings and errors")}</option>
            <option value="ERROR">{tx("Errors only")}</option>
          </select></div>
        <div className="flex flex-col gap-2 justify-end">
          {(f.kind !== 'syslog' || f.transport === 'tls') && (
            <label className="flex items-center gap-2 text-sm text-slate-200"><input type="checkbox" className="w-4 h-4 accent-shield-500" checked={f.verify_tls} onChange={set('verify_tls')} />{tx("Check the server's certificate")}</label>)}
          <label className="flex items-center gap-2 text-sm text-slate-200"><input type="checkbox" className="w-4 h-4 accent-shield-500" checked={f.enabled} onChange={set('enabled')} />{tx("Turned on")}</label>
        </div>
      </div>
      {err && <p role="alert" className="text-red-300 text-sm">{err}</p>}
      <div className="flex gap-2"><button className={primary} onClick={save}>{tx("Save")}</button><button className={btn} onClick={onCancel}>{tx("Cancel")}</button></div>
    </div>
  )
}

export default function Monitoring() {
  const { user } = useAuth()
  const [s, setS] = useState(null)
  const [msg, setMsg] = useState('')
  const [editHook, setEditHook] = useState(null)     // null | 'new' | hook
  const [editLog, setEditLog] = useState(null)
  const load = useCallback(() => {
    api.get('/observability').then(r => setS(r.data)).catch(e => setMsg(detailText(e) || tx("Couldn't load the settings.")))
  }, [])
  useEffect(() => { load() }, [load])
  if (user?.role !== 'super_admin') return <div className="p-6 text-slate-400 text-sm">{tx("Only super admins can see this page.")}</div>
  if (!s) return <div className="p-6 text-slate-400 text-sm">{msg || tx("Loading…")}</div>

  const test = async path => {
    setMsg('')
    try { const { data } = await api.post(path); setMsg(data.message); load() }
    catch (e) { setMsg(detailText(e) || tx("Couldn't send it.")) }
  }
  const remove = async (path, name) => {
    if (!window.confirm(tx("Remove {name}?", { name }))) return
    await api.delete(path); load()
  }
  const labels = EVENT_LABELS()

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2"><Activity size={18} aria-hidden="true" />{" "}{tx("Monitoring and alerts")}</h1>
      <p className="text-slate-400 text-sm mt-1 mb-4">{tx("Keep an eye on OpenOptOut from your own tools. Messages, metrics and logs sent from here hold counts and names of brokers, never anyone's details.")}</p>
      {msg && <p role="status" className="text-slate-200 text-sm mb-3">{msg}</p>}

      <Health settings={s} reload={load} />

      <section aria-labelledby="h-hooks" className={card}>
        <h2 id="h-hooks" className="text-white font-medium mb-1 flex items-center gap-2"><Bell size={15} aria-hidden="true" />{tx("Notifications (webhooks)")}</h2>
        <p className="text-slate-400 text-xs mb-3">{tx("Short messages to ntfy, Gotify, Slack, Microsoft Teams, Discord, Home Assistant or any service that takes JSON.")}</p>
        <ul className="space-y-2 mb-3">
          {s.webhooks.map(h => editHook?.id === h.id ? <li key={h.id}><WebhookForm hook={h} settings={s} onDone={() => { setEditHook(null); load() }} onCancel={() => setEditHook(null)} /></li> : (
            <li key={h.id} className={`rounded-lg border border-slate-700 bg-slate-900/50 p-3 flex flex-wrap items-start justify-between gap-2 ${h.enabled ? '' : 'opacity-60'}`}>
              <div className="min-w-0">
                <p className="text-slate-100 text-sm font-medium">{h.name} <span className="text-slate-400 font-normal">· {h.kind === 'json' ? tx("Other (JSON)") : s.webhook_kinds[h.kind]} · <span dir="ltr">{h.host}</span></span></p>
                <p className="text-slate-400 text-xs">{h.events.map(e => labels[e]).filter(Boolean).join(' · ') || tx("No events chosen")}</p>
                {h.last_status && <p className="text-slate-500 text-xs">{tx("Last message: {status}, {when}", { status: h.last_status, when: fmtDateTime(h.last_at) })}</p>}
                {!h.enabled && <p className="text-slate-400 text-xs">{tx("Turned off")}</p>}
              </div>
              <div className="flex gap-1.5">
                <button className={btn} onClick={() => test(`/observability/webhooks/${h.id}/test`)}><Send size={12} aria-hidden="true" />{tx("Send a test")}</button>
                <button className={btn} onClick={() => setEditHook(h)}>{tx("Change")}</button>
                <button className={btn} aria-label={tx("Remove {name}", { name: h.name })} onClick={() => remove(`/observability/webhooks/${h.id}`, h.name)}><Trash2 size={12} aria-hidden="true" /></button>
              </div>
            </li>
          ))}
        </ul>
        {editHook === 'new' ? <WebhookForm settings={s} onDone={() => { setEditHook(null); load() }} onCancel={() => setEditHook(null)} />
          : <button className={btn} onClick={() => setEditHook('new')}><Plus size={13} aria-hidden="true" />{tx("Add a webhook")}</button>}
      </section>

      <section aria-labelledby="h-logs" className={card}>
        <h2 id="h-logs" className="text-white font-medium mb-1 flex items-center gap-2"><ScrollText size={15} aria-hidden="true" />{tx("Log forwarding")}</h2>
        <p className="text-slate-400 text-xs mb-1">{tx("Send a copy of the System logs to a central log server: syslog (rsyslog, Graylog, most SIEMs), OpenTelemetry, Grafana Loki or Splunk.")}</p>
        <p className="text-slate-400 text-xs mb-3">{tx("Passwords, tokens, email addresses and phone numbers are removed from each line before it leaves.")}{" "}
          {txn(s.log_stats.sent, "{n} line sent since the last restart.", "{n} lines sent since the last restart.", { n: fmtNumber(s.log_stats.sent) })}
          {s.log_stats.dropped > 0 && ` ${txn(s.log_stats.dropped, "{n} line couldn't be sent.", "{n} lines couldn't be sent.", { n: fmtNumber(s.log_stats.dropped) })}`}</p>
        <ul className="space-y-2 mb-3">
          {s.log_forwarding.map(d => editLog?.id === d.id ? <li key={d.id}><LogForm dest={d} settings={s} onDone={() => { setEditLog(null); load() }} onCancel={() => setEditLog(null)} /></li> : (
            <li key={d.id} className={`rounded-lg border border-slate-700 bg-slate-900/50 p-3 flex flex-wrap items-start justify-between gap-2 ${d.enabled ? '' : 'opacity-60'}`}>
              <div className="min-w-0">
                <p className="text-slate-100 text-sm font-medium">{d.name} <span className="text-slate-400 font-normal">· {s.log_kinds[d.kind]}</span></p>
                <p className="text-slate-400 text-xs" dir="ltr">{d.kind === 'syslog' ? `${d.transport?.toUpperCase()} ${d.host}:${d.port}` : d.endpoint}</p>
                {d.last_error && <p className="text-amber-300 text-xs">{tx("Can't send right now: {v}", { v: d.last_error })}</p>}
                {!d.enabled && <p className="text-slate-400 text-xs">{tx("Turned off")}</p>}
              </div>
              <div className="flex gap-1.5">
                <button className={btn} onClick={() => test(`/observability/log-forwarding/${d.id}/test`)}><Send size={12} aria-hidden="true" />{tx("Send a test")}</button>
                <button className={btn} onClick={() => setEditLog(d)}>{tx("Change")}</button>
                <button className={btn} aria-label={tx("Remove {name}", { name: d.name })} onClick={() => remove(`/observability/log-forwarding/${d.id}`, d.name)}><Trash2 size={12} aria-hidden="true" /></button>
              </div>
            </li>
          ))}
        </ul>
        {editLog === 'new' ? <LogForm settings={s} onDone={() => { setEditLog(null); load() }} onCancel={() => setEditLog(null)} />
          : <button className={btn} onClick={() => setEditLog('new')}><Plus size={13} aria-hidden="true" />{tx("Add a log server")}</button>}
      </section>
    </div>
  )
}
