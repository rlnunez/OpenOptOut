import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Bell, CheckCheck, AlertTriangle, Eye, Info } from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'

const LEVEL = {
  urgent: { icon: AlertTriangle, cls: 'text-amber-300', label: 'Needs attention' },
  review: { icon: Eye, cls: 'text-sky-300', label: 'Worth a look' },
  info:   { icon: Info, cls: 'text-slate-400', label: 'For your information' },
}
const LINK = {
  auto_disabled: '/broker-health', defunct: '/broker-health', back_online: '/broker-health',
  new_brokers: '/state-registries', delisted: '/state-registries', new_site: '/brokers', contact_changed: '/brokers',
}

export default function BrokerUpdates() {
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [onlyNew, setOnlyNew] = useState(false)
  const [digest, setDigest] = useState(null)
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    api.get('/broker-updates', { params: onlyNew ? { unread: true } : {} })
      .then(r => setData(r.data)).catch(() => setMsg("Couldn't load broker updates."))
  }, [onlyNew])
  useEffect(() => { load() }, [load])
  useEffect(() => { api.get('/broker-updates/settings').then(r => setDigest(r.data.email_digest)).catch(() => {}) }, [])

  const markRead = async (ids) => {
    await api.post('/broker-updates/read', { ids: ids || null })
    window.dispatchEvent(new Event('broker-updates-read'))
    load()
  }
  const saveDigest = async (v) => {
    setDigest(v); setMsg('')
    try { await api.put('/broker-updates/settings', { email_digest: v }); setMsg('Saved.') }
    catch (e) { setMsg(e.response?.data?.detail || "Couldn't save.") }
  }

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      <div className="flex items-start justify-between gap-3 flex-wrap mb-1">
        <h1 className="text-white text-xl font-semibold flex items-center gap-2">
          <Bell size={20} className="text-shield-500" aria-hidden="true" /> Broker updates
        </h1>
        {data?.unread > 0 && (
          <button onClick={() => markRead()} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border border-slate-600 text-slate-200 hover:bg-slate-800">
            <CheckCheck size={14} aria-hidden="true" /> Mark all read
          </button>
        )}
      </div>
      <p className="text-slate-400 text-sm mb-4">
        Changes to your broker list: brokers turned off after failing, websites that disappeared or came back,
        new brokers from state registries, and new sites found in listings.
      </p>

      <div className="flex flex-wrap items-center gap-4 mb-4 text-sm">
        <label className="flex items-center gap-2 text-slate-300">
          <input type="checkbox" checked={onlyNew} onChange={e => setOnlyNew(e.target.checked)} className="accent-shield-500" />
          Only new
        </label>
        {digest && (
          <label className="flex items-center gap-2 text-slate-300">
            Email digest to super administrators
            <select value={digest} onChange={e => saveDigest(e.target.value)} disabled={!can(user, 'settings.system')}
              className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-sm text-slate-100">
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="off">Off</option>
            </select>
          </label>
        )}
        {msg && <span role="status" className="text-shield-300 text-xs">{msg}</span>}
      </div>

      {!data ? <p className="text-slate-500 text-sm">Loading…</p> : data.updates.length === 0 ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-slate-700 bg-slate-800/40">
          <p className="text-slate-200 font-medium">{onlyNew ? 'Nothing new.' : 'No broker updates yet.'}</p>
          <p className="text-slate-400 text-sm mt-1">They'll show up here as OpenOptOut checks brokers and registries.</p>
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
                    {!u.read && <span className="sr-only">New: </span>}
                    <span className={u.read ? '' : 'font-medium'}>{u.title}</span>
                  </div>
                  {u.detail && <p className="text-xs text-slate-400 mt-0.5 whitespace-pre-line">{u.detail}</p>}
                  <p className="text-[11px] text-slate-500 mt-1">
                    {u.label} · {u.created_at ? new Date(u.created_at + 'Z').toLocaleString() : ''}
                    {LINK[u.kind] && <> · <Link to={LINK[u.kind]} className="text-shield-400 hover:text-shield-300">Open</Link></>}
                  </p>
                </div>
                {!u.read && (
                  <button onClick={() => markRead([u.id])} className="text-xs text-slate-400 hover:text-white shrink-0">Mark read</button>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
