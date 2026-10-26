import { useEffect, useRef, useState } from 'react'
import { ShieldAlert, ScrollText, Info } from 'lucide-react'
import api from '../api'
import { useAuth } from '../hooks/useAuth'
import Markdown from './Markdown'
import { tx } from '../i18n/tx'
import { fmtDate } from '../i18n/format'
import { detailText } from '../errorMessage'

// What people are asked to read and accept before using OpenOptOut
// (backend/core/terms.py). Changing the wording of LimitsText or NoticeText
// means bumping LIMITS_VERSION or NOTICE_VERSION there, so everyone is asked
// again. All of it is a draft that no lawyer has reviewed yet.

export function LimitsText() {
  const items = [
    [tx("It can't remove everything."), tx("It knows about the brokers on its list. New ones appear every day, and many aren't covered. It doesn't touch government or court records, news, or social media.")],
    [tx("Brokers decide."), tx("Some ignore requests, take months, or ask for things OpenOptOut won't send, like ID numbers. Some put listings back later, which is why it checks again.")],
    [tx("Mistakes can happen."), tx("To opt someone out, OpenOptOut has to send that person's details to the broker. Details are stored encrypted, requests go only to brokers on its list, broker plugins (the steps OpenOptOut follows to opt out of a site) that nobody has checked yet start turned off, every message is checked before it leaves, and Social Security numbers, ID numbers and passwords are never sent. These lower the risk but can't remove it: a broker's site can change owners or change its form between checks.")],
    [tx("No warranty."), tx("OpenOptOut is free software, provided as is, under the AGPL (sections 15 and 16). Its authors aren't responsible for what brokers do with requests.")],
    [tx("This server is yours."), tx("You decide who's added, and you make sure you're allowed to act for them. You keep the server updated and backed up, and you follow the laws where you run it. If you offer it to others, like a library's patrons, you're the one offering it, so set your own terms on the Terms page.")],
    [tx("Not legal advice."), tx("The opt-out letters and these terms are drafts that a lawyer hasn't reviewed yet.")],
  ]
  return (
    <div className="space-y-3 text-sm text-slate-300">
      <p>{tx("OpenOptOut asks data brokers to remove the details of the people you add, and checks back later to see if they did. It can't promise more than that.")}</p>
      <ul className="space-y-2.5">
        {items.map(([head, body]) => (
          <li key={head} className="border-s-2 border-slate-700 ps-3">
            <strong className="text-slate-100">{head}</strong> {body}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function NoticeText({ operator, onTerms }) {
  const who = operator
  const items = [
    who ? tx("{operator} uses OpenOptOut to ask data brokers (sites that collect and sell personal details) to remove your details.", { operator: who })
        : tx("This server uses OpenOptOut to ask data brokers (sites that collect and sell personal details) to remove your details."),
    tx("To do that, it sends brokers your name and the details you add, such as address, phone, email and birth date. It never sends your Social Security number, ID numbers or passwords."),
    tx("It's a best effort. It can't reach every site, brokers decide whether to comply, and listings can come back. You may still find your details online."),
    who ? tx("Your details are stored encrypted on a server that {operator} runs.", { operator: who })
        : tx("Your details are stored encrypted on this server."),
    who ? tx("You can stop at any time. Ask {operator} to remove you, and your details and requests are deleted.", { operator: who })
        : tx("You can stop at any time. Ask the people who run this server to remove you, and your details and requests are deleted."),
  ]
  return (
    <div className="space-y-3 text-sm text-slate-300">
      <ul className="space-y-2.5">
        {items.map(t => <li key={t} className="border-s-2 border-slate-700 ps-3">{t}</li>)}
      </ul>
      {onTerms && <p>{onTerms}</p>}
    </div>
  )
}

function Step({ need, data, onAccepted, onSignOut }) {
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const head = useRef(null)
  useEffect(() => { head.current?.focus(); setChecked(false); setError('') }, [need.kind])

  const accept = async () => {
    setBusy(true); setError('')
    try {
      const r = await api.post('/terms/accept', { kind: need.kind, version: need.version })
      onAccepted(r.data.needs)
    } catch (e) {
      setError(detailText(e) || tx("Couldn't save that. Please try again."))
    } finally { setBusy(false) }
  }

  const t = data.terms || {}
  let icon, title, body, confirm
  if (need.kind === 'limits') {
    icon = <ShieldAlert size={20} className="text-amber-400" aria-hidden="true" />
    title = tx("Before you start: what OpenOptOut can and can't do")
    body = <LimitsText />
    confirm = tx("I understand OpenOptOut makes a best effort and can't guarantee removal, and I'm responsible for how this server is used.")
  } else if (need.kind === 'notice') {
    icon = <Info size={20} className="text-shield-400" aria-hidden="true" />
    title = tx("How OpenOptOut works for you")
    body = <NoticeText operator={t.operator}
      onTerms={t.enabled ? tx("Next you'll see the terms from the people who run this server.") : null} />
  } else {
    icon = <ScrollText size={20} className="text-shield-400" aria-hidden="true" />
    title = t.operator ? tx("Terms from {operator}", { operator: t.operator }) : tx("Terms for this server")
    body = (
      <div className="text-sm text-slate-300">
        {t.updated_at && <p className="text-xs text-slate-500 mb-2">{tx("Last changed {date}", { date: fmtDate(t.updated_at) })}</p>}
        <div className="max-h-[45vh] overflow-y-auto border border-slate-700 rounded-lg p-3 bg-slate-950/40">
          <Markdown source={t.text} />
        </div>
      </div>
    )
    confirm = tx("I've read these terms and I accept them.")
  }
  const ready = !confirm || checked

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <section role="dialog" aria-modal="true" aria-labelledby="terms-title"
        className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[92vh] overflow-y-auto p-6">
        <div className="flex items-center gap-2 mb-4">
          {icon}
          <h1 id="terms-title" ref={head} tabIndex="-1" className="text-white text-lg font-semibold focus:outline-hidden">{title}</h1>
        </div>
        {body}
        {confirm && (
          <label className="flex items-start gap-2 mt-5 text-sm text-slate-200">
            <input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-shield-500 shrink-0" />
            <span>{confirm}</span>
          </label>
        )}
        {error && <p role="alert" className="text-red-400 text-sm mt-3">{error}</p>}
        <div className="flex flex-wrap items-center justify-end gap-2 mt-5">
          <button onClick={onSignOut} className="px-3 py-2 text-sm text-slate-400 hover:text-white">{tx("Sign out")}</button>
          <button onClick={accept} disabled={!ready || busy}
            className="px-4 py-2 bg-shield-600 hover:bg-shield-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">
            {busy ? tx("Saving…") : need.kind === 'notice' ? tx("I understand") : tx("Continue")}
          </button>
        </div>
      </section>
    </div>
  )
}

// Shows what the signed-in person still has to accept, one at a time, then
// the app. If the check itself fails, the app opens anyway: a broken notice
// mustn't lock everyone out.
export default function TermsGate({ children }) {
  const { user, logout } = useAuth()
  const [data, setData] = useState(undefined)
  useEffect(() => {
    if (!user) return
    api.get('/terms/status').then(r => setData(r.data)).catch(() => setData(null))
  }, [user?.id])
  if (data === undefined)
    return <div className="min-h-screen bg-slate-950 flex items-center justify-center"><p className="text-slate-400 text-sm">{tx("Loading…")}</p></div>
  const need = data?.needs?.[0]
  if (!need) return children
  return <Step need={need} data={data} onSignOut={logout}
    onAccepted={needs => setData(d => ({ ...d, needs }))} />
}
