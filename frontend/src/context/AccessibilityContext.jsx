import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../api'

const AccessibilityContext = createContext(null)

export function AccessibilityProvider({ children }) {
  // Theme state: 'light' | 'gray' | 'dark' | 'system'
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

  // Compute resolved theme ('light', 'gray', or 'dark')
  const resolvedTheme = theme === 'system'
    ? (systemPrefersDark ? 'dark' : 'light')
    : theme

  // Sync theme and high contrast classes to <html>
  useEffect(() => {
    const root = document.documentElement

    // Remove old theme classes
    root.classList.remove('theme-light', 'theme-gray', 'theme-dark')
    root.classList.add(`theme-${resolvedTheme}`)

    // Contrast classes
    root.classList.remove('a11y-high-contrast', 'a11y-high-contrast-light', 'a11y-high-contrast-dark')
    if (highContrast) {
      root.classList.add('a11y-high-contrast')
      if (resolvedTheme === 'light') {
        root.classList.add('a11y-high-contrast-light')
      } else {
        root.classList.add('a11y-high-contrast-dark')
      }
    }
  }, [resolvedTheme, highContrast])

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
          if (cfg.theme && ['light', 'gray', 'dark', 'system'].includes(cfg.theme)) {
            setThemeState(cfg.theme)
            localStorage.setItem('app_theme', cfg.theme)
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
    if (!['light', 'gray', 'dark', 'system'].includes(nextTheme)) return
    setThemeState(nextTheme)
    localStorage.setItem('app_theme', nextTheme)
    persistSettings({ theme: nextTheme })
    announce(`Theme switched to ${nextTheme}`)
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
    persistSettings({ high_contrast: next })
    announce(next ? 'High Contrast Mode enabled' : 'High Contrast Mode disabled')
  }

  const setDyslexicFont = (val) => {
    const next = Boolean(val)
    setDyslexicFontState(next)
    localStorage.setItem('a11y_dyslexic_font', String(next))
    persistSettings({ dyslexic_font: next })
    announce(next ? 'OpenDyslexic font enabled' : 'Default font restored')
  }

  const setReducedMotion = (val) => {
    const next = Boolean(val)
    setReducedMotionState(next)
    localStorage.setItem('a11y_reduced_motion', String(next))
    persistSettings({ reduced_motion: next })
    announce(next ? 'Reduced motion enabled' : 'Reduced motion disabled')
  }

  const setEnhancedTargets = (val) => {
    const next = Boolean(val)
    setEnhancedTargetsState(next)
    localStorage.setItem('a11y_enhanced_targets', String(next))
    persistSettings({ enhanced_targets: next })
    announce(next ? '44 pixel enhanced touch targets enabled' : 'Enhanced touch targets disabled')
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
