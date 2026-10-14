// Dates, times and numbers, shown the way the admin chose under
// Settings → Regional formats (default: United States).
//
// Numbers follow the region for everyone: in the US, "1,234.5" in every
// language. Dates use the person's language for month and day names, with the
// region's clock (12- or 24-hour) unless the admin picked one. So German in
// the US gives "11. Okt. 2026, 3:05 PM" and "1,234.5"; English in the UK gives
// "11 Oct 2026, 15:05" and "1,234.5". The browser's Intl tables do the work.
//
// Use these instead of toLocaleString()/toLocaleDateString(): the test
// i18n.regional_formats_used checks that nothing else formats dates or numbers.
//
//   fmtDate(v)              Oct 11, 2026
//   fmtDate(v, 'short')     Oct 11
//   fmtDate(v, 'weekday')   Sun, Oct 11
//   fmtDate(v, 'month')     October 2026
//   fmtDateTime(v)          Oct 11, 2026, 3:05 PM
//   fmtDateTime(v, 'short') Oct 11, 3:05 PM
//   fmtClock('02:00')       2:00 AM
//   fmtNumber(n)            1,234.5
//   fmtMB(bytes)            12.3
//   weekStart()             0 = Sunday … 6 = Saturday
//
// Values can be Date objects, numbers (ms) or strings. A plain date
// ("2026-10-11") is a calendar day and never shifts with the time zone. A
// date-time without a zone ("2026-10-11T20:05:00") is UTC, which is how the
// server stores times.

import { activeLanguage } from './tx'

const DEFAULTS = { region: 'US', hour_cycle: 'auto', week_start: 'auto', time_zone: '', digits: 'latn' }
let cfg = { ...DEFAULTS }
const cache = new Map()

export function setRegional(c) {
  cfg = { ...DEFAULTS }
  for (const k of Object.keys(DEFAULTS)) if (c && c[k] != null) cfg[k] = c[k]
  cache.clear()
}

export function regional() { return { ...cfg } }

// Loads the admin's choice. Called once before the app starts (main.jsx) and
// again after the admin saves.
export async function loadRegional() {
  try {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 4000)
    const res = await fetch('/api/settings/regional', { signal: ctrl.signal })
    clearTimeout(timer)
    if (res.ok) setRegional(await res.json())
  } catch { /* defaults */ }
}

// The region's own main locale (US -> en-US, MX -> es-MX, JP -> ja-JP).
function regionLocale() {
  try { return new Intl.Locale('und', { region: cfg.region }).maximize() } catch { return new Intl.Locale('en-US') }
}

// The clock the admin chose, or the one usual in the region.
function hourCycle() {
  if (cfg.hour_cycle === 'h12' || cfg.hour_cycle === 'h23') return cfg.hour_cycle
  try {
    const r = regionLocale()
    const hc = new Intl.DateTimeFormat(`${r.language}-${r.region}`, { hour: 'numeric' }).resolvedOptions().hourCycle
    return hc === 'h11' || hc === 'h12' ? 'h12' : 'h23'
  } catch { return 'h12' }
}

// The BCP 47 tag for dates: the person's language, the admin's region,
// clock and digits.
export function formatLocale() {
  const lang = activeLanguage()
  const base = !lang || lang === 'pirate' ? 'en' : lang
  const opts = { region: cfg.region, hourCycle: hourCycle() }
  if (cfg.digits === 'latn') opts.numberingSystem = 'latn'
  try { return new Intl.Locale(base, opts).toString() } catch { return 'en-US' }
}

// The tag for numbers: the region's own locale, so separators are the same
// for everyone. "native" digits use the person's language's digits.
export function numberLocale() {
  const r = regionLocale()
  const lang = activeLanguage()
  try {
    const opts = { region: cfg.region }
    if (cfg.digits === 'latn') opts.numberingSystem = 'latn'
    else {
      const nu = new Intl.NumberFormat(lang === 'pirate' ? 'en' : lang).resolvedOptions().numberingSystem
      if (nu) opts.numberingSystem = nu
    }
    return new Intl.Locale(r.language, opts).toString()
  } catch { return 'en-US' }
}

function formatter(kind, options) {
  const key = kind + JSON.stringify(options)
  let f = cache.get(key)
  if (!f) {
    const loc = kind === 'n' ? numberLocale() : formatLocale()
    try { f = kind === 'n' ? new Intl.NumberFormat(loc, options) : new Intl.DateTimeFormat(loc, options) }
    catch { f = kind === 'n' ? new Intl.NumberFormat('en-US', options) : new Intl.DateTimeFormat('en-US', { ...options, timeZone: undefined }) }
    cache.set(key, f)
  }
  return f
}

const DAY_ONLY = /^\d{4}-\d{2}-\d{2}$/
const NAIVE = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/

// [Date, isCalendarDay]
function parse(v) {
  if (v == null || v === '') return [null, false]
  if (v instanceof Date) return [isNaN(v) ? null : v, false]
  if (typeof v === 'number') return [new Date(v), false]
  const s = String(v).trim()
  if (DAY_ONLY.test(s)) return [new Date(s + 'T00:00:00Z'), true]
  const d = new Date(NAIVE.test(s) ? s.replace(' ', 'T') + 'Z' : s)
  return [isNaN(d) ? null : d, false]
}

const tz = day => (day ? 'UTC' : (cfg.time_zone || undefined))

const DATE_STYLES = {
  medium: { year: 'numeric', month: 'short', day: 'numeric' },
  short: { month: 'short', day: 'numeric' },
  weekday: { weekday: 'short', month: 'short', day: 'numeric' },
  month: { year: 'numeric', month: 'long' },
  long: { year: 'numeric', month: 'long', day: 'numeric' },
  numeric: { year: 'numeric', month: '2-digit', day: '2-digit' },
}

export function fmtDate(v, style = 'medium', empty = '—') {
  const [d, day] = parse(v)
  if (!d) return empty
  // A Date built in the browser for a calendar cell (the Calendar page) is a
  // local day: show it as it is, not shifted into the admin's time zone.
  const local = v instanceof Date
  return formatter('d', { ...(DATE_STYLES[style] || DATE_STYLES.medium), timeZone: local ? undefined : tz(day) }).format(d)
}

export function fmtDateTime(v, style = 'medium', empty = '—') {
  const [d] = parse(v)
  if (!d) return empty
  const date = style === 'short' ? DATE_STYLES.short : DATE_STYLES.medium
  return formatter('d', { ...date, hour: 'numeric', minute: '2-digit', timeZone: tz(false) }).format(d)
}

export function fmtTime(v, empty = '—') {
  const [d] = parse(v)
  if (!d) return empty
  return formatter('d', { hour: 'numeric', minute: '2-digit', timeZone: tz(false) }).format(d)
}

// A wall-clock time with no date or zone, such as a schedule's "02:00".
export function fmtClock(hhmm, empty = '') {
  const m = /^(\d{1,2}):(\d{2})/.exec(String(hhmm || ''))
  if (!m) return hhmm || empty
  return formatter('d', { hour: 'numeric', minute: '2-digit', timeZone: 'UTC' }).format(Date.UTC(1970, 0, 1, +m[1], +m[2]))
}

export function fmtNumber(n, options = {}, empty = '—') {
  if (n == null || n === '' || isNaN(Number(n))) return empty
  return formatter('n', options).format(Number(n))
}

export const fmtMB = bytes => fmtNumber(bytes / 1048576, { maximumFractionDigits: 1, minimumFractionDigits: 1 })

// Countries where the week starts on Sunday or Saturday; Monday elsewhere.
// (CLDR week data, for browsers without Intl.Locale week info.)
const SUNDAY = new Set(['US', 'CA', 'MX', 'PR', 'BR', 'CO', 'JP', 'KR', 'TW', 'HK', 'CN', 'PH', 'IN', 'IL', 'ZA', 'AU', 'SG', 'PT', 'SA'])
const SATURDAY = new Set(['AE', 'EG'])

export function weekStart() {
  if (cfg.week_start === 'sun') return 0
  if (cfg.week_start === 'mon') return 1
  if (cfg.week_start === 'sat') return 6
  try {
    const loc = new Intl.Locale(formatLocale())
    const info = loc.getWeekInfo?.() || loc.weekInfo
    if (info?.firstDay) return info.firstDay % 7
  } catch { /* table below */ }
  return SUNDAY.has(cfg.region) ? 0 : SATURDAY.has(cfg.region) ? 6 : 1
}

// Uses 12-hour time right now? (for showing a "3:00 PM" style example)
export function uses12Hour() {
  try { return formatter('d', { hour: 'numeric', timeZone: 'UTC' }).resolvedOptions().hour12 === true } catch { return true }
}
