import { useEffect, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Plus, Trash2, Star, StarOff, ChevronDown,
  ShieldCheck, User, Mail, Phone, MapPin, Eye, EyeOff,
  AlertCircle, Grid3X3, Home, FileText, Edit2, Check, X
} from 'lucide-react'
import api from '../api'

// ── Config ────────────────────────────────────────────────────────────────────

// Vault limits loaded from API — see VaultLimitsSection in Settings
const DEFAULT_LIMITS = { name: 4, email: 5, phone: 5, address: 10 }

const KINDS = [
  {
    key: 'name', label: 'Name variants', icon: User,
    color: 'text-purple-400', bg: 'bg-purple-900/20 border-purple-800/50',
    placeholder: 'e.g. Robert Nunez, Rob Nunez, Bobby Nunez',
    hint: 'Include maiden names, nicknames, middle name variants, misspellings that appear on broker sites.',
  },
  {
    key: 'email', label: 'Email addresses', icon: Mail,
    color: 'text-blue-400', bg: 'bg-blue-900/20 border-blue-800/50',
    placeholder: 'e.g. robert@gmail.com',
    hint: 'Add all addresses you\'ve ever used — each may appear on different broker sites.',
  },
  {
    key: 'phone', label: 'Phone numbers', icon: Phone,
    color: 'text-emerald-400', bg: 'bg-emerald-900/20 border-emerald-800/50',
    placeholder: 'e.g. (713) 555-0142',
    hint: 'Include current and all past numbers. Especially important if tied to old addresses.',
  },
  {
    key: 'address', label: 'Addresses', icon: MapPin,
    color: 'text-amber-400', bg: 'bg-amber-900/20 border-amber-800/50',
    placeholder: 'e.g. 123 Main St, Houston TX 77001',
    hint: 'Add current and past addresses going back as far as possible. Format: Street, City, ST ZIP.',
  },
]

// ── Combination matrix preview ────────────────────────────────────────────────

function MatrixPreview({ stats, memberId }) {
  if (!stats) return null
  const { names, addresses, phones, emails, discovery_combos, optout_combos, limits = DEFAULT_LIMITS } = stats

  const atLimit = kind => {
    const counts = { name: names, address: addresses, phone: phones, email: emails }
    return counts[kind] >= limits[kind]
  }

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 p-4 mb-5">
      <div className="flex items-center gap-2 mb-3">
        <Grid3X3 size={13} className="text-shield-400" />
        <p className="text-slate-300 text-sm font-medium">Combination matrix</p>
        <span className="text-slate-600 text-xs ml-auto">
          How many searches the bot will run per broker
        </span>
      </div>

      {/* Count pills */}
      <div className="flex gap-2 flex-wrap mb-3">
        {[
          { label: 'names',     value: names,     limit: limits.name,    color: 'purple' },
          { label: 'addresses', value: addresses, limit: limits.address,  color: 'amber' },
          { label: 'phones',    value: phones,    limit: limits.phone,    color: 'emerald' },
          { label: 'emails',    value: emails,    limit: limits.email,    color: 'blue' },
        ].map(({ label, value, limit, color }) => (
          <div key={label}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs ${
              value >= limit
                ? `bg-${color}-900/30 border-${color}-700 text-${color}-300`
                : 'bg-slate-800 border-slate-700 text-slate-400'
            }`}>
            <span className={`font-semibold ${value >= limit ? `text-${color}-300` : 'text-slate-200'}`}>
              {value}/{limit}
            </span>
            {label}
            {value >= limit && <span className="text-xs opacity-60">✓ max</span>}
          </div>
        ))}
      </div>

      {/* Matrix sizes */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <p className="text-slate-500 mb-0.5">Discovery pass (name × address)</p>
          <p className="text-slate-200 font-semibold text-sm">{discovery_combos} searches</p>
          <p className="text-slate-600">per broker to find listings</p>
        </div>
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <p className="text-slate-500 mb-0.5">Opt-out pass (all combinations)</p>
          <p className="text-slate-200 font-semibold text-sm">{optout_combos.toLocaleString()} submissions</p>
          <p className="text-slate-600">per broker where you're found</p>
        </div>
      </div>

      {optout_combos > 200 && (
        <div className="mt-2 flex items-start gap-1.5 text-amber-400 text-xs">
          <AlertCircle size={11} className="shrink-0 mt-0.5" />
          <span>
            Large matrix — the bot uses a 1.5s delay between submissions per broker
            to avoid triggering rate limits.
          </span>
        </div>
      )}

      {/* Property records summary */}
      {(stats.deed_addresses > 0 || stats.mortgage_addresses > 0 || stats.has_formal_name) && (
        <div className="mt-3 pt-3 border-t border-slate-700/30">
          <p className="text-slate-500 text-xs uppercase tracking-wide mb-2">Property records</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
            <div className="bg-slate-800 rounded-lg px-2.5 py-2">
              <p className="text-slate-500 mb-0.5">Formal name</p>
              <p className={stats.has_formal_name ? 'text-slate-200 font-medium truncate' : 'text-slate-700 italic'}>
                {stats.formal_name || 'not set'}
              </p>
            </div>
            <div className="bg-slate-800 rounded-lg px-2.5 py-2">
              <p className="text-slate-500 mb-0.5">Deed addresses</p>
              <p className={stats.deed_addresses > 0 ? 'text-purple-400 font-semibold' : 'text-slate-700'}>
                {stats.deed_addresses}
              </p>
            </div>
            <div className="bg-slate-800 rounded-lg px-2.5 py-2">
              <p className="text-slate-500 mb-0.5">Mortgage addresses</p>
              <p className={stats.mortgage_addresses > 0 ? 'text-blue-400 font-semibold' : 'text-slate-700'}>
                {stats.mortgage_addresses}
              </p>
            </div>
          </div>
          <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            <div className="bg-slate-800 rounded-lg px-2.5 py-2">
              <p className="text-slate-500 mb-0.5">Property discovery</p>
              <p className="text-slate-200 font-semibold">{stats.property_discovery_combos} searches</p>
            </div>
            <div className="bg-slate-800 rounded-lg px-2.5 py-2">
              <p className="text-slate-500 mb-0.5">Property opt-out</p>
              <p className="text-slate-200 font-semibold">{stats.property_optout_combos} submissions</p>
            </div>
          </div>
          {!stats.has_formal_name && (stats.deed_addresses > 0 || stats.mortgage_addresses > 0) && (
            <p className="text-amber-400 text-xs mt-2 flex items-center gap-1">
              <AlertCircle size={10} />
              Add a formal name above to use the exact legal name for property record removal.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ── Member selector ───────────────────────────────────────────────────────────

function MemberSelector({ members, selectedId, onChange }) {
  return (
    <div className="relative">
      <select value={selectedId ?? ''} onChange={e => onChange(parseInt(e.target.value))}
        className="appearance-none bg-slate-800 border border-slate-700 rounded-lg pl-3 pr-8 py-2 text-sm text-slate-200 focus:outline-hidden focus:border-shield-500 min-w-48">
        <option value="" disabled>Select member…</option>
        {members.map(m => <option key={m.id} value={m.id}>{m.full_name}</option>)}
      </select>
      <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
    </div>
  )
}


// ── Formal name editor ────────────────────────────────────────────────────────

function FormalNameEditor({ member, onUpdated }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal]         = useState(member.formal_name || '')
  const [saving, setSaving]   = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      const { data } = await api.patch(`/family/${member.id}`, { formal_name: val.trim() })
      onUpdated(data)
      setEditing(false)
    } finally { setSaving(false) }
  }

  const clear = async () => {
    setSaving(true)
    try {
      const { data } = await api.patch(`/family/${member.id}`, { formal_name: '' })
      setVal('')
      onUpdated(data)
      setEditing(false)
    } finally { setSaving(false) }
  }

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4 mb-4">
      <div className="flex items-center gap-2 mb-2">
        <FileText size={13} className="text-shield-400" />
        <p className="text-slate-300 text-sm font-medium">Formal / legal name</p>
        <span className="text-slate-600 text-xs">— used for property record searches only · max 1</span>
      </div>

      {editing ? (
        <div className="flex gap-2">
          <input
            value={val}
            onChange={e => setVal(e.target.value)}
            placeholder="e.g. Robert Antonio Nunez"
            autoFocus
            onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false) }}
            className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500 font-mono"
          />
          <button onClick={save} disabled={saving}
            className="px-2 py-1.5 bg-shield-600 text-white rounded-lg text-sm hover:bg-shield-700 disabled:opacity-40 transition-colors">
            {saving ? '…' : <Check size={13} />}
          </button>
          <button onClick={() => setEditing(false)}
            className="px-2 py-1.5 text-slate-500 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors">
            <X size={13} />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          {member.formal_name ? (
            <>
              <span className="text-slate-200 text-sm font-mono flex-1">{member.formal_name}</span>
              <button onClick={() => { setVal(member.formal_name); setEditing(true) }}
                className="text-slate-500 hover:text-shield-400 transition-colors p-1">
                <Edit2 size={12} />
              </button>
              <button onClick={clear} disabled={saving}
                className="text-slate-500 hover:text-red-400 transition-colors p-1">
                <X size={12} />
              </button>
            </>
          ) : (
            <button onClick={() => setEditing(true)}
              className="flex items-center gap-1.5 text-slate-500 hover:text-slate-300 text-sm transition-colors">
              <Plus size={12} /> Add formal name
              <span className="text-slate-700 text-xs">(name as it appears on deeds and mortgages)</span>
            </button>
          )}
        </div>
      )}

      {member.formal_name && (
        <p className="text-slate-600 text-xs mt-2">
          Property record searches will use this name instead of your name variants.
        </p>
      )}
    </div>
  )
}

// ── Add identity row ──────────────────────────────────────────────────────────

function AddIdentityRow({ kind, memberId, currentCount, maxCount, onAdded }) {
  const [val, setVal]       = useState('')
  const [primary, setPrimary] = useState(false)
  const [saving, setSaving]   = useState(false)
  const cfg   = KINDS.find(k => k.key === kind)
  const limit = maxCount ?? DEFAULT_LIMITS[kind] ?? 10
  const atMax = currentCount >= limit

  const submit = async e => {
    e.preventDefault()
    if (!val.trim() || atMax) return
    setSaving(true)
    try {
      const { data } = await api.post(`/identity/${memberId}`, {
        kind, value: val.trim(), is_primary: primary,
      })
      onAdded(data)
      setVal(''); setPrimary(false)
    } finally { setSaving(false) }
  }

  if (atMax) return (
    <p className="text-slate-600 text-xs mt-2 italic">
      Maximum {limit} {kind}s reached per member.
    </p>
  )

  return (
    <form onSubmit={submit} className="flex gap-2 mt-2">
      <input value={val} onChange={e => setVal(e.target.value)}
        placeholder={cfg.placeholder}
        className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500" />
      <button type="button" onClick={() => setPrimary(p => !p)}
        title={primary ? 'Primary — used first in opt-outs' : 'Set as primary'}
        className={`px-2 rounded-lg border transition-colors ${primary ? 'text-amber-400 border-amber-700 bg-amber-900/20' : 'text-slate-600 border-slate-700 hover:text-amber-400'}`}>
        <Star size={13} />
      </button>
      <button type="submit" disabled={saving || !val.trim()}
        className="flex items-center gap-1 px-3 py-1.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-sm rounded-lg transition-colors">
        <Plus size={13} />{saving ? '…' : 'Add'}
      </button>
    </form>
  )
}

// ── Identity row ──────────────────────────────────────────────────────────────

function IdentityRow({ identity, onDeleted, onTogglePrimary, masked }) {
  const [deleting, setDeleting] = useState(false)

  const del = async () => {
    setDeleting(true)
    try { await api.delete(`/identity/${identity.id}`); onDeleted(identity.id) }
    finally { setDeleting(false) }
  }

  const togglePrimary = async () => {
    const { data } = await api.patch(`/identity/${identity.id}`, { is_primary: !identity.is_primary })
    onTogglePrimary(data)
  }

  const maskedVal = (val, kind) => {
    if (kind === 'email') {
      const [local, domain] = val.split('@')
      return `${local[0]}${'*'.repeat(Math.max(local.length - 2, 2))}${local.slice(-1)}@${domain}`
    }
    if (kind === 'phone')   return val.replace(/\d(?=\d{4})/g, '*')
    if (kind === 'address') return val.replace(/\d/g, '*')
    return val
  }

  return (
    <div className={`flex items-center gap-2 py-2 px-3 rounded-lg group ${identity.is_primary ? 'bg-slate-700/30' : 'hover:bg-slate-800/50'}`}>
      {identity.is_primary && <Star size={11} className="text-amber-400 shrink-0" title="Primary" />}
      <span className={`flex-1 text-sm font-mono ${identity.is_primary ? 'text-slate-200' : 'text-slate-400'}`}>
        {masked ? maskedVal(identity.value, identity.kind) : identity.value}
      </span>
      {identity.kind === 'address' && (identity.is_deed || identity.is_mortgage) && (
        <div className="flex gap-1 shrink-0">
          {identity.is_deed && (
            <span className="flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-sm bg-purple-900/30 text-purple-400 border border-purple-800">
              <Home size={9} /> deed
            </span>
          )}
          {identity.is_mortgage && (
            <span className="flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-sm bg-blue-900/30 text-blue-400 border border-blue-800">
              <FileText size={9} /> mortgage
            </span>
          )}
        </div>
      )}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onClick={togglePrimary}
          className={`p-1 rounded-sm transition-colors ${identity.is_primary ? 'text-amber-400 hover:text-slate-400' : 'text-slate-600 hover:text-amber-400'}`}
          title={identity.is_primary ? 'Remove primary' : 'Set as primary'}>
          {identity.is_primary ? <StarOff size={12} /> : <Star size={12} />}
        </button>
        <button onClick={del} disabled={deleting}
          className="p-1 rounded-sm text-slate-600 hover:text-red-400 transition-colors">
          <Trash2 size={12} />
        </button>
      </div>
    </div>
  )
}

// ── Kind section ──────────────────────────────────────────────────────────────

function KindSection({ cfg, identities, memberId, onAdded, onDeleted, onTogglePrimary, masked, limits }) {
  const { key, label, icon: Icon, color, bg, hint } = cfg
  const mine  = identities.filter(i => i.kind === key)
  const limit = limits?.[key] ?? DEFAULT_LIMITS[key] ?? 10
  const [open, setOpen] = useState(true)

  return (
    <div className={`rounded-xl border ${bg} overflow-hidden`}>
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <Icon size={14} className={color} />
          <span className="text-slate-200 text-sm font-medium">{label}</span>
          <span className="text-slate-500 text-xs">({mine.length}/{limit})</span>
          {mine.length >= limit && (
            <span className={`text-xs px-1.5 py-0.5 rounded-sm ${color} bg-opacity-10 border border-current opacity-60`}>
              max
            </span>
          )}
        </div>
        <ChevronDown size={13} className={`text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-4">
          <p className="text-slate-500 text-xs mb-3">{hint}</p>
          <div className="space-y-0.5 mb-2">
            {mine.length === 0 && (
              <p className="text-slate-600 text-xs italic py-1">None added yet</p>
            )}
            {mine.map(i => (
              <IdentityRow key={i.id} identity={i} masked={masked}
                onDeleted={onDeleted} onTogglePrimary={onTogglePrimary} />
            ))}
          </div>
          <AddIdentityRow kind={key} memberId={memberId}
            currentCount={mine.length} maxCount={limit} onAdded={onAdded} />
        </div>
      )}
    </div>
  )
}

// ── Vault score ───────────────────────────────────────────────────────────────

function VaultScore({ identities }) {
  const counts = KINDS.map(k => ({
    ...k, count: identities.filter(i => i.kind === k.key).length,
  }))
  const filled     = counts.filter(k => k.count > 0).length
  const pct        = Math.round((filled / KINDS.length) * 100)
  const hasPrimary = KINDS.every(k => identities.some(i => i.kind === k.key && i.is_primary))

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4 mb-5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-slate-400 text-xs uppercase tracking-wide">Vault completeness</span>
        <span className={`text-sm font-semibold ${pct === 100 ? 'text-emerald-400' : 'text-amber-400'}`}>{pct}%</span>
      </div>
      <div className="h-1.5 bg-slate-700 rounded-full mb-3">
        <div className={`h-full rounded-full transition-all ${pct === 100 ? 'bg-emerald-500' : 'bg-amber-500'}`}
          style={{ width: `${pct}%` }} />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {counts.map(k => (
          <div key={k.key} className="text-center">
            <k.icon size={12} className={`mx-auto mb-0.5 ${k.count > 0 ? k.color : 'text-slate-700'}`} />
            <p className={`text-xs ${k.count > 0 ? 'text-slate-300' : 'text-slate-700'}`}>
              {k.count}
            </p>
            <p className="text-slate-600 text-xs">{k.label.split(' ')[0]}</p>
          </div>
        ))}
      </div>
      {!hasPrimary && pct > 0 && (
        <p className="text-amber-400 text-xs mt-3 flex items-center gap-1">
          <Star size={10} /> Mark one entry per category as primary — used first in opt-outs.
        </p>
      )}
      {pct === 100 && hasPrimary && (
        <p className="text-emerald-400 text-xs mt-3 flex items-center gap-1">
          <ShieldCheck size={10} /> Vault complete — ready to run opt-outs.
        </p>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function IdentityVault() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [members, setMembers]       = useState([])
  const [identities, setIdentities] = useState([])
  const [stats, setStats]           = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [masked, setMasked]         = useState(true)
  const [loading, setLoading]       = useState(true)

  useEffect(() => {
    api.get('/family').then(r => {
      setMembers(r.data)
      const param = parseInt(searchParams.get('member'))
      const first = param || r.data[0]?.id || null
      if (first) setSelectedId(first)
    }).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedId) return
    setStats(null)
    api.get(`/identity/${selectedId}`).then(r => setIdentities(r.data))
    api.get(`/identity/${selectedId}/stats`).then(r => setStats(r.data)).catch(() => {})
    setSearchParams({ member: selectedId })
  }, [selectedId])

  // Refresh stats when identities change
  const refreshStats = useCallback(() => {
    if (!selectedId) return
    api.get(`/identity/${selectedId}/stats`).then(r => setStats(r.data)).catch(() => {})
  }, [selectedId])

  const onAdded = i => { setIdentities(prev => [...prev, i]); refreshStats() }
  const onDeleted = id => { setIdentities(prev => prev.filter(i => i.id !== id)); refreshStats() }
  const onTogglePrimary = i => setIdentities(prev => prev.map(x => {
    if (x.kind === i.kind && x.is_primary && x.id !== i.id) return { ...x, is_primary: false }
    if (x.id === i.id) return i
    return x
  }))

  const selectedMember = members.find(m => m.id === selectedId)

  return (
    <div className="p-4 md:p-6 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">Identity vault</h1>
          <p className="text-slate-400 text-sm mt-0.5">All PII variants used to find and remove listings</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setMasked(m => !m)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
            {masked ? <Eye size={12} /> : <EyeOff size={12} />}
            {masked ? 'Show' : 'Hide'}
          </button>
          {members.length > 1 && (
            <MemberSelector members={members} selectedId={selectedId} onChange={setSelectedId} />
          )}
        </div>
      </div>

      {loading && <p className="text-slate-500 text-sm">Loading…</p>}

      {!loading && members.length === 0 && (
        <div className="text-center py-16 bg-slate-800/50 rounded-xl border border-dashed border-slate-700">
          <ShieldCheck size={32} className="text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400 text-sm">No family members yet.</p>
          <a href="/family" className="text-shield-400 text-sm hover:underline mt-1 block">Add a family member first →</a>
        </div>
      )}

      {!loading && selectedMember && (
        <>
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-full bg-shield-600/30 border border-shield-600/50 flex items-center justify-center text-xs font-medium text-shield-300">
              {selectedMember.full_name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase()}
            </div>
            <span className="text-white font-medium">{selectedMember.full_name}</span>
            {selectedMember.age && <span className="text-slate-500 text-sm">· Age {selectedMember.age}</span>}
          </div>

          <FormalNameEditor
            member={selectedMember}
            onUpdated={m => {
              setMembers(prev => prev.map(x => x.id === m.id ? m : x))
            }}
          />
          <VaultScore identities={identities} />
          <MatrixPreview stats={stats} memberId={selectedId} />

          <div className="space-y-3">
            {KINDS.map(cfg => (
              <KindSection key={cfg.key} cfg={cfg} identities={identities}
                memberId={selectedId} masked={masked} limits={stats?.limits}
                onAdded={onAdded} onDeleted={onDeleted} onTogglePrimary={onTogglePrimary} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
