import { useEffect, useState } from 'react'
import { Bot, ShieldCheck } from 'lucide-react'
import api from '../api'

// Admin: automatic CAPTCHA solving through a solving service you have an
// account with. Only the site's CAPTCHA key and a cleaned page address, or a
// cropped picture of the puzzle with personal details blacked out, are sent.

export default function SolvingSettings() {
  const [d, setD] = useState(null)
  const [service, setService] = useState('2captcha')
  const [key, setKey] = useState('')
  const [msg, setMsg] = useState('')
  const load = () => api.get('/captcha/solving').then(r => {
    setD(r.data)
    const cur = r.data.services?.[r.data.plugin_id]
    if (cur?.service) setService(cur.service)
  }).catch(() => setD(false))
  useEffect(() => { load() }, [])
  if (!d) return null
  const cur = d.services?.[d.plugin_id] || {}

  const save = async (clear = false) => {
    setMsg('')
    try {
      await api.patch('/captcha/solving', { service, api_key: clear ? '' : (key || undefined) })
      setKey(''); setMsg(clear ? 'Key removed.' : 'Saved.'); load()
    } catch (e) { setMsg(e.response?.data?.detail || "Couldn't save that.") }
  }

  return (
    <section aria-labelledby="solve-h" className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-4 mb-6">
      <h2 id="solve-h" className="text-white font-medium flex items-center gap-2"><Bot size={16} aria-hidden="true" /> Automatic solving (admins)</h2>
      <p className="text-slate-400 text-sm mt-1 mb-3 max-w-3xl">
        A solving service can answer CAPTCHAs before anyone has to. It never gets personal details: only the site's
        CAPTCHA key and the page address without anything personal in it, or a cropped picture of just the puzzle with
        every form field and saved detail blacked out. If it can't solve one, it comes here for a person.
      </p>
      <p className="text-sm mb-3 flex items-center gap-1.5">
        <ShieldCheck size={14} className={d.plugin_enabled && cur.has_key ? 'text-emerald-400' : 'text-slate-500'} aria-hidden="true" />
        <span className="text-slate-200">
          {d.plugin_enabled && cur.has_key ? `On, using ${d.choices[cur.service] || cur.service}.`
            : !d.plugin_installed ? 'Off: add the solving plugin, turn it on on the Plugins page, then add your key here.'
            : !d.plugin_enabled ? 'Off: turn on "CAPTCHA solving service" on the Plugins page.'
            : 'Off: add your service account key.'}
        </span>
        {!d.plugin_installed && (
          <button onClick={async () => { try { await api.post('/captcha/solving/install'); setMsg('Added. Now turn it on on the Plugins page.'); load() } catch (e) { setMsg(e.response?.data?.detail || "Couldn't add it.") } }}
            className="ml-2 px-2.5 py-1 text-xs text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-700">Add the solving plugin</button>
        )}
        {d.plugin_installed && !d.plugin_enabled && <a href="/plugins" className="ml-2 text-shield-300 text-xs hover:underline">Open Plugins</a>}
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor="svc" className="block text-slate-300 text-xs mb-1">Service</label>
          <select id="svc" value={service} onChange={e => setService(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200">
            {Object.entries(d.choices).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="svc-key" className="block text-slate-300 text-xs mb-1">Account key {cur.has_key && <span className="text-slate-500">(saved; type a new one to replace it)</span>}</label>
          <input id="svc-key" type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 w-72" />
        </div>
        <button onClick={() => save(false)} className="px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700">Save</button>
        {cur.has_key && <button onClick={() => save(true)} className="px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">Remove key</button>}
      </div>
      {msg && <p role="status" className="text-slate-300 text-sm mt-2">{msg}</p>}
      <p className="text-slate-500 text-xs mt-2">Services charge per CAPTCHA. The key is stored encrypted and given only to the solving plugin while it works.</p>
    </section>
  )
}
