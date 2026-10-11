import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Inbox } from 'lucide-react'
import api from '../api'

// Shown after sign-in to anyone whose profile has no inbox to send opt-outs from.
export default function InboxPrompt() {
  const [needs, setNeeds] = useState(false)
  const location = useLocation()

  useEffect(() => {
    api.get('/mailboxes/me').then(r => setNeeds(!!r.data.needs_inbox)).catch(() => setNeeds(false))
  }, [location.pathname])

  if (!needs || location.pathname === '/inboxes') return null
  return (
    <div role="status" className="flex items-center gap-3 px-4 py-2.5 border-b bg-amber-900/40 border-amber-800">
      <Inbox size={16} className="text-amber-200 shrink-0" aria-hidden="true" />
      <p className="text-sm flex-1 text-amber-100">
        Connect your email inbox so opt-out requests can be sent for you and replies can be tracked.
      </p>
      <Link to="/inboxes" className="text-sm font-medium text-amber-100 underline shrink-0">Connect inbox</Link>
    </div>
  )
}
