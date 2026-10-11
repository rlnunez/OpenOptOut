// Finds names used but never defined or imported (e.g. an icon used in JSX
// without importing it). The build doesn't catch these; the screen crashes.
//   node scripts/check-names.mjs [srcDir]     exit 1 if any are found
import fs from 'node:fs'
import path from 'node:path'
import { parse } from '@babel/parser'
import _traverse from '@babel/traverse'
const traverse = _traverse.default || _traverse

const GLOBALS = new Set([...Object.getOwnPropertyNames(globalThis), ...`window document localStorage sessionStorage
  navigator location fetch console setTimeout clearTimeout setInterval clearInterval requestAnimationFrame
  cancelAnimationFrame alert confirm prompt URL URLSearchParams Blob File FileReader FormData Image HTMLElement Event
  CustomEvent KeyboardEvent MouseEvent AbortController TextEncoder TextDecoder crypto atob btoa performance history
  screen getComputedStyle matchMedia ResizeObserver IntersectionObserver MutationObserver PublicKeyCredential
  Notification structuredClone queueMicrotask process arguments undefined NaN Infinity globalThis self DOMParser
  XMLSerializer Audio WebSocket EventSource Worker indexedDB caches scrollTo open print innerWidth innerHeight
  devicePixelRatio Intl Option CSS ClipboardItem DataTransfer Response Request Headers`.split(/\s+/)])

const root = path.resolve(process.argv[2] || 'src')
const files = []
;(function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const f = path.join(d, e.name)
    if (e.isDirectory()) { if (e.name !== 'node_modules') walk(f) }
    else if (/\.(jsx?|mjs)$/.test(e.name)) files.push(f)
  }
})(root)

const problems = []
for (const f of files) {
  const ast = parse(fs.readFileSync(f, 'utf8'), { sourceType: 'module', plugins: ['jsx'] })
  traverse(ast, {
    ReferencedIdentifier(p) {
      const n = p.node.name
      if (p.node.type === 'JSXIdentifier' && !/^[A-Z]/.test(n)) return       // <div>, <span>
      if (p.parentPath.isJSXMemberExpression() && p.parentPath.node.property === p.node) return
      if (!p.scope.hasBinding(n) && !GLOBALS.has(n))
        problems.push(`${path.relative(root, f)}:${p.node.loc.start.line}  ${n} is used but never defined or imported`)
    },
  })
}
if (problems.length) {
  console.log([...new Set(problems)].join('\n'))
  process.exit(1)
}
console.log(`check-names: ${files.length} files, no undefined names`)
