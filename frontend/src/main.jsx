import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource/opendyslexic/400.css'
import '@fontsource/opendyslexic/700.css'
import '@fontsource/antonio/400.css'
import '@fontsource/antonio/700.css'
import './index.css'
import { loadTable } from './i18n/tx'
import { loadRegional } from './i18n/format'

// The language's text is loaded first, so every screen (and every list a
// module builds when it loads) comes up in that language.
let lang = 'en'
try { lang = localStorage.getItem('preferred_language') || 'en' } catch { /* private mode */ }

Promise.allSettled([loadTable(lang), loadRegional()]).finally(async () => {
  const { default: App } = await import('./App')
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode><App /></React.StrictMode>
  )
})
