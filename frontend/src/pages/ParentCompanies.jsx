import { useEffect, useState, useCallback } from 'react'
import {
  Building2, RefreshCw, Plus, Trash2, Search, X, Mail,
  CheckCircle2, AlertTriangle, XCircle, HelpCircle, Link2, FlaskConical, Send
} from 'lucide-react'
import api from '../api'

const HONOR = {
  honors:  { label: 'Honors requests', icon: CheckCircle2, cls: 'text-emerald-400' },
  partial: { label: 'Partial',         icon: AlertTriangle, cls: 'text-amber-400' },
  ignores: { label: 'Ignores',         icon: XCircle,      cls: 'text-red-400' },
  bounces: { label: 'Email bounces',   icon: XCircle,      cls: 'text-red-400' },
  unknown: { label: 'Unknown',         icon: HelpCircle,   cls: 'text-slate-500' },
}

export default function ParentCompanies() {
  const [parents, setParents] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null)   // parent obj or {} for new
  const [managing, setManaging] = useState(null)  // parent whose children we manage
  const [msg, setMsg] = useState('')

  const [dispatching, setDispatching] = useState(null)
  const [dispatchingAll, setDispatchingAll] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    api.get('/parent-companies').then(r => setParents(r.data)).finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])

  const remove = async (p) => {
    if (!window.confirm(`Delete parent "${p.name}"? Its ${p.child_count} child broker(s) will be ungrouped, not deleted.`)) return
    try { await api.delete(`/parent-companies/${p.id}`); setMsg(`Deleted ${p.name}`); load() }
    catch { setMsg('Delete failed') }
  }

  const dispatchParent = async (p) => {
    setDispatching(p.id)
    try {
      const res = await api.post(`/parent-companies/${p.id}/dispatch`)
      const d = res.data
      if (d.covered_requests > 0) {
        setMsg(`Sent ${d.sent_emails} email(s) to ${p.name}, covering ${d.covered_requests} broker requests`)
      } else {
        setMsg(`No pending requests for ${p.name}'s child brokers`)
      }
      load()
    } catch (e) {
      setMsg(e.response?.data?.detail || 'Dispatch failed')
    } finally {
      setDispatching(null)
    }
  }

  const dispatchAll = async () => {
    setDispatchingAll(true)
    try {
      const res = await api.post('/parent-companies/dispatch-all')
      const d = res.data
      if (d.covered_requests > 0) {
        setMsg(`Dispatched ${d.sent_emails} email(s) across parent companies, covering ${d.covered_requests} requests`)
      } else {
        setMsg('No pending requests under any parent company')
      }
      load()
    } catch (e) {
      setMsg(e.response?.data?.detail || 'Dispatch all failed')
    } finally {
      setDispatchingAll(false)
    }
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-start justify-between mb-1 flex-wrap gap-2">
        <div>
          <h1 className="text-white text-xl font-semibold flex items-center gap-2">
            <Building2 size={20} className="text-shield-500" /> Parent companies
          </h1>
          <p className="text-slate-400 text-sm mt-0.5">
            Group broker front-sites under the company that operates them. One email opt-out to a
            parent covers all its child sites at once. Effectiveness shows which parents actually respond.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={dispatchAll} disabled={dispatchingAll}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
            title="Dispatch email opt-outs across all parent companies">
            <Send size={14} /> {dispatchingAll ? 'Dispatching…' : 'Send all parent opt-outs'}
          </button>
          <button onClick={() => setEditing({})}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 hover:bg-shield-700 text-white rounded-lg">
            <Plus size={14} /> New parent
          </button>
          <button onClick={load} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      <TestBrokerPanel onChanged={load} />

      {msg && (
        <div className="mt-3 px-3 py-2 rounded-lg border border-slate-700 bg-slate-800/60 text-slate-300 text-xs flex items-center justify-between">
          <span>{msg}</span>
          <button onClick={() => setMsg('')} className="text-slate-500 hover:text-slate-300"><X size={13} /></button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm py-12 justify-center mt-4">
          <RefreshCw size={14} className="animate-spin" /> Loading…
        </div>
      ) : parents.length === 0 ? (
        <div className="flex flex-col items-center gap-2 text-slate-500 py-12 mt-4">
          <Building2 size={26} className="text-slate-600" />
          <p className="text-sm">No parent companies yet. Create one, then group its broker sites under it.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 mt-4">
          {parents.map(p => {
            const h = HONOR[p.honor_status] || HONOR.unknown
            const HIcon = h.icon
            return (
              <div key={p.id} className="bg-slate-800/40 rounded-xl border border-slate-700/50 px-4 py-3">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-100 font-medium">{p.name}</span>
                      <span className={`inline-flex items-center gap-1 text-xs ${h.cls}`}>
                        <HIcon size={12} /> {h.label}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-slate-400 flex-wrap">
                      {p.optout_email
                        ? <span className="inline-flex items-center gap-1"><Mail size={11} /> {p.optout_email}</span>
                        : <span className="text-amber-400/80 inline-flex items-center gap-1"><AlertTriangle size={11} /> no opt-out email set</span>}
                      <span>· {p.child_count} child site{p.child_count === 1 ? '' : 's'}</span>
                      {p.emails_sent > 0 && (
                        <span>· {p.emails_confirmed}/{p.emails_sent} confirmed
                          {p.confirm_rate != null ? ` (${p.confirm_rate}%)` : ''}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0 items-center">
                    {p.optout_email && p.child_count > 0 && (
                      <button onClick={() => dispatchParent(p)} disabled={dispatching === p.id}
                        className="flex items-center gap-1 px-2.5 py-1 text-xs text-sky-300 bg-sky-950/60 border border-sky-800/60 rounded-lg hover:bg-sky-900/60 transition-colors"
                        title="Send opt-out email covering all child broker requests for this parent">
                        <Send size={11} /> {dispatching === p.id ? 'Sending…' : 'Send opt-outs'}
                      </button>
                    )}
                    <button onClick={() => setManaging(p)}
                      className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
                      <Link2 size={12} /> Sites
                    </button>
                    <button onClick={() => setEditing(p)}
                      className="px-2.5 py-1 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">Edit</button>
                    <button onClick={() => remove(p)}
                      className="px-2 py-1 text-xs text-slate-500 hover:text-red-400"><Trash2 size={13} /></button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {editing && <EditModal parent={editing} onClose={() => setEditing(null)}
        onSaved={(m) => { setMsg(m); setEditing(null); load() }} />}
      {managing && <ManageChildrenModal parent={managing} onClose={() => setManaging(null)}
        onChanged={() => load()} />}
    </div>
  )
}

function EditModal({ parent, onClose, onSaved }) {
  const isNew = !parent.id
  const [form, setForm] = useState({
    name: parent.name || '', optout_email: parent.optout_email || '',
    cc_emails: parent.cc_emails || '', locale: parent.locale || 'en',
    website: parent.website || '', notes: parent.notes || '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async () => {
    if (!form.name.trim()) { setError('Name is required'); return }
    setSaving(true); setError('')
    try {
      if (isNew) await api.post('/parent-companies', form)
      else await api.patch(`/parent-companies/${parent.id}`, form)
      onSaved(isNew ? `Created ${form.name}` : `Updated ${form.name}`)
    } catch (e) { setError(e.response?.data?.detail || 'Save failed') }
    finally { setSaving(false) }
  }

  const field = (label, key, placeholder = '') => (
    <div>
      <label className="text-slate-400 text-xs block mb-1">{label}</label>
      <input value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })}
        placeholder={placeholder}
        className="w-full bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2.5 py-1.5 placeholder-slate-500" />
    </div>
  )

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-md max-h-[85vh] overflow-y-auto">
        <div className="px-5 py-4 border-b border-slate-700/50 flex items-center justify-between">
          <h2 className="text-white font-semibold">{isNew ? 'New parent company' : `Edit ${parent.name}`}</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-200"><X size={18} /></button>
        </div>
        <div className="px-5 py-4 space-y-3">
          {field('Company name', 'name', 'e.g. PeopleConnect')}
          {field('Opt-out email', 'optout_email', 'privacy@company.com')}
          {field('CC emails (comma-separated)', 'cc_emails', 'dpo@company.com')}
          <div className="grid grid-cols-2 gap-3">
            {field('Locale', 'locale', 'en')}
            {field('Website', 'website', 'company.com')}
          </div>
          <div>
            <label className="text-slate-400 text-xs block mb-1">Notes</label>
            <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
              rows={2}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2.5 py-1.5" />
          </div>
          {error && <div className="px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs">{error}</div>}
        </div>
        <div className="px-5 py-4 border-t border-slate-700/50 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button onClick={save} disabled={saving}
            className="px-4 py-1.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-sm rounded-lg">
            {saving ? 'Saving…' : (isNew ? 'Create' : 'Save')}
          </button>
        </div>
      </div>
    </div>
  )
}

function ManageChildrenModal({ parent, onClose, onChanged }) {
  const [children, setChildren] = useState([])
  const [candidates, setCandidates] = useState([])
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(new Set())
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([
      api.get(`/parent-companies/${parent.id}/children`),
      api.get(`/parent-companies/unassigned/brokers${search ? `?search=${encodeURIComponent(search)}` : ''}`),
    ]).then(([c, u]) => { setChildren(c.data); setCandidates(u.data) })
      .finally(() => setLoading(false))
  }, [parent.id, search])
  useEffect(() => { load() }, [load])

  const assign = async () => {
    if (selected.size === 0) return
    await api.post(`/parent-companies/${parent.id}/assign`, { broker_ids: [...selected] })
    setSelected(new Set()); load(); onChanged()
  }
  const unassign = async (id) => {
    await api.post('/parent-companies/unassign', { broker_ids: [id] })
    load(); onChanged()
  }
  const toggle = (id) => setSelected(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n
  })

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto">
        <div className="px-5 py-4 border-b border-slate-700/50 flex items-center justify-between">
          <h2 className="text-white font-semibold flex items-center gap-2">
            <Link2 size={16} className="text-shield-400" /> Child sites of {parent.name}
          </h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-200"><X size={18} /></button>
        </div>
        <div className="px-5 py-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Current children */}
          <div>
            <p className="text-slate-300 text-sm font-medium mb-2">Grouped under this parent ({children.length})</p>
            <div className="space-y-1 max-h-72 overflow-y-auto">
              {children.length === 0
                ? <p className="text-slate-500 text-xs">No sites grouped yet.</p>
                : children.map(c => (
                  <div key={c.id} className="flex items-center justify-between px-2.5 py-1.5 bg-slate-800/60 rounded-lg">
                    <span className="text-slate-200 text-sm truncate">{c.name}</span>
                    <button onClick={() => unassign(c.id)} title="Remove from parent"
                      className="text-slate-500 hover:text-red-400"><X size={13} /></button>
                  </div>
                ))}
            </div>
          </div>
          {/* Add candidates */}
          <div>
            <p className="text-slate-300 text-sm font-medium mb-2">Add unassigned brokers</p>
            <div className="relative mb-2">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search brokers"
                className="pl-8 pr-3 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 w-full" />
            </div>
            <div className="space-y-1 max-h-56 overflow-y-auto">
              {loading ? <p className="text-slate-500 text-xs">Loading…</p>
                : candidates.length === 0 ? <p className="text-slate-500 text-xs">No unassigned brokers match.</p>
                : candidates.map(c => (
                  <label key={c.id} className="flex items-center gap-2 px-2.5 py-1.5 bg-slate-800/40 rounded-lg cursor-pointer">
                    <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)}
                      className="accent-shield-500" />
                    <span className="text-slate-300 text-sm truncate">{c.name}</span>
                  </label>
                ))}
            </div>
            {selected.size > 0 && (
              <button onClick={assign}
                className="mt-2 w-full px-3 py-1.5 bg-shield-600 hover:bg-shield-700 text-white text-sm rounded-lg">
                Group {selected.size} under {parent.name}
              </button>
            )}
          </div>
        </div>
        <div className="px-5 py-4 border-t border-slate-700/50 flex justify-end">
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">Done</button>
        </div>
      </div>
    </div>
  )
}


// ── Test broker: validate real email delivery to an address you choose ──────
function TestBrokerPanel({ onChanged }) {
  const [tb, setTb] = useState(null)          // current test broker (or {exists:false})
  const [addr, setAddr] = useState('')
  const [members, setMembers] = useState([])
  const [memberId, setMemberId] = useState('') // '' = built-in fake identity
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.get('/test-broker').then(r => {
      setTb(r.data)
      if (r.data.exists) setAddr(r.data.optout_email || '')
    }).catch(() => setTb({ exists: false }))
    api.get('/family').then(r => setMembers(r.data || [])).catch(() => setMembers([]))
  }, [])
  useEffect(() => { load() }, [load])

  const save = async () => {
    setBusy(true); setError(''); setResult(null)
    try {
      const r = await api.post('/test-broker/setup', { optout_email: addr })
      setTb(r.data); onChanged && onChanged()
    } catch (e) { setError(e.response?.data?.detail || 'Could not save the test broker') }
    finally { setBusy(false) }
  }

  const send = async () => {
    setBusy(true); setError(''); setResult(null)
    try {
      const r = await api.post('/test-broker/send', memberId ? { member_id: +memberId } : {})
      setResult(r.data); load(); onChanged && onChanged()
    } catch (e) { setError(e.response?.data?.detail || 'Test send failed') }
    finally { setBusy(false) }
  }

  const remove = async () => {
    if (!window.confirm('Remove the test broker?')) return
    setBusy(true)
    try { await api.delete('/test-broker'); setTb({ exists: false }); setAddr(''); setResult(null); onChanged && onChanged() }
    finally { setBusy(false) }
  }

  if (!tb) return null

  return (
    <div className="mt-4 bg-slate-800/40 rounded-xl border border-slate-700/50 px-4 py-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-slate-100 text-sm font-medium flex items-center gap-2">
          <FlaskConical size={15} className="text-shield-400" /> Test broker
        </p>
        {tb.exists && (
          <button onClick={remove} disabled={busy} className="text-slate-500 hover:text-red-400 text-xs flex items-center gap-1">
            <Trash2 size={12} /> Remove
          </button>
        )}
      </div>
      <p className="text-slate-400 text-xs mt-1">
        Sends a real opt-out through the production email path to an address <strong className="text-slate-300">you</strong> control,
        so you can confirm delivery end to end. It's fenced off: never scanned by discovery and never included in scheduled runs.
      </p>

      <div className="flex gap-2 mt-3 flex-wrap">
        <input value={addr} onChange={e => setAddr(e.target.value)} placeholder="your-test-inbox@example.com"
          className="flex-1 min-w-48 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2.5 py-1.5 placeholder-slate-500" />
        <button onClick={save} disabled={busy || !addr}
          className="px-3 py-1.5 text-sm text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-800 disabled:opacity-40">
          {tb.exists ? 'Update address' : 'Create test broker'}
        </button>
      </div>

      {tb.exists && (
        <div className="flex gap-2 mt-2 flex-wrap items-center">
          <select value={memberId} onChange={e => setMemberId(e.target.value)}
            className="flex-1 min-w-48 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2 py-1.5">
            <option value="">Use built-in fake identity ("Test Person")</option>
            {members.map(m => <option key={m.id} value={m.id}>{m.full_name}</option>)}
          </select>
          <button onClick={send} disabled={busy}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg">
            <Send size={13} /> {busy ? 'Sending…' : 'Send test opt-out'}
          </button>
        </div>
      )}

      {error && <div className="mt-2 px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs">{error}</div>}

      {result && (
        <div className={`mt-2 px-3 py-2 rounded-lg border text-xs ${result.ok
            ? 'border-emerald-800/60 bg-emerald-950/20 text-emerald-200'
            : 'border-red-800 bg-red-900/20 text-red-300'}`}>
          <p className="font-medium flex items-center gap-1.5">
            {result.ok ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
            {result.ok ? 'Sent — check your inbox' : 'Send failed'}
          </p>
          <div className="mt-1 space-y-0.5 text-[11px] opacity-90">
            <div>Transport: {result.via || '—'}</div>
            <div>To: {result.to}{result.cc?.length ? ` (cc ${result.cc.join(', ')})` : ''}</div>
            <div>Subject: {result.subject}</div>
            <div>Identity: {result.identity}</div>
            {!result.ok && result.error && <div>Error: {result.error}</div>}
          </div>
        </div>
      )}
    </div>
  )
}
