import { useEffect, useState, useCallback } from 'react'
import { DatabaseBackup, KeyRound, Plus, Trash2, CheckCircle2, AlertTriangle, Download, ShieldCheck, Plug } from 'lucide-react'
import api from '../api'
import { tx, txr } from '../i18n/tx'
import { fmtDateTime, fmtMB } from '../i18n/format'

const inp = 'w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-shield-500'
const btn = 'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm'

const FIELDS = {
  folder: [['path', 'Folder (full path, e.g. /mnt/nas/openoptout)']],
  sftp: [['host', tx("Server address")], ['port', tx("Port (22)")], ['username', tx("User name")], ['password', tx("Password (or use a key below)"), 'password'],
         ['private_key', tx("Private key (optional, paste it)"), 'textarea'], ['path', tx("Folder on the server")]],
  s3: [['endpoint', tx("Storage address (leave empty for Amazon S3; https://storage.googleapis.com for Google Cloud Storage)")],
       ['region', tx("Region (e.g. us-east-1; \"auto\" for some services)")], ['bucket', 'Bucket'], ['prefix', tx("Folder in the bucket (optional)")],
       ['access_key', tx("Access key")], ['secret_key', tx("Secret key"), 'password']],
  gdrive: [], onedrive: [], dropbox: [],
  rclone: [['remote', tx("Remote name (the name in [brackets] in rclone.conf)")], ['path', tx("Folder (optional)")],
           ['rclone_config', tx("The remote's settings, pasted from rclone.conf"), 'textarea']],
}
const HELP = {
  folder: tx("A folder on this server, or a network drive mounted into it (NFS or SMB). On a Windows or Mac server, this can also be the folder a desktop app syncs, such as Proton Drive, so the backups go to that cloud without signing in here."),
  sftp: tx("Any server you can reach with SFTP. Its identity is remembered the first time, so a different server can't pretend to be it."),
  s3: tx("Amazon S3, Google Cloud Storage (with HMAC keys), Backblaze B2, Wasabi, MinIO and other S3-compatible storage."),
  gdrive: tx("Saves into an \"OpenOptOut backups\" folder. OpenOptOut can only see files it made there."),
  onedrive: tx("Saves into OpenOptOut's own app folder in OneDrive."),
  dropbox: tx("Saves into OpenOptOut's own app folder in Dropbox."),
  rclone: tx("Proton Drive, Box, pCloud, MEGA, iCloud Drive, Nextcloud and many more, through rclone. Run \"rclone config\" on any computer to set up the remote, then paste its section of rclone.conf here. It is stored encrypted. For Proton Drive, this uses rclone's unofficial connection, which needs your Proton password and can break when Proton changes things."),
}

export default function Backups() {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState({ text: '', ok: true })
  const [pass, setPass] = useState('')
  const [shown, setShown] = useState('')
  const [adding, setAdding] = useState(null)
  const [form, setForm] = useState({})

  const load = useCallback(() => api.get('/backups').then(r => setD(r.data)).catch(() => setMsg({ text: tx("Couldn't load backups."), ok: false })), [])
  useEffect(() => { load() }, [load])
  useEffect(() => { if (!d?.running) return; const t = setTimeout(load, 5000); return () => clearTimeout(t) }, [d, load])

  const say = (text, ok = true) => setMsg({ text, ok })
  const err = (e) => say(e.response?.data?.detail || tx("Something went wrong. Please try again."), false)

  const savePass = async (generate) => {
    try {
      const { data } = await api.post('/backups/passphrase', { passphrase: pass, generate })
      setPass(''); if (data.passphrase) setShown(data.passphrase); say(data.message); load()
    } catch (e) { err(e) }
  }
  const saveSchedule = async (patch) => {
    const body = { enabled: d.enabled, schedule: d.schedule, hour: d.hour, keep: d.keep, include_plugins: d.include_plugins, ...patch }
    try { await api.put('/backups', body); say('Saved.'); load() } catch (e) { err(e) }
  }
  const addDest = async (e) => {
    e.preventDefault()
    try { await api.post('/backups/destinations', { kind: adding, ...form }); setAdding(null); setForm({}); say(tx("Added. Test it to make sure it works.")); load() }
    catch (e2) { err(e2) }
  }
  const act = async (fn) => { try { const { data } = await fn(); say(data.message || 'Done.', data.ok !== false); load() } catch (e) { err(e) } }
  const connect = async (id) => {
    try { const { data } = await api.post(`/backups/destinations/${id}/connect`); window.open(data.authorize_url, '_blank', 'noopener'); say(tx("Finish signing in in the new tab, then come back and press Test.")) }
    catch (e) { err(e) }
  }
  const download = async (name) => {
    const r = await api.get(`/backups/files/${name}`, { responseType: 'blob' })
    const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url)
  }

  if (!d) return <div className="p-6 text-slate-400 text-sm">{msg.text || tx("Loading…")}</div>
  return (
    <div className="p-4 md:p-6 max-w-4xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2 mb-1">
        <DatabaseBackup size={20} className="text-shield-500" aria-hidden="true" />{" "}{tx("Backups")}
      </h1>
      <p className="text-slate-400 text-sm mb-4">
        {tx("A backup holds everything needed to bring OpenOptOut back on a new server: the database, settings, installed plugins and the keys that unlock them. It's encrypted with your backup passphrase before it leaves this server, so wherever you store it, nobody can read it without the passphrase.")}
      </p>
      {msg.text && <p role="status" className={`mb-4 text-sm ${msg.ok ? 'text-shield-300' : 'text-red-300'}`}>{msg.text}</p>}

      <section aria-labelledby="bk-pass" className="mb-5 p-4 rounded-xl border border-slate-700/60 bg-slate-800/40">
        <h2 id="bk-pass" className="text-white font-medium flex items-center gap-2"><KeyRound size={16} className="text-shield-400" aria-hidden="true" />{" "}{tx("Backup passphrase")}</h2>
        <p className="text-slate-400 text-xs mt-0.5 mb-3">
          {d.has_passphrase ? tx("A passphrase is set. Changing it only affects new backups; older ones still need the old one.") : tx("Needed before any backup can be made.")}
          {' '}{tx("Keep it somewhere safe that isn't this server. If it's lost, the backups can't be opened by anyone.")}
        </p>
        {shown && (
          <div role="alert" className="mb-3 p-3 rounded-lg border border-amber-700 bg-amber-950/30 text-sm text-amber-100">
            {txr("Your new passphrase (shown once): <0/>", [<code className="text-white text-base select-all">{shown}</code>])}
          </div>
        )}
        <div className="flex gap-2 flex-wrap">
          <label htmlFor="bk-pw" className="sr-only">{tx("New passphrase")}</label>
          <input id="bk-pw" type="password" className={inp + ' max-w-xs'} placeholder={tx("At least 12 characters")} value={pass} onChange={e => setPass(e.target.value)} />
          <button onClick={() => savePass(false)} disabled={pass.length < 12} className={`${btn} bg-shield-600 hover:bg-shield-500 text-white disabled:opacity-50`}>{tx("Save passphrase")}</button>
          <button onClick={() => savePass(true)} className={`${btn} border border-slate-600 text-slate-200`}>{tx("Make one for me")}</button>
        </div>
      </section>

      <section aria-labelledby="bk-sched" className="mb-5 p-4 rounded-xl border border-slate-700/60 bg-slate-800/40">
        <h2 id="bk-sched" className="text-white font-medium mb-2">{tx("Automatic backups")}</h2>
        <div className="flex flex-wrap items-end gap-4 text-sm">
          <label className="flex items-center gap-2 text-slate-200">
            <input type="checkbox" checked={d.enabled} disabled={!d.has_passphrase} onChange={e => saveSchedule({ enabled: e.target.checked })} className="accent-shield-500" />
            {tx("Back up automatically")}
          </label>
          <label className="text-slate-300">{tx("How often")}
            <select value={d.schedule} onChange={e => saveSchedule({ schedule: e.target.value })} className={inp + ' mt-1 w-32'}>
              <option value="daily">{tx("Every day")}</option><option value="weekly">{tx("Every week")}</option>
            </select>
          </label>
          <label className="text-slate-300">{tx("At (server time)")}
            <select value={d.hour} onChange={e => saveSchedule({ hour: Number(e.target.value) })} className={inp + ' mt-1 w-28'}>
              {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
            </select>
          </label>
          <label className="text-slate-300">{tx("Keep the newest")}
            <input type="number" min="1" max="365" value={d.keep} onChange={e => setD({ ...d, keep: Number(e.target.value) })}
              onBlur={() => saveSchedule({})} className={inp + ' mt-1 w-24'} />
          </label>
          <button onClick={() => act(() => api.post('/backups/run'))} disabled={!d.has_passphrase || d.running}
            className={`${btn} bg-shield-600 hover:bg-shield-500 text-white disabled:opacity-50`}>
            {d.running ? tx("Backing up…") : tx("Back up now")}
          </button>
        </div>
        <p className="text-slate-500 text-xs mt-2">{tx("A copy is always kept on this server in {local_dir}, and sent to every place below.", { local_dir: d.local_dir })}</p>
      </section>

      <section aria-labelledby="bk-dest" className="mb-5 p-4 rounded-xl border border-slate-700/60 bg-slate-800/40">
        <h2 id="bk-dest" className="text-white font-medium mb-2">{tx("Where backups go")}</h2>
        {d.destinations.length === 0 && <p className="text-slate-400 text-sm mb-2">{tx("Only this server so far. Add at least one place that isn't this server.")}</p>}
        <ul className="divide-y divide-slate-700/40">
          {d.destinations.map(x => (
            <li key={x.id} className="py-2 flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <div className="text-sm text-slate-100">{x.label} <span className="text-slate-500 text-xs">· {x.kind_label}</span></div>
                <div className="text-xs text-slate-500 break-all">{x.path || x.bucket || x.host || (x.needs_connect ? tx("Not signed in yet") : tx("Signed in"))}</div>
              </div>
              <div className="flex gap-2 flex-wrap shrink-0">
                {x.needs_connect && <button onClick={() => connect(x.id)} className={`${btn} bg-shield-600 text-white`}><Plug size={13} aria-hidden="true" />{" "}{tx("Sign in")}</button>}
                <button onClick={() => act(() => api.post(`/backups/destinations/${x.id}/test`))} className={`${btn} border border-slate-600 text-slate-200`}>{tx("Test")}</button>
                <button onClick={() => act(() => api.delete(`/backups/destinations/${x.id}`))} className={`${btn} text-slate-400 hover:text-red-300`}
                  aria-label={tx("Remove {label}", { label: x.label })}><Trash2 size={13} aria-hidden="true" /></button>
              </div>
            </li>
          ))}
        </ul>
        {!adding ? (
          <div className="flex gap-2 flex-wrap mt-3">
            {Object.entries(d.kinds).map(([k, label]) => (
              <button key={k} onClick={() => { setAdding(k); setForm({}) }} className={`${btn} border border-slate-600 text-slate-200`}>
                <Plus size={13} aria-hidden="true" /> {label}
              </button>
            ))}
          </div>
        ) : (
          <form onSubmit={addDest} className="mt-3 p-3 rounded-lg border border-slate-700 bg-slate-900/60 space-y-2">
            <p className="text-slate-200 text-sm font-medium">{d.kinds[adding]}</p>
            <p className="text-slate-400 text-xs">{HELP[adding]}</p>
            <label className="block text-sm text-slate-300">{tx("Name for it")}
              <input className={inp + ' mt-1'} value={form.label || ''} onChange={e => setForm({ ...form, label: e.target.value })} placeholder={d.kinds[adding]} />
            </label>
            {FIELDS[adding].map(([k, label, type]) => (
              <label key={k} className="block text-sm text-slate-300">{label}
                {type === 'textarea'
                  ? <textarea rows={3} className={inp + ' mt-1 font-mono text-xs'} value={form[k] || ''} onChange={e => setForm({ ...form, [k]: e.target.value })} />
                  : <input type={type || 'text'} className={inp + ' mt-1'} value={form[k] || ''} onChange={e => setForm({ ...form, [k]: k === 'port' ? Number(e.target.value) || '' : e.target.value })} />}
              </label>
            ))}
            {['gdrive', 'onedrive', 'dropbox'].includes(adding) && <p className="text-xs text-slate-400">{tx("After adding it, press Sign in.")}</p>}
            <div className="flex gap-2">
              <button type="submit" className={`${btn} bg-shield-600 hover:bg-shield-500 text-white`}>{tx("Add")}</button>
              <button type="button" onClick={() => setAdding(null)} className={`${btn} text-slate-300`}>{tx("Cancel")}</button>
            </div>
          </form>
        )}
      </section>

      <section aria-labelledby="bk-hist" className="p-4 rounded-xl border border-slate-700/60 bg-slate-800/40">
        <h2 id="bk-hist" className="text-white font-medium mb-2">{tx("Recent backups")}</h2>
        {d.history.length === 0 ? <p className="text-slate-400 text-sm">{tx("None yet.")}</p> : (
          <ul className="divide-y divide-slate-700/40">
            {d.history.slice(0, 10).map((h, i) => (
              <li key={i} className="py-2 text-sm">
                <div className="flex items-center gap-2">
                  {h.ok ? <CheckCircle2 size={14} className="text-emerald-400" aria-label={tx("Worked")} /> : <AlertTriangle size={14} className="text-amber-400" aria-label={tx("Problem")} />}
                  <span className="text-slate-200">{fmtDateTime(h.started, 'medium', '')}</span>
                  {h.size && <span className="text-slate-500 text-xs">{fmtMB(h.size)}{" "}{tx("MB")}</span>}
                </div>
                {h.error && <p className="text-xs text-red-300 ms-6">{h.error}</p>}
                {(h.destinations || []).map((x, j) => (
                  <p key={j} className={`text-xs ms-6 ${x.ok ? 'text-slate-400' : 'text-red-300'}`}>{x.label}: {x.ok ? 'saved' : x.error}</p>
                ))}
              </li>
            ))}
          </ul>
        )}
        {d.files.length > 0 && (
          <>
            <h3 className="text-slate-300 text-sm font-medium mt-4 mb-1">{tx("On this server")}</h3>
            <ul className="divide-y divide-slate-700/40">
              {d.files.map(f => (
                <li key={f.name} className="py-1.5 flex items-center justify-between gap-2 text-xs">
                  <span className="text-slate-300 break-all">{f.name} <span className="text-slate-500">{tx("({v} MB)", { v: fmtMB(f.size) })}</span></span>
                  <span className="flex gap-3 shrink-0">
                    <button onClick={() => act(() => api.post(`/backups/files/${f.name}/verify`))} className="text-shield-400 hover:text-shield-300 flex items-center gap-1"><ShieldCheck size={12} aria-hidden="true" />{" "}{tx("Check it opens")}</button>
                    <button onClick={() => download(f.name)} className="text-shield-400 hover:text-shield-300 flex items-center gap-1"><Download size={12} aria-hidden="true" />{" "}{tx("Download")}</button>
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="text-slate-500 text-xs mt-3">{tx("To restore, see docs/admin/backups.md: stop OpenOptOut, then run the restore command with the backup file and your passphrase.")}</p>
      </section>
    </div>
  )
}
