import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  ListChecks, Inbox, Hand, ShieldAlert, Search, Clock, RotateCcw,
  ExternalLink, Check, Send, CheckCircle2, MailCheck, MousePointerClick
} from 'lucide-react'
import api from '../api'
import { tx } from '../i18n/tx'
import LiveCaptcha from '../components/LiveCaptcha'
import { detailText } from '../errorMessage'
import { isSafeHref } from '../components/Markdown'

const btn = 'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm'

const GROUPS = [
  { key: 'inbox',   icon: Inbox,       title: tx("Connect an email inbox"),  intro: tx("Nothing can be sent for these people until they have an inbox.") },
  { key: 'finish',  icon: Hand,        title: tx("Finish these opt-outs"),   intro: tx("OpenOptOut got as far as it could. Each one says exactly what's left.") },
  { key: 'confirm', icon: MailCheck,   title: tx("Confirm these opt-outs"),  intro: tx("These brokers emailed a link to click before they'll remove anything. OpenOptOut couldn't click them by itself.") },
  { key: 'captcha', icon: ShieldAlert, title: tx("Solve a CAPTCHA"),         intro: tx("These sites asked to prove a person is there.") },
  { key: 'review',  icon: Search,      title: tx("Is this you?"),            intro: tx("Web search found pages that might be about your family.") },
  { key: 'overdue', icon: Clock,       title: tx("Brokers that haven't answered"), intro: tx("They were sent a request and their time to respond has passed.") },
  { key: 'recheck', icon: RotateCcw,   title: tx("Check that listings stayed gone"), intro: tx("Brokers often add people back. A quick look keeps them off.") },
]

function Progress({ p }) {
  const total = p.removed + p.in_progress + p.needs_you + p.other
  const pct = (n) => (total ? Math.round((n / total) * 100) : 0)
  return (
    <li className="p-3 rounded-xl border border-slate-700/60 bg-slate-800/60">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-slate-100 font-medium">{p.member_name}</span>
        <span className="text-xs text-slate-400">{total ? tx("{pct}% removed", { pct: pct(p.removed) }) : tx("Nothing found yet")}</span>
      </div>
      {total > 0 && (
        <div className="mt-2 h-2.5 rounded-full bg-slate-700 overflow-hidden flex" role="img"
          aria-label={`${p.member_name}: ${p.removed} removed, ${p.in_progress} in progress, ${p.needs_you} need you`}>
          <div className="bg-emerald-500" style={{ width: `${pct(p.removed)}%` }} />
          <div className="bg-sky-500" style={{ width: `${pct(p.in_progress)}%` }} />
          <div className="bg-amber-400" style={{ width: `${pct(p.needs_you)}%` }} />
        </div>
      )}
      <dl className="mt-2 grid grid-cols-3 gap-1 text-xs">
        <div><dt className="text-slate-400">{tx("Removed")}</dt><dd className="text-emerald-300 text-sm font-medium">{p.removed}</dd></div>
        <div><dt className="text-slate-400">{tx("In progress")}</dt><dd className="text-sky-300 text-sm font-medium">{p.in_progress}</dd></div>
        <div><dt className="text-slate-400">{tx("Need you")}</dt><dd className="text-amber-300 text-sm font-medium">{p.needs_you}</dd></div>
      </dl>
    </li>
  )
}

// "Which of these is you?" for sites that list people by name only.
function Picker({ item, act }) {
  const [picked, setPicked] = useState([])
  const toggle = url => setPicked(p => (p.includes(url) ? p.filter(u => u !== url) : [...p, url]))
  return (
    <fieldset className="mt-2 space-y-2">
      <legend className="text-sm text-slate-200 font-medium">{tx("Which of these is {member_name}?", { member_name: item.member_name })}</legend>
      <p className="text-xs text-slate-400">{tx("The site hides the city and age, so OpenOptOut can't tell. Open each one if you need to look closer.")}</p>
      <ul className="space-y-2">
        {item.candidates.map((c, i) => (
          <li key={c.url} className="flex items-start gap-2 p-2 rounded-lg border border-slate-700/60 bg-slate-900/40">
            <input id={`pick-${item.request_id}-${i}`} type="checkbox" className="mt-1"
              checked={picked.includes(c.url)} onChange={() => toggle(c.url)} />
            <div className="min-w-0 flex-1">
              <label htmlFor={`pick-${item.request_id}-${i}`} className="text-sm text-slate-200 cursor-pointer break-words">
                {c.text || tx("No details shown")}
              </label>
              {isSafeHref(c.url) && (
                <a href={c.url} target="_blank" rel="noopener noreferrer nofollow" referrerPolicy="no-referrer"
                  className="ms-2 inline-flex items-center gap-1 text-xs text-shield-300 underline">
                  <ExternalLink size={11} aria-hidden="true" />{" "}{tx("Open")}<span className="sr-only">{" "}{tx("listing {v} in a new tab", { v: i + 1 })}</span>
                </a>
              )}
            </div>
          </li>
        ))}
      </ul>
      <div className="flex gap-2 flex-wrap">
        <button disabled={!picked.length} onClick={() => act('pick', item, picked)}
          className={`${btn} bg-shield-600 hover:bg-shield-500 text-white disabled:opacity-40`}>
          <Send size={13} aria-hidden="true" />{" "}{tx("Remove the ones I picked")}
        </button>
        <button onClick={() => act('pick', item, [])} className={`${btn} border border-slate-600 text-slate-200`}>
          {tx("None of these are {member_name}", { member_name: item.member_name })}
        </button>
      </div>
    </fieldset>
  )
}

function Item({ group, item, act, reload }) {
  const open = item.listing_url || item.site
  const [live, setLive] = useState(false)
  return (
    <li className="py-3 flex items-start justify-between gap-3 flex-wrap">
      <div className="min-w-0 flex-1">
        <div className="text-sm text-slate-100">
          {item.broker_name ? <><span className="font-medium">{item.broker_name}</span> <span className="text-slate-400">· {item.member_name}</span></>
            : <span className="font-medium">{item.member_name}</span>}
        </div>
        {item.text && <p className="text-sm text-slate-300 mt-0.5 whitespace-pre-line">{item.text}</p>}
        {group === 'finish' && item.candidates?.length > 0 && <Picker item={item} act={act} />}
      </div>
      <div className="flex gap-2 flex-wrap shrink-0">
        {item.link && (
          <Link to={item.link} className={`${btn} bg-shield-600 hover:bg-shield-500 text-white`}>
            {group === 'inbox' ? tx("Connect inbox") : group === 'captcha' ? tx("Open CAPTCHAs") : tx("Review")}
          </Link>
        )}
        {group === 'confirm' && item.confirm_url && isSafeHref(item.confirm_url) && (
          <a href={item.confirm_url} target="_blank" rel="noopener noreferrer nofollow" referrerPolicy="no-referrer"
            className={`${btn} bg-shield-600 hover:bg-shield-500 text-white`}
            aria-label={tx("Open {broker_name}'s confirmation link in a new tab", { broker_name: item.broker_name })}>
            <ExternalLink size={13} aria-hidden="true" />{" "}{tx("Open confirmation link")}
          </a>
        )}
        {group === 'confirm' && (
          <button onClick={() => act('confirmed', item)} className={`${btn} bg-emerald-700 hover:bg-emerald-600 text-white`}>
            <Check size={13} aria-hidden="true" />{" "}{tx("I've confirmed it")}
          </button>
        )}
        {!item.link && open && isSafeHref(open) && group !== 'confirm' && (
          <a href={open} target="_blank" rel="noopener noreferrer" className={`${btn} border border-slate-600 text-slate-200`}
            aria-label={tx("Open {broker_name} in a new tab", { broker_name: item.broker_name })}>
            <ExternalLink size={13} aria-hidden="true" />{" "}{tx("Open site")}
          </a>
        )}
        {group === 'finish' && item.live && !item.candidates?.length && (
          <button onClick={() => setLive(true)} className={`${btn} bg-shield-600 hover:bg-shield-500 text-white`}
            title={tx("OpenOptOut opens the site, fills in the form again up to this step, and shows you the page here. You do the step; OpenOptOut finishes the rest.")}>
            <MousePointerClick size={13} aria-hidden="true" />{" "}{tx("Do it here")}
          </button>
        )}
        {live && (
          <LiveCaptcha base={`/live-steps/${item.request_id}`}
            title={tx("Do it here: {broker_name} for {member_name}", { broker_name: item.broker_name, member_name: item.member_name })}
            onClose={() => { setLive(false); reload?.() }} onFinished={() => reload?.()} />
        )}
        {group === 'finish' && !item.candidates?.length && (
          <button onClick={() => act('done', item)} className={`${btn} bg-emerald-700 hover:bg-emerald-600 text-white`}>
            <Check size={13} aria-hidden="true" />{" "}{tx("I've done this")}
          </button>
        )}
        {(group === 'overdue' || group === 'recheck') && (
          <>
            <button onClick={() => act('requeue', item)} className={`${btn} bg-shield-600 hover:bg-shield-500 text-white`}>
              <Send size={13} aria-hidden="true" /> {group === 'recheck' ? tx("It's back — send again") : tx("Send again")}
            </button>
            <button onClick={() => act('removed', item)} className={`${btn} border border-slate-600 text-slate-200`}>
              <CheckCircle2 size={13} aria-hidden="true" /> {group === 'recheck' ? tx("Still gone") : tx("The listing is gone")}
            </button>
          </>
        )}
      </div>
    </li>
  )
}

export default function Checklist() {
  const [members, setMembers] = useState([])
  const [memberId, setMemberId] = useState('')
  const [data, setData] = useState(null)
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    api.get('/checklist', { params: memberId ? { member_id: memberId } : {} })
      .then(r => setData(r.data)).catch(() => setMsg(tx("Couldn't load the checklist. Please refresh.")))
  }, [memberId])
  useEffect(() => { api.get('/family').then(r => setMembers(r.data)).catch(() => {}) }, [])
  useEffect(() => { load() }, [load])

  const act = async (kind, item, urls) => {
    try {
      if (kind === 'pick') { const { data: d } = await api.post(`/checklist/${item.request_id}/pick`, { urls }); setMsg(d.message) }
      if (kind === 'done') { const { data: d } = await api.post(`/checklist/${item.request_id}/done`); setMsg(d.message) }
      else if (kind === 'confirmed') { const { data: d } = await api.post(`/checklist/confirm/${item.confirm_id}/done`); setMsg(d.message) }
      else if (kind === 'removed') { const { data: d } = await api.post(`/checklist/${item.request_id}/removed`); setMsg(d.message) }
      else if (kind === 'requeue') { await api.post(`/requests/${item.request_id}/requeue`); setMsg(tx("{broker_name} will be sent again in the next run.", { broker_name: item.broker_name })) }
      load()
    } catch (e) { setMsg(detailText(e) || tx("Couldn't save that. Please try again.")) }
  }

  const g = data?.groups || {}
  const shown = GROUPS.filter(x => (g[x.key] || []).length > 0)

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      <div className="flex items-start justify-between gap-3 flex-wrap mb-1">
        <h1 className="text-white text-xl font-semibold flex items-center gap-2">
          <ListChecks size={20} className="text-shield-500" aria-hidden="true" />{" "}{tx("Checklist")}
        </h1>
        {members.length > 1 && (
          <div>
            <label htmlFor="cl-member" className="sr-only">{tx("Family member")}</label>
            <select id="cl-member" value={memberId} onChange={e => setMemberId(e.target.value)}
              className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100">
              <option value="">{tx("Whole family")}</option>
              {members.map(m => <option key={m.id} value={m.id}>{m.full_name}</option>)}
            </select>
          </div>
        )}
      </div>
      <p className="text-slate-400 text-sm mb-4">{tx("Everything OpenOptOut can't finish on its own, in the order to do it.")}</p>

      {msg && <p role="status" className="mb-3 text-sm text-shield-300">{msg}</p>}
      {!data ? <p className="text-slate-500 text-sm">{tx("Loading…")}</p> : (
        <>
          <section aria-labelledby="progress-h" className="mb-6">
            <h2 id="progress-h" className="sr-only">{tx("Progress")}</h2>
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.progress.map(p => <Progress key={p.member_id} p={p} />)}
            </ul>
            <p className="text-xs text-slate-500 mt-2">
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-emerald-500 align-middle me-1" aria-hidden="true" />{tx("Removed")}
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-sky-500 align-middle ms-3 me-1" aria-hidden="true" />{tx("In progress")}
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-amber-400 align-middle ms-3 me-1" aria-hidden="true" />{tx("Needs you")}
            </p>
          </section>

          {shown.length === 0 ? (
            <div className="text-center py-12 rounded-xl border border-dashed border-slate-700 bg-slate-800/40">
              <CheckCircle2 size={28} className="text-emerald-400 mx-auto mb-2" aria-hidden="true" />
              <p className="text-slate-200 font-medium">{tx("Nothing needs you right now.")}</p>
              <p className="text-slate-400 text-sm mt-1">{tx("OpenOptOut will add things here when it needs a hand.")}</p>
            </div>
          ) : shown.map(({ key, icon: Icon, title, intro }) => (
            <section key={key} aria-labelledby={`g-${key}`} className="mb-5 p-4 rounded-xl border border-slate-700/60 bg-slate-800/40">
              <h2 id={`g-${key}`} className="text-white font-medium flex items-center gap-2">
                <Icon size={16} className="text-shield-400" aria-hidden="true" /> {title}
                <span className="text-xs font-normal text-slate-400">({g[key].length})</span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">{intro}</p>
              <ul className="divide-y divide-slate-700/40 mt-1">
                {g[key].map((item, i) => <Item key={`${key}-${item.request_id || item.member_id}-${i}`} group={key} item={item} act={act} reload={load} />)}
              </ul>
            </section>
          ))}
        </>
      )}
    </div>
  )
}
