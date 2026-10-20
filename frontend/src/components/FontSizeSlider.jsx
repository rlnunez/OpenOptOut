import React from 'react'
import { Type } from 'lucide-react'
import { useAccessibility } from '../context/AccessibilityContext'
import { tx } from '../i18n/tx'

export default function FontSizeSlider({
  id = 'font-size-slider',
  color = 'shield', // 'shield' | 'blue'
  showIcon = true,
  showLabel = true,
  showPreview = false,
  className = '',
}) {
  const { fontSize, setFontSize } = useAccessibility()

  const handleKeyDown = (e) => {
    const isRtl = typeof document !== 'undefined' && document.documentElement.dir === 'rtl'
    const forwardKey = isRtl ? 'ArrowLeft' : 'ArrowRight'
    const backwardKey = isRtl ? 'ArrowRight' : 'ArrowLeft'

    if (e.key === 'ArrowUp' || e.key === forwardKey) {
      e.preventDefault()
      setFontSize(Math.min(150, fontSize + 5))
    } else if (e.key === 'ArrowDown' || e.key === backwardKey) {
      e.preventDefault()
      setFontSize(Math.max(100, fontSize - 5))
    } else if (e.key === 'PageUp') {
      e.preventDefault()
      setFontSize(Math.min(150, fontSize + 10))
    } else if (e.key === 'PageDown') {
      e.preventDefault()
      setFontSize(Math.max(100, fontSize - 10))
    } else if (e.key === 'Home') {
      e.preventDefault()
      setFontSize(100)
    } else if (e.key === 'End') {
      e.preventDefault()
      setFontSize(150)
    }
  }

  const isBlue = color === 'blue'
  const accentClass = isBlue ? 'accent-blue-500' : 'accent-shield-500'
  const textClass = isBlue ? 'text-blue-400' : 'text-shield-400'
  const focusRingClass = isBlue
    ? 'focus-visible:ring-blue-400'
    : 'focus-visible:ring-shield-400'

  const sizeTierLabel =
    fontSize <= 100
      ? tx("Default")
      : fontSize <= 120
      ? tx("Comfortable")
      : fontSize <= 135
      ? tx("Enhanced")
      : tx("AAA Large")

  return (
    <div className={`p-3.5 rounded-xl border border-slate-800 bg-slate-950/60 space-y-3 ${className}`}>
      {showLabel && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-white">
            {showIcon && <Type size={14} className={textClass} />}
            <label htmlFor={id} className="cursor-pointer">
              {tx("Font Size & Scaling")}
            </label>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`text-xs font-mono font-bold ${textClass}`}>{fontSize}%</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
              {sizeTierLabel}
            </span>
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        <input
          id={id}
          type="range"
          role="slider"
          min="100"
          max="150"
          step="5"
          value={fontSize}
          onChange={(e) => setFontSize(Number(e.target.value))}
          onKeyDown={handleKeyDown}
          aria-label={tx("Font Size & Scaling")}
          aria-valuemin="100"
          aria-valuemax="150"
          aria-valuenow={fontSize}
          aria-valuetext={`${fontSize}%`}
          aria-describedby={`${id}-hint`}
          className={`w-full h-2.5 bg-slate-800 rounded-lg appearance-none cursor-pointer ${accentClass} focus-visible:outline-hidden focus-visible:ring-2 ${focusRingClass} focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 transition-all`}
        />

        <div className="flex justify-between text-[10px] text-slate-400 font-mono px-0.5 select-none" aria-hidden="true">
          <span>100%</span>
          <span>115%</span>
          <span>125%</span>
          <span>135%</span>
          <span>150%</span>
        </div>
      </div>

      <p id={`${id}-hint`} className="text-[11px] text-slate-400 leading-normal">
        {tx("Use arrow keys to adjust in 5% increments.")}
      </p>

      {showPreview && (
        <div className="p-3 rounded-lg border border-slate-800/80 bg-slate-900/60 space-y-1">
          <p className="text-[11px] text-slate-400 font-medium uppercase tracking-wider">
            {tx("Live Preview")}
          </p>
          <p className="text-sm font-semibold text-white">
            {tx("Sample Heading (Scales with Slider)")}
          </p>
          <p className="text-xs text-slate-300">
            {tx("This text previews your selected font size in real time. All tables, forms, and menus adjust proportionally across OpenOptOut.")}
          </p>
        </div>
      )}
    </div>
  )
}
