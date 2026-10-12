import { useEffect, useState } from 'react'
import { Gauge, FileDown } from 'lucide-react'
import api from '../api'
import { tx } from '../i18n/tx'
import { fmtDate } from '../i18n/format'

// Privacy score: how much of the family's known exposure has been cleaned up
// (0–100), where it started, and a daily trend line. Single series, so the
// title names it and there's no legend; each point has a hover tooltip, and
// the same numbers are available as a list for screen readers.

const fmtDay = d => fmtDate(d, 'short')

function Trend({ history }) {
  const [hover, setHover] = useState(null)
  if (history.length < 2) return null
  const W = 280, H = 64, P = 6
  // Time runs the reading way: left to right, or right to left in RTL languages.
  const rtl = typeof document !== 'undefined' && document.documentElement.dir === 'rtl'
  const xs = i => { const x = P + (i * (W - 2 * P)) / (history.length - 1); return rtl ? W - x : x }
  const ys = v => H - P - (v / 100) * (H - 2 * P)
  const pts = history.map((h, i) => [xs(i), ys(h.score)])
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const h = hover != null ? history[hover] : null
  return (
    <div className="relative mt-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-16" role="img"
        aria-label={tx("Score went from {score} on {fmtDay} to {score2} on {fmtDay2}", { score: history[0].score, fmtDay: fmtDay(history[0].day), score2: history[history.length - 1].score, fmtDay2: fmtDay(history[history.length - 1].day) })}
        onMouseLeave={() => setHover(null)}>
        <line x1={P} x2={W - P} y1={ys(50)} y2={ys(50)} stroke="currentColor" className="text-slate-700" strokeWidth="1" strokeDasharray="2 3" />
        <path d={d} fill="none" stroke="var(--color-shield-400)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {hover != null && <line x1={pts[hover][0]} x2={pts[hover][0]} y1={P} y2={H - P} stroke="currentColor" className="text-slate-500" strokeWidth="1" />}
        {hover != null && <circle cx={pts[hover][0]} cy={pts[hover][1]} r="4" fill="var(--color-shield-400)" stroke="var(--color-slate-800, #1e293b)" strokeWidth="2" />}
        {pts.map((p, i) => (
          <rect key={i} x={p[0] - (W / history.length) / 2} y={0} width={W / history.length} height={H}
            fill="transparent" onMouseEnter={() => setHover(i)} />
        ))}
      </svg>
      {h && (
        <div className="absolute -top-7 text-xs bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-slate-200 pointer-events-none"
          style={{ left: `${(pts[hover][0] / W) * 100}%`, transform: 'translateX(-50%)' }}>
          {fmtDay(h.day)}: {h.score}
        </div>
      )}
      <ul className="sr-only">{history.map(x => <li key={x.day}>{fmtDay(x.day)}: {x.score}</li>)}</ul>
    </div>
  )
}

export async function downloadReport(scope = 'family') {
  const r = await api.get('/reports/removal.pdf', { params: { scope }, responseType: 'blob' })
  const url = URL.createObjectURL(r.data)
  const a = document.createElement('a'); a.href = url; a.download = 'openoptout-removal-report.pdf'; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function PrivacyScore() {
  const [busy, setBusy] = useState(false)
  const [data, setData] = useState(null)
  useEffect(() => { api.get('/reports/score').then(r => setData(r.data)).catch(() => setData(false)) }, [])
  if (!data || data.family.now == null) return null
  const f = data.family
  const change = f.start != null ? f.now - f.start : null
  return (
    <section aria-labelledby="score-h" className="bg-slate-800 rounded-xl p-4 border border-slate-700/50 mb-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 id="score-h" className="text-slate-400 text-xs uppercase tracking-wide flex items-center gap-1.5">
            <Gauge size={13} aria-hidden="true" />{" "}{tx("Privacy score")}
          </h2>
          <p className="mt-1"><span className="text-white text-4xl font-semibold">{f.now}</span><span className="text-slate-400 text-sm"> / 100</span></p>
          {change != null && (
            <p className="text-slate-300 text-sm">
              {tx("Started at {start} on {fmtDay}", { start: f.start, fmtDay: fmtDay(f.start_day) })}
              {change !== 0 && <span className={change > 0 ? 'text-emerald-300' : 'text-amber-300'}> · {change > 0 ? tx("up {n}", { n: Math.abs(change) }) : tx("down {n}", { n: Math.abs(change) })}</span>}
            </p>
          )}
        </div>
        <dl className="grid grid-cols-3 gap-4 text-sm">
          <div><dt className="text-slate-400 text-xs">{tx("Still listed")}</dt><dd className="text-white text-lg">{f.exposed_now}</dd></div>
          <div><dt className="text-slate-400 text-xs">{tx("Sites")}</dt><dd className="text-white text-lg">{f.sites_now}</dd></div>
          {f.exposed_start != null && <div><dt className="text-slate-400 text-xs">{tx("Listed at start")}</dt><dd className="text-white text-lg">{f.exposed_start}</dd></div>}
        </dl>
      </div>
      <Trend history={f.history} />
      <div className="flex flex-wrap items-center justify-between gap-2 mt-2">
        <p className="text-slate-500 text-xs">{tx("100 means none of the sites we know about still show your family. Bigger sites count for more.")}</p>
        <button onClick={async () => { setBusy(true); try { await downloadReport() } catch { /* shown by the button state */ } finally { setBusy(false) } }}
          disabled={busy}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-700 disabled:opacity-50">
          <FileDown size={13} aria-hidden="true" /> {busy ? tx("Making the report…") : tx("Download full report (PDF)")}
        </button>
      </div>
    </section>
  )
}
