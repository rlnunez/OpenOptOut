import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Bell, CheckCheck, AlertTriangle, Eye, Info, SearchCheck } from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'
import { tx, txn, txr } from '../i18n/tx'
import { fmtDateTime } from '../i18n/format'

const LEVEL = {
  urgent: { icon: AlertTriangle, cls: 'text-amber-300', label: tx("Needs attention") },
  review: { icon: Eye, cls: 'text-sky-300', label: tx("Worth a look") },
  info:   { icon: Info, cls: 'text-slate-400', label: tx("For your information") },
}
const LINK = {
  auto_disabled: '/broker-health', defunct: '/broker-health', back_online: '/broker-health',
  new_brokers: '/state-registries', delisted: '/state-registries', new_site: '/brokers', contact_changed: '/brokers',
  steps_applied: '/spec-helpers', steps_ready: '/spec-helpers', steps_rehearsal_failed: '/spec-helpers',
  found_while_off: '/brokers', turned_on_found: '/brokers',
  plugin_added: '/brokers', plugin_updated: '/brokers', privacy_found: '/brokers',
}
// The kind of each update, in the reader's language (the server's label is English).
const KIND = () => ({
  auto_disabled: tx("Turned off after failing"), defunct: tx("Website gone"), back_online: tx("Website back"),
  new_brokers: tx("New brokers"), delisted: tx("Left a registry"), new_site: tx("New site from a listing"),
  contact_changed: tx("New contact address"), steps_applied: tx("Steps fixed automatically"),
  steps_ready: tx("Steps ready to approve"), steps_rehearsal_failed: tx("Drafted steps need a look"),
  found_while_off: tx("Found on a broker that's off"), turned_on_found: tx("Turned on after listings were found"),
  plugin_added: tx("Built-in plugin added"), plugin_updated: tx("Built-in plugin updated"), privacy_found: tx("Privacy page found"),
})

export default function BrokerUpdates() {
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [onlyNew, setOnlyNew] = useState(false)
  const [digest, setDigest] = useState(null)
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    api.get('/broker-updates', { params: onlyNew ? { unread: true } : {} })
      .then(r => setData(r.data)).catch(() => setMsg(tx("Couldn't load broker updates.")))
  }, [onlyNew])
  useEffect(() => { load() }, [load])
  useEffect(() => { api.get('/broker-updates/settings').then(r => setDigest(r.data.email_digest)).catch(() => {}) }, [])

  const turnOn = async (u) => {
    setMsg('')
    try {
      await api.post(`/brokers/${u.broker_id}/enable`)
      setMsg(tx("{name} is turned on. Its waiting opt-outs go out in the next run.", { name: u.broker_name || '' }))
      load()
    } catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't turn it on.")) }
  }

  const markRead = async (ids) => {
    await api.post('/broker-updates/read', { ids: ids || null })
    window.dispatchEvent(new Event('broker-updates-read'))
    load()
  }
  const saveDigest = async (v) => {
    setDigest(v); setMsg('')
    try { await api.put('/broker-updates/settings', { email_digest: v }); setMsg(tx("Saved.")) }
    catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't save.")) }
  }

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      <div className="flex items-start justify-between gap-3 flex-wrap mb-1">
        <h1 className="text-white text-xl font-semibold flex items-center gap-2">
          <Bell size={20} className="text-shield-500" aria-hidden="true" />{" "}{tx("Broker updates")}
        </h1>
        {data?.unread > 0 && (
          <button onClick={() => markRead()} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border border-slate-600 text-slate-200 hover:bg-slate-800">
            <CheckCheck size={14} aria-hidden="true" />{" "}{tx("Mark all read")}
          </button>
        )}
      </div>
      <p className="text-slate-400 text-sm mb-4">
        {tx("Changes to your broker list: brokers turned off after failing, websites that disappeared or came back, new brokers from state registries, new sites found in listings, built-in plugins added or updated, and privacy pages found on brokers' websites.")}
      </p>

      <div className="flex flex-wrap items-center gap-4 mb-4 text-sm">
        <label className="flex items-center gap-2 text-slate-300">
          <input type="checkbox" checked={onlyNew} onChange={e => setOnlyNew(e.target.checked)} className="accent-shield-500" />
          {tx("Only new")}
        </label>
        {digest && (
          <label className="flex items-center gap-2 text-slate-300">
            {tx("Email digest to super administrators")}
            <select value={digest} onChange={e => saveDigest(e.target.value)} disabled={!can(user, 'settings.system')}
              className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-sm text-slate-100">
              <option value="daily">{tx("Daily")}</option>
              <option value="weekly">{tx("Weekly")}</option>
              <option value="off">{tx("Off")}</option>
            </select>
          </label>
        )}
        {msg && <span role="status" className="text-shield-300 text-xs">{msg}</span>}
      </div>

      {can(user, 'brokers.manage') && <FoundRule onChanged={load} />}

      {!data ? <p className="text-slate-500 text-sm">{tx("Loading…")}</p> : data.updates.length === 0 ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-slate-700 bg-slate-800/40">
          <p className="text-slate-200 font-medium">{onlyNew ? tx("Nothing new.") : tx("No broker updates yet.")}</p>
          <p className="text-slate-400 text-sm mt-1">{tx("They'll show up here as OpenOptOut checks brokers and registries.")}</p>
        </div>
      ) : (
        <ul className="divide-y divide-slate-700/40 rounded-xl border border-slate-700/60 bg-slate-800/40">
          {data.updates.map(u => {
            const L = LEVEL[u.level] || LEVEL.info
            return (
              <li key={u.id} className={`p-3 flex items-start gap-3 ${u.read ? 'opacity-70' : ''}`}>
                <L.icon size={16} className={`${L.cls} shrink-0 mt-0.5`} aria-label={L.label} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-slate-100">
                    {!u.read && <span className="sr-only">{tx("New:")}{" "}</span>}
                    <span className={u.read ? '' : 'font-medium'}>{u.title}</span>
                  </div>
                  {u.detail && <p className="text-xs text-slate-400 mt-0.5 whitespace-pre-line">{u.detail}</p>}
                  <p className="text-[11px] text-slate-500 mt-1">
                    {KIND()[u.kind] || u.label} · {fmtDateTime(u.created_at, 'medium', '')}
                    {LINK[u.kind] && <> · <Link to={LINK[u.kind]} className="text-shield-400 hover:text-shield-300">{tx("Open")}</Link></>}
                  </p>
                </div>
                {u.kind === 'found_while_off' && u.broker_enabled === false && can(user, 'brokers.manage') && (
                  <button onClick={() => turnOn(u)} aria-label={tx("Turn on {name}", { name: u.broker_name || '' })}
                    className="text-xs px-2 py-1 rounded-sm border border-slate-600 text-slate-100 hover:bg-slate-700 shrink-0">{tx("Turn on")}</button>
                )}
                {!u.read && (
                  <button onClick={() => markRead([u.id])} className="text-xs text-slate-400 hover:text-white shrink-0">{tx("Mark read")}</button>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

// What happens when a listing is found on a broker that's turned off
// (backend/core/found_listings.py), and the brokers waiting now.
function FoundRule({ onChanged }) {
  const [r, setR] = useState(null)
  const [form, setForm] = useState(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const load = () => api.get('/brokers/found-rule').then(x => { setR(x.data); setForm({ action: x.data.action, threshold: x.data.threshold, fallback: x.data.fallback }) }).catch(() => {})
  useEffect(() => { load() }, [])
  if (!r || !form) return null

  const save = async () => {
    setBusy(true); setMsg('')
    try {
      const x = await api.put('/brokers/found-rule', { ...form, threshold: Number(form.threshold) })
      setR(x.data)
      setMsg(x.data.turned_on?.length
        ? txn(x.data.turned_on.length, "Saved. {n} broker was turned on: {names}.", "Saved. {n} brokers were turned on: {names}.", { names: x.data.turned_on.join(', ') })
        : tx("Saved."))
      onChanged && onChanged()
    } catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't save.")) }
    finally { setBusy(false) }
  }
  const turnOn = async (w) => {
    setMsg('')
    try { await api.post(`/brokers/${w.broker_id}/enable`); load(); onChanged && onChanged() }
    catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't turn it on.")) }
  }
  const why = {
    no_plugin: tx("No plugin, so only an admin can turn it on."),
    defunct: tx("Its website looked gone."),
    failing: tx("Turned off after failing."),
    turned_off: tx("An admin turned it off."),
  }
  const opt = (value, label, help) => (
    <label className="flex items-start gap-2 text-sm text-slate-200">
      <input type="radio" name="found-action" value={value} checked={form.action === value}
        onChange={() => setForm({ ...form, action: value })} className="mt-1 accent-shield-500" />
      <span>{label}{help && <span className="block text-xs text-slate-400 mt-0.5">{help}</span>}</span>
    </label>
  )
  return (
    <section className="mb-5 rounded-xl border border-slate-700/60 bg-slate-800/40 p-4 space-y-3" aria-labelledby="found-rule-title">
      <h2 id="found-rule-title" className="text-white font-medium flex items-center gap-2">
        <SearchCheck size={16} className="text-shield-400" aria-hidden="true" />{tx("When a listing is found on a broker that's turned off")}
      </h2>
      <p className="text-slate-400 text-sm">{tx("Some brokers start turned off until someone checks them. When Find listings or web search finds a person on one, the site is clearly live and already has them, so opting out can't add anyone new.")}</p>
      <fieldset className="space-y-2">
        <legend className="sr-only">{tx("When a listing is found on a broker that's turned off")}</legend>
        {opt('ask', tx("Ask an admin here first"), tx("The broker shows up below with a Turn on button. Opt-outs wait until it's on."))}
        {opt('auto', tx("Turn the broker on and opt out automatically"), tx("Only for brokers with a plugin that nobody turned off on purpose."))}
        {form.action === 'auto' && (
          <div className="ms-6 flex flex-wrap items-center gap-2 text-sm text-slate-300">
            <label className="flex flex-wrap items-center gap-2">
              {txr("once listings are found for at least <0/> people", [
                <input type="number" min="1" max="100000" value={form.threshold} onChange={e => setForm({ ...form, threshold: e.target.value })}
                  className="w-24 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-sm text-slate-100" aria-label={tx("Number of people")} />])}
            </label>
            <label className="flex items-center gap-2">{tx("Until then:")}
              <select value={form.fallback} onChange={e => setForm({ ...form, fallback: e.target.value })}
                className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-sm text-slate-100">
                <option value="ask">{tx("ask an admin")}</option>
                <option value="tell">{tx("tell the person")}</option>
              </select></label>
            <span className="basis-full text-xs text-slate-400">{tx("For a family, 1 is fine. For a library or school, a higher number means one stray match doesn't turn a site on.")}</span>
          </div>
        )}
        {opt('tell', tx("Tell the person"), tx("It goes on their checklist with the site's opt-out page, so they can do it themselves. If the broker is turned on later, OpenOptOut takes over."))}
      </fieldset>
      <div className="flex items-center gap-3">
        <button onClick={save} disabled={busy} className="px-4 py-1.5 bg-shield-600 hover:bg-shield-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">{tx("Save")}</button>
        {msg && <span role="status" className="text-shield-300 text-xs">{msg}</span>}
      </div>
      {r.waiting.length > 0 && (
        <div>
          <h3 className="text-slate-200 text-sm font-medium mb-1.5">{tx("Turned off, with listings found")}</h3>
          <ul className="divide-y divide-slate-700/40 rounded-lg border border-slate-700/60">
            {r.waiting.map(w => (
              <li key={w.broker_id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
                <span className="text-slate-100 font-medium">{w.name}</span>
                <span className="text-slate-400 text-xs">{txn(w.people, "found for {n} person", "found for {n} people")}</span>
                {!w.can_auto && <span className="text-slate-500 text-xs">{why[w.why_not] || ''}</span>}
                <button onClick={() => turnOn(w)} aria-label={tx("Turn on {name}", { name: w.name })}
                  className="ms-auto text-xs px-2 py-1 rounded-sm border border-slate-600 text-slate-100 hover:bg-slate-700">{tx("Turn on")}</button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
