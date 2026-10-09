import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  UserPlus, Trash2, ChevronRight, Users,
  ShieldCheck, AlertCircle, Edit2, Check, X
} from 'lucide-react'
import api from '../api'

const KIND_LABELS = { name: 'Names', email: 'Emails', phone: 'Phones', address: 'Addresses' }
const KIND_COLORS = {
  name:    'bg-purple-900/40 text-purple-300 border-purple-800',
  email:   'bg-blue-900/40   text-blue-300   border-blue-800',
  phone:   'bg-emerald-900/40 text-emerald-300 border-emerald-800',
  address: 'bg-amber-900/40  text-amber-300   border-amber-800',
}

function initials(name) {
  return name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase()
}

function Avatar({ name, size = 'md' }) {
  const sz = size === 'lg' ? 'w-12 h-12 text-base' : 'w-9 h-9 text-sm'
  return (
    <div className={`${sz} rounded-full bg-shield-600/30 border border-shield-600/50 flex items-center justify-center font-medium text-shield-300 shrink-0`}>
      {initials(name)}
    </div>
  )
}

function IdentityPill({ kind }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-sm text-xs border ${KIND_COLORS[kind] ?? 'bg-slate-800 text-slate-400 border-slate-700'}`}>
      {kind}
    </span>
  )
}

// ── Add member modal ──────────────────────────────────────────────────────────

function AddMemberModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [age, setAge]   = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState('')

  const submit = async e => {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    try {
      const { data } = await api.post('/family', { full_name: name.trim(), age: age ? parseInt(age) : null })
      onCreated(data)
      onClose()
    } catch {
      setError('Failed to add member')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-sm p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-white font-semibold">Add family member</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors"><X size={16} /></button>
        </div>
        {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="text-slate-400 text-xs mb-1 block">Full name *</label>
            <input
              value={name} onChange={e => setName(e.target.value)}
              placeholder="Jane Smith"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"
              required autoFocus
            />
          </div>
          <div>
            <label className="text-slate-400 text-xs mb-1 block">Age <span className="text-slate-600">(optional)</span></label>
            <input
              type="number" value={age} onChange={e => setAge(e.target.value)}
              placeholder="42"
              min="1" max="120"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"
            />
          </div>
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className="flex-1 py-2 border border-slate-700 rounded-lg text-slate-400 text-sm hover:bg-slate-800 transition-colors">Cancel</button>
            <button type="submit" disabled={saving} className="flex-1 py-2 bg-shield-600 hover:bg-shield-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
              {saving ? 'Adding…' : 'Add member'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Inline edit name ──────────────────────────────────────────────────────────

function EditableName({ member, onUpdated }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(member.full_name)

  const save = async () => {
    if (!val.trim() || val === member.full_name) { setEditing(false); return }
    await api.patch(`/family/${member.id}`, { full_name: val.trim() })
    onUpdated({ ...member, full_name: val.trim() })
    setEditing(false)
  }

  if (editing) return (
    <div className="flex items-center gap-1">
      <input
        value={val} onChange={e => setVal(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false) }}
        className="bg-slate-700 border border-slate-600 rounded-sm px-2 py-0.5 text-sm text-white focus:outline-hidden focus:border-shield-500 w-40"
        autoFocus
      />
      <button onClick={save} className="text-emerald-400 hover:text-emerald-300"><Check size={13} /></button>
      <button onClick={() => setEditing(false)} className="text-slate-500 hover:text-white"><X size={13} /></button>
    </div>
  )

  return (
    <button
      onClick={() => setEditing(true)}
      className="flex items-center gap-1.5 text-white font-medium hover:text-shield-300 transition-colors group"
    >
      {member.full_name}
      <Edit2 size={11} className="text-slate-600 group-hover:text-shield-400 transition-colors" />
    </button>
  )
}

// ── Member card ───────────────────────────────────────────────────────────────

function MemberCard({ member, onUpdated, onDeleted, onSelect, selected }) {
  const kindCounts = member.identities.reduce((acc, i) => {
    acc[i.kind] = (acc[i.kind] || 0) + 1; return acc
  }, {})
  const total = member.identities.length
  const complete = Object.keys(KIND_LABELS).every(k => kindCounts[k] > 0)

  const deleteMember = async () => {
    if (!confirm(`Remove ${member.full_name} and all their data?`)) return
    await api.delete(`/family/${member.id}`)
    onDeleted(member.id)
  }

  return (
    <div
      className={`bg-slate-800 rounded-xl border transition-all cursor-pointer ${
        selected ? 'border-shield-500 ring-1 ring-shield-500/30' : 'border-slate-700/50 hover:border-slate-600'
      }`}
      onClick={() => onSelect(member)}
    >
      <div className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <Avatar name={member.full_name} size="lg" />
            <div>
              <EditableName member={member} onUpdated={onUpdated} />
              <p className="text-slate-500 text-xs mt-0.5">
                {member.age ? `Age ${member.age} · ` : ''}{total} identit{total === 1 ? 'y' : 'ies'}
              </p>
            </div>
          </div>
          <button
            onClick={e => { e.stopPropagation(); deleteMember() }}
            className="text-slate-600 hover:text-red-400 transition-colors p-1"
            title="Remove member"
          >
            <Trash2 size={13} />
          </button>
        </div>

        {/* Identity kind pills */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          {Object.entries(KIND_LABELS).map(([kind, label]) => (
            <span
              key={kind}
              className={`text-xs px-2 py-0.5 rounded border ${
                kindCounts[kind]
                  ? KIND_COLORS[kind]
                  : 'bg-slate-900 text-slate-600 border-slate-700 opacity-50'
              }`}
            >
              {kindCounts[kind] ? `${kindCounts[kind]} ${kind}${kindCounts[kind] > 1 ? 's' : ''}` : label}
            </span>
          ))}
        </div>

        {/* Completeness indicator */}
        <div className="flex items-center justify-between">
          <div className={`flex items-center gap-1.5 text-xs ${complete ? 'text-emerald-400' : 'text-amber-400'}`}>
            {complete
              ? <><ShieldCheck size={11} /> Vault complete</>
              : <><AlertCircle size={11} /> Add more identity data</>
            }
          </div>
          <ChevronRight size={13} className={`transition-colors ${selected ? 'text-shield-400' : 'text-slate-600'}`} />
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Family() {
  const navigate = useNavigate()
  const [members, setMembers]     = useState([])
  const [loading, setLoading]     = useState(true)
  const [showAdd, setShowAdd]     = useState(false)
  const [selected, setSelected]   = useState(null)

  useEffect(() => {
    api.get('/family').then(r => {
      setMembers(r.data)
      if (r.data.length > 0) setSelected(r.data[0])
    }).finally(() => setLoading(false))
  }, [])

  const handleCreated = m => {
    setMembers(prev => [...prev, m])
    setSelected(m)
  }

  const handleUpdated = m => {
    setMembers(prev => prev.map(x => x.id === m.id ? m : x))
    if (selected?.id === m.id) setSelected(m)
  }

  const handleDeleted = id => {
    const remaining = members.filter(x => x.id !== id)
    setMembers(remaining)
    setSelected(remaining[0] ?? null)
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">Family members</h1>
          <p className="text-slate-400 text-sm mt-0.5">Everyone you're protecting. Click a member to manage their identity data.</p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 transition-colors"
        >
          <UserPlus size={13} /> Add member
        </button>
      </div>

      {loading && <p className="text-slate-500 text-sm">Loading…</p>}

      {!loading && members.length === 0 && (
        <div className="text-center py-16 bg-slate-800/50 rounded-xl border border-dashed border-slate-700">
          <Users size={32} className="text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400 text-sm font-medium">No family members yet</p>
          <p className="text-slate-600 text-xs mt-1 mb-4">Add yourself first, then add family members</p>
          <button
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 bg-shield-600 text-white text-sm rounded-lg hover:bg-shield-700 transition-colors"
          >
            Add first member
          </button>
        </div>
      )}

      {!loading && members.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
          {members.map(m => (
            <MemberCard
              key={m.id}
              member={m}
              selected={selected?.id === m.id}
              onSelect={m => { setSelected(m); navigate(`/identity?member=${m.id}`) }}
              onUpdated={handleUpdated}
              onDeleted={handleDeleted}
            />
          ))}
        </div>
      )}

      {showAdd && (
        <AddMemberModal onClose={() => setShowAdd(false)} onCreated={handleCreated} />
      )}
    </div>
  )
}
