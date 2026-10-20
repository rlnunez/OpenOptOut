import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import api from '../api'
import { tx } from '../i18n/tx'

const AccessibilityContext = createContext(null)

export function AccessibilityProvider({ children }) {
  // Theme state: 'light' | 'gray' | 'dark' | 'system' | 'space'
  const [theme, setThemeState] = useState(() => {
    return localStorage.getItem('app_theme') || 'dark'
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

  // Font size scaling (100% to 150% in 5% increments)
  const [fontSize, setFontSizeState] = useState(() => {
    const saved = localStorage.getItem('a11y_font_size')
    if (saved) {
      const parsed = parseInt(saved, 10)
      if (!isNaN(parsed)) {
        return Math.min(150, Math.max(100, Math.round(parsed / 5) * 5))
      }
    }
    return 100
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
  const isAda = Boolean(highContrast || (typeof theme === 'string' && theme.endsWith('-ada')))
  let baseTheme = theme
  if (typeof theme === 'string' && theme.endsWith('-ada')) {
    baseTheme = theme.replace(/-ada$/, '')
  } else if (theme === 'system') {
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
      'theme-space', 'theme-space-ada'
    )
    root.classList.add(`theme-${baseTheme}`)
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

  // Fresh ref tracking settings to avoid stale closures in callbacks
  const settingsRef = useRef({
    theme,
    highContrast,
    dyslexicFont,
    fontSize,
    reducedMotion,
    enhancedTargets,
  })
  useEffect(() => {
    settingsRef.current = {
      theme,
      highContrast,
      dyslexicFont,
      fontSize,
      reducedMotion,
      enhancedTargets,
    }
  }, [theme, highContrast, dyslexicFont, fontSize, reducedMotion, enhancedTargets])

  // Synchronize and apply incoming preferences
  const applySettings = useCallback((cfg) => {
    if (!cfg || typeof cfg !== 'object') return
    let nextTheme = cfg.theme
    let nextHighContrast = cfg.high_contrast

    // Reconcile theme and high contrast so they can never contradict
    if (typeof nextHighContrast === 'boolean') {
      if (nextHighContrast) {
        if (nextTheme === 'light' || nextTheme === 'light-ada') nextTheme = 'light-ada'
        else if (nextTheme === 'space' || nextTheme === 'space-ada') nextTheme = 'space-ada'
        else nextTheme = 'dark-ada'
      } else {
        if (typeof nextTheme === 'string' && nextTheme.endsWith('-ada')) {
          nextTheme = nextTheme.replace(/-ada$/, '')
        }
      }
    } else if (typeof nextTheme === 'string') {
      nextHighContrast = nextTheme.endsWith('-ada')
    }

    if (nextTheme && ['light', 'light-ada', 'gray', 'dark', 'dark-ada', 'system', 'space', 'space-ada'].includes(nextTheme)) {
      setThemeState(nextTheme)
      localStorage.setItem('app_theme', nextTheme)
    }
    if (typeof nextHighContrast === 'boolean') {
      setHighContrastState(nextHighContrast)
      localStorage.setItem('a11y_high_contrast', String(nextHighContrast))
    }
    if (typeof cfg.dyslexic_font === 'boolean') {
      setDyslexicFontState(cfg.dyslexic_font)
      localStorage.setItem('a11y_dyslexic_font', String(cfg.dyslexic_font))
    }
    if (typeof cfg.font_size === 'number') {
      const num = Math.min(150, Math.max(100, Math.round(cfg.font_size / 5) * 5))
      setFontSizeState(num)
      localStorage.setItem('a11y_font_size', String(num))
    }
    if (typeof cfg.reduced_motion === 'boolean') {
      setReducedMotionState(cfg.reduced_motion)
      localStorage.setItem('a11y_reduced_motion', String(cfg.reduced_motion))
    }
    if (typeof cfg.enhanced_targets === 'boolean') {
      setEnhancedTargetsState(cfg.enhanced_targets)
      localStorage.setItem('a11y_enhanced_targets', String(cfg.enhanced_targets))
    }
  }, [])

  // Fetch saved user preferences on mount and auth changes
  const fetchUserPreferences = useCallback(() => {
    api.get('/i18n/user/preference')
      .then(res => {
        if (res.data?.accessibility_settings) {
          applySettings(res.data.accessibility_settings)
        }
      })
      .catch(() => {})
  }, [applySettings])

  useEffect(() => {
    fetchUserPreferences()
    window.addEventListener('auth-changed', fetchUserPreferences)
    return () => window.removeEventListener('auth-changed', fetchUserPreferences)
  }, [fetchUserPreferences])

  const persistSettings = useCallback(async (updates = {}) => {
    const current = settingsRef.current
    const full = {
      theme: updates.theme ?? current.theme,
      high_contrast: updates.high_contrast ?? current.highContrast,
      dyslexic_font: updates.dyslexic_font ?? current.dyslexicFont,
      font_size: updates.font_size ?? current.fontSize,
      reduced_motion: updates.reduced_motion ?? current.reducedMotion,
      enhanced_targets: updates.enhanced_targets ?? current.enhancedTargets,
    }
    try {
      await api.post('/i18n/user/preference', { accessibility_settings: full })
    } catch (e) {
      // Non-fatal if offline
    }
  }, [])

  const setTheme = (nextTheme) => {
    const target = nextTheme
    const valid = ['light', 'light-ada', 'gray', 'dark', 'dark-ada', 'system', 'space', 'space-ada']
    if (!valid.includes(target)) return

    const isTargetAda = target.endsWith('-ada')
    setThemeState(target)
    localStorage.setItem('app_theme', target)
    setHighContrastState(isTargetAda)
    localStorage.setItem('a11y_high_contrast', String(isTargetAda))

    persistSettings({ theme: target, high_contrast: isTargetAda })

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
    const num = Math.min(150, Math.max(100, Math.round(Number(size) / 5) * 5))
    setFontSizeState(num)
    localStorage.setItem('a11y_font_size', String(num))
    persistSettings({ font_size: num })
    announce(`Font size set to ${num}%`)
  }

  const setHighContrast = (val) => {
    const next = Boolean(val)
    setHighContrastState(next)
    localStorage.setItem('a11y_high_contrast', String(next))

    const currentTheme = settingsRef.current.theme || theme
    let nextTheme = currentTheme
    if (next) {
      if (currentTheme === 'light' || currentTheme === 'light-ada') nextTheme = 'light-ada'
      else if (currentTheme === 'space' || currentTheme === 'space-ada') nextTheme = 'space-ada'
      else nextTheme = 'dark-ada'
    } else {
      if (typeof currentTheme === 'string' && currentTheme.endsWith('-ada')) {
        nextTheme = currentTheme.replace(/-ada$/, '')
      } else if (!['light', 'dark', 'space', 'gray', 'system'].includes(currentTheme)) {
        nextTheme = 'dark'
      }
    }

    setThemeState(nextTheme)
    localStorage.setItem('app_theme', nextTheme)
    persistSettings({ theme: nextTheme, high_contrast: next })

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
