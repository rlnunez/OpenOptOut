import { useState, useEffect } from 'react'
import { X, Clock, Wrench } from 'lucide-react'
import api from '../api'
import { tx } from '../i18n/tx'
import { fmtDateTime } from '../i18n/format'

export default function MaintenanceNoticeBanner() {
  const [notice, setNotice] = useState(null)
  const [dismissed, setDismissed] = useState(false)

  const loadNotice = async () => {
    try {
      const res = await api.get('/calendar/maintenance/notice')
      const n = res.data?.notice
      if (n && n.window?.id) {
        const key = `dismissed_downtime_${n.window.id}_${n.status}`
        if (sessionStorage.getItem(key)) {
          setDismissed(true)
        } else {
          setDismissed(false)
        }
        setNotice(n)
      } else {
        setNotice(null)
      }
    } catch {
      // Not logged in or network error
    }
  }

  useEffect(() => {
    loadNotice()
    const interval = setInterval(loadNotice, 60000)
    const onSettingsChanged = () => loadNotice()
    window.addEventListener('maintenance-settings-changed', onSettingsChanged)
    return () => {
      clearInterval(interval)
      window.removeEventListener('maintenance-settings-changed', onSettingsChanged)
    }
  }, [])

  if (!notice || !notice.window?.id || dismissed) return null

  const handleDismiss = () => {
    const key = `dismissed_downtime_${notice.window.id}_${notice.status}`
    sessionStorage.setItem(key, '1')
    setDismissed(true)
  }

  const isActive = notice.status === 'active'
  const Icon = isActive ? Wrench : Clock
  const bannerStyles = isActive
    ? 'bg-purple-950/90 border-purple-800/80 text-purple-200'
    : 'bg-amber-950/90 border-amber-800/80 text-amber-200'
  const iconColor = isActive ? 'text-purple-300' : 'text-amber-300'

  return (
    <aside
      aria-label={isActive ? tx("Maintenance in progress:") : tx("Scheduled downtime:")}
      className={`flex items-center gap-3 px-4 py-2.5 border-b ${bannerStyles}`}
    >
      <Icon size={16} className={`${iconColor} shrink-0`} aria-hidden="true" />
      <p className="text-sm flex-1 leading-snug">
        <strong className="font-semibold">
          {isActive ? tx("Maintenance in progress:") : tx("Scheduled downtime:")}
        </strong>{' '}
        {notice.message} —{' '}
        {isActive
          ? tx("All tasks paused until {end}.", { end: fmtDateTime(notice.end) })
          : tx("Downtime scheduled from {start} to {end}.", {
              start: fmtDateTime(notice.start),
              end: fmtDateTime(notice.end),
            })}
      </p>
      <button
        type="button"
        onClick={handleDismiss}
        className="opacity-70 hover:opacity-100 transition-opacity p-1 -me-1 shrink-0"
        aria-label={tx("Dismiss")}
      >
        <X size={15} aria-hidden="true" />
      </button>
    </aside>
  )
}

