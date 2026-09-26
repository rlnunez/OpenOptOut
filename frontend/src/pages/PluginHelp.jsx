import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BookOpen, Code2, RefreshCw, ShieldAlert } from 'lucide-react'
import api from '../api'
import Markdown from '../components/Markdown'

const TABS = [
  { key: 'using',   label: 'Using plugins',   icon: BookOpen, blurb: 'Security model, permissions, safety controls, and how to install and operate plugins.' },
  { key: 'writing', label: 'Writing plugins', icon: Code2,    blurb: 'Extension points, host capabilities, the manifest format, and the plugin SDK.' },
]

export default function PluginHelp() {
  const [params, setParams] = useSearchParams()
  const initial = params.get('doc') === 'writing' ? 'writing' : 'using'
  const [tab, setTab] = useState(initial)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError('')
    api.get(`/plugins/docs/${tab}`)
      .then(r => { if (!cancelled) setContent(r.data.markdown || '') })
      .catch(e => { if (!cancelled) setError(e.response?.data?.detail || 'Could not load documentation') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [tab])

  const selectTab = (key) => {
    setTab(key)
    setParams({ doc: key }, { replace: true })
  }

  return (
    <div className="p-4 md:p-6 max-w-3xl">
      <div className="mb-5">
        <h1 className="text-white text-xl font-semibold">Plugin documentation</h1>
        <p className="text-slate-400 text-sm mt-0.5">
          Reference for administrators and developers. Rendered live from the source docs, so it
          always matches the installed version.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-5">
        {TABS.map(t => {
          const Icon = t.icon
          const active = tab === t.key
          return (
            <button key={t.key} onClick={() => selectTab(t.key)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm transition-colors ${active
                ? 'border-shield-600 bg-shield-900/20 text-white'
                : 'border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-200'}`}>
              <Icon size={15} />
              {t.label}
            </button>
          )
        })}
      </div>

      <p className="text-slate-500 text-xs mb-4">{TABS.find(t => t.key === tab)?.blurb}</p>

      {/* Content */}
      <div className="bg-slate-800/40 rounded-xl border border-slate-700/50 px-5 py-4">
        {loading ? (
          <div className="flex items-center gap-2 text-slate-500 text-sm py-8 justify-center">
            <RefreshCw size={14} className="animate-spin" /> Loading documentation…
          </div>
        ) : error ? (
          <div className="flex items-start gap-2 px-3 py-3 rounded-lg border border-red-800 bg-red-900/15">
            <ShieldAlert size={15} className="text-red-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-red-300 text-sm font-medium">Documentation unavailable</p>
              <p className="text-red-400/80 text-xs mt-0.5">{error}</p>
            </div>
          </div>
        ) : (
          <Markdown source={content} />
        )}
      </div>
    </div>
  )
}
