import { Fragment, useEffect, useState, useCallback } from 'react'
import { Search, Upload, ExternalLink, ChevronDown, ChevronRight, ScanSearch } from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'
import Badge, { plainLabel } from '../components/Badge'
import PrivacyPagesPanel from '../components/PrivacyPagesPanel'
import BrokerTimelines from '../components/RemovalTimeline'
import { tx } from '../i18n/tx'
import { fmtDate } from '../i18n/format'

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
  const [solvers, setSolvers]     = useState([])
  const [ppKey, setPpKey]         = useState(0)
  const [openId, setOpenId]       = useState(null)   // broker whose history is showing

  const findPrivacyPage = async (b) => {
    try {
      const { data } = await api.post(`/privacy-pages/find/${b.id}`)
      setImportMsg(data.message ? `✓ ${data.message}` : tx("✓ Already looking at {name}'s website.", { name: b.name }))
      setPpKey(k => k + 1)
    } catch (e) { setImportMsg(e.response?.data?.detail || tx("Couldn't start the search.")) }
  }

  useEffect(() => {
    api.get('/brokers/captcha-solvers')
      .then(r => setSolvers(r.data || []))
      .catch(() => {})
  }, [])

  const handleSolverChange = async (brokerId, solverId) => {
    try {
      await api.patch(`/brokers/${brokerId}/captcha-solver`, {
        captcha_plugin_id: solverId || null
      })
      setBrokers(prev => prev.map(b => b.id === brokerId ? { ...b, captcha_plugin_id: solverId || null } : b))
    } catch (e) {
      console.error('Failed to update captcha solver', e)
    }
  }

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
      setImportMsg(tx("✓ Done: {added} new sites added, {updated} updated", { added: data.added, updated: data.updated }))
      fetchBrokers()
    } catch {
      setImportMsg(tx("Couldn't read that file. It needs to be a CSV spreadsheet with the same columns as the broker list."))
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="p-4 md:p-6 max-w-6xl">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div>
          <h1 className="text-white text-xl font-semibold">{tx("Data broker sites")}</h1>
          <p className="text-slate-400 text-sm mt-0.5">{brokers.length}{" "}{tx("sites that sell or publish personal details")}</p>
        </div>
        {canManage && <label className={`flex items-center gap-1.5 px-3 py-1.5 text-sm border rounded-lg cursor-pointer transition-colors ${
          importing
            ? 'text-slate-500 border-slate-700'
            : 'text-slate-300 border-slate-700 hover:bg-slate-800'
        }`}>
          <Upload size={13} />
          {importing ? tx("Importing…") : tx("Add sites from a spreadsheet")}
          <input type="file" accept=".csv" className="hidden" onChange={handleImport} disabled={importing} />
        </label>}
      </div>

      {importMsg && (
        <div className={`mb-4 px-3 py-2 rounded-lg text-sm ${
          importMsg.startsWith('✓') ? 'bg-emerald-900/30 text-emerald-400' : 'bg-red-900/30 text-red-400'
        }`}>{importMsg}</div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={13} className="absolute start-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={tx("Search sites…")}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg ps-8 pe-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-hidden focus:border-shield-500"
          />
        </div>
        <Select value={status} onChange={setStatus} options={STATUS_OPTIONS} label={tx("Any track record")} />
        <Select value={method} onChange={setMethod} options={METHOD_OPTIONS} label={tx("Any way to ask")} />
        <Select value={difficulty} onChange={setDifficulty} options={DIFF_OPTIONS} label={tx("Any difficulty")} />
      </div>

      {/* Table */}
      <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-500 text-xs border-b border-slate-700/50">
              <th className="text-start px-4 py-3 font-normal">{tx("Site")}</th>
              <th className="text-start px-4 py-3 font-normal">{tx("Track record")}</th>
              <th className="text-start px-4 py-3 font-normal">{tx("How to ask")}</th>
              <th className="text-start px-4 py-3 font-normal">{tx("Difficulty")}</th>
              <th className="text-start px-4 py-3 font-normal">{tx("CAPTCHA helper")}</th>
              <th className="text-start px-4 py-3 font-normal">{tx("Last request")}</th>
              <th className="text-start px-4 py-3 font-normal">{tx("Check again")}</th>
              <th className="px-4 py-3 font-normal"></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={8} className="px-4 py-8 text-slate-500 text-center">{tx("Loading…")}</td></tr>
            )}
            {!loading && brokers.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-slate-500 text-center">
                {tx("No sites match. Try clearing the filters above.")}
              </td></tr>
            )}
            {!loading && brokers.map(b => (
              <Fragment key={b.id}>
              <tr className="border-t border-slate-700/30 hover:bg-slate-700/20 transition-colors">
                <td className="px-4 py-2.5 text-slate-200 font-medium">
                  <button onClick={() => setOpenId(id => id === b.id ? null : b.id)} aria-expanded={openId === b.id}
                    aria-controls={`hist-${b.id}`} className="flex items-center gap-1 text-start hover:text-white"
                    title={tx("Show the history of requests to this site")}>
                    {openId === b.id ? <ChevronDown size={13} aria-hidden="true" /> : <ChevronRight size={13} aria-hidden="true" />}
                    {b.name}
                  </button>
                </td>
                <td className="px-4 py-2.5"><Badge value={b.status} /></td>
                <td className="px-4 py-2.5"><Badge value={b.method} /></td>
                <td className="px-4 py-2.5"><Badge value={b.difficulty} /></td>
                <td className="px-4 py-2.5">
                  {canManage ? (
                    <select
                      value={b.captcha_plugin_id || ''}
                      aria-label={tx("CAPTCHA helper for {name}", { name: b.name })}
                      onChange={e => handleSolverChange(b.id, e.target.value)}
                      className="bg-slate-900 border border-slate-700 rounded-sm px-2 py-1 text-xs text-slate-300 focus:outline-hidden focus:border-shield-500"
                    >
                      <option value="">{tx("Whichever is on")}</option>
                      {solvers.map(s => (
                        <option key={s.plugin_id} value={s.plugin_id}>
                          {s.name} {!s.enabled ? '(off)' : ''}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-xs text-slate-400">
                      {solvers.find(s => s.plugin_id === b.captcha_plugin_id)?.name || (b.captcha_plugin_id || tx("Whichever is on"))}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5">
                  {b.latest_status ? <Badge value={b.latest_status} /> : <span className="text-slate-600 text-xs">—</span>}
                </td>
                <td className="px-4 py-2.5 text-slate-500 text-xs">
                  {b.recheck_after
                    ? new Date(b.recheck_after) < new Date()
                      ? <span className="text-orange-400">{tx("now")}</span>
                      : fmtDate(b.recheck_after)
                    : '—'}
                </td>
                <td className="px-4 py-2.5 flex items-center gap-2">
                  {canManage && (
                    <button onClick={() => findPrivacyPage(b)} className="text-slate-400 hover:text-shield-300"
                      title={tx("Look on this site for its privacy request page")} aria-label={tx("Find {name}'s privacy request page", { name: b.name })}>
                      <ScanSearch size={13} />
                    </button>
                  )}
                  {b.opt_out_url && (
                    <a
                      href={b.opt_out_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-shield-400 hover:text-shield-300 transition-colors"
                      title={tx("Open the opt-out page")} aria-label={tx("Open {name}'s opt-out page", { name: b.name })}
                    >
                      <ExternalLink size={13} />
                    </a>
                  )}
                </td>
              </tr>
              {openId === b.id && (
                <tr id={`hist-${b.id}`} className="bg-slate-800/60">
                  <td colSpan={8} className="px-4 py-3"><BrokerTimelines brokerId={b.id} /></td>
                </tr>
              )}
              </Fragment>
            ))}
          </tbody>
        </table>
        </div>
      </div>
      {canManage && <PrivacyPagesPanel refreshKey={ppKey} />}
    </div>
  )
}

function Select({ value, onChange, options, label }) {
  return (
    <div className="relative min-w-[110px]">
      <select
        value={value}
        aria-label={label}
        onChange={e => onChange(e.target.value)}
        className="w-full appearance-none bg-slate-800 border border-slate-700 rounded-lg ps-3 pe-7 py-1.5 text-sm text-slate-300 focus:outline-hidden focus:border-shield-500"
      >
        {options.map(o => (
          <option key={o} value={o}>{o ? plainLabel(o) : label}</option>
        ))}
      </select>
      <ChevronDown size={11} className="absolute end-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
    </div>
  )
}
