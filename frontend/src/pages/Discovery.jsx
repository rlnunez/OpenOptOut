import { useEffect, useState } from 'react'
import {
  Search, Play, RefreshCw, CheckCircle, XCircle,
  ExternalLink, ChevronDown, AlertTriangle, Radar
} from 'lucide-react'
import api from '../api'
import Badge from '../components/Badge'
import FindListings from '../components/FindListings'
import { tx, txn } from '../i18n/tx'

function MemberSelect({ members, value, onChange }) {
  return (
    <div className="relative">
      <select value={value ?? ''} onChange={e => onChange(parseInt(e.target.value) || null)}
        className="appearance-none bg-slate-800 border border-slate-700 rounded-lg ps-3 pe-8 py-2 text-sm text-slate-200 focus:outline-hidden focus:border-shield-500 min-w-48">
        <option value="">{tx("Choose a person…")}</option>
        {members.map(m => <option key={m.id} value={m.id}>{m.full_name}</option>)}
      </select>
      <ChevronDown size={11} className="absolute end-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
    </div>
  )
}

function DiscoveryRow({ result }) {
  return (
    <tr className="border-t border-slate-700/30 hover:bg-slate-700/20 transition-colors">
      <td className="px-4 py-3">
        <p className="text-slate-200 text-sm font-medium">{result.broker_name}</p>
      </td>
      <td className="px-4 py-3">
        {result.found
          ? <span className="flex items-center gap-1 text-emerald-400 text-sm"><CheckCircle size={13} aria-hidden="true" />{" "}{tx("Listed")}</span>
          : <span className="flex items-center gap-1 text-slate-600 text-sm"><XCircle size={13} aria-hidden="true" />{" "}{tx("Not listed")}</span>
        }
      </td>
      <td className="px-4 py-3">
        {result.source && (
          <span className={`text-xs px-2 py-0.5 rounded border ${
            result.source === 'google' ? 'text-blue-400 border-blue-800 bg-blue-900/20'
              : result.source === 'manual' ? 'text-emerald-400 border-emerald-800 bg-emerald-900/20'
              : 'text-purple-400 border-purple-800 bg-purple-900/20'
          }`}>{result.source === 'manual' ? tx("added by you") : result.source === 'web_search' ? tx("web search") : result.source === 'scan' ? tx("site check") : String(result.source || '').replace(/_/g, ' ')}</span>
        )}
      </td>
      <td className="px-4 py-3 max-w-64">
        {result.listing_url ? (
          <a href={result.listing_url} target="_blank" rel="noopener noreferrer"
            className="text-shield-400 hover:text-shield-300 text-xs flex items-center gap-1 truncate">
            <ExternalLink size={10} className="shrink-0" />
            <span className="truncate">{result.listing_url}</span>
          </a>
        ) : <span className="text-slate-700 text-xs">—</span>}
      </td>
      <td className="px-4 py-3 text-slate-500 text-xs">
        {new Date(result.scanned_at).toLocaleDateString()}
      </td>
      <td className="px-4 py-3">
        {result.scan_error && (
          <span className="text-red-400 text-xs" title={tx("Couldn't check this site: {scan_error}", { scan_error: result.scan_error })} aria-label={tx("Couldn't check this site")}>
            <AlertTriangle size={12} />
          </span>
        )}
      </td>
    </tr>
  )
}

export default function Discovery() {
  const [members,    setMembers]    = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [results,    setResults]    = useState([])
  const [loading,    setLoading]    = useState(false)
  const [scanning,   setScanning]   = useState(false)
  const [filter,     setFilter]     = useState('all')   // 'all' | 'found' | 'notfound'
  const [searchTerm, setSearch]     = useState('')

  useEffect(() => {
    api.get('/family').then(r => {
      setMembers(r.data)
      if (r.data.length === 1) setSelectedId(r.data[0].id)
    })
  }, [])

  useEffect(() => {
    if (!selectedId) return
    setLoading(true)
    api.get(`/automation/discover/${selectedId}`)
      .then(r => setResults(r.data))
      .finally(() => setLoading(false))
  }, [selectedId])

  const runScan = async () => {
    if (!selectedId) return
    setScanning(true)
    try {
      await api.post(`/automation/discover/${selectedId}`)
      // Poll for results — scan runs in background
      let attempts = 0
      const poll = setInterval(async () => {
        attempts++
        const r = await api.get(`/automation/discover/${selectedId}`)
        setResults(r.data)
        if (attempts >= 20) { clearInterval(poll); setScanning(false) }
      }, 5000)
    } catch (e) {
      setScanning(false)
    }
  }

  const filteredResults = results
    .filter(r => {
      if (filter === 'found')    return r.found
      if (filter === 'notfound') return !r.found
      return true
    })
    .filter(r => !searchTerm || r.broker_name.toLowerCase().includes(searchTerm.toLowerCase()))

  const foundCount    = results.filter(r => r.found).length
  const notFoundCount = results.filter(r => !r.found).length
  const selectedMember = members.find(m => m.id === selectedId)

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">{tx("Find listings")}</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {tx("Find the sites that have a page about each family member")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {members.length > 1 && (
            <MemberSelect members={members} value={selectedId} onChange={setSelectedId} />
          )}
          <button
            onClick={runScan}
            disabled={!selectedId || scanning}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 disabled:opacity-40 transition-colors"
          >
            {scanning ? <RefreshCw size={13} className="animate-spin" /> : <Radar size={13} />}
            {scanning ? tx("Checking sites…") : tx("Check broker sites")}
          </button>
        </div>
      </div>

      <FindListings memberId={selectedId} memberName={selectedMember?.full_name}
        onAdded={() => api.get(`/automation/discover/${selectedId}`).then(r => setResults(r.data))} />

      {scanning && (
        <div className="mb-4 px-4 py-3 bg-shield-900/20 border border-shield-800 rounded-xl">
          <div className="flex items-center gap-2">
            <RefreshCw size={13} className="text-shield-400 animate-spin shrink-0" />
            <div>
              <p className="text-shield-300 text-sm">{tx("Checking broker sites")}</p>
              <p className="text-shield-500 text-xs">
                {tx("OpenOptOut is looking at each broker's site for this person. It can take a few minutes; results appear as they come in.")}
              </p>
            </div>
          </div>
        </div>
      )}

      {selectedMember && results.length > 0 && (
        <>
          {/* Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
            <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4">
              <p className="text-slate-500 text-xs uppercase tracking-wide mb-1">{tx("Sites with a listing")}</p>
              <p className="text-2xl font-semibold text-red-400">{foundCount}</p>
              <p className="text-slate-600 text-xs mt-1">{tx("out of {length} sites checked", { length: results.length })}</p>
            </div>
            <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4">
              <p className="text-slate-500 text-xs uppercase tracking-wide mb-1">{tx("Sites without one")}</p>
              <p className="text-2xl font-semibold text-emerald-400">{notFoundCount}</p>
            </div>
            <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4">
              <p className="text-slate-500 text-xs uppercase tracking-wide mb-1">{tx("Sites checked")}</p>
              <p className="text-2xl font-semibold text-slate-300">{results.length}</p>
              <p className="text-slate-600 text-xs mt-1">{tx("so far")}</p>
            </div>
          </div>

          {foundCount > 0 && (
            <div className="mb-4 px-4 py-3 bg-amber-900/20 border border-amber-800 rounded-xl flex items-center justify-between">
              <p className="text-amber-300 text-sm">
                {txn(foundCount, "{n} site has a listing for {name}. An opt-out was added for it and will be sent automatically.", "{n} sites have a listing for {name}. Opt-outs were added for each one, and will be sent automatically.", { name: selectedMember.full_name })}
              </p>
              <a href="/brokers" className="text-amber-400 text-xs hover:underline shrink-0 ms-3">{tx("See them →")}</a>
            </div>
          )}

          {/* Filters + search */}
          <div className="flex items-center gap-2 mb-4">
            <div className="relative flex-1 max-w-xs">
              <Search size={12} className="absolute start-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input value={searchTerm} onChange={e => setSearch(e.target.value)}
                placeholder={tx("Find a site…")} aria-label={tx("Find a site")}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg ps-8 pe-3 py-1.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500" />
            </div>
            <div className="flex gap-1 bg-slate-800 p-1 rounded-lg border border-slate-700/50">
              {[
                { key: 'all',      label: tx("All ({length})", { length: results.length }) },
                { key: 'found',    label: tx("Listed ({foundCount})", { foundCount }) },
                { key: 'notfound', label: tx("Not listed ({notFoundCount})", { notFoundCount }) },
              ].map(f => (
                <button key={f.key} onClick={() => setFilter(f.key)}
                  className={`px-2.5 py-1 text-xs rounded transition-colors ${
                    filter === f.key ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'
                  }`}>{f.label}</button>
              ))}
            </div>
          </div>

          {/* Results table */}
          <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-xs border-b border-slate-700/50">
                  <th className="text-start px-4 py-3 font-normal">{tx("Site")}</th>
                  <th className="text-start px-4 py-3 font-normal">{tx("Result")}</th>
                  <th className="text-start px-4 py-3 font-normal">{tx("How we know")}</th>
                  <th className="text-start px-4 py-3 font-normal">{tx("Their page")}</th>
                  <th className="text-start px-4 py-3 font-normal">{tx("Checked")}</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} className="px-4 py-8 text-slate-500 text-center">{tx("Loading…")}</td></tr>
                ) : filteredResults.length === 0 ? (
                  <tr><td colSpan={6} className="px-4 py-8 text-slate-500 text-center">{tx("Nothing matches. Try a different word or filter.")}</td></tr>
                ) : (
                  filteredResults.map(r => <DiscoveryRow key={r.id} result={r} />)
                )}
              </tbody>
            </table>
            </div>
          </div>
        </>
      )}

      {!selectedId && (
        <div className="text-center py-16 bg-slate-800/50 rounded-xl border border-dashed border-slate-700">
          <Radar size={32} className="text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400 text-sm">{tx("Choose a family member to look for their listings")}</p>
        </div>
      )}

      {selectedId && results.length === 0 && !loading && !scanning && (
        <div className="text-center py-16 bg-slate-800/50 rounded-xl border border-dashed border-slate-700">
          <Radar size={32} className="text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400 text-sm font-medium">{tx("No sites checked yet")}</p>
          <p className="text-slate-600 text-xs mt-1 mb-4">
            {tx("Press \"Check broker sites\" to look for {full_name} on every broker OpenOptOut knows.", { full_name: selectedMember?.full_name })}
          </p>
          <button onClick={runScan}
            className="px-4 py-2 bg-shield-600 text-white text-sm rounded-lg hover:bg-shield-700 transition-colors">
            {tx("Check broker sites")}
          </button>
        </div>
      )}
    </div>
  )
}
