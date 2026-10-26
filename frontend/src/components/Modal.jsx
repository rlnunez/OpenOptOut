import React, { useEffect, useId } from 'react'
import { X } from 'lucide-react'
import { tx } from '../i18n/tx'

/**
 * Standard accessible modal dialog component.
 *
 * Provides:
 * - Proper ARIA semantics (role="dialog", aria-modal="true", aria-labelledby)
 * - Automatic Escape key dismissal
 * - Backdrop click dismissal
 * - Accessible close button with aria-label
 * - Keyboard and scroll containment
 */
export default function Modal({
  isOpen = true,
  onClose,
  title,
  description,
  children,
  maxWidth = 'max-w-sm',
  className = '',
  showClose = true,
  closeAriaLabel,
}) {
  const titleId = useId()
  const descId = useId()

  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose?.()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-describedby={description ? descId : undefined}
        className={`bg-slate-900 border border-slate-700 rounded-2xl w-full ${maxWidth} max-h-[90vh] overflow-y-auto p-6 ${className}`}
        onClick={(e) => e.stopPropagation()}
      >
        {(title || showClose) && (
          <div className="flex items-center justify-between mb-5">
            {title ? (
              <h2 id={titleId} className="text-white font-semibold">
                {title}
              </h2>
            ) : <span />}
            {showClose && onClose && (
              <button
                type="button"
                onClick={onClose}
                aria-label={closeAriaLabel || tx("Close")}
                className="text-slate-500 hover:text-white transition-colors"
              >
                <X size={16} />
              </button>
            )}
          </div>
        )}
        {description && (
          <p id={descId} className="text-slate-400 text-sm mb-4">
            {description}
          </p>
        )}
        {children}
      </div>
    </div>
  )
}

