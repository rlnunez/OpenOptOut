import { ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import { tx, txr } from '../i18n/tx'

// Shown wherever a parent is adding or editing someone under 13 — the age a
// US federal law (COPPA) treats as needing real parental consent, not just a
// checkbox. We're not a lawyer and can't confirm that consent for anyone, so
// this says so plainly instead of implying the checkbox already covers it.
// The actual bureau letters/addresses already live on the Freeze credit page
// (pages/CreditFreeze.jsx) — this just points there instead of repeating them.
export default function ChildPrivacyNotice({ age }) {
  if (age == null || age >= 13) return null
  return (
    <div className="bg-amber-950/30 border border-amber-800/40 rounded-lg p-3 text-xs text-amber-200/90 space-y-1.5">
      <p className="flex items-center gap-1.5 font-medium text-amber-200">
        <ShieldAlert size={13} className="shrink-0" />
        {tx("Adding someone under 13")}
      </p>
      <p>{tx("A US law called COPPA expects real, verified parental consent before a service collects a child's details online — more than the checkbox above. We can't confirm that for you, and this isn't legal advice.")}</p>
      <p>{tx("You can still go ahead. You don't need to know why their details ended up on these sites to have them removed.")}</p>
      <p>{txr("While you're here: a credit freeze stops anyone opening credit in a child's name, for free. See <0>Freeze credit</0> in the menu for ready-to-mail letters to each bureau.",
             [<Link to="/credit-freeze" className="text-amber-100 underline hover:text-white" />])}</p>
    </div>
  )
}
