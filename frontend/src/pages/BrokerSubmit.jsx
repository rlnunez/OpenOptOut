import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus, Upload, Check, X, ChevronDown, FileJson,
  AlertTriangle, ExternalLink, Info
} from 'lucide-react'
import api from '../api'

const inp = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"

function Field({ label, hint, required, children }) {
  return (
    <div>
      <label className="text-slate-400 text-xs mb-1 block">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
      {hint && <p className="text-slate-600 text-xs mt-1">{hint}</p>}
    </div>
  )
}

function Select({ value, onChange, options }) {
  return (
    <div className="relative">
      <select value={value} onChange={e => onChange(e.target.value)}
        className={`${inp} appearance-none pr-7`}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <ChevronDown size={11} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
    </div>
  )
}

// ── JSON schema helper ────────────────────────────────────────────────────────

const JSON_SCHEMA = `[
  {
    "name": "Example-site.com",
    "opt_out_url": "https://example-site.com/optout",
    "method": "form",
    "difficulty": "medium",
    "status": "compliant",
    "notes": "Optional notes about this broker"
  }
]`

const FIELD_DOCS = [
  { field: 'name',         required: true,  desc: 'Broker name or domain (unique identifier)' },
  { field: 'opt_out_url',  required: false, desc: 'Direct URL to the opt-out page or form' },
  { field: 'method',       required: false, desc: '"form" | "email" | "manual" | "phone"' },
  { field: 'difficulty',   required: false, desc: '"easy" | "medium" | "hard"' },
  { field: 'status',       required: false, desc: '"compliant" | "resistant" | "inconsistent" | "undetermined"' },
  { field: 'notes',        required: false, desc: 'Any notes about the opt-out process' },
]

// ── Form add ──────────────────────────────────────────────────────────────────

function AddBrokerForm({ onAdded }) {
  const [form, setForm] = useState({
    name: '', opt_out_url: '', method: 'form',
    difficulty: 'medium', status: 'compliant', notes: '',
    is_property_broker: false,
  })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState('')
  const [success, setSuccess] = useState('')

  const submit = async e => {
    e.preventDefault()
    if (!form.name.trim()) { setError('Name is required'); return }
    setSaving(true); setError(''); setSuccess('')
    try {
      const { data } = await api.post('/brokers', {
        ...form,
        opt_out_url: form.opt_out_url || undefined,
        notes: form.notes || undefined,
      })
      setSuccess(`✓ Added "${data.name}" (id ${data.id})`)
      setForm({ name: '', opt_out_url: '', method: 'form', difficulty: 'medium', status: 'compliant', notes: '' })
      onAdded(data)
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Failed to add broker')
    } finally { setSaving(false) }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error   && <div className="px-3 py-2 bg-red-900/20 border border-red-800 rounded-lg text-red-400 text-sm">{error}</div>}
      {success && <div className="px-3 py-2 bg-emerald-900/20 border border-emerald-800 rounded-lg text-emerald-400 text-sm">{success}</div>}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="col-span-2">
          <Field label="Broker name or domain" required hint='e.g. "Spokeo.com" or "Acme Data"'>
            <input value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))}
              placeholder="DataBroker.com" className={inp} autoFocus />
          </Field>
        </div>

        <div className="col-span-2">
          <Field label="Opt-out URL" hint="Direct link to the removal/opt-out page">
            <input value={form.opt_out_url} onChange={e => setForm(f => ({...f, opt_out_url: e.target.value}))}
              placeholder="https://databroker.com/optout" className={inp} />
          </Field>
        </div>

        <Field label="Method">
          <Select value={form.method} onChange={v => setForm(f => ({...f, method: v}))} options={[
            { value: 'form',   label: 'Form — online opt-out form' },
            { value: 'email',  label: 'Email — send removal request' },
            { value: 'manual', label: 'Manual — mail / fax / phone' },
            { value: 'phone',  label: 'Phone — call required' },
          ]} />
        </Field>

        <Field label="Difficulty">
          <Select value={form.difficulty} onChange={v => setForm(f => ({...f, difficulty: v}))} options={[
            { value: 'easy',   label: 'Easy — quick form, fast compliance' },
            { value: 'medium', label: 'Medium — verification required' },
            { value: 'hard',   label: 'Hard — resistant or complex process' },
          ]} />
        </Field>

        <div className="col-span-2">
          <Field label="Compliance status">
            <Select value={form.status} onChange={v => setForm(f => ({...f, status: v}))} options={[
              { value: 'compliant',    label: 'Compliant — honors opt-outs reliably' },
              { value: 'inconsistent', label: 'Inconsistent — sometimes complies' },
              { value: 'resistant',    label: 'Resistant — frequently ignores requests' },
              { value: 'undetermined', label: 'Undetermined — not yet tested' },
            ]} />
          </Field>
        </div>

        <div className="col-span-2">
          <label className="flex items-center gap-2 cursor-pointer mb-1">
            <input type="checkbox" checked={form.is_property_broker}
              onChange={e => setForm(f => ({...f, is_property_broker: e.target.checked}))}
              className="w-3.5 h-3.5 rounded-sm accent-shield-500" />
            <span className="text-slate-300 text-sm">Property broker</span>
            <span className="text-slate-600 text-xs">
              — uses formal name + deed/mortgage addresses instead of name variants
            </span>
          </label>
        </div>

        <div className="col-span-2">
          <Field label="Notes" hint="Opt-out process details, tips, known issues">
            <textarea value={form.notes} onChange={e => setForm(f => ({...f, notes: e.target.value}))}
              rows={3} placeholder="e.g. Requires email confirmation. Re-lists within 60 days — use 30-day recheck."
              className={`${inp} resize-none`} />
          </Field>
        </div>
      </div>

      <div className="flex justify-end pt-1">
        <button type="submit" disabled={saving}
          className="flex items-center gap-1.5 px-4 py-2 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors">
          {saving ? <><span className="animate-spin inline-block w-3 h-3 border border-white/30 border-t-white rounded-full"/>Adding…</> : <><Plus size={13}/>Add broker</>}
        </button>
      </div>
    </form>
  )
}

// ── JSON upload ───────────────────────────────────────────────────────────────

function JsonUpload({ onImported }) {
  const fileRef   = useRef()
  const [result, setResult]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const [showSchema, setShowSchema] = useState(false)

  const handleFile = async e => {
    const file = e.target.files?.[0]; if (!file) return
    setLoading(true); setResult(null); setError('')
    const form = new FormData(); form.append('file', file)
    try {
      const { data } = await api.post('/brokers/import-json', form)
      setResult(data)
      onImported()
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Import failed — check JSON format')
    } finally {
      setLoading(false)
      e.target.value = ''
    }
  }

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        onClick={() => fileRef.current?.click()}
        className="border-2 border-dashed border-slate-700 hover:border-shield-600 rounded-xl p-8 text-center cursor-pointer transition-colors group"
      >
        <FileJson size={28} className="text-slate-600 group-hover:text-shield-500 mx-auto mb-2 transition-colors" />
        <p className="text-slate-400 text-sm">Click to select a JSON file</p>
        <p className="text-slate-600 text-xs mt-1">or drag and drop</p>
        <input ref={fileRef} type="file" accept=".json,application/json" className="hidden" onChange={handleFile} />
      </div>

      {loading && <p className="text-slate-400 text-sm text-center">Importing…</p>}

      {error && (
        <div className="flex items-start gap-2 px-3 py-2.5 bg-red-900/20 border border-red-800 rounded-lg">
          <AlertTriangle size={13} className="text-red-400 shrink-0 mt-0.5" />
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {result && (
        <div className="px-3 py-3 bg-emerald-900/20 border border-emerald-800 rounded-lg">
          <p className="text-emerald-400 text-sm font-medium mb-1">Import complete</p>
          <div className="flex gap-4 text-xs text-emerald-300">
            <span><strong>{result.added}</strong> added</span>
            <span><strong>{result.updated}</strong> updated</span>
            {result.skipped > 0 && <span><strong>{result.skipped}</strong> skipped</span>}
          </div>
          {result.errors?.length > 0 && (
            <div className="mt-2">
              <p className="text-amber-400 text-xs font-medium">{result.errors.length} errors:</p>
              {result.errors.slice(0, 5).map((e, i) => (
                <p key={i} className="text-amber-300 text-xs ml-2">{e}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Schema toggle */}
      <button onClick={() => setShowSchema(s => !s)}
        className="flex items-center gap-1.5 text-slate-500 hover:text-slate-300 text-xs transition-colors">
        <Info size={11} />{showSchema ? 'Hide' : 'Show'} JSON format reference
      </button>

      {showSchema && (
        <div className="space-y-3">
          <pre className="bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-xs text-slate-300 font-mono overflow-x-auto">
            {JSON_SCHEMA}
          </pre>
          <div className="bg-slate-900 border border-slate-700 rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700 text-slate-500">
                  <th className="text-left px-3 py-2 font-normal">Field</th>
                  <th className="text-left px-3 py-2 font-normal">Required</th>
                  <th className="text-left px-3 py-2 font-normal">Description</th>
                </tr>
              </thead>
              <tbody>
                {FIELD_DOCS.map(f => (
                  <tr key={f.field} className="border-t border-slate-800">
                    <td className="px-3 py-2 font-mono text-shield-400">{f.field}</td>
                    <td className="px-3 py-2 text-slate-500">{f.required ? 'yes' : 'no'}</td>
                    <td className="px-3 py-2 text-slate-400">{f.desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-slate-600 text-xs">
            The JSON file can also be wrapped in <code className="bg-slate-800 px-1 rounded-sm">{"{ \"brokers\": [ ... ] }"}</code> for compatibility with export files.
            Existing brokers are matched by name (case-insensitive) and updated rather than duplicated.
          </p>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function BrokerSubmit() {
  const navigate = useNavigate()
  const [tab, setTab]         = useState('form')  // 'form' | 'json'
  const [addedCount, setAddedCount] = useState(0)

  return (
    <div className="p-4 md:p-6 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">Add brokers</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            Add a single broker via form or bulk-import from a JSON file
          </p>
        </div>
        <button onClick={() => navigate('/brokers')}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors">
          <ExternalLink size={13} /> View broker list
        </button>
      </div>

      {addedCount > 0 && (
        <div className="mb-4 px-3 py-2 bg-emerald-900/20 border border-emerald-800 rounded-lg text-emerald-400 text-sm">
          {addedCount} broker{addedCount > 1 ? 's' : ''} added this session
        </div>
      )}

      {/* Tab switcher */}
      <div className="flex gap-1 bg-slate-800 p-1 rounded-lg border border-slate-700/50 mb-6 w-fit">
        {[
          { key: 'form', label: 'Add one', icon: Plus },
          { key: 'json', label: 'Bulk import JSON', icon: FileJson },
        ].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded transition-colors ${
              tab === t.key ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
            }`}>
            <t.icon size={13} />{t.label}
          </button>
        ))}
      </div>

      <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-5">
        {tab === 'form' ? (
          <AddBrokerForm onAdded={() => setAddedCount(c => c + 1)} />
        ) : (
          <JsonUpload onImported={() => setAddedCount(c => c + 1)} />
        )}
      </div>

      {/* Community note */}
      <div className="mt-4 flex items-start gap-2 px-3 py-2.5 bg-slate-800/50 border border-slate-700/50 rounded-lg">
        <Info size={13} className="text-slate-500 shrink-0 mt-0.5" />
        <p className="text-slate-500 text-xs">
          If you discover a new data broker not in the default list, consider contributing it back to the open-source project
          so other users benefit too. Export your broker list from the Brokers page and open a pull request.
        </p>
      </div>
    </div>
  )
}
