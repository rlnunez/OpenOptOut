import { useEffect, useState, useCallback } from 'react'
import {
  Building2, RefreshCw, Plus, Trash2, Search, X, Mail,
  CheckCircle2, AlertTriangle, XCircle, HelpCircle, Link2, FlaskConical, Send
} from 'lucide-react'
import api from '../api'
import { tx, txn, txr } from '../i18n/tx'
import { detailText } from '../errorMessage'

const HONOR = {
  honors:  { label: tx("Honors requests"), icon: CheckCircle2, cls: 'text-emerald-400' },
  partial: { label: tx("Partial"),         icon: AlertTriangle, cls: 'text-amber-400' },
  ignores: { label: tx("Ignores"),         icon: XCircle,      cls: 'text-red-400' },
  bounces: { label: tx("Email bounces"),   icon: XCircle,      cls: 'text-red-400' },
  unknown: { label: tx("Not known yet"),         icon: HelpCircle,   cls: 'text-slate-500' },
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
        setMsg(tx("Sent {sent_emails} email(s) to {name}, covering {covered_requests} broker requests", { sent_emails: d.sent_emails, name: p.name, covered_requests: d.covered_requests }))
      } else {
        setMsg(tx("No pending requests for {name}'s child brokers", { name: p.name }))
      }
      load()
    } catch (e) {
      setMsg(detailText(e) || tx("Dispatch failed"))
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
        setMsg(tx("Dispatched {sent_emails} email(s) across parent companies, covering {covered_requests} requests", { sent_emails: d.sent_emails, covered_requests: d.covered_requests }))
      } else {
        setMsg(tx("No pending requests under any parent company"))
      }
      load()
    } catch (e) {
      setMsg(detailText(e) || tx("Dispatch all failed"))
    } finally {
      setDispatchingAll(false)
    }
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-start justify-between mb-1 flex-wrap gap-2">
        <div>
          <h1 className="text-white text-xl font-semibold flex items-center gap-2">
            <Building2 size={20} className="text-shield-500" />{" "}{tx("Parent companies")}
          </h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {tx("Group broker front-sites under the company that operates them. One email opt-out to a parent covers all its child sites at once. Effectiveness shows which parents actually respond.")}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={dispatchAll} disabled={dispatchingAll}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
            title={tx("Dispatch email opt-outs across all parent companies")}>
            <Send size={14} /> {dispatchingAll ? tx("Dispatching…") : tx("Send all parent opt-outs")}
          </button>
          <button onClick={() => setEditing({})}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 hover:bg-shield-700 text-white rounded-lg">
            <Plus size={14} />{" "}{tx("New parent")}
          </button>
          <button onClick={load} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
            <RefreshCw size={13} />{" "}{tx("Refresh")}
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
          <RefreshCw size={14} className="animate-spin" />{" "}{tx("Loading…")}
        </div>
      ) : parents.length === 0 ? (
        <div className="flex flex-col items-center gap-2 text-slate-500 py-12 mt-4">
          <Building2 size={26} className="text-slate-600" />
          <p className="text-sm">{tx("No parent companies yet. Create one, then group its broker sites under it.")}</p>
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
                        : <span className="text-amber-400/80 inline-flex items-center gap-1"><AlertTriangle size={11} />{" "}{tx("no opt-out email set")}</span>}
                      <span>· {txn(p.child_count, "{n} child site", "{n} child sites")}</span>
                      {p.letter?.id && (
                        <span title={tx("Opt-out letters follow the company's country and are written in its legal language, not the language you use the app in.")}>
                          · {tx("Letter: {law} in {language}", { law: letterName(p.letter.id), language: (p.letter.language || '').toUpperCase() })}
                          {p.letter.review_status !== 'reviewed' && <span className="text-amber-400/80">{" "}{tx("(draft wording, not yet checked by a lawyer)")}</span>}
                        </span>
                      )}
                      {p.emails_sent > 0 && (
                        <span>{tx("· {emails_confirmed}/{emails_sent} confirmed", { emails_confirmed: p.emails_confirmed, emails_sent: p.emails_sent })}
                          {p.confirm_rate != null ? ` (${p.confirm_rate}%)` : ''}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0 items-center">
                    {p.optout_email && p.child_count > 0 && (
                      <button onClick={() => dispatchParent(p)} disabled={dispatching === p.id}
                        className="flex items-center gap-1 px-2.5 py-1 text-xs text-sky-300 bg-sky-950/60 border border-sky-800/60 rounded-lg hover:bg-sky-900/60 transition-colors"
                        title={tx("Send opt-out email covering all child broker requests for this parent")}>
                        <Send size={11} /> {dispatching === p.id ? tx("Sending…") : tx("Send opt-outs")}
                      </button>
                    )}
                    <button onClick={() => setManaging(p)}
                      className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
                      <Link2 size={12} />{" "}{tx("Sites")}
                    </button>
                    <button onClick={() => setEditing(p)}
                      className="px-2.5 py-1 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">{tx("Edit")}</button>
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

function letterName(id) {
  switch (id) {
    case 'ccpa': return tx("California privacy law (CCPA)")
    case 'us': return tx("US state privacy laws")
    case 'gdpr': return tx("EU privacy law (GDPR)")
    case 'uk_gdpr': return tx("UK privacy law (UK GDPR)")
    case 'lgpd': return tx("Brazil privacy law (LGPD)")
    case 'pipeda': return tx("Canada privacy law (PIPEDA)")
    default: return tx("general privacy law")
  }
}

function EditModal({ parent, onClose, onSaved }) {
  const isNew = !parent.id
  const [form, setForm] = useState({
    name: parent.name || '', optout_email: parent.optout_email || '',
    cc_emails: parent.cc_emails || '', locale: parent.locale || '',
    jurisdiction: parent.jurisdiction || '',
    website: parent.website || '', notes: parent.notes || '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async () => {
    if (!form.name.trim()) { setError(tx("Name is required")); return }
    setSaving(true); setError('')
    try {
      if (isNew) await api.post('/parent-companies', form)
      else await api.patch(`/parent-companies/${parent.id}`, form)
      onSaved(isNew ? `Created ${form.name}` : `Updated ${form.name}`)
    } catch (e) { setError(detailText(e) || tx("Save failed")) }
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
          <h2 className="text-white font-semibold">{isNew ? tx("New parent company") : `Edit ${parent.name}`}</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-200"><X size={18} /></button>
        </div>
        <div className="px-5 py-4 space-y-3">
          {field(tx("Company name"), 'name', tx("e.g. PeopleConnect"))}
          {field(tx("Opt-out email"), 'optout_email', 'privacy@company.com')}
          {field(tx("CC emails (comma-separated)"), 'cc_emails', 'dpo@company.com')}
          {field(tx("Website"), 'website', 'company.com')}
          <div className="grid grid-cols-2 gap-3">
            {field(tx("Country"), 'jurisdiction', 'US')}
            {field(tx("Letter language"), 'locale', tx("automatic"))}
          </div>
          <p className="text-slate-500 text-xs">
            {tx("The country decides which privacy law the opt-out letter cites (US, GB, FR, BR, CA, or EU). The letter is written in the company's language — French for a French company — not the language you use here. Leave the language blank to use the usual one for the country.")}
          </p>
          <div>
            <label className="text-slate-400 text-xs block mb-1">{tx("Notes")}</label>
            <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
              rows={2}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2.5 py-1.5" />
          </div>
          {error && <div className="px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs">{error}</div>}
        </div>
        <div className="px-5 py-4 border-t border-slate-700/50 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-slate-400 hover:text-slate-200">{tx("Cancel")}</button>
          <button onClick={save} disabled={saving}
            className="px-4 py-1.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-sm rounded-lg">
            {saving ? tx("Saving…") : (isNew ? tx("Create") : tx("Save"))}
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
            <Link2 size={16} className="text-shield-400" />{" "}{tx("Child sites of {name}", { name: parent.name })}
          </h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-200"><X size={18} /></button>
        </div>
        <div className="px-5 py-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Current children */}
          <div>
            <p className="text-slate-300 text-sm font-medium mb-2">{tx("Grouped under this parent ({length})", { length: children.length })}</p>
            <div className="space-y-1 max-h-72 overflow-y-auto">
              {children.length === 0
                ? <p className="text-slate-500 text-xs">{tx("No sites grouped yet.")}</p>
                : children.map(c => (
                  <div key={c.id} className="flex items-center justify-between px-2.5 py-1.5 bg-slate-800/60 rounded-lg">
                    <span className="text-slate-200 text-sm truncate">{c.name}</span>
                    <button onClick={() => unassign(c.id)} title={tx("Remove from parent")}
                      className="text-slate-500 hover:text-red-400"><X size={13} /></button>
                  </div>
                ))}
            </div>
          </div>
          {/* Add candidates */}
          <div>
            <p className="text-slate-300 text-sm font-medium mb-2">{tx("Add unassigned brokers")}</p>
            <div className="relative mb-2">
              <Search size={13} className="absolute start-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder={tx("Search brokers")}
                className="ps-8 pe-3 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 w-full" />
            </div>
            <div className="space-y-1 max-h-56 overflow-y-auto">
              {loading ? <p className="text-slate-500 text-xs">{tx("Loading…")}</p>
                : candidates.length === 0 ? <p className="text-slate-500 text-xs">{tx("No unassigned brokers match.")}</p>
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
                {tx("Group {size} under {name}", { size: selected.size, name: parent.name })}
              </button>
            )}
          </div>
        </div>
        <div className="px-5 py-4 border-t border-slate-700/50 flex justify-end">
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">{tx("Done")}</button>
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
    } catch (e) { setError(detailText(e) || tx("Could not save the test broker")) }
    finally { setBusy(false) }
  }

  const send = async () => {
    setBusy(true); setError(''); setResult(null)
    try {
      const r = await api.post('/test-broker/send', memberId ? { member_id: +memberId } : {})
      setResult(r.data); load(); onChanged && onChanged()
    } catch (e) { setError(detailText(e) || tx("Test send failed")) }
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
          <FlaskConical size={15} className="text-shield-400" />{" "}{tx("Test broker")}
        </p>
        {tb.exists && (
          <button onClick={remove} disabled={busy} className="text-slate-500 hover:text-red-400 text-xs flex items-center gap-1">
            <Trash2 size={12} />{" "}{tx("Remove")}
          </button>
        )}
      </div>
      <p className="text-slate-400 text-xs mt-1">
        {txr("Sends a real opt-out through the production email path to an address <0>you</0> control, so you can confirm delivery end to end. It's fenced off: never scanned by discovery and never included in scheduled runs.", [<strong className="text-slate-300" />])}
      </p>

      <div className="flex gap-2 mt-3 flex-wrap">
        <input value={addr} onChange={e => setAddr(e.target.value)} placeholder="your-test-inbox@example.com"
          className="flex-1 min-w-48 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2.5 py-1.5 placeholder-slate-500" />
        <button onClick={save} disabled={busy || !addr}
          className="px-3 py-1.5 text-sm text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-800 disabled:opacity-40">
          {tb.exists ? tx("Update address") : tx("Create test broker")}
        </button>
      </div>

      {tb.exists && (
        <div className="flex gap-2 mt-2 flex-wrap items-center">
          <select value={memberId} onChange={e => setMemberId(e.target.value)}
            className="flex-1 min-w-48 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm px-2 py-1.5">
            <option value="">{tx("Use built-in fake identity (\"Test Person\")")}</option>
            {members.map(m => <option key={m.id} value={m.id}>{m.full_name}</option>)}
          </select>
          <button onClick={send} disabled={busy}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg">
            <Send size={13} /> {busy ? tx("Sending…") : tx("Send test opt-out")}
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
            {result.ok ? tx("Sent — check your inbox") : tx("Send failed")}
          </p>
          <div className="mt-1 space-y-0.5 text-[11px] opacity-90">
            <div>{tx("Transport:")}{" "}{result.via || '—'}</div>
            <div>{tx("To:")}{" "}{result.to}{result.cc?.length ? tx("(cc {v})", { v: result.cc.join(', ') }) : ''}</div>
            <div>{tx("Subject:")}{" "}{result.subject}</div>
            <div>{tx("Identity:")}{" "}{result.identity}</div>
            {!result.ok && result.error && <div>{tx("Problem:")}{" "}{result.error}</div>}
          </div>
        </div>
      )}
    </div>
  )
}
