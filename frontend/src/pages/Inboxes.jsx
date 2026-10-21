import { useEffect, useState, useCallback } from 'react'
import { Inbox, Plus, Trash2, RefreshCw, CheckCircle2, AlertTriangle, Clock, HelpCircle, Link2, X } from 'lucide-react'
import api from '../api'
import { tx, txr } from '../i18n/tx'
import { detailText } from '../errorMessage'

// Plain-language status for the "+address" capability of an inbox.
const PLUS = {
  verified:    { icon: CheckCircle2,  cls: 'text-emerald-400' },
  checking:    { icon: Clock,         cls: 'text-sky-400' },
  unsupported: { icon: AlertTriangle, cls: 'text-amber-400' },
  unknown:     { icon: HelpCircle,    cls: 'text-slate-400' },
}

const HOW = {
  assigned: 'Assigned',
  own: tx("Their own inbox"),
  parent: tx("A parent's inbox"),
  none: tx("No inbox yet"),
}

const inp = 'w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-shield-500'

function AddInbox({ providers, members, onDone, onCancel }) {
  const [form, setForm] = useState({ address: '', provider_key: '', label: '', assign_member_id: '',
    smtp_host: '', smtp_port: 587, imap_host: '', imap_port: 993, username: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))
  const appPassword = form.provider_key === 'smtp'

  const submit = async (e) => {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      const body = { ...form, assign_member_id: form.assign_member_id ? Number(form.assign_member_id) : null }
      const { data } = await api.post('/mailboxes', body)
      if (data.authorize_url) {
        // Provider sign-in opens in a new tab; this page refreshes when you come back.
        window.open(data.authorize_url, '_blank', 'noopener')
        onDone(tx("Finish signing in to your email in the new tab, then come back here."))
      } else {
        onDone(tx("Inbox connected."))
      }
    } catch (err) {
      setError(detailText(err) || tx("Something went wrong. Please check the details and try again."))
    } finally { setBusy(false) }
  }

  return (
    <form onSubmit={submit} className="p-4 rounded-xl border border-slate-700 bg-slate-900/60 space-y-3" aria-labelledby="add-inbox-title">
      <div className="flex items-center justify-between">
        <h2 id="add-inbox-title" className="text-white font-medium">{tx("Connect an inbox")}</h2>
        <button type="button" onClick={onCancel} className="text-slate-400 hover:text-white" aria-label={tx("Close")}><X size={16} /></button>
      </div>

      <div>
        <label htmlFor="ib-provider" className="block text-sm text-slate-300 mb-1">{tx("Email service")}</label>
        <select id="ib-provider" className={inp} value={form.provider_key} onChange={set('provider_key')} required>
          <option value="">{tx("Choose one…")}</option>
          {providers.map(p => (
            <option key={p.key} value={p.key} disabled={!p.available}>
              {p.label}{!p.available ? tx("(not set up by your administrator yet)") : ''}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="ib-address" className="block text-sm text-slate-300 mb-1">{tx("Email address")}</label>
        <input id="ib-address" type="email" autoComplete="email" className={inp} value={form.address} onChange={set('address')} required />
      </div>

      <div>
        <label htmlFor="ib-label" className="block text-sm text-slate-300 mb-1">{txr("Name for this inbox <0>(optional)</0>", [<span className="text-slate-500" />])}</label>
        <input id="ib-label" className={inp} placeholder={tx("e.g. Mom's Gmail")} value={form.label} onChange={set('label')} />
      </div>

      {members.length > 0 && (
        <div>
          <label htmlFor="ib-member" className="block text-sm text-slate-300 mb-1">{txr("Use it for <0>(optional)</0>", [<span className="text-slate-500" />])}</label>
          <select id="ib-member" className={inp} value={form.assign_member_id} onChange={set('assign_member_id')}>
            <option value="">{tx("Decide later")}</option>
            {members.map(m => <option key={m.member_id} value={m.member_id}>{m.full_name}</option>)}
          </select>
        </div>
      )}

      {appPassword && (
        <fieldset className="space-y-3 border-t border-slate-800 pt-3">
          <legend className="text-sm text-slate-300">{txr("Mail server details <0>(from your email provider's help pages)</0>", [<span className="text-slate-500" />])}</legend>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div className="sm:col-span-2">
              <label htmlFor="ib-smtp" className="block text-xs text-slate-400 mb-1">{tx("Outgoing mail server (SMTP)")}</label>
              <input id="ib-smtp" className={inp} value={form.smtp_host} onChange={set('smtp_host')} required />
            </div>
            <div>
              <label htmlFor="ib-smtp-port" className="block text-xs text-slate-400 mb-1">{tx("Port")}</label>
              <input id="ib-smtp-port" type="number" className={inp} value={form.smtp_port} onChange={set('smtp_port')} />
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="ib-imap" className="block text-xs text-slate-400 mb-1">{tx("Incoming mail server (IMAP)")}</label>
              <input id="ib-imap" className={inp} value={form.imap_host} onChange={set('imap_host')} required />
            </div>
            <div>
              <label htmlFor="ib-imap-port" className="block text-xs text-slate-400 mb-1">{tx("Port")}</label>
              <input id="ib-imap-port" type="number" className={inp} value={form.imap_port} onChange={set('imap_port')} />
            </div>
          </div>
          <div>
            <label htmlFor="ib-user" className="block text-xs text-slate-400 mb-1">{txr("Username <0>(usually your email address)</0>", [<span className="text-slate-500" />])}</label>
            <input id="ib-user" className={inp} value={form.username} onChange={set('username')} />
          </div>
          <div>
            <label htmlFor="ib-pass" className="block text-xs text-slate-400 mb-1">{txr("App password <0>(not your normal password)</0>", [<span className="text-slate-500" />])}</label>
            <input id="ib-pass" type="password" autoComplete="new-password" className={inp} value={form.password} onChange={set('password')} required />
          </div>
        </fieldset>
      )}

      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className="px-4 py-2 rounded-lg bg-shield-600 hover:bg-shield-500 text-white text-sm font-medium disabled:opacity-50">
          {busy ? tx("Connecting…") : appPassword ? tx("Connect") : tx("Continue to sign in")}
        </button>
        <button type="button" onClick={onCancel} className="px-4 py-2 rounded-lg border border-slate-700 text-slate-300 text-sm">{tx("Cancel")}</button>
      </div>
    </form>
  )
}

export default function Inboxes() {
  const [data, setData] = useState({ mailboxes: [], members: [] })
  const [providers, setProviders] = useState([])
  const [adding, setAdding] = useState(false)
  const [msg, setMsg] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([api.get('/mailboxes'), api.get('/mailboxes/providers')])
      .then(([a, b]) => { setData(a.data); setProviders(b.data.providers) })
      .catch(() => setMsg(tx("Couldn't load your inboxes. Please refresh the page.")))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])
  // Coming back from the provider's sign-in tab: refresh.
  useEffect(() => {
    const onFocus = () => load()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [load])

  const assign = async (member_id, mailbox_id) => {
    try {
      await api.post('/mailboxes/assign', { member_id, mailbox_id: mailbox_id ? Number(mailbox_id) : null })
      setMsg(tx("Saved.")); load()
    } catch (e) { setMsg(detailText(e) || tx("Couldn't save that change.")) }
  }
  const checkPlus = async (mb) => {
    try { await api.post(`/mailboxes/${mb.id}/check-plus`); setMsg(tx("Test email sent. This usually finishes within a few minutes.")); load() }
    catch (e) { setMsg(detailText(e) || tx("Couldn't send the test email.")) }
  }
  const reconnect = async (mb) => {
    try { const { data } = await api.post(`/mailboxes/${mb.id}/reconnect`); window.open(data.authorize_url, '_blank', 'noopener') }
    catch (e) { setMsg(detailText(e) || "Couldn't start sign-in.") }
  }
  const remove = async (mb) => {
    if (!window.confirm(`Disconnect ${mb.address}? Family members using it will need another inbox before more opt-outs are sent.`)) return
    try { await api.delete(`/mailboxes/${mb.id}`); setMsg('Inbox disconnected.'); load() }
    catch { setMsg("Couldn't disconnect that inbox.") }
  }

  const needsInbox = data.members.filter(m => m.how === 'none')

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2 mb-1">
        <Inbox size={20} className="text-shield-500" aria-hidden="true" />{" "}{tx("Email inboxes")}
      </h1>
      <p className="text-slate-400 text-sm mb-4 max-w-2xl">
        {txr("Opt-out requests are sent from these inboxes, and brokers reply to them. Each person needs one. Inboxes like Gmail can give every opt-out its own address (like <0>you+oo7f3k2a9@gmail.com</0>), so one inbox can cover the whole family and replies are matched automatically.", [<span className="text-slate-300" />])}
      </p>

      {msg && <p role="status" className="mb-3 text-sm text-shield-300">{msg}</p>}

      {needsInbox.length > 0 && (
        <div className="mb-4 p-3 rounded-lg border border-amber-700 bg-amber-950/30 text-sm text-amber-200 flex gap-2" role="alert">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" aria-hidden="true" />
          <span>{tx("No opt-outs will be sent for {v} until an inbox is connected or assigned below.", { v: needsInbox.map(m => m.full_name).join(', ') })}</span>
        </div>
      )}

      <section aria-labelledby="my-inboxes" className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <h2 id="my-inboxes" className="text-white font-medium">{tx("Your inboxes")}</h2>
          {!adding && (
            <button onClick={() => setAdding(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-shield-600 hover:bg-shield-500 text-white text-sm">
              <Plus size={14} aria-hidden="true" />{" "}{tx("Connect an inbox")}
            </button>
          )}
        </div>

        {adding && (
          <div className="mb-3">
            <AddInbox providers={providers} members={data.members}
              onDone={(m) => { setAdding(false); setMsg(m); load() }}
              onCancel={() => setAdding(false)} />
          </div>
        )}

        {loading ? <p className="text-slate-500 text-sm">{tx("Loading…")}</p> :
         data.mailboxes.length === 0 ? (
          <p className="text-slate-400 text-sm">{tx("You haven't connected an inbox yet.")}</p>
        ) : (
          <ul className="space-y-2">
            {data.mailboxes.map(mb => {
              const P = PLUS[mb.plus_status] || PLUS.unknown
              const PIcon = P.icon
              return (
                <li key={mb.id} className="p-3 rounded-lg border border-slate-700 bg-slate-900/60">
                  <div className="flex items-start justify-between gap-2 flex-wrap">
                    <div className="min-w-0">
                      <div className="text-slate-100 font-medium break-all">{mb.label ? `${mb.label} — ` : ''}{mb.address}</div>
                      <div className="text-sm mt-1">
                        {mb.status === 'connected'
                          ? <span className="text-emerald-400">{tx("Connected")}</span>
                          : <span className="text-amber-300">{tx("Sign-in not finished")}</span>}
                      </div>
                      <div className={`text-sm mt-1 flex items-center gap-1.5 ${P.cls}`}>
                        <PIcon size={14} aria-hidden="true" /> {mb.plus_label}
                      </div>
                      {mb.example_address && <div className="text-xs text-slate-500 mt-0.5">{tx("Example:")}{" "}{mb.example_address}</div>}
                      {mb.status_detail && <div className="text-xs text-slate-400 mt-1">{mb.status_detail}</div>}
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      {mb.status !== 'connected' && mb.transport === 'oauth' && (
                        <button onClick={() => reconnect(mb)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 text-sm">
                          <Link2 size={14} aria-hidden="true" />{" "}{tx("Finish sign-in")}
                        </button>
                      )}
                      {mb.status === 'connected' && ['unknown', 'unsupported'].includes(mb.plus_status) && (
                        <button onClick={() => checkPlus(mb)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 text-sm">
                          <RefreshCw size={14} aria-hidden="true" />{" "}{tx("Check +addresses")}
                        </button>
                      )}
                      <button onClick={() => remove(mb)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-700 text-red-300 text-sm" aria-label={tx("Disconnect {address}", { address: mb.address })}>
                        <Trash2 size={14} aria-hidden="true" />{" "}{tx("Disconnect")}
                      </button>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="who-uses">
        <h2 id="who-uses" className="text-white font-medium mb-1">{tx("Who uses which inbox")}</h2>
        <p className="text-slate-400 text-sm mb-2">
          {tx("If you leave someone on \"Automatic\", they use their own inbox, or else a parent's inbox that gives every opt-out its own address.")}
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-start text-slate-400 border-b border-slate-800">
                <th scope="col" className="py-2 pe-3 font-medium">{tx("Family member")}</th>
                <th scope="col" className="py-2 pe-3 font-medium">{tx("Inbox")}</th>
                <th scope="col" className="py-2 font-medium">{tx("Opt-outs go through")}</th>
              </tr>
            </thead>
            <tbody>
              {data.members.map(m => (
                <tr key={m.member_id} className="border-b border-slate-800/60">
                  <td className="py-2 pe-3 text-slate-200">{m.full_name}</td>
                  <td className="py-2 pe-3">
                    <label className="sr-only" htmlFor={`assign-${m.member_id}`}>{tx("Inbox for")}{" "}{m.full_name}</label>
                    <select id={`assign-${m.member_id}`} className={inp + ' py-1.5'} value={m.mailbox_id || ''}
                      onChange={e => assign(m.member_id, e.target.value)}>
                      <option value="">{tx("Automatic")}</option>
                      {data.mailboxes.filter(mb => mb.status === 'connected').map(mb =>
                        <option key={mb.id} value={mb.id}>{mb.label || mb.address}</option>)}
                    </select>
                  </td>
                  <td className={`py-2 ${m.how === 'none' ? 'text-amber-300' : 'text-slate-300'}`}>
                    {m.using_address ? <>{m.using_address} <span className="text-slate-500">· {HOW[m.how]}</span></> : HOW.none}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
