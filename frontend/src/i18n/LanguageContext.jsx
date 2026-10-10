import React, { createContext, useContext, useState, useEffect } from 'react'
import api from '../api'

const LanguageContext = createContext(null)

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(() => localStorage.getItem('preferred_language') || 'en')
  const [isRTL, setIsRTL] = useState(false)
  const [translations, setTranslations] = useState({})
  const [availableLanguages, setAvailableLanguages] = useState([
    { code: 'en', name: 'English', native_name: 'English', is_rtl: false, enabled: true },
    { code: 'es', name: 'Spanish', native_name: 'Español', is_rtl: false, enabled: true },
    { code: 'ar', name: 'Arabic', native_name: 'العربية', is_rtl: true, enabled: true },
    { code: 'fr', name: 'French', native_name: 'Français', is_rtl: false, enabled: true },
    { code: 'pirate', name: 'Pirate', native_name: 'Pirate (Ahoy!)', is_rtl: false, enabled: true },
  ])
  const [showWelcomeTour, setShowWelcomeTour] = useState(false)
  const [loading, setLoading] = useState(true)

  // Load available languages from server
  const fetchLanguages = async () => {
    try {
      const res = await api.get('/i18n/languages')
      if (Array.isArray(res.data) && res.data.length > 0) {
        setAvailableLanguages(res.data)
      }
    } catch (e) {
      console.warn('Failed loading language list from server, using defaults', e)
    }
  }

  // Load translation strings for active language
  const loadTranslations = async (code) => {
    try {
      const res = await api.get(`/i18n/translations/${code}`)
      if (res.data?.translations) {
        setTranslations(res.data.translations)
        setIsRTL(Boolean(res.data.is_rtl))
        document.documentElement.dir = res.data.is_rtl ? 'rtl' : 'ltr'
        document.documentElement.lang = code
      }
    } catch (e) {
      console.warn(`Failed loading translations for ${code}`, e)
    }
  }

  // On initial mount
  useEffect(() => {
    fetchLanguages()
    const storedLang = localStorage.getItem('preferred_language') || 'en'
    setLanguageState(storedLang)
    loadTranslations(storedLang).finally(() => setLoading(false))

    // Check user preference if authenticated
    api.get('/i18n/user/preference')
      .then(res => {
        if (res.data?.preferred_language) {
          const userLang = res.data.preferred_language
          setLanguageState(userLang)
          localStorage.setItem('preferred_language', userLang)
          loadTranslations(userLang)
        }
        if (res.data && !res.data.tutorial_completed) {
          setShowWelcomeTour(true)
        }
      })
      .catch(() => {
        // Unauthenticated or not yet loaded; ignore
      })
  }, [])

  // Switch language on the fly
  const setLanguage = async (code) => {
    const target = code.toLowerCase().trim()
    setLanguageState(target)
    localStorage.setItem('preferred_language', target)
    await loadTranslations(target)

    // Save to user profile if logged in
    try {
      await api.post('/i18n/user/preference', { language: target })
    } catch (e) {
      // Non-fatal if offline/guest
    }
  }

  // Translation function: t('key', 'Fallback message', { param: 'value' })
  const t = (key, fallback = '', vars = {}) => {
    let str = translations[key] ?? fallback ?? key
    if (typeof str !== 'string') return String(str)
    if (vars && typeof vars === 'object') {
      Object.entries(vars).forEach(([k, v]) => {
        str = str.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
      })
    }
    return str
  }

  const completeWelcomeTour = async () => {
    setShowWelcomeTour(false)
    try {
      await api.post('/i18n/user/tutorial-complete')
    } catch (e) {
      // Non-fatal
    }
  }

  return (
    <LanguageContext.Provider value={{
      language,
      isRTL,
      setLanguage,
      availableLanguages: availableLanguages.filter(l => l.enabled),
      allLanguages: availableLanguages,
      refreshLanguages: fetchLanguages,
      translations,
      t,
      showWelcomeTour,
      setShowWelcomeTour,
      completeWelcomeTour,
      loading
    }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) {
    throw new Error('useLanguage must be used within a LanguageProvider')
  }
  return ctx
}
