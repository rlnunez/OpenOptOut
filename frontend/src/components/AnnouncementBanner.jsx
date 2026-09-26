import { X, Info, AlertTriangle, Wrench, CheckCircle } from 'lucide-react'
import { useBranding } from '../hooks/useBranding'

const SEVERITY = {
  info:        { icon: Info,          bg: 'bg-blue-900/40',   border: 'border-blue-800',  text: 'text-blue-200' },
  warning:     { icon: AlertTriangle, bg: 'bg-amber-900/40',  border: 'border-amber-800', text: 'text-amber-200' },
  maintenance: { icon: Wrench,        bg: 'bg-orange-900/40', border: 'border-orange-800',text: 'text-orange-200' },
  success:     { icon: CheckCircle,   bg: 'bg-emerald-900/40',border: 'border-emerald-800',text: 'text-emerald-200' },
}

export default function AnnouncementBanner() {
  const { banner, dismissed, setDismissed } = useBranding()
  if (!banner || !banner.active || dismissed) return null

  const s = SEVERITY[banner.severity] ?? SEVERITY.info
  const Icon = s.icon

  return (
    <div className={`flex items-center gap-3 px-4 py-2.5 border-b ${s.bg} ${s.border}`}>
      <Icon size={14} className={s.text + ' shrink-0'} />
      <p className={`text-sm flex-1 ${s.text}`}>{banner.message}</p>
      <button
        onClick={() => setDismissed(true)}
        className={`${s.text} opacity-60 hover:opacity-100 transition-opacity shrink-0`}
        aria-label="Dismiss"
      >
        <X size={14} />
      </button>
    </div>
  )
}
