import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../api'
import { tx } from '../i18n/tx'

const AccessibilityContext = createContext(null)

export function AccessibilityProvider({ children }) {
  // Theme state: 'light' | 'gray' | 'dark' | 'system' | 'space'
  const [theme, setThemeState] = useState(() => {
    const saved = localStorage.getItem('app_theme')
    if (saved === 'lcars') {
      localStorage.setItem('app_theme', 'space')
      return 'space'
    }
    return saved || 'dark'
  })

  // System OS color scheme listener
  const [systemPrefersDark, setSystemPrefersDark] = useState(() => {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia('(prefers-color-scheme: dark)').matches
    }
    return true
  })

  // High contrast mode
  const [highContrast, setHighContrastState] = useState(() => {
    return localStorage.getItem('a11y_high_contrast') === 'true'
  })

  // Dyslexia-friendly font (OpenDyslexic)
  const [dyslexicFont, setDyslexicFontState] = useState(() => {
    return localStorage.getItem('a11y_dyslexic_font') === 'true'
  })

  // Font size scaling (100% to 150%)
  const [fontSize, setFontSizeState] = useState(() => {
    const saved = localStorage.getItem('a11y_font_size')
    return saved ? parseInt(saved, 10) : 100
  })

  const [reducedMotion, setReducedMotionState] = useState(() => {
    return localStorage.getItem('a11y_reduced_motion') === 'true'
  })

  const [enhancedTargets, setEnhancedTargetsState] = useState(() => {
    return localStorage.getItem('a11y_enhanced_targets') === 'true'
  })

  const [announcement, setAnnouncement] = useState('')

  // Watch system color scheme changes
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e) => setSystemPrefersDark(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  // Compute base theme ('light', 'gray', 'dark', 'space') and ADA compliance flag
  const isAda = highContrast || (typeof theme === 'string' && theme.endsWith('-ada'))
  let baseTheme = theme
  if (theme === 'dark-ada') baseTheme = 'dark'
  else if (theme === 'light-ada') baseTheme = 'light'
  else if (theme === 'space-ada') baseTheme = 'space'
  else if (theme === 'system') {
    baseTheme = systemPrefersDark ? 'dark' : 'light'
  }
  const resolvedTheme = baseTheme

  // Sync theme and contrast classes to <html>
  useEffect(() => {
    const root = document.documentElement

    // Remove old theme classes
    root.classList.remove(
      'theme-light', 'theme-light-ada',
      'theme-gray',
      'theme-dark', 'theme-dark-ada',
      'theme-space', 'theme-space-ada', 'theme-lcars'
    )
    root.classList.add(`theme-${baseTheme}`)
    if (baseTheme === 'space') {
      root.classList.add('theme-lcars')
    }
    if (isAda) {
      root.classList.add(`theme-${baseTheme}-ada`)
    }

    // Contrast classes: global a11y-high-contrast plus variant-specific class
    root.classList.remove(
      'a11y-high-contrast',
      'a11y-high-contrast-light',
      'a11y-high-contrast-dark',
      'a11y-high-contrast-space'
    )
    if (isAda) {
      root.classList.add('a11y-high-contrast')
      if (baseTheme === 'light') {
        root.classList.add('a11y-high-contrast-light')
      } else if (baseTheme === 'space') {
        root.classList.add('a11y-high-contrast-space')
      } else {
        root.classList.add('a11y-high-contrast-dark')
      }
    }
  }, [baseTheme, isAda])

  // Sync font size variable and large-text flag
  useEffect(() => {
    const root = document.documentElement
    root.style.setProperty('--a11y-font-size', `${fontSize}%`)
    if (fontSize > 115) {
      root.classList.add('a11y-large-text')
    } else {
      root.classList.remove('a11y-large-text')
    }
  }, [fontSize])

  // Sync reduced motion
  useEffect(() => {
    const root = document.documentElement
    if (reducedMotion) {
      root.classList.add('a11y-reduced-motion')
    } else {
      root.classList.remove('a11y-reduced-motion')
    }
  }, [reducedMotion])

  // Sync enhanced targets
  useEffect(() => {
    const root = document.documentElement
    if (enhancedTargets) {
      root.classList.add('a11y-enhanced-targets')
    } else {
      root.classList.remove('a11y-enhanced-targets')
    }
  }, [enhancedTargets])

  // Sync dyslexic font
  useEffect(() => {
    const root = document.documentElement
    if (dyslexicFont) {
      root.classList.add('a11y-dyslexic-font')
    } else {
      root.classList.remove('a11y-dyslexic-font')
    }
  }, [dyslexicFont])

  // Fetch saved user preferences on login
  useEffect(() => {
    api.get('/i18n/user/preference')
      .then(res => {
        if (res.data?.accessibility_settings) {
          const cfg = res.data.accessibility_settings
          if (cfg.theme) {
            const normalized = cfg.theme === 'lcars' ? 'space' : cfg.theme
            if (['light', 'light-ada', 'gray', 'dark', 'dark-ada', 'system', 'space', 'space-ada'].includes(normalized)) {
              setThemeState(normalized)
              localStorage.setItem('app_theme', normalized)
            }
          }
          if (typeof cfg.high_contrast === 'boolean') {
            setHighContrastState(cfg.high_contrast)
            localStorage.setItem('a11y_high_contrast', String(cfg.high_contrast))
          }
          if (typeof cfg.dyslexic_font === 'boolean') {
            setDyslexicFontState(cfg.dyslexic_font)
            localStorage.setItem('a11y_dyslexic_font', String(cfg.dyslexic_font))
          }
          if (typeof cfg.font_size === 'number') {
            setFontSizeState(cfg.font_size)
            localStorage.setItem('a11y_font_size', String(cfg.font_size))
          }
          if (typeof cfg.reduced_motion === 'boolean') {
            setReducedMotionState(cfg.reduced_motion)
            localStorage.setItem('a11y_reduced_motion', String(cfg.reduced_motion))
          }
          if (typeof cfg.enhanced_targets === 'boolean') {
            setEnhancedTargetsState(cfg.enhanced_targets)
            localStorage.setItem('a11y_enhanced_targets', String(cfg.enhanced_targets))
          }
        }
      })
      .catch(() => {})
  }, [])

  const persistSettings = useCallback(async (updates) => {
    const full = {
      theme: updates.theme ?? theme,
      high_contrast: updates.high_contrast ?? highContrast,
      dyslexic_font: updates.dyslexic_font ?? dyslexicFont,
      font_size: updates.font_size ?? fontSize,
      reduced_motion: updates.reduced_motion ?? reducedMotion,
      enhanced_targets: updates.enhanced_targets ?? enhancedTargets,
    }
    try {
      await api.post('/i18n/user/preference', { accessibility_settings: full })
    } catch (e) {
      // Non-fatal if offline
    }
  }, [theme, highContrast, dyslexicFont, fontSize, reducedMotion, enhancedTargets])

  const setTheme = (nextTheme) => {
    const target = nextTheme === 'lcars' ? 'space' : nextTheme
    const valid = ['light', 'light-ada', 'gray', 'dark', 'dark-ada', 'system', 'space', 'space-ada']
    if (!valid.includes(target)) return
    setThemeState(target)
    localStorage.setItem('app_theme', target)

    const isTargetAda = target.endsWith('-ada')
    if (isTargetAda) {
      setHighContrastState(true)
      localStorage.setItem('a11y_high_contrast', 'true')
      persistSettings({ theme: target, high_contrast: true })
    } else if (target === 'dark' || target === 'light' || target === 'space' || target === 'gray') {
      setHighContrastState(false)
      localStorage.setItem('a11y_high_contrast', 'false')
      persistSettings({ theme: target, high_contrast: false })
    } else {
      persistSettings({ theme: target })
    }

    const themeNames = {
      'space': tx("Space Explorer"),
      'space-ada': tx("Space Explorer (ADA Compliant)"),
      'dark': tx("Dark"),
      'dark-ada': tx("Dark (ADA Compliant)"),
      'light': tx("Light"),
      'light-ada': tx("Light (ADA Compliant)"),
      'gray': tx("Gray"),
      'system': tx("System"),
    }
    announce(`Theme switched to ${themeNames[target] || target}`)
  }

  const setFontSize = (size) => {
    const num = Math.min(150, Math.max(100, Math.round(Number(size))))
    setFontSizeState(num)
    localStorage.setItem('a11y_font_size', String(num))
    persistSettings({ font_size: num })
  }

  const setHighContrast = (val) => {
    const next = Boolean(val)
    setHighContrastState(next)
    localStorage.setItem('a11y_high_contrast', String(next))

    let nextTheme = theme
    if (next) {
      if (theme === 'dark') nextTheme = 'dark-ada'
      else if (theme === 'light') nextTheme = 'light-ada'
      else if (theme === 'space') nextTheme = 'space-ada'
    } else {
      if (theme === 'dark-ada') nextTheme = 'dark'
      else if (theme === 'light-ada') nextTheme = 'light'
      else if (theme === 'space-ada') nextTheme = 'space'
    }

    if (nextTheme !== theme) {
      setThemeState(nextTheme)
      localStorage.setItem('app_theme', nextTheme)
      persistSettings({ theme: nextTheme, high_contrast: next })
    } else {
      persistSettings({ high_contrast: next })
    }

    announce(next ? tx("High Contrast Mode enabled") : tx("High Contrast Mode disabled"))
  }

  const setDyslexicFont = (val) => {
    const next = Boolean(val)
    setDyslexicFontState(next)
    localStorage.setItem('a11y_dyslexic_font', String(next))
    persistSettings({ dyslexic_font: next })
    announce(next ? tx("OpenDyslexic font enabled") : tx("Default font restored"))
  }

  const setReducedMotion = (val) => {
    const next = Boolean(val)
    setReducedMotionState(next)
    localStorage.setItem('a11y_reduced_motion', String(next))
    persistSettings({ reduced_motion: next })
    announce(next ? tx("Reduced motion enabled") : tx("Reduced motion disabled"))
  }

  const setEnhancedTargets = (val) => {
    const next = Boolean(val)
    setEnhancedTargetsState(next)
    localStorage.setItem('a11y_enhanced_targets', String(next))
    persistSettings({ enhanced_targets: next })
    announce(next ? tx("44 pixel enhanced touch targets enabled") : tx("Enhanced touch targets disabled"))
  }

  const announce = (message) => {
    if (!message) return
    setAnnouncement('')
    setTimeout(() => {
      setAnnouncement(message)
    }, 50)
  }

  return (
    <AccessibilityContext.Provider value={{
      theme,
      resolvedTheme,
      setTheme,
      highContrast,
      setHighContrast,
      dyslexicFont,
      setDyslexicFont,
      fontSize,
      setFontSize,
      reducedMotion,
      setReducedMotion,
      enhancedTargets,
      setEnhancedTargets,
      announce,
    }}>
      {children}
      <div
        id="a11y-live-announcer"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        style={{
          position: 'absolute',
          width: '1px',
          height: '1px',
          padding: 0,
          margin: '-1px',
          overflow: 'hidden',
          clip: 'rect(0, 0, 0, 0)',
          whiteSpace: 'nowrap',
          border: 0,
        }}
      >
        {announcement}
      </div>
    </AccessibilityContext.Provider>
  )
}

export function useAccessibility() {
  const ctx = useContext(AccessibilityContext)
  if (!ctx) {
    return {
      theme: 'dark',
      resolvedTheme: 'dark',
      setTheme: () => {},
      highContrast: false,
      setHighContrast: () => {},
      dyslexicFont: false,
      setDyslexicFont: () => {},
      fontSize: 100,
      setFontSize: () => {},
      reducedMotion: false,
      setReducedMotion: () => {},
      enhancedTargets: false,
      setEnhancedTargets: () => {},
      announce: () => {},
    }
  }
  return ctx
}
