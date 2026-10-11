import { useEffect, useState } from 'react'
import { Globe2, AlertTriangle, Save } from 'lucide-react'
import api from '../api'

const inp = 'w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-shield-500'

export default function WebSearchSettings() {
  const [s, setS] = useState(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.get('/web-search/settings').then(r => setS(r.data)).catch(() => setMsg("Couldn't load the settings.")) }, [])
  if (!s) return <div className="p-6 text-slate-400 text-sm">{msg || 'Loading…'}</div>
  const set = (k) => (e) => setS(v => ({ ...v, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  const save = async (e) => {
    e.preventDefault(); setBusy(true); setMsg('')
    try {
      const body = { enabled: s.enabled, provider: 'searxng', searxng_url: s.searxng_url,
        max_queries: Number(s.max_queries) || 12, weekly: s.weekly, auto_add_strong: s.auto_add_strong }
      await api.put('/web-search/settings', body)
      setMsg('Saved.')
      const r = await api.get('/web-search/settings'); setS(r.data)
    } catch (err) { setMsg(err.response?.data?.detail || "Couldn't save.") }
    finally { setBusy(false) }
  }

  return (
    <div className="p-4 md:p-6 max-w-3xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2 mb-1">
        <Globe2 size={20} className="text-shield-500" aria-hidden="true" /> Web search
      </h1>
      <p className="text-slate-400 text-sm mb-4">
        Lets OpenOptOut search the web for pages about each family member. Pages on known data brokers that
        show one of their exact phone numbers, addresses or email addresses are added to removals automatically;
        everything else waits for the person to say "that's me" or "not me".
      </p>
      <div role="note" className="mb-5 p-3 rounded-lg border border-amber-700 bg-amber-950/30 text-sm text-amber-100 flex gap-2">
        <AlertTriangle size={16} className="shrink-0 mt-0.5 text-amber-400" aria-hidden="true" />
        <span>{s.privacy_note}</span>
      </div>

      <form onSubmit={save} className="space-y-4">
        <div className="p-3 rounded-lg border border-slate-700 bg-slate-900/60">
          <div className="text-slate-200 text-sm font-medium">Search provider: SearXNG (self-hosted, free)</div>
          <div className="text-slate-400 text-xs mt-0.5">Run your own SearXNG server next to OpenOptOut. In its settings.yml, add <code>json</code> under <code>search: formats:</code>.</div>
          <label htmlFor="ws-url" className="block text-sm text-slate-300 mt-3 mb-1">SearXNG address</label>
          <input id="ws-url" className={inp} placeholder="http://searxng:8080" value={s.searxng_url} onChange={set('searxng_url')} />
        </div>

        <div>
          <label htmlFor="ws-max" className="block text-sm text-slate-300 mb-1">Searches per person per run</label>
          <input id="ws-max" type="number" min="1" max="40" className={inp + ' w-28'} value={s.max_queries} onChange={set('max_queries')} />
        </div>

        <label className="flex items-start gap-2 text-sm text-slate-200">
          <input type="checkbox" checked={s.auto_add_strong} onChange={set('auto_add_strong')} className="mt-0.5 accent-shield-500" />
          Add strong matches on known data brokers to removals automatically
        </label>
        <label className="flex items-start gap-2 text-sm text-slate-200">
          <input type="checkbox" checked={s.weekly} onChange={set('weekly')} className="mt-0.5 accent-shield-500" />
          Search again for everyone once a week
        </label>
        <label className="flex items-start gap-2 text-sm text-slate-200">
          <input type="checkbox" checked={s.enabled} onChange={set('enabled')} className="mt-0.5 accent-shield-500" />
          Turn on web search (I've read the note above)
        </label>

        {msg && <p role="status" className="text-sm text-shield-300">{msg}</p>}
        <button type="submit" disabled={busy} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-shield-600 hover:bg-shield-500 text-white text-sm font-medium disabled:opacity-50">
          <Save size={14} aria-hidden="true" /> {busy ? 'Saving…' : 'Save'}
        </button>
      </form>
    </div>
  )
}
