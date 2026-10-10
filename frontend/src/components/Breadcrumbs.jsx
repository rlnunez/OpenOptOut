import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ChevronRight, Home } from 'lucide-react'
import { useLanguage } from '../i18n/LanguageContext'

export default function Breadcrumbs() {
  const location = useLocation()
  const { t, isRTL } = useLanguage()

  const pathname = location.pathname

  // Build breadcrumb items based on current pathname
  const getCrumbs = () => {
    const homeCrumb = { label: t('nav.dashboard', 'Dashboard'), to: '/' }

    if (pathname === '/' || pathname === '') {
      return [homeCrumb]
    }

    const segments = {
      '/brokers': [{ label: t('nav.brokers', 'Data Brokers'), to: '/brokers' }],
      '/brokers/add': [
        { label: t('nav.brokers', 'Data Brokers'), to: '/brokers' },
        { label: t('common.add_broker', 'Add Broker'), to: '/brokers/add' },
      ],
      '/email': [{ label: t('nav.email_monitor', 'Email Monitor'), to: '/email' }],
      '/scheduled': [{ label: t('nav.scheduled', 'Scheduled Tasks'), to: '/scheduled' }],
      '/discovery': [{ label: t('nav.discovery', 'Discovery'), to: '/discovery' }],
      '/captcha': [{ label: t('nav.captcha', 'CAPTCHA Queue'), to: '/captcha' }],
      '/family': [{ label: t('nav.family', 'Family Members'), to: '/family' }],
      '/identity': [{ label: t('nav.vault', 'Identity Vault'), to: '/identity' }],
      '/settings': [{ label: t('nav.settings', 'Settings'), to: '/settings' }],
      '/help': [{ label: t('nav.help', 'Help'), to: '/help' }],
      '/admin': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.admin_panel', 'Admin Panel'), to: '/admin' },
      ],
      '/branding': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.branding', 'Branding & Consortia'), to: '/branding' },
      ],
      '/translations': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.translations', 'Translations'), to: '/translations' },
      ],
      '/reporting': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.reporting', 'Reporting'), to: '/reporting' },
      ],
      '/database': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.database', 'Database Admin'), to: '/database' },
      ],
      '/plugins': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.plugins', 'Plugins'), to: '/plugins' },
      ],
      '/plugin-upload': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.plugins', 'Plugins'), to: '/plugins' },
        { label: t('nav.plugin_upload', 'Upload Plugin'), to: '/plugin-upload' },
      ],
      '/plugin-help': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.plugins', 'Plugins'), to: '/plugins' },
        { label: t('nav.plugin_docs', 'Plugin Documentation'), to: '/plugin-help' },
      ],
      '/broker-health': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.broker_health', 'Broker Health'), to: '/broker-health' },
      ],
      '/broker-priority': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.broker_priority', 'Broker Priority'), to: '/broker-priority' },
      ],
      '/parent-companies': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.parent_companies', 'Parent Companies'), to: '/parent-companies' },
      ],
      '/logs': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.logs', 'System Logs'), to: '/logs' },
      ],
      '/worker-fleet': [
        { label: t('nav.admin', 'Admin'), to: '/admin' },
        { label: t('nav.worker_fleet', 'Worker Fleet'), to: '/worker-fleet' },
      ],
    }

    const matched = segments[pathname]
    if (matched) {
      return [homeCrumb, ...matched]
    }

    // Fallback: derive from pathname chunks
    const parts = pathname.split('/').filter(Boolean)
    const dynamicCrumbs = parts.map((part, index) => {
      const url = `/${parts.slice(0, index + 1).join('/')}`
      const formatted = part.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
      return { label: formatted, to: url }
    })

    return [homeCrumb, ...dynamicCrumbs]
  }

  const crumbs = getCrumbs()

  return (
    <nav
      aria-label={t('nav.breadcrumbs', 'Breadcrumb')}
      className="px-6 py-2.5 bg-slate-900/40 border-b border-slate-800/80 text-xs font-medium"
    >
      <ol className="flex items-center flex-wrap gap-1.5 list-none m-0 p-0 text-slate-400">
        {crumbs.map((crumb, idx) => {
          const isLast = idx === crumbs.length - 1
          return (
            <li key={crumb.to + idx} className="flex items-center gap-1.5">
              {idx > 0 && (
                <span aria-hidden="true" className="text-slate-600 select-none">
                  {isRTL ? <ChevronRight size={12} className="rotate-180" /> : <ChevronRight size={12} />}
                </span>
              )}
              {isLast ? (
                <span
                  aria-current="page"
                  className="text-white font-semibold flex items-center gap-1"
                >
                  {idx === 0 && <Home size={13} className="shrink-0 text-blue-400" aria-hidden="true" />}
                  {crumb.label}
                </span>
              ) : (
                <Link
                  to={crumb.to}
                  className="hover:text-white transition-colors flex items-center gap-1 focus-visible:outline-2 focus-visible:outline-blue-400 focus-visible:outline-offset-2 rounded-xs"
                >
                  {idx === 0 && <Home size={13} className="shrink-0 text-slate-400" aria-hidden="true" />}
                  <span>{crumb.label}</span>
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
