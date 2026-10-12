import { useEffect, useState } from 'react'
import { Check, Circle, AlertTriangle, RotateCcw, ChevronDown, ChevronRight } from 'lucide-react'
import api from '../api'
import Badge from './Badge'
import { tx } from '../i18n/tx'
import { fmtDate } from '../i18n/format'

// Progress of one opt-out, round after round: sent → reply → removed →
// staying gone. If a later check finds the listing again, a new round starts.

const fmt = d => fmtDate(d, 'medium', '')

function Steps({ cycle, stages }) {
  const at = {
    sent: cycle.sent_at,
    reply: cycle.replied_at,
    removed: cycle.removed_at,
    watching: cycle.stage === 'watching' ? cycle.last_checked_gone_at : null,
  }
  const reached = stages.map(s => !!at[s.key])
  return (
    <ol className="flex items-start w-full" aria-label={tx("Progress")}>
      {stages.map((s, i) => {
        const done = reached[i]
        const current = done && !reached[i + 1]
        return (
          <li key={s.key} className="flex-1 min-w-0" aria-current={current ? 'step' : undefined}>
            <div className="flex items-center">
              <span className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center border ${
                done ? 'bg-emerald-600 border-emerald-500 text-white' : 'border-slate-600 text-slate-600'}`}>
                {done ? <Check size={13} aria-hidden="true" /> : <Circle size={8} aria-hidden="true" />}
              </span>
              {i < stages.length - 1 && (
                <span className={`h-0.5 flex-1 mx-1 ${reached[i + 1] ? 'bg-emerald-600' : 'bg-slate-700'}`} aria-hidden="true" />
              )}
            </div>
            <p className={`text-xs mt-1 ${done ? 'text-slate-200' : 'text-slate-500'}`}>
              {s.label}<span className="sr-only">{done ? ': done' : ': not yet'}</span>
            </p>
            <p className="text-[11px] text-slate-400">{fmt(at[s.key])}</p>
          </li>
        )
      })}
    </ol>
  )
}

function Round({ c, n, stages, open: startOpen }) {
  const [open, setOpen] = useState(!!startOpen)
  return (
    <div className="border-t border-slate-700/50 pt-3 mt-3 first:border-0 first:pt-0 first:mt-0">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <p className="text-slate-300 text-sm font-medium">{tx("Round")}{" "}{n}{c.sent_at ? tx("· started {fmt}", { fmt: fmt(c.sent_at) }) : ''}</p>
        {c.follow_ups.length > 0 && (
          <p className="text-slate-400 text-xs">{tx("Followed up {length}× (last {fmt})", { length: c.follow_ups.length, fmt: fmt(c.follow_ups[c.follow_ups.length - 1]) })}</p>
        )}
      </div>
      <Steps cycle={c} stages={stages} />
      {c.found_again_at && (
        <p className="mt-2 flex items-center gap-1.5 text-amber-300 text-sm">
          <RotateCcw size={13} aria-hidden="true" />{" "}{tx("Found again on {fmt}. A new request goes out on the next run.", { fmt: fmt(c.found_again_at) })}
        </p>
      )}
      <button onClick={() => setOpen(o => !o)} aria-expanded={open}
        className="mt-2 flex items-center gap-1 text-slate-400 hover:text-slate-200 text-xs">
        {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}{" "}{tx("Every step ({length})", { length: c.events.length })}
      </button>
      {open && (
        <ul className="mt-1 space-y-0.5 text-xs">
          {c.events.map((e, i) => (
            <li key={i} className="flex gap-3">
              <span className="text-slate-500 w-24 shrink-0">{fmt(e.at)}</span>
              <span className="text-slate-300">{e.label}{e.note ? <span className="text-slate-500"> · {e.note}</span> : null}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function RemovalTimeline({ t }) {
  const rounds = t.cycles
  return (
    <div className="bg-slate-900/60 rounded-lg border border-slate-700/50 p-3">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-white text-sm font-medium">{t.member}</span>
        <Badge value={t.status} />
        {t.next_check && <span className="text-slate-400 text-xs">{tx("Next check")}{" "}{fmt(t.next_check)}</span>}
      </div>
      {t.overdue && (
        <p className="mb-3 flex items-start gap-1.5 text-red-300 text-sm" role="note">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" aria-hidden="true" />
          {tx("No answer within the {response_days} days the law gives them (due {fmt}).", { response_days: t.response_days, fmt: fmt(rounds[rounds.length - 1].due_by) })}
        </p>
      )}
      {rounds.length === 0 ? (
        <p className="text-slate-400 text-sm">{tx("Nothing sent yet.")}</p>
      ) : (
        [...rounds].reverse().map((c, i) => (
          <Round key={i} c={c} n={rounds.length - i} stages={t.stages} open={false} />
        ))
      )}
    </div>
  )
}

export default function BrokerTimelines({ brokerId }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.get(`/timeline/broker/${brokerId}`)
      .then(r => setData(r.data))
      .catch(e => setError(e.response?.data?.detail || tx("Couldn't load the history.")))
  }, [brokerId])
  if (error) return <p role="alert" className="text-red-400 text-sm">{error}</p>
  if (!data) return <p className="text-slate-400 text-sm">{tx("Loading…")}</p>
  if (!data.timelines.length) return <p className="text-slate-400 text-sm">{tx("No one in your family has a request with {broker} yet.", { broker: data.broker })}</p>
  return <div className="space-y-3">{data.timelines.map(t => <RemovalTimeline key={t.request_id} t={t} />)}</div>
}
