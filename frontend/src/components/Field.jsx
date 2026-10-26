import React from 'react'

/** Standard styled input class used across forms */
export const inputCls = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"

/** Standard label styling class used across forms */
export const labelCls = "text-slate-400 text-xs mb-1 block"

/**
 * Standard form field wrapper with label, required asterisk, and optional hint.
 */
export default function Field({ id, label, required, hint, children, className = '' }) {
  return (
    <div className={className}>
      {label && (
        <label htmlFor={id} className="text-slate-400 text-xs mb-1 block">
          {label}
          {required && <span className="text-red-400 ms-1">*</span>}
        </label>
      )}
      {children}
      {hint && <p className="text-slate-500 text-xs mt-1">{hint}</p>}
    </div>
  )
}
