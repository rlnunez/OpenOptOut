import React from 'react'
import { useLanguage } from '../i18n/LanguageContext'

export default function SkipLink() {
  const { t } = useLanguage()

  const handleSkip = (e) => {
    e.preventDefault()
    const target = document.getElementById('main-content')
    if (target) {
      target.tabIndex = -1
      target.focus()
      target.scrollIntoView()
    }
  }

  return (
    <a
      href="#main-content"
      onClick={handleSkip}
      className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:px-4 focus:py-2.5 focus:bg-yellow-400 focus:text-black focus:font-extrabold focus:text-sm focus:rounded-md focus:shadow-2xl focus:ring-4 focus:ring-black focus:outline-hidden"
    >
      {t('a11y.skip_to_content', 'Skip to main content')}
    </a>
  )
}
