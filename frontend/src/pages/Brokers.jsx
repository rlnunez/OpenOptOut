import { useEffect, useState, useCallback } from 'react'
import { Search, Upload, ExternalLink, ChevronDown } from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'
import Badge from '../components/Badge'

const STATUS_OPTIONS   = ['', 'compliant', 'resistant', 'inconsistent', 'undetermined']
const METHOD_OPTIONS   = ['', 'form', 'email', 'manual', 'phone']
const DIFF_OPTIONS     = ['', 'easy', 'medium', 'hard']

export default function Brokers() {
  const { user } = useAuth()
  const canManage = can(user, 'brokers.manage')   // importing brokers
  const [brokers, setBrokers]     = useState([])
  const [loading, setLoading]     = useState(true)
  const [search, setSearch]       = useState('')
  const [status, setStatus]       = useState('')
  const [method, setMethod]       = useState('')
  const [difficulty, setDifficulty] = useState('')
  const [importing, setImporting] = useState(false)
  const [importMsg, setImportMsg] = useState('')

  const fetchBrokers = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (search)     params.set('search', search)
    if (status)     params.set('status', status)
    if (method)     params.set('method', method)
    if (difficulty) params.set('difficulty', difficulty)
    params.set('limit', '200')
    api.get(`/brokers?${params}`).then(r => setBrokers(r.data)).finally(() => setLoading(false))
  }, [search, status, method, difficulty])

  useEffect(() => {
    const t = setTimeout(fetchBrokers, 300)
    return () => clearTimeout(t)
  }, [fetchBrokers])

  const handleImport = async e => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setImportMsg('')
    const form = new FormData()
    form.append('file', file)
    try {
      const { data } = await api.post('/brokers/import-csv', form)
      setImportMsg(`✓ Imported: ${data.added} added, ${data.updated} updated`)
      fetchBrokers()
    } catch {
      setImportMsg('Import failed — check CSV format')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="p-4 md:p-6 max-w-6xl">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-white text-xl font-semibold">Brokers</h1>
          <p className="text-slate-400 text-sm mt-0.5">{brokers.length} brokers loaded</p>
        </div>
        {canManage && <label className={`flex items-center gap-1.5 px-3 py-1.5 text-sm border rounded-lg cursor-pointer transition-colors ${
          importing
            ? 'text-slate-500 border-slate-700'
            : 'text-slate-300 border-slate-700 hover:bg-slate-800'
        }`}>
          <Upload size={13} />
          {importing ? 'Importing…' : 'Import CSV'}
          <input type="file" accept=".csv" className="hidden" onChange={handleImport} disabled={importing} />
        </label>}
      </div>

      {importMsg && (
        <div className={`mb-4 px-3 py-2 rounded-lg text-sm ${
          importMsg.startsWith('✓') ? 'bg-emerald-900/30 text-emerald-400' : 'bg-red-900/30 text-red-400'
        }`}>{importMsg}</div>
      )}

      {/* Filters */}
      <div className="flex gap-2 mb-4">
        <div className="relative flex-1">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search brokers…"
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-8 pr-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-shield-500"
          />
        </div>
        <Select value={status} onChange={setStatus} options={STATUS_OPTIONS} label="Status" />
        <Select value={method} onChange={setMethod} options={METHOD_OPTIONS} label="Method" />
        <Select value={difficulty} onChange={setDifficulty} options={DIFF_OPTIONS} label="Difficulty" />
      </div>

      {/* Table */}
      <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-500 text-xs border-b border-slate-700/50">
              <th className="text-left px-4 py-3 font-normal">Broker</th>
              <th className="text-left px-4 py-3 font-normal">Incogni status</th>
              <th className="text-left px-4 py-3 font-normal">Method</th>
              <th className="text-left px-4 py-3 font-normal">Difficulty</th>
              <th className="text-left px-4 py-3 font-normal">Type</th>
              <th className="text-left px-4 py-3 font-normal">Last request</th>
              <th className="text-left px-4 py-3 font-normal">Re-check</th>
              <th className="px-4 py-3 font-normal"></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="px-4 py-8 text-slate-500 text-center">Loading…</td></tr>
            )}
            {!loading && brokers.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-slate-500 text-center">
                No brokers found. Import the enriched CSV to get started.
              </td></tr>
            )}
            {!loading && brokers.map(b => (
              <tr key={b.id} className="border-t border-slate-700/30 hover:bg-slate-700/20 transition-colors">
                <td className="px-4 py-2.5 text-slate-200 font-medium">{b.name}</td>
                <td className="px-4 py-2.5"><Badge value={b.status} /></td>
                <td className="px-4 py-2.5"><Badge value={b.method} /></td>
                <td className="px-4 py-2.5"><Badge value={b.difficulty} /></td>
                <td className="px-4 py-2.5">
                  {b.latest_status ? <Badge value={b.latest_status} /> : <span className="text-slate-600 text-xs">—</span>}
                </td>
                <td className="px-4 py-2.5 text-slate-500 text-xs">
                  {b.recheck_after
                    ? new Date(b.recheck_after) < new Date()
                      ? <span className="text-orange-400">overdue</span>
                      : new Date(b.recheck_after).toLocaleDateString()
                    : '—'}
                </td>
                <td className="px-4 py-2.5">
                  {b.opt_out_url && (
                    <a
                      href={b.opt_out_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-shield-400 hover:text-shield-300 transition-colors"
                      title="Open opt-out page"
                    >
                      <ExternalLink size={13} />
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  )
}

function Select({ value, onChange, options, label }) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="appearance-none bg-slate-800 border border-slate-700 rounded-lg pl-3 pr-7 py-1.5 text-sm text-slate-300 focus:outline-none focus:border-shield-500"
      >
        {options.map(o => (
          <option key={o} value={o}>{o || label}</option>
        ))}
      </select>
      <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
    </div>
  )
}
