const styles = {
  confirmed:  'bg-emerald-900/50 text-emerald-400 border-emerald-800',
  pending:    'bg-amber-900/50  text-amber-400  border-amber-800',
  sent:       'bg-amber-900/50  text-amber-400  border-amber-800',
  rejected:   'bg-red-900/50    text-red-400    border-red-800',
  failed:     'bg-red-900/50    text-red-400    border-red-800',
  resistant:  'bg-red-900/50    text-red-400    border-red-800',
  recheck_due:'bg-orange-900/50 text-orange-400 border-orange-800',
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

export default function Badge({ value }) {
  const cls = styles[value?.toLowerCase()] ?? 'bg-slate-800 text-slate-300 border-slate-700'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-sm text-xs border ${cls}`}>
      {value}
    </span>
  )
}
