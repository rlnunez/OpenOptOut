const styles = {
  confirmed:  'bg-emerald-900/50 text-emerald-400 border-emerald-800',
  pending:    'bg-amber-900/50  text-amber-400  border-amber-800',
  sent:       'bg-amber-900/50  text-amber-400  border-amber-800',
  rejected:   'bg-red-900/50    text-red-400    border-red-800',
  failed:     'bg-red-900/50    text-red-400    border-red-800',
  resistant:  'bg-red-900/50    text-red-400    border-red-800',
  recheck_due:'bg-orange-900/50 text-orange-400 border-orange-800',
  needs_manual:'bg-amber-900/50 text-amber-300 border-amber-700',
  submitted:  'bg-amber-900/50  text-amber-400  border-amber-800',
  compliant:  'bg-slate-800     text-slate-300  border-slate-700',
  inconsistent:'bg-orange-900/50 text-orange-400 border-orange-800',
  undetermined:'bg-slate-800    text-slate-400  border-slate-700',
  form:       'bg-slate-800     text-slate-300  border-slate-700',
  email:      'bg-blue-900/50   text-blue-400   border-blue-800',
  manual:     'bg-purple-900/50 text-purple-400 border-purple-800',
  phone:      'bg-purple-900/50 text-purple-400 border-purple-800',
  easy:       'bg-emerald-900/50 text-emerald-400 border-emerald-800',
  medium:     'bg-amber-900/50  text-amber-400  border-amber-800',
  hard:       'bg-red-900/50    text-red-400    border-red-800',
}

// Plain words for the codes the server uses. Anything not listed is shown
// with underscores turned into spaces.
export const LABELS = {
  pending: 'Waiting to send', sent: 'Sent', submitted: 'Sent', confirmed: 'Removed',
  rejected: 'Refused', failed: "Didn't work", needs_manual: 'Needs you', recheck_due: 'Check again',
  resistant: 'Often refuses', compliant: 'Usually removes', inconsistent: 'Mixed results',
  undetermined: 'Not known yet', form: 'Web form', email: 'Email', manual: 'By hand', phone: 'By phone',
  easy: 'Easy', medium: 'Medium', hard: 'Hard', running: 'Running', done: 'Done', error: 'Problem',
  success: 'Worked', failure: "Didn't work", captcha: 'CAPTCHA', skipped: 'Skipped',
}

export function plainLabel(value) {
  if (value == null || value === '') return ''
  const v = String(value)
  return LABELS[v.toLowerCase()] || (v.charAt(0).toUpperCase() + v.slice(1)).replace(/_/g, ' ')
}

export default function Badge({ value }) {
  const cls = styles[value?.toLowerCase()] ?? 'bg-slate-800 text-slate-300 border-slate-700'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-sm text-xs border ${cls}`}>
      {plainLabel(value)}
    </span>
  )
}
