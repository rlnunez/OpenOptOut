import { useMemo } from 'react'

/**
 * Minimal, dependency-free Markdown renderer for the in-app plugin docs.
 *
 * Supports the subset our docs actually use: ATX headers (#..####), fenced
 * code blocks (``` ), inline code (`x`), bold (**x**), italic (*x* / _x_),
 * links [t](u), unordered/ordered lists, blockquotes (>), horizontal rules
 * (---), and GitHub-style pipe tables. Intentionally small — not a full
 * CommonMark implementation — and it escapes HTML so doc content can't inject
 * markup.
 */

// Quotes are escaped too: rendered text ends up inside attribute values (link
// hrefs), where an unescaped " would let content add its own attributes.
export function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const HTML_DECODE_MAP = {
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
}

// Link URLs: allow http(s), mailto, and relative/anchor links; anything else
// (javascript:, data:, vbscript:, ...) is rejected. Takes already-escaped text,
// so entities are decoded in a single pass before checking, and whitespace/control characters
// are stripped because browsers ignore them inside a scheme ("java\tscript:").
export function isSafeHref(escapedUrl) {
  const url = escapedUrl
    .replace(/&(?:amp|lt|gt|quot|#39);/g, m => HTML_DECODE_MAP[m] || m)
    .replace(/[\u0000- \u007f]/g, '')
    .toLowerCase()
  const scheme = url.match(/^([a-z][a-z0-9+.-]*):/)
  if (!scheme) return true            // relative URL or #anchor
  return ['http', 'https', 'mailto'].includes(scheme[1])
}

// [text](url) -> <a>, or just the text when the URL isn't allowed.
// Operates on already-escaped text.
export function renderLinks(t) {
  return t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) =>
    isSafeHref(url)
      ? `<a href="${url}" target="_blank" rel="noopener noreferrer" class="text-shield-400 hover:underline">${label}</a>`
      : label)
}

// Inline formatting: code, bold, italic, links. Operates on already-escaped text.
function renderInline(text) {
  let t = text
  // inline code first (protect its contents from other rules)
  const codeSpans = []
  t = t.replace(/`([^`]+)`/g, (_, c) => {
    codeSpans.push(c)
    return `\u0000CODE${codeSpans.length - 1}\u0000`
  })
  // links [text](url)
  t = renderLinks(t)
  // bold
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong class="text-slate-100 font-semibold">$1</strong>')
  // italic (avoid touching ** already handled; simple single * or _)
  t = t.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
  t = t.replace(/(^|[^_])_([^_\n]+)_(?!_)/g, '$1<em>$2</em>')
  // restore code spans
  t = t.replace(/\u0000CODE(\d+)\u0000/g, (_, i) =>
    `<code class="px-1 py-0.5 rounded bg-slate-800 border border-slate-700 text-[0.85em] text-shield-300 font-mono">${codeSpans[+i]}</code>`)
  return t
}

function mdToHtml(md) {
  const lines = md.replace(/\r\n/g, '\n').split('\n')
  const out = []
  let i = 0

  const flushParagraph = (buf) => {
    if (buf.length) {
      out.push(`<p class="text-slate-300 text-sm leading-relaxed my-2">${renderInline(buf.join(' '))}</p>`)
      buf.length = 0
    }
  }

  let paragraph = []

  while (i < lines.length) {
    let line = lines[i]

    // Fenced code block
    if (/^```/.test(line.trim())) {
      flushParagraph(paragraph)
      const fence = []
      i++
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        fence.push(escapeHtml(lines[i]))
        i++
      }
      i++ // skip closing fence
      out.push(
        `<pre class="my-3 p-3 rounded-lg bg-slate-900 border border-slate-700 overflow-x-auto"><code class="text-xs text-slate-300 font-mono whitespace-pre">${fence.join('\n')}</code></pre>`
      )
      continue
    }

    // Horizontal rule
    if (/^---+\s*$/.test(line)) {
      flushParagraph(paragraph)
      out.push('<hr class="my-4 border-slate-700/60" />')
      i++
      continue
    }

    // Headers
    const h = line.match(/^(#{1,4})\s+(.*)$/)
    if (h) {
      flushParagraph(paragraph)
      const level = h[1].length
      const cls = {
        1: 'text-white text-lg font-semibold mt-5 mb-2',
        2: 'text-white text-base font-semibold mt-5 mb-2',
        3: 'text-slate-100 text-sm font-semibold mt-4 mb-1.5',
        4: 'text-slate-200 text-sm font-medium mt-3 mb-1',
      }[level]
      out.push(`<h${level} class="${cls}">${renderInline(escapeHtml(h[2]))}</h${level}>`)
      i++
      continue
    }

    // Table (pipe table with a separator row)
    if (line.includes('|') && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes('-')) {
      flushParagraph(paragraph)
      const parseRow = (r) => r.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim())
      const headers = parseRow(line)
      i += 2 // skip header + separator
      const rows = []
      while (i < lines.length && lines[i].includes('|') && lines[i].trim() !== '') {
        rows.push(parseRow(lines[i]))
        i++
      }
      const thead = headers.map(c =>
        `<th class="text-left px-3 py-1.5 border-b border-slate-700 text-slate-300 font-medium">${renderInline(escapeHtml(c))}</th>`).join('')
      const tbody = rows.map(r =>
        `<tr>${r.map(c => `<td class="px-3 py-1.5 border-b border-slate-800 text-slate-400 align-top">${renderInline(escapeHtml(c))}</td>`).join('')}</tr>`).join('')
      out.push(`<div class="my-3 overflow-x-auto"><table class="w-full text-xs border-collapse"><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table></div>`)
      continue
    }

    // Blockquote
    if (/^>\s?/.test(line)) {
      flushParagraph(paragraph)
      const quote = []
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        quote.push(escapeHtml(lines[i].replace(/^>\s?/, '')))
        i++
      }
      out.push(`<blockquote class="my-3 pl-3 border-l-2 border-shield-700 text-slate-400 text-sm italic">${renderInline(quote.join(' '))}</blockquote>`)
      continue
    }

    // Lists (grouped)
    if (/^\s*([-*+]|\d+\.)\s+/.test(line)) {
      flushParagraph(paragraph)
      const ordered = /^\s*\d+\.\s+/.test(line)
      const items = []
      while (i < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[i])) {
        const item = lines[i].replace(/^\s*([-*+]|\d+\.)\s+/, '')
        items.push(`<li class="text-slate-300 text-sm my-0.5 ml-1">${renderInline(escapeHtml(item))}</li>`)
        i++
      }
      const tag = ordered ? 'ol' : 'ul'
      const listCls = ordered ? 'list-decimal' : 'list-disc'
      out.push(`<${tag} class="${listCls} pl-5 my-2 space-y-0.5">${items.join('')}</${tag}>`)
      continue
    }

    // Blank line ends a paragraph
    if (line.trim() === '') {
      flushParagraph(paragraph)
      i++
      continue
    }

    // Default: accumulate into paragraph
    paragraph.push(escapeHtml(line))
    i++
  }
  flushParagraph(paragraph)
  return out.join('\n')
}

export default function Markdown({ source }) {
  const html = useMemo(() => mdToHtml(source || ''), [source])
  // nosemgrep: typescript.react.security.audit.react-dangerouslysetinnerhtml.react-dangerouslysetinnerhtml
  return <div className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} /> // nosemgrep
}
