import { useEffect, useState } from 'react'
import { ShieldAlert } from 'lucide-react'
import api from '../api'
import { useAuth } from '../hooks/useAuth'
import { tx, txr } from '../i18n/tx'

// Docker Compose's web service binds 0.0.0.0:80 by default (deliberately —
// it has to be reachable by family members/patrons on the network before
// anyone sets anything up), so a fresh install is plain HTTP until an admin
// runs enable-https.sh. Dashboard.jsx used to carry this same warning, but
// only on the Dashboard — someone who signs in and goes straight to Family
// or Settings never saw it. It's lifted here, unchanged in wording and in
// the 'external reverse proxy, trust the admin' opt-out, so every page
// carries it and it isn't something a single page visit settles.
//
// Checked the most honest way available: whether THIS PAGE, right now,
// loaded over http:. That's always current (no stored setting to go stale
// if HTTPS gets added outside the wizard later), and it can't be spoofed by
// anything server-side.
export default function HttpsBanner() {
  const { user } = useAuth()
  const [reverseProxy, setReverseProxy] = useState(null)

  useEffect(() => {
    if (user?.role !== 'super_admin') return
    api.get('/wizard/state')
      .then(r => setReverseProxy(r.data.reverse_proxy || 'unset'))
      .catch(() => setReverseProxy('unset'))
  }, [user])

  const onPlainHttp = typeof window !== 'undefined' && window.location.protocol === 'http:' &&
    !['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname) &&
    reverseProxy !== 'external'   // an admin told us this server sits behind its own reverse proxy — take their word for it

  if (user?.role !== 'super_admin' || !onPlainHttp) return null

  return (
    <div role="alert" className="bg-red-950/95 border-b-2 border-red-500 text-red-100 px-4 py-3 shrink-0">
      <div className="max-w-6xl mx-auto flex items-start gap-2.5">
        <ShieldAlert size={20} className="text-red-400 shrink-0 mt-0.5" />
        <div className="text-xs sm:text-sm">
          <span className="font-bold text-white me-1.5">
            {tx("Critical Security Action Required:")}
          </span>
          <span className="me-1">{tx("This site isn't using HTTPS")}.</span>
          <span>{tx("Passwords cross the network unencrypted, and Google/Microsoft sign-in requires HTTPS.")}</span>{' '}
          {reverseProxy === 'native'
            ? txr("On the server, run <0>scripts/enable-https-native.sh</0> (Linux) or see the Windows steps in <1>docs/admin/native-install.md</1>.",
                  [<code className="px-1.5 py-0.5 rounded bg-red-900/80 text-amber-200 font-mono text-xs" />,
                   <code className="px-1.5 py-0.5 rounded bg-red-900/80 text-amber-200 font-mono text-xs" />])
            : txr("On the server, run <0>./scripts/enable-https.sh</0> (Linux/macOS) or <1>scripts\\enable-https.ps1</1> (Windows) — see docs/admin/https.md.",
                  [<code className="px-1.5 py-0.5 rounded bg-red-900/80 text-amber-200 font-mono text-xs" />,
                   <code className="px-1.5 py-0.5 rounded bg-red-900/80 text-amber-200 font-mono text-xs" />])}
        </div>
      </div>
    </div>
  )
}
