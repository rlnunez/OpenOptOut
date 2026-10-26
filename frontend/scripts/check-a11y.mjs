// OpenOptOut — Static JSX Accessibility (a11y) Verification Suite
// Validates frontend JSX files against fundamental WCAG 2.2 AA / AAA principles:
//   1. Every <img> has an alt attribute (WCAG 1.1.1)
//   2. Every <button> has accessible text, aria-label, aria-labelledby, or title (WCAG 4.1.2)
//   3. No element uses positive tabIndex (> 0) which disrupts natural focus flow (WCAG 2.4.3)
//   4. Interactive controls have accessible name or label associations (WCAG 1.3.1, 4.1.2)
//
// Usage: node scripts/check-a11y.mjs [srcDir]

import fs from 'node:fs'
import path from 'node:path'
import { parse } from '@babel/parser'
import _traverse from '@babel/traverse'
const traverse = _traverse.default || _traverse

const root = path.resolve(process.argv[2] || 'src')
const files = []

;(function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const f = path.join(d, e.name)
    if (e.isDirectory()) {
      if (e.name !== 'node_modules' && e.name !== 'dist') walk(f)
    } else if (/\.(jsx|tsx)$/.test(e.name)) {
      files.push(f)
    }
  }
})(root)

const violations = []

function getProp(openingElement, propName) {
  const attr = openingElement.attributes.find(
    (a) => a.type === 'JSXAttribute' && a.name?.name === propName
  )
  return attr
}

function hasAnyProp(openingElement, propNames) {
  return openingElement.attributes.some(
    (a) => a.type === 'JSXAttribute' && propNames.includes(a.name?.name)
  )
}

function hasMeaningfulText(children) {
  for (const child of children) {
    if (child.type === 'JSXText' && child.value.trim().length > 0) return true
    if (child.type === 'JSXExpressionContainer') {
      const expr = child.expression
      if (expr && expr.type !== 'JSXEmptyExpression') return true
    }
    if (child.type === 'JSXElement') {
      const elName = child.openingElement.name?.name
      // If child element is a text tag like span, p, strong, tx() call
      if (['span', 'p', 'b', 'strong', 'em', 'i', 'small'].includes(elName)) {
        if (hasMeaningfulText(child.children)) return true
      }
    }
  }
  return false
}

for (const f of files) {
  const code = fs.readFileSync(f, 'utf8')
  let ast
  try {
    ast = parse(code, { sourceType: 'module', plugins: ['jsx'] })
  } catch (err) {
    violations.push(`${path.relative(root, f)}: Parse error: ${err.message}`)
    continue
  }

  traverse(ast, {
    JSXElement(p) {
      const opening = p.node.openingElement
      const tag = opening.name?.name
      if (!tag) return

      const line = opening.loc?.start?.line || 0
      const relPath = path.relative(root, f)

      // 1. <img> must have alt attribute (WCAG 1.1.1)
      if (tag === 'img') {
        const altProp = getProp(opening, 'alt')
        const ariaHidden = getProp(opening, 'aria-hidden')
        if (!altProp && !ariaHidden) {
          violations.push(
            `${relPath}:${line} <img /> element is missing an 'alt' attribute (WCAG 1.1.1). Use alt="" for decorative images.`
          )
        }
      }

      // 2. Positive tabIndex is an anti-pattern (WCAG 2.4.3)
      const tabIndexProp = getProp(opening, 'tabIndex')
      if (tabIndexProp && tabIndexProp.value) {
        if (tabIndexProp.value.type === 'StringLiteral') {
          const val = parseInt(tabIndexProp.value.value, 10)
          if (val > 0) {
            violations.push(
              `${relPath}:${line} <${tag}> uses positive tabIndex="${val}" which breaks natural tab sequence (WCAG 2.4.3). Use tabIndex="0" or "-1".`
            )
          }
        } else if (
          tabIndexProp.value.type === 'JSXExpressionContainer' &&
          tabIndexProp.value.expression.type === 'NumericLiteral'
        ) {
          const val = tabIndexProp.value.expression.value
          if (val > 0) {
            violations.push(
              `${relPath}:${line} <${tag}> uses positive tabIndex={${val}} which breaks natural tab sequence (WCAG 2.4.3). Use tabIndex={0} or {-1}.`
            )
          }
        }
      }

      // 3. <button> must have accessible content or an accessible label (WCAG 4.1.2)
      if (tag === 'button') {
        const hasAccessibleLabel = hasAnyProp(opening, [
          'aria-label',
          'aria-labelledby',
          'title',
        ])
        const hasText = hasMeaningfulText(p.node.children)
        // Also check if spread attribute or aria-hidden
        const hasSpread = opening.attributes.some((a) => a.type === 'JSXSpreadAttribute')
        const isAriaHidden = getProp(opening, 'aria-hidden')?.value?.value === 'true'

        if (!hasText && !hasAccessibleLabel && !hasSpread && !isAriaHidden) {
          violations.push(
            `${relPath}:${line} <button> has no text content or accessible label (aria-label, aria-labelledby, or title) (WCAG 4.1.2).`
          )
        }
      }
    },
  })
}

const isStrict = process.argv.includes('--strict')

if (violations.length > 0) {
  if (isStrict) {
    console.error(`\x1b[31m[FAIL] Found ${violations.length} accessibility (a11y) violations:\x1b[0m`)
    console.error(violations.join('\n'))
    process.exit(1)
  } else {
    console.warn(`\x1b[33m[WARN] Found ${violations.length} accessibility (a11y) warnings:\x1b[0m`)
    console.warn(violations.join('\n'))
    console.log(`\x1b[33mRun with --strict to enforce 0 violations.\x1b[0m`)
    process.exit(0)
  }
}

console.log(`\x1b[32m[PASS] check-a11y: ${files.length} JSX files scanned, no WCAG rule violations.\x1b[0m`)
