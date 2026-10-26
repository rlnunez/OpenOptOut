import React, { useId } from 'react'

/** Standard styled input class used across forms */
export const inputCls = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"

/** Standard label styling class used across forms */
export const labelCls = "text-slate-400 text-xs mb-1 block"

function attachLabel(node, labelText, fieldId) {
  if (!React.isValidElement(node)) return node
  const isInput = node.type === 'input' || node.type === 'select' || node.type === 'textarea'
  if (isInput) {
    return React.cloneElement(node, {
      id: node.props.id || fieldId,
      'aria-label': node.props['aria-label'] || (typeof labelText === 'string' ? labelText : undefined),
    })
  }
  if (node.props && node.props.children) {
    if (React.isValidElement(node.props.children)) {
      return React.cloneElement(node, {
        children: attachLabel(node.props.children, labelText, fieldId),
      })
    }
    if (Array.isArray(node.props.children)) {
      let attached = false
      const mapped = node.props.children.map(child => {
        if (!attached && React.isValidElement(child) && (child.type === 'input' || child.type === 'select' || child.type === 'textarea')) {
          attached = true
          return attachLabel(child, labelText, fieldId)
        }
        return child
      })
      if (attached) {
        return React.cloneElement(node, { children: mapped })
      }
    }
  }
  return node
}

/**
 * Standard form field wrapper with label, required asterisk, and optional hint.
 * Automatically wires htmlFor/id and accessible aria-label to nested input/select/textarea controls.
 */
export default function Field({ id: explicitId, label, required, hint, children, className = '' }) {
  const generatedId = useId()
  const fieldId = explicitId || (label ? `fld-${generatedId.replace(/:/g, '')}` : undefined)
  const labeledChildren = label ? attachLabel(children, label, fieldId) : children

  return (
    <div className={className}>
      {label && (
        <label htmlFor={fieldId} className="text-slate-400 text-xs mb-1 block">
          {label}
          {required && <span className="text-red-400 ms-1">*</span>}
        </label>
      )}
      {labeledChildren}
      {hint && <p className="text-slate-500 text-xs mt-1">{hint}</p>}
    </div>
  )
}
