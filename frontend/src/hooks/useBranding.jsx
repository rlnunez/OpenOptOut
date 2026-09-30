import { createContext, useContext, useState, useEffect } from 'react'
import api from '../api'

const BrandingContext = createContext(null)

const DEFAULTS = {
  system_name:     'OpenOptOut',
  tagline:         'Your personal data removal service',
  primary_color:   '#6366f1',
  accent_color:    '#4f46e5',
  logo_url:        null,
  contact_email:   null,
  contact_phone:   null,
  support_url:     null,
  welcome_message: null,
  email_footer:    null,
  terms_url:       null,
  show_powered_by: true,
}

export function BrandingProvider({ children }) {
  const [branding, setBranding] = useState(DEFAULTS)
  const [banner,   setBanner]   = useState(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    // Load branding (public endpoint — no auth required for login page)
    api.get('/branding/config').then(r => {
      setBranding(r.data)
      applyColors(r.data)
    }).catch(() => {})

    api.get('/branding/banner').then(r => {
      if (r.data) setBanner(r.data)
    }).catch(() => {})
  }, [])

  const applyColors = (b) => {
    const root = document.documentElement
    root.style.setProperty('--color-primary',       b.primary_color || '#6366f1')
    root.style.setProperty('--color-accent',        b.accent_color  || '#4f46e5')
    // Update document title
    document.title = b.system_name || 'OpenOptOut'
  }

  const refresh = () => {
    api.get('/branding/config').then(r => { setBranding(r.data); applyColors(r.data) }).catch(() => {})
    api.get('/branding/banner').then(r => setBanner(r.data ? r.data : null)).catch(() => {})
  }

  return (
    <BrandingContext.Provider value={{ branding, setBranding, banner, setBanner, dismissed, setDismissed, refresh }}>
      {children}
    </BrandingContext.Provider>
  )
}

export const useBranding = () => useContext(BrandingContext)
