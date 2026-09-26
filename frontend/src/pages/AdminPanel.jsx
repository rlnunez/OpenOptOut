import { useEffect, useState } from 'react'
import {
  UserPlus, Shield, ShieldCheck, User, Trash2,
  Link2, Link2Off, ChevronDown, X, Check, KeyRound, Eye, Edit3, Upload
} from 'lucide-react'
import api from '../api'

const ROLE_STYLES = {
  super_admin: 'bg-purple-900/40 text-purple-300 border-purple-700',
  parent:      'bg-teal-900/40   text-teal-300   border-teal-700',
  member:      'bg-slate-800     text-slate-400  border-slate-700',
}
const ROLE_ICONS = {
  super_admin: ShieldCheck,
  parent:      Shield,
  member:      User,
}

function RoleBadge({ role }) {
  const Icon = ROLE_ICONS[role] ?? User
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border ${ROLE_STYLES[role] ?? ROLE_STYLES.member}`}>
      <Icon size={10} />{role}
    </span>
  )
}

// ── Create user modal ─────────────────────────────────────────────────────────
function CreateUserModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ full_name: '', email: '', role: 'member', password: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState('')
  const needsPassword = form.role !== 'member'

  const submit = async e => {
    e.preventDefault()
    setSaving(true); setError('')
    try {
      const payload = { ...form, password: form.password || undefined }
      const { data } = await api.post('/admin/users', payload)
      onCreated(data); onClose()
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Failed to create user')
    } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-sm p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-white font-semibold">Add user</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-white"><X size={16} /></button>
        </div>
        {error && <p className="text-red-400 text-sm mb-3 bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
        <form onSubmit={submit} className="space-y-3">
          <Field label="Full name" required>
            <input value={form.full_name} onChange={e => setForm(f => ({...f, full_name: e.target.value}))}
              placeholder="Jane Smith" className={input} required autoFocus />
          </Field>
          <Field label="Email" required>
            <input type="email" value={form.email} onChange={e => setForm(f => ({...f, email: e.target.value}))}
              placeholder="jane@example.com" className={input} required />
          </Field>
          <Field label="Role">
            <div className="relative">
              <select value={form.role} onChange={e => setForm(f => ({...f, role: e.target.value}))}
                className={`${input} appearance-none pr-7`}>
                <option value="member">member — managed profile, no login</option>
                <option value="parent">parent — can log in, manages profiles</option>
                <option value="super_admin">super_admin — full access</option>
              </select>
              <ChevronDown size={11} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
            </div>
          </Field>
          <Field label={`Password ${needsPassword ? '*' : '(optional)'}`}>
            <input type="password" value={form.password} onChange={e => setForm(f => ({...f, password: e.target.value}))}
              placeholder={needsPassword ? 'Required for login' : 'Leave blank — no login'}
              className={input} required={needsPassword} />
          </Field>
          {form.role === 'member' && (
            <p className="text-slate-500 text-xs">Member profiles don't need a password — they're managed by a parent. You can upgrade them later.</p>
          )}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className={cancelBtn}>Cancel</button>
            <button type="submit" disabled={saving} className={primaryBtn}>{saving ? 'Creating…' : 'Create user'}</button>
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
    if (managerId === managedId) { setError("Can't grant access to own profile"); return }
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
      setError(err.response?.data?.detail ?? 'Failed to create grant')
    } finally { setSaving(false) }
  }

  const loginUsers = users.filter(u => u.can_login)

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-sm p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-white font-semibold">Grant profile access</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-white"><X size={16} /></button>
        </div>
        {error && <p className="text-red-400 text-sm mb-3 bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
        <form onSubmit={submit} className="space-y-3">
          <Field label="Who gets access (manager)">
            <UserSelect users={loginUsers} value={managerId} onChange={setManagerId} placeholder="Select manager…" />
          </Field>
          <div className="flex items-center justify-center gap-2 text-slate-600 text-xs">
            <div className="flex-1 h-px bg-slate-700"/>
            can access profile of
            <div className="flex-1 h-px bg-slate-700"/>
          </div>
          <Field label="Whose profile (managed)">
            <UserSelect users={users} value={managedId} onChange={setManagedId} placeholder="Select profile…" />
          </Field>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={canEdit} onChange={e => setCanEdit(e.target.checked)}
              className="w-3.5 h-3.5 rounded accent-shield-500" />
            <span className="text-slate-300 text-sm">Allow editing (not just viewing)</span>
          </label>
          <div>
            <label className="text-slate-400 text-xs mb-1 block">
              Children limit override <span className="text-slate-600">(blank = use system default)</span>
            </label>
            <input type="number" min="0" value={childLimit}
              onChange={e => setChildLimit(e.target.value)}
              placeholder="System default"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-shield-500" />
            <p className="text-slate-600 text-xs mt-1">
              Max number of member (child) profiles this parent can manage. 0 = unlimited.
            </p>
          </div>
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className={cancelBtn}>Cancel</button>
            <button type="submit" disabled={saving || !managerId || !managedId} className={primaryBtn}>
              {saving ? 'Granting…' : 'Grant access'}
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
function EditUserRow({ user, onUpdated, onDeleted, currentUserId }) {
  const [editing, setEditing] = useState(false)
  const [role, setRole]       = useState(user.role)
  const [saving, setSaving]   = useState(false)
  const isSelf = user.id === currentUserId

  const save = async () => {
    setSaving(true)
    try {
      const { data } = await api.patch(`/admin/users/${user.id}`, { role })
      onUpdated(data)
      setEditing(false)
    } finally { setSaving(false) }
  }

  const del = async () => {
    if (!confirm(`Delete ${user.full_name}? This removes all their data.`)) return
    await api.delete(`/admin/users/${user.id}`)
    onDeleted(user.id)
  }

  // Delegate the plugin upload wizard. Uploads still land disabled; only a
  // super admin can enable a plugin.
  const toggleUploads = async () => {
    const grant = !user.can_upload_plugins
    if (grant && !confirm(`Let ${user.full_name} upload plugins?\n\nThey can add plugin bundles, ` +
        'which are installed disabled. Only a super admin can enable one.')) return
    const { data } = await api.patch(`/admin/users/${user.id}`, { can_upload_plugins: grant })
    onUpdated(data)
  }

  const setPassword = async () => {
    const pw = prompt(`Set new password for ${user.full_name}:`)
    if (!pw) return
    await api.patch(`/admin/users/${user.id}`, { password: pw })
    alert('Password updated.')
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
              className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 focus:outline-none appearance-none pr-6">
              <option value="member">member</option>
              <option value="parent">parent</option>
              <option value="super_admin">super_admin</option>
            </select>
          </div>
        ) : <RoleBadge role={user.role} />}
      </td>
      <td className="px-4 py-3">
        <span className={`text-xs ${user.can_login ? 'text-emerald-400' : 'text-slate-600'}`}>
          {user.can_login ? '✓ can log in' : 'no login'}
        </span>
        {user.can_login && user.role !== 'super_admin' && (
          <button onClick={toggleUploads}
            title={user.can_upload_plugins ? 'Revoke plugin uploads' : 'Allow this user to upload plugins'}
            className={`mt-1 flex items-center gap-1 text-[11px] ${user.can_upload_plugins
              ? 'text-shield-300 hover:text-shield-200' : 'text-slate-600 hover:text-slate-400'}`}>
            <Upload size={10} /> {user.can_upload_plugins ? 'can upload plugins' : 'plugin uploads off'}
          </button>
        )}
      </td>
      <td className="px-4 py-3 text-slate-500 text-xs">{user.managing_count} managing</td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {editing ? (
            <>
              <button onClick={save} disabled={saving} className="p-1 text-emerald-400 hover:text-emerald-300"><Check size={13} /></button>
              <button onClick={() => setEditing(false)} className="p-1 text-slate-500 hover:text-white"><X size={13} /></button>
            </>
          ) : (
            <>
              <button onClick={() => setEditing(true)} className="p-1 text-slate-500 hover:text-shield-400" title="Edit role"><Edit3 size={13} /></button>
              <button onClick={setPassword} className="p-1 text-slate-500 hover:text-amber-400" title="Set password"><KeyRound size={13} /></button>
              {!isSelf && <button onClick={del} className="p-1 text-slate-500 hover:text-red-400" title="Delete"><Trash2 size={13} /></button>}
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

  useEffect(() => {
    Promise.all([
      api.get('/admin/users'),
      api.get('/admin/access'),
      api.get('/auth/me'),
    ]).then(([u, g, m]) => {
      setUsers(u.data); setGrants(g.data); setMe(m.data)
    }).finally(() => setLoading(false))
  }, [])

  const revokeGrant = async id => {
    if (!confirm('Revoke this access grant?')) return
    await api.delete(`/admin/access/${id}`)
    setGrants(g => g.filter(x => x.id !== id))
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">Admin panel</h1>
          <p className="text-slate-400 text-sm mt-0.5">Manage users, roles, and profile access grants</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowGrant(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
            <Link2 size={13} /> Grant access
          </button>
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 transition-colors">
            <UserPlus size={13} /> Add user
          </button>
        </div>
      </div>

      {loading && <p className="text-slate-500 text-sm">Loading…</p>}

      {/* Users table */}
      {!loading && (
        <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden mb-6">
          <div className="px-4 py-3 border-b border-slate-700/50">
            <p className="text-slate-300 text-sm font-medium">Users ({users.length})</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 text-xs border-b border-slate-700/30">
                <th className="text-left px-4 py-2 font-normal">Name</th>
                <th className="text-left px-4 py-2 font-normal">Role</th>
                <th className="text-left px-4 py-2 font-normal">Login</th>
                <th className="text-left px-4 py-2 font-normal">Access</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <EditUserRow
                  key={u.id} user={u}
                  currentUserId={me?.id}
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
            <p className="text-slate-300 text-sm font-medium">Profile access grants ({grants.length})</p>
            <p className="text-slate-500 text-xs mt-0.5">Who can see and edit whose data</p>
          </div>
          {grants.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <Link2 size={24} className="text-slate-700 mx-auto mb-2" />
              <p className="text-slate-500 text-sm">No access grants yet.</p>
              <p className="text-slate-600 text-xs mt-1">Grant a parent access to manage another person's profile.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-xs border-b border-slate-700/30">
                  <th className="text-left px-4 py-2 font-normal">Manager</th>
                  <th className="text-left px-4 py-2 font-normal"></th>
                  <th className="text-left px-4 py-2 font-normal">Can access profile of</th>
                  <th className="text-left px-4 py-2 font-normal">Permissions</th>
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
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-blue-900/30 text-blue-400 border border-blue-800">
                          <Eye size={9} /> view
                        </span>
                        {g.can_edit && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-emerald-900/30 text-emerald-400 border border-emerald-800">
                            <Edit3 size={9} /> edit
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <button onClick={() => revokeGrant(g.id)}
                        className="opacity-0 group-hover:opacity-100 text-slate-600 hover:text-red-400 transition-all p-1"
                        title="Revoke">
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
    </div>
  )
}

// ── Shared styles ─────────────────────────────────────────────────────────────
const input = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-shield-500"
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
