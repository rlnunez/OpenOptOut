// Page text translation.
//
// Every phrase people read is written in English in the code and wrapped in
// tx("..."): the English text is the key. The active language's table is
// loaded before the app starts (main.jsx), so tx() works anywhere, including
// lists built when a module loads. Switching language reloads the page.
//
//   tx("Saved.")
//   tx("{name} will be sent again.", { name })
//
// A phrase with no translation shows in English. The English list and each
// language's translations live in backend/core/page_texts.json and in the
// language-pack plugins (texts.json).

import { cloneElement, isValidElement } from 'react'

let table = {}
let current = 'en'

export function setTable(code, t) {
  current = code || 'en'
  table = t && typeof t === 'object' ? t : {}
}

export function activeLanguage() {
  return current
}

function fill(str, vars) {
  if (!vars) return str
  return str.replace(/\{(\w+)\}/g, (m, k) => (k in vars && vars[k] != null ? String(vars[k]) : m))
}

export function tx(text, vars) {
  if (typeof text !== 'string') return text
  const hit = table[text]
  return fill(typeof hit === 'string' && hit ? hit : text, vars)
}

// Loads a language's table from the server; English needs nothing.
export async function loadTable(code) {
  const lang = (code || 'en').toLowerCase()
  try {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 4000)
    const res = await fetch(`/api/i18n/translations/${encodeURIComponent(lang)}`, { signal: ctrl.signal })
    clearTimeout(timer)
    if (!res.ok) throw new Error(String(res.status))
    const data = await res.json()
    setTable(lang, data.translations || {})
    document.documentElement.dir = data.is_rtl ? 'rtl' : 'ltr'
    document.documentElement.lang = lang
    return data
  } catch {
    setTable('en', {})
    return null
  }
}

// Counted phrases: txn(n, "{n} site", "{n} sites", vars). Both forms are
// translated; the language's own rule picks one (forms other than "one" use
// the second, so translators write a form that reads well for those).
export function txn(n, one, other, vars) {
  let form = 'other'
  try { form = new Intl.PluralRules(current === 'pirate' ? 'en' : current).select(Number(n)) } catch { form = Number(n) === 1 ? 'one' : 'other' }
  return tx(form === 'one' ? one : other, { n, ...(vars || {}) })
}

// Sentences with bold text, links or code inside them stay one phrase, with
// numbered tags marking the inline parts, so translators can move them:
//
//   txr("Sends it to an address <0>you</0> control.", [<strong className="…" />])
//
// <n>…</n> takes element n and puts the (translated) words inside it;
// <n/> puts element n in as it is. {name} placeholders work as in tx().
export function txr(text, elements, vars) {
  const s = tx(text, vars)
  const out = []
  const re = /<(\d+)>([\s\S]*?)<\/\1>|<(\d+)\/>/g
  let last = 0, m, k = 0
  while ((m = re.exec(s))) {
    if (m.index > last) out.push(s.slice(last, m.index))
    const idx = Number(m[1] ?? m[3])
    const el = elements && elements[idx]
    if (el && isValidElement(el)) {
      out.push(m[1] !== undefined ? cloneElement(el, { key: `t${k++}` }, m[2]) : cloneElement(el, { key: `t${k++}` }))
    } else if (m[2] !== undefined) {
      out.push(m[2])
    }
    last = re.lastIndex
  }
  if (last < s.length) out.push(s.slice(last))
  return out
}
