import { useEffect, useState } from 'react'
import {
  UserPlus, Shield, ShieldCheck, User, Trash2,
  Link2, Link2Off, ChevronDown, X, Check, KeyRound, Eye, Edit3,
  Briefcase, SlidersHorizontal, AlertTriangle, RotateCcw
} from 'lucide-react'
import api from '../api'
import { tx, txn, txr } from '../i18n/tx'

const ROLE_STYLES = {
  super_admin: 'bg-purple-900/40 text-purple-300 border-purple-700',
  manager:     'bg-sky-900/40    text-sky-300    border-sky-700',
  parent:      'bg-teal-900/40   text-teal-300   border-teal-700',
  member:      'bg-slate-800     text-slate-400  border-slate-700',
}
const ROLE_ICONS = {
  super_admin: ShieldCheck,
  manager:     Briefcase,
  parent:      Shield,
  member:      User,
}

function RoleBadge({ role }) {
  const Icon = ROLE_ICONS[role] ?? User
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-sm text-xs border ${ROLE_STYLES[role] ?? ROLE_STYLES.member}`}>
      <Icon size={10} />{role}
    </span>
  )
}

// ── Create user modal ─────────────────────────────────────────────────────────
function CreateUserModal({ onClose, onCreated, isSuper }) {
  const [form, setForm] = useState({ full_name: '', email: '', role: 'member', password: '', branch_id: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState('')
  const [branches, setBranches] = useState({ branches: [], required: false })
  const needsPassword = form.role !== 'member'

  // Branches this user may put the account in; scoped managers only get theirs.
  useEffect(() => {
    api.get('/admin/branches').then(({ data }) => {
      setBranches(data)
      if (data.default_branch_id) setForm(f => ({ ...f, branch_id: String(data.default_branch_id) }))
    }).catch(() => {})
  }, [])

  const submit = async e => {
    e.preventDefault()
    setSaving(true); setError('')
    try {
      const payload = { ...form, password: form.password || undefined,
                        branch_id: form.branch_id ? Number(form.branch_id) : undefined }
      const { data } = await api.post('/admin/users', payload)
      onCreated(data); onClose()
    } catch (err) {
      setError(err.response?.data?.detail ?? tx("Couldn't create the account. Check the details and try again."))
    } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-sm max-h-[90vh] overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-white font-semibold">{tx("Add user")}</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-white"><X size={16} /></button>
        </div>
        {error && <p className="text-red-400 text-sm mb-3 bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
        <form onSubmit={submit} className="space-y-3">
          <Field label={tx("Full name")} required>
            <input value={form.full_name} onChange={e => setForm(f => ({...f, full_name: e.target.value}))}
              placeholder={tx("Jane Smith")} className={input} required autoFocus />
          </Field>
          <Field label={tx("Email")} required>
            <input type="email" value={form.email} onChange={e => setForm(f => ({...f, email: e.target.value}))}
              placeholder="jane@example.com" className={input} required />
          </Field>
          <Field label={tx("Role")}>
            <div className="relative">
              <select value={form.role} onChange={e => setForm(f => ({...f, role: e.target.value}))}
                className={`${input} appearance-none pr-7`}>
                <option value="member">{tx("member — managed profile, no login")}</option>
                <option value="parent">{tx("parent — can log in, manages profiles")}</option>
                {isSuper && <option value="manager">{tx("manager — a parent plus the permissions you grant")}</option>}
                {isSuper && <option value="super_admin">{tx("super_admin — full access")}</option>}
              </select>
              <ChevronDown size={11} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
            </div>
          </Field>
          {(branches.branches.length > 0 || branches.required) && (
            <Field label={tx("Branch")} required={branches.required}>
              <div className="relative">
                <select value={form.branch_id} onChange={e => setForm(f => ({...f, branch_id: e.target.value}))}
                  className={`${input} appearance-none pr-7`} required={branches.required}>
                  <option value="">{branches.required ? tx("Choose a branch") : tx("No branch")}</option>
                  {branches.branches.map(b => (
                    <option key={b.id} value={b.id}>{b.name}{b.system_name ? ` — ${b.system_name}` : ''}</option>
                  ))}
                </select>
                <ChevronDown size={11} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              </div>
            </Field>
          )}
          <Field label={tx("Password {v}", { v: needsPassword ? '*' : '(optional)' })}>
            <input type="password" value={form.password} onChange={e => setForm(f => ({...f, password: e.target.value}))}
              placeholder={needsPassword ? tx("Required for login") : tx("Leave blank — no login")}
              className={input} required={needsPassword} />
          </Field>
          {form.role === 'member' && (
            <p className="text-slate-500 text-xs">{tx("Member profiles don't need a password — they're managed by a parent. You can upgrade them later.")}</p>
          )}
          {form.role === 'manager' && (
            <p className="text-slate-500 text-xs">{tx("New managers start with the manager defaults. Adjust them from the user's Permissions button.")}</p>
          )}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className={cancelBtn}>{tx("Cancel")}</button>
            <button type="submit" disabled={saving} className={primaryBtn}>{saving ? tx("Creating…") : tx("Create user")}</button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Grant access modal ────────────────────────────────────────────────────────
function GrantModal({ users, onClose, onGranted }) {
  const [managerId, setManagerId] = useState('')
  const [managedId, setManagedId] = useState('')
  const [canEdit, setCanEdit]     = useState(true)
  const [childLimit, setChildLimit] = useState('')
  const [saving, setSaving]       = useState(false)
  const [error, setError]         = useState('')

  const submit = async e => {
    e.preventDefault()
    if (managerId === managedId) { setError(tx("Can't grant access to own profile")); return }
    setSaving(true); setError('')
    try {
      const { data } = await api.post('/admin/access', {
        manager_id: parseInt(managerId),
        managed_id: parseInt(managedId),
        can_view: true, can_edit: canEdit,
        max_children_override: childLimit !== '' ? parseInt(childLimit) : null,
      })
      onGranted(data); onClose()
    } catch (err) {
      setError(err.response?.data?.detail ?? tx("Couldn't give that access. Please try again."))
    } finally { setSaving(false) }
  }

  const loginUsers = users.filter(u => u.can_login)

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-sm max-h-[90vh] overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-white font-semibold">{tx("Grant profile access")}</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-white"><X size={16} /></button>
        </div>
        {error && <p className="text-red-400 text-sm mb-3 bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
        <form onSubmit={submit} className="space-y-3">
          <Field label={tx("Who gets access (manager)")}>
            <UserSelect users={loginUsers} value={managerId} onChange={setManagerId} placeholder={tx("Select manager…")} />
          </Field>
          <div className="flex items-center justify-center gap-2 text-slate-600 text-xs">
            <div className="flex-1 h-px bg-slate-700"/>
            {tx("can access profile of")}
            <div className="flex-1 h-px bg-slate-700"/>
          </div>
          <Field label={tx("Whose profile (managed)")}>
            <UserSelect users={users} value={managedId} onChange={setManagedId} placeholder={tx("Select profile…")} />
          </Field>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={canEdit} onChange={e => setCanEdit(e.target.checked)}
              className="w-3.5 h-3.5 rounded-sm accent-shield-500" />
            <span className="text-slate-300 text-sm">{tx("Allow editing (not just viewing)")}</span>
          </label>
          <div>
            <label className="text-slate-400 text-xs mb-1 block">
              {txr("Children limit override <0>(blank = use system default)</0>", [<span className="text-slate-600" />])}
            </label>
            <input type="number" min="0" value={childLimit}
              onChange={e => setChildLimit(e.target.value)}
              placeholder={tx("System default")}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500" />
            <p className="text-slate-600 text-xs mt-1">
              {tx("Max number of member (child) profiles this parent can manage. 0 = unlimited.")}
            </p>
          </div>
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className={cancelBtn}>{tx("Cancel")}</button>
            <button type="submit" disabled={saving || !managerId || !managedId} className={primaryBtn}>
              {saving ? tx("Granting…") : tx("Grant access")}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function UserSelect({ users, value, onChange, placeholder }) {
  return (
    <div className="relative">
      <select value={value} onChange={e => onChange(e.target.value)} className={`${input} appearance-none pr-7`} required>
        <option value="">{placeholder}</option>
        {users.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>)}
      </select>
      <ChevronDown size={11} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
    </div>
  )
}

// ── Edit user inline ──────────────────────────────────────────────────────────
function EditUserRow({ user, onUpdated, onDeleted, currentUserId, isSuper, onEditPermissions }) {
  const [editing, setEditing] = useState(false)
  const [role, setRole]       = useState(user.role)
  const [saving, setSaving]   = useState(false)
  const isSelf = user.id === currentUserId
  // Managers act on parent and member accounts only; roles are super-admin only.
  const privileged = user.role === 'super_admin' || user.role === 'manager'
  const canAct = isSuper || !privileged

  const save = async () => {
    setSaving(true)
    try {
      const { data } = await api.patch(`/admin/users/${user.id}`, { role })
      onUpdated(data)
      setEditing(false)
    } finally { setSaving(false) }
  }

  const del = async () => {
    if (!confirm(tx("Delete {full_name}? This removes all their data.", { full_name: user.full_name }))) return
    await api.delete(`/admin/users/${user.id}`)
    onDeleted(user.id)
  }

  const setPassword = async () => {
    const pw = prompt(tx("Set new password for {full_name}:", { full_name: user.full_name }))
    if (!pw) return
    await api.patch(`/admin/users/${user.id}`, { password: pw })
    alert(tx("Password updated."))
  }

  return (
    <tr className="border-t border-slate-700/30 hover:bg-slate-700/20 transition-colors group">
      <td className="px-4 py-3">
        <p className="text-slate-200 text-sm font-medium">{user.full_name}</p>
        <p className="text-slate-500 text-xs">{user.email}</p>
      </td>
      <td className="px-4 py-3">
        {editing ? (
          <div className="relative">
            <select value={role} onChange={e => setRole(e.target.value)}
              className="bg-slate-700 border border-slate-600 rounded-sm px-2 py-1 text-xs text-slate-200 focus:outline-hidden appearance-none pr-6">
              <option value="member">{tx("member")}</option>
              <option value="parent">{tx("parent")}</option>
              <option value="manager">{tx("manager")}</option>
              <option value="super_admin">{tx("super_admin")}</option>
            </select>
          </div>
        ) : <RoleBadge role={user.role} />}
        {user.role === 'manager' && (
          <p className="text-slate-500 text-[11px] mt-1">
            {txn(user.permissions.length, "{n} permission", "{n} permissions")}
            {(user.permissions_granted.length > 0 || user.permissions_revoked.length > 0) && tx("· customized")}
          </p>
        )}
      </td>
      <td className="px-4 py-3">
        <span className={`text-xs ${user.can_login ? 'text-emerald-400' : 'text-slate-600'}`}>
          {user.can_login ? tx("✓ can log in") : tx("no login")}
        </span>
      </td>
      <td className="px-4 py-3 text-slate-500 text-xs">{user.managing_count}{" "}{tx("managing")}</td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {editing ? (
            <>
              <button onClick={save} disabled={saving} className="p-1 text-emerald-400 hover:text-emerald-300"><Check size={13} /></button>
              <button onClick={() => setEditing(false)} className="p-1 text-slate-500 hover:text-white"><X size={13} /></button>
            </>
          ) : canAct && (
            <>
              {isSuper && user.role === 'manager' && (
                <button onClick={() => onEditPermissions(user)} className="p-1 text-slate-500 hover:text-sky-300" title={tx("Permissions")}><SlidersHorizontal size={13} /></button>
              )}
              {isSuper && <button onClick={() => setEditing(true)} className="p-1 text-slate-500 hover:text-shield-400" title={tx("Edit role")}><Edit3 size={13} /></button>}
              <button onClick={setPassword} className="p-1 text-slate-500 hover:text-amber-400" title={tx("Set password")}><KeyRound size={13} /></button>
              {!isSelf && <button onClick={del} className="p-1 text-slate-500 hover:text-red-400" title={tx("Delete")}><Trash2 size={13} /></button>}
            </>
          )}
        </div>
      </td>
    </tr>
  )
}

// ── Main admin page ───────────────────────────────────────────────────────────
export default function AdminPanel() {
  const [users, setUsers]     = useState([])
  const [grants, setGrants]   = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [showGrant, setShowGrant]   = useState(false)
  const [me, setMe] = useState(null)
  const [perms, setPerms] = useState(null)          // { catalog, defaults, builtin_defaults }
  const [permTarget, setPermTarget] = useState(null) // a manager, or 'defaults'
  const isSuper = me?.role === 'super_admin'

  const loadUsers = () => api.get('/admin/users').then(r => setUsers(r.data))

  useEffect(() => {
    Promise.all([
      api.get('/admin/users'),
      api.get('/admin/access'),
      api.get('/auth/me'),
      api.get('/admin/permissions'),
    ]).then(([u, g, m, p]) => {
      setUsers(u.data); setGrants(g.data); setMe(m.data); setPerms(p.data)
    }).finally(() => setLoading(false))
  }, [])

  const savePermissions = async (keys) => {
    if (permTarget === 'defaults') {
      const { data } = await api.put('/admin/permissions/defaults', { permissions: keys })
      setPerms(p => ({ ...p, defaults: data.defaults }))
      await loadUsers()   // every manager's effective permissions may have changed
    } else {
      const { data } = await api.put(`/admin/users/${permTarget.id}/permissions`, { permissions: keys })
      setUsers(us => us.map(x => x.id === data.id ? data : x))
    }
    setPermTarget(null)
  }

  const revokeGrant = async id => {
    if (!confirm('Revoke this access grant?')) return
    await api.delete(`/admin/access/${id}`)
    setGrants(g => g.filter(x => x.id !== id))
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">{tx("Admin panel")}</h1>
          <p className="text-slate-400 text-sm mt-0.5">{tx("Manage users, roles, and profile access grants")}</p>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          {isSuper && (
            <button onClick={() => setPermTarget('defaults')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
              <SlidersHorizontal size={13} />{" "}{tx("Manager defaults")}
            </button>
          )}
          <button onClick={() => setShowGrant(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
            <Link2 size={13} />{" "}{tx("Grant access")}
          </button>
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 transition-colors">
            <UserPlus size={13} />{" "}{tx("Add user")}
          </button>
        </div>
      </div>

      {loading && <p className="text-slate-500 text-sm">{tx("Loading…")}</p>}

      {/* Users table */}
      {!loading && (
        <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden mb-6">
          <div className="px-4 py-3 border-b border-slate-700/50">
            <p className="text-slate-300 text-sm font-medium">{tx("Users ({length})", { length: users.length })}</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 text-xs border-b border-slate-700/30">
                <th className="text-left px-4 py-2 font-normal">{tx("Name")}</th>
                <th className="text-left px-4 py-2 font-normal">{tx("Role")}</th>
                <th className="text-left px-4 py-2 font-normal">{tx("Login")}</th>
                <th className="text-left px-4 py-2 font-normal">{tx("Access")}</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <EditUserRow
                  key={u.id} user={u}
                  currentUserId={me?.id}
                  isSuper={isSuper}
                  onEditPermissions={setPermTarget}
                  onUpdated={updated => setUsers(us => us.map(x => x.id === updated.id ? updated : x))}
                  onDeleted={id => setUsers(us => us.filter(x => x.id !== id))}
                />
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {/* Access grants */}
      {!loading && (
        <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/50">
            <p className="text-slate-300 text-sm font-medium">{tx("Profile access grants ({length})", { length: grants.length })}</p>
            <p className="text-slate-500 text-xs mt-0.5">{tx("Who can see and edit whose data")}</p>
          </div>
          {grants.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <Link2 size={24} className="text-slate-700 mx-auto mb-2" />
              <p className="text-slate-500 text-sm">{tx("No access grants yet.")}</p>
              <p className="text-slate-600 text-xs mt-1">{tx("Grant a parent access to manage another person's profile.")}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-xs border-b border-slate-700/30">
                  <th className="text-left px-4 py-2 font-normal">{tx("Manager")}</th>
                  <th className="text-left px-4 py-2 font-normal"></th>
                  <th className="text-left px-4 py-2 font-normal">{tx("Can access profile of")}</th>
                  <th className="text-left px-4 py-2 font-normal">{tx("Permissions")}</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {grants.map(g => (
                  <tr key={g.id} className="border-t border-slate-700/30 hover:bg-slate-700/20 group">
                    <td className="px-4 py-2.5 text-slate-200">{g.manager_name}</td>
                    <td className="px-4 py-2.5 text-slate-600"><Link2 size={12} /></td>
                    <td className="px-4 py-2.5 text-slate-200">{g.managed_name}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex gap-1">
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-xs bg-blue-900/30 text-blue-400 border border-blue-800">
                          <Eye size={9} />{" "}{tx("view")}
                        </span>
                        {g.can_edit && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-xs bg-emerald-900/30 text-emerald-400 border border-emerald-800">
                            <Edit3 size={9} />{" "}{tx("edit")}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <button onClick={() => revokeGrant(g.id)}
                        className="opacity-0 group-hover:opacity-100 text-slate-600 hover:text-red-400 transition-all p-1"
                        title={tx("Revoke")}>
                        <Link2Off size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </div>
      )}

      {showCreate && (
        <CreateUserModal
          isSuper={isSuper}
          onClose={() => setShowCreate(false)}
          onCreated={u => setUsers(us => [...us, u])}
        />
      )}
      {showGrant && (
        <GrantModal
          users={users}
          onClose={() => setShowGrant(false)}
          onGranted={g => setGrants(gs => [...gs, g])}
        />
      )}
      {permTarget && perms && (
        <PermissionsModal
          catalog={perms.catalog}
          defaults={permTarget === 'defaults' ? perms.builtin_defaults : perms.defaults}
          initial={permTarget === 'defaults' ? perms.defaults : permTarget.permissions}
          title={permTarget === 'defaults' ? tx("Manager defaults") : tx("Permissions for {full_name}", { full_name: permTarget.full_name })}
          subtitle={permTarget === 'defaults'
            ? tx("What every manager gets, unless you changed it for that manager.")
            : tx("Changes apply to this manager only. Anything left matching the defaults keeps following them.")}
          resetLabel={permTarget === 'defaults' ? tx("Restore built-in defaults") : tx("Reset to manager defaults")}
          onSave={savePermissions}
          onClose={() => setPermTarget(null)}
        />
      )}
    </div>
  )
}

// ── Permissions editor (super admin) ──────────────────────────────────────────
// One grouped checklist, used both for a single manager and for the manager
// defaults. `defaults` is what "reset" restores and what gets the "default" tag.
function PermissionsModal({ catalog, defaults, initial, title, subtitle, resetLabel, onSave, onClose }) {
  const [selected, setSelected] = useState(new Set(initial))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const groups = [...new Set(catalog.map(p => p.group))]
  const toggle = key => setSelected(s => {
    const next = new Set(s)
    next.has(key) ? next.delete(key) : next.add(key)
    return next
  })
  const save = async () => {
    setSaving(true); setError('')
    try { await onSave(catalog.map(p => p.key).filter(k => selected.has(k))) }
    catch (e) { setError(e.response?.data?.detail ?? tx("Could not save permissions")); setSaving(false) }
  }
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg max-h-[85vh] flex flex-col"
        onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-slate-700/50 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-white font-semibold">{title}</h2>
            <p className="text-slate-500 text-xs mt-0.5">{subtitle}</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white" aria-label={tx("Close")}><X size={16} /></button>
        </div>
        <div className="px-5 py-4 overflow-y-auto space-y-4">
          {error && <p className="text-red-400 text-sm bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
          {groups.map(g => (
            <div key={g}>
              <p className="text-slate-500 text-[11px] uppercase tracking-wide mb-1.5">{g}</p>
              <div className="space-y-1">
                {catalog.filter(p => p.group === g).map(p => (
                  <label key={p.key} className="flex items-start gap-2.5 px-2 py-1.5 rounded-lg hover:bg-slate-800/60 cursor-pointer">
                    <input type="checkbox" checked={selected.has(p.key)} onChange={() => toggle(p.key)}
                      className="mt-0.5 accent-sky-500" />
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-slate-200 text-sm">{p.label}</span>
                        {defaults.includes(p.key) && <span className="text-[10px] px-1 rounded-sm border border-slate-700 text-slate-500">{tx("default")}</span>}
                        {p.sensitive && (
                          <span className="inline-flex items-center gap-0.5 text-[10px] px-1 rounded-sm border border-amber-800 text-amber-300">
                            <AlertTriangle size={9} />{" "}{tx("sensitive")}
                          </span>
                        )}
                      </span>
                      <span className="block text-slate-500 text-xs mt-0.5">{p.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          ))}
          <p className="text-slate-600 text-xs">
            {tx("Always kept for super admins: roles and permissions, the setup wizard, enabling plugins and the plugin-system switch, database migration, and resetting all requests.")}
          </p>
        </div>
        <div className="px-5 py-3 border-t border-slate-700/50 flex items-center justify-between gap-2">
          <button onClick={() => setSelected(new Set(defaults))}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200">
            <RotateCcw size={11} /> {resetLabel}
          </button>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1.5 border border-slate-700 rounded-lg text-slate-400 text-sm hover:bg-slate-800">{tx("Cancel")}</button>
            <button onClick={save} disabled={saving}
              className="px-3 py-1.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg text-sm">
              {saving ? tx("Saving…") : tx("Save")}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Shared styles ─────────────────────────────────────────────────────────────
const input = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"
const cancelBtn = "flex-1 py-2 border border-slate-700 rounded-lg text-slate-400 text-sm hover:bg-slate-800 transition-colors"
const primaryBtn = "flex-1 py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors"

function Field({ label, required, children }) {
  return (
    <div>
      <label className="text-slate-400 text-xs mb-1 block">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  )
}
