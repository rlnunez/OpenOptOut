import { useCallback, useEffect, useMemo, useState } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight, Link2, Download, X } from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'
import { tx } from '../i18n/tx'

// What happens when: the days opt-outs go out, when each site is checked
// again, and when a site's legal deadline to answer runs out. Admins choose
// which weekdays opt-outs go out and which dates to skip. Anyone can add it
// to their own calendar with a private link.

const DAYS = [tx("Mon"), tx("Tue"), tx("Wed"), tx("Thu"), tx("Fri"), tx("Sat"), tx("Sun")]
const LONG_DAYS = [tx("Monday"), tx("Tuesday"), tx("Wednesday"), tx("Thursday"), tx("Friday"), tx("Saturday"), tx("Sunday")]
const KIND = {
  run:      { label: tx("Opt-outs go out"), cls: 'bg-shield-600/30 text-shield-200 border-shield-600/50' },
  check:    { label: tx("Check again"),     cls: 'bg-slate-700/60 text-slate-200 border-slate-600' },
  deadline: { label: tx("Legal deadline"),  cls: 'bg-amber-900/40 text-amber-200 border-amber-700/60' },
  skip:     { label: tx("Day off"),         cls: 'bg-slate-800 text-slate-400 border-slate-700 line-through' },
}
const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const nice = s => new Date(s + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })

export default function Calendar() {
  const { user } = useAuth()
  const isStaff = can(user, 'scheduler.manage')
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1) })
  const [data, setData] = useState(null)
  const [msg, setMsg] = useState('')
  const [feed, setFeed] = useState('')
  const [newSkip, setNewSkip] = useState('')

  const load = useCallback(() => {
    const start = new Date(month); start.setDate(start.getDate() - ((start.getDay() + 6) % 7))
    api.get('/calendar', { params: { start: iso(start), days: 42 } })
      .then(r => setData(r.data)).catch(e => setMsg(e.response?.data?.detail || tx("Couldn't load the calendar.")))
  }, [month])
  useEffect(() => { load() }, [load])

  const byDay = useMemo(() => {
    const m = {}
    for (const e of data?.events || []) (m[e.date] ||= []).push(e)
    return m
  }, [data])

  const cells = useMemo(() => {
    const start = new Date(month); start.setDate(start.getDate() - ((start.getDay() + 6) % 7))
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d })
  }, [month])

  const saveSchedule = async (patch) => {
    setMsg('')
    try { await api.patch('/settings/scheduler', patch); setMsg(tx("Saved.")); load() }
    catch (e) { setMsg(e.response?.data?.detail || tx("Couldn't save that.")) }
  }
  const runDays = data?.run_days ?? [0, 1, 2, 3, 4, 5, 6]
  const toggleDay = i => {
    const next = runDays.includes(i) ? runDays.filter(x => x !== i) : [...runDays, i].sort()
    if (next.length === 0) { setMsg(tx("Pick at least one day.")); return }
    saveSchedule({ run_days: next })
  }

  const makeFeed = async () => {
    try { const { data } = await api.post('/calendar/feed'); setFeed(data.url); load() }
    catch { setMsg(tx("Couldn't make the link.")) }
  }
  const dropFeed = async () => { await api.delete('/calendar/feed'); setFeed(''); load() }
  const downloadIcs = async () => {
    const r = await api.get('/calendar/my.ics', { responseType: 'blob' })
    const url = URL.createObjectURL(r.data); const a = document.createElement('a')
    a.href = url; a.download = 'openoptout.ics'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  const today = iso(new Date())
  const upcoming = (data?.events || []).filter(e => e.date >= today && e.kind !== 'run').slice(0, 30)
  const card = 'bg-slate-800 rounded-xl border border-slate-700/50 p-4 mb-4'

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <h1 className="text-white text-xl font-semibold flex items-center gap-2"><CalendarDays size={18} aria-hidden="true" />{" "}{tx("Calendar")}</h1>
      <p className="text-slate-400 text-sm mt-1 mb-4">{tx("When opt-outs go out, when each site gets checked again, and when a site's legal deadline to answer runs out.")}</p>
      {msg && <p role="status" className="text-slate-200 text-sm mb-3">{msg}</p>}

      <section aria-labelledby="h-month" className={card}>
        <div className="flex items-center justify-between mb-3">
          <button onClick={() => setMonth(m => new Date(m.getFullYear(), m.getMonth() - 1, 1))} aria-label={tx("Previous month")}
            className="p-1.5 rounded-lg text-slate-300 hover:bg-slate-700"><ChevronLeft size={16} /></button>
          <h2 id="h-month" className="text-white font-medium">{month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</h2>
          <button onClick={() => setMonth(m => new Date(m.getFullYear(), m.getMonth() + 1, 1))} aria-label={tx("Next month")}
            className="p-1.5 rounded-lg text-slate-300 hover:bg-slate-700"><ChevronRight size={16} /></button>
        </div>
        <div className="flex flex-wrap gap-2 mb-3 text-xs">
          {Object.entries(KIND).map(([k, v]) => <span key={k} className={`px-2 py-0.5 rounded border ${v.cls}`}>{v.label}</span>)}
        </div>
        <div className="hidden md:grid grid-cols-7 gap-px bg-slate-700/40 rounded-lg overflow-hidden" role="grid" aria-label={tx("Month view")}>
          {DAYS.map(d => <div key={d} role="columnheader" className="bg-slate-900 text-slate-400 text-xs px-2 py-1">{d}</div>)}
          {cells.map(d => {
            const k = iso(d), evs = byDay[k] || [], inMonth = d.getMonth() === month.getMonth()
            return (
              <div key={k} role="gridcell" aria-label={`${nice(k)}: ${evs.length ? evs.map(e => e.title).join('; ') : 'nothing'}`}
                className={`bg-slate-900 min-h-24 p-1.5 ${inMonth ? '' : 'opacity-40'} ${k === today ? 'ring-1 ring-inset ring-shield-500' : ''}`}>
                <p className="text-slate-400 text-xs mb-1">{d.getDate()}</p>
                {evs.slice(0, 3).map((e, i) => (
                  <p key={i} title={e.title} className={`text-[11px] leading-tight px-1 py-0.5 mb-0.5 rounded border truncate ${KIND[e.kind].cls}`}>
                    {e.kind === 'run' ? tx("Opt-outs {time}", { time: e.time }) : e.title}</p>
                ))}
                {evs.length > 3 && <p className="text-[11px] text-slate-400">{tx("+{v} more", { v: evs.length - 3 })}</p>}
              </div>
            )
          })}
        </div>
        <p className="md:hidden text-slate-400 text-sm">{tx("The month view needs a wider screen. Everything coming up is listed below.")}</p>
      </section>

      <section aria-labelledby="h-up" className={card}>
        <h2 id="h-up" className="text-white font-medium mb-2">{tx("Coming up")}</h2>
        {upcoming.length === 0 ? <p className="text-slate-400 text-sm">{tx("Nothing to check or chase yet.")}</p> : (
          <ul className="space-y-1 text-sm">{upcoming.map((e, i) => (
            <li key={i} className="flex gap-3"><span className="text-slate-400 w-28 shrink-0">{nice(e.date)}</span>
              <span className={e.kind === 'deadline' ? 'text-amber-200' : 'text-slate-200'}>{e.title}</span></li>))}</ul>
        )}
      </section>

      <section aria-labelledby="h-sub" className={card}>
        <h2 id="h-sub" className="text-white font-medium mb-1 flex items-center gap-2"><Link2 size={15} aria-hidden="true" />{" "}{tx("Add to my calendar")}</h2>
        <p className="text-slate-400 text-sm mb-2">{tx("Subscribe in Google Calendar, Apple Calendar or Outlook with a private link, or download a file to import once. Only first names and site names are shown.")}</p>
        <div className="flex flex-wrap gap-2">
          <button onClick={makeFeed} className="px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700">
            {data?.has_feed ? tx("Make a new link") : tx("Make my private link")}</button>
          <button onClick={downloadIcs} className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-700">
            <Download size={13} aria-hidden="true" />{" "}{tx("Download .ics")}</button>
          {data?.has_feed && <button onClick={dropFeed} className="px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">{tx("Turn my link off")}</button>}
        </div>
        {feed && (
          <div className="mt-3">
            <label htmlFor="feed-url" className="text-slate-300 text-xs">{tx("Your link (copy it now; it isn't shown again)")}</label>
            <input id="feed-url" readOnly value={feed} onFocus={e => e.target.select()}
              className="w-full mt-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono" />
          </div>
        )}
      </section>

      {isStaff && data && (
        <section aria-labelledby="h-sched" className={card}>
          <h2 id="h-sched" className="text-white font-medium mb-1">{tx("When opt-outs go out")}</h2>
          <p className="text-slate-400 text-sm mb-2">
            {data.enabled ? tx("At {run_time} ({timezone}) on the days ticked below.", { run_time: data.run_time, timezone: data.timezone }) : tx("Automatic sending is off in Settings, so nothing goes out by itself.")}
            {' '}{tx("\"Send opt-outs now\" on the Dashboard always works.")}
          </p>
          <fieldset className="flex flex-wrap gap-3 mb-3">
            <legend className="sr-only">{tx("Days opt-outs go out")}</legend>
            {LONG_DAYS.map((d, i) => (
              <label key={d} className="flex items-center gap-1.5 text-sm text-slate-200">
                <input type="checkbox" checked={runDays.includes(i)} onChange={() => toggleDay(i)} className="w-4 h-4 accent-shield-500" />{d}
              </label>
            ))}
          </fieldset>
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label htmlFor="skip" className="block text-slate-300 text-sm mb-1">{tx("Days off (holidays)")}</label>
              <input id="skip" type="date" value={newSkip} onChange={e => setNewSkip(e.target.value)}
                className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200" />
            </div>
            <button disabled={!newSkip} onClick={() => { saveSchedule({ skip_dates: [...(data.skip_dates || []), newSkip] }); setNewSkip('') }}
              className="px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700 disabled:opacity-40">{tx("Add day off")}</button>
          </div>
          {data.skip_dates?.length > 0 && (
            <ul className="flex flex-wrap gap-2 mt-3">{data.skip_dates.map(d => (
              <li key={d} className="flex items-center gap-1 text-sm text-slate-200 bg-slate-900 border border-slate-700 rounded-lg pl-2 pr-1 py-0.5">
                {nice(d)}
                <button onClick={() => saveSchedule({ skip_dates: data.skip_dates.filter(x => x !== d) })} aria-label={tx("Remove day off {nice}", { nice: nice(d) })}
                  className="p-0.5 text-slate-400 hover:text-white"><X size={12} /></button>
              </li>))}</ul>
          )}
        </section>
      )}
    </div>
  )
}
