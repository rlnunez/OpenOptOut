import { useEffect, useRef, useState } from 'react'
import {
  Upload, FolderOpen, Folder, CheckCircle2, XCircle, AlertTriangle,
  Info, ArrowLeft, Package, X,
} from 'lucide-react'
import api from '../api'

/**
 * Plugin upload wizard: pick a .zip, see what kind of plugin it is and which
 * folder it will be installed into (<plugins root>/<type>/<id>/), then install.
 *
 * Step 1 (choose) -> POST /plugins/upload/inspect: nothing is written yet.
 * Step 2 (review) -> POST /plugins/upload: extracted into its type folder,
 *                    registered DISABLED.
 * Step 3 (done)   -> a super admin still has to enable it.
 *
 * Used as a modal on the Plugins page (super admin) and as a page for users a
 * super admin has granted "can upload plugins" (asPage).
 */
export default function PluginUploadWizard({ onClose, onInstalled, expectedType, asPage = false }) {
  const [step, setStep]       = useState('choose')   // choose | review | done
  const [file, setFile]       = useState(null)
  const [plan, setPlan]       = useState(null)
  const [result, setResult]   = useState(null)
  const [types, setTypes]     = useState([])
  const [busy, setBusy]       = useState(false)
  const [error, setError]     = useState('')
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    api.get('/plugins/types').then(r => setTypes(r.data)).catch(() => {})
  }, [])

  const query = expectedType ? `?expected_type=${encodeURIComponent(expectedType)}` : ''
  const formData = (f) => { const fd = new FormData(); fd.append('file', f); return fd }

  const inspect = async (f) => {
    if (!f) return
    setError(''); setFile(f); setBusy(true)
    try {
      const { data } = await api.post(`/plugins/upload/inspect${query}`, formData(f))
      setPlan(data); setStep('review')
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not read that file')
    } finally { setBusy(false) }
  }

  const install = async () => {
    setError(''); setBusy(true)
    try {
      const { data } = await api.post(`/plugins/upload${query}`, formData(file))
      setResult(data); setStep('done')
      onInstalled?.(data)
    } catch (e) {
      setError(e.response?.data?.detail || 'Install failed')
    } finally { setBusy(false) }
  }

  const restart = () => {
    setStep('choose'); setFile(null); setPlan(null); setResult(null); setError('')
  }

  const body = (
    <div className={asPage ? 'bg-slate-800 rounded-xl border border-slate-700/50' :
      'bg-slate-900 rounded-2xl border border-slate-700 max-w-lg w-full max-h-[85vh] overflow-y-auto'}
      onClick={e => e.stopPropagation()}>
      <div className="px-5 py-4 border-b border-slate-700/50 flex items-center justify-between">
        <div>
          <h3 className="text-white font-semibold">Upload a plugin</h3>
          <p className="text-slate-500 text-xs mt-0.5">
            {step === 'choose' && 'Step 1 of 3 — choose a .zip bundle'}
            {step === 'review' && 'Step 2 of 3 — check where it goes'}
            {step === 'done' && 'Step 3 of 3 — installed'}
          </p>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 text-slate-500 hover:text-white" aria-label="Close">
            <X size={16} />
          </button>
        )}
      </div>

      <div className="px-5 py-4 space-y-4">
        {error && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs">
            <XCircle size={13} className="shrink-0 mt-0.5" /> <span>{error}</span>
          </div>
        )}

        {step === 'choose' && (
          <>
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => { e.preventDefault(); setDragOver(false); inspect(e.dataTransfer.files?.[0]) }}
              onClick={() => fileRef.current?.click()}
              className={`cursor-pointer rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors
                ${dragOver ? 'border-shield-500 bg-shield-900/20' : 'border-slate-700 hover:border-slate-600'}`}>
              <Upload size={22} className="text-slate-500 mx-auto mb-2" />
              <p className="text-slate-300 text-sm">
                {busy ? 'Checking…' : 'Drag & drop a plugin .zip here, or click to browse'}
              </p>
              <p className="text-slate-600 text-xs mt-1">
                Nothing is installed until you confirm on the next step.
              </p>
              <input ref={fileRef} type="file" accept=".zip" className="hidden" disabled={busy}
                onChange={e => { inspect(e.target.files?.[0]); e.target.value = '' }} />
            </div>
            {expectedType && (
              <p className="text-slate-500 text-xs">
                Only <span className="text-slate-300">{expectedType}</span> plugins can be uploaded here.
              </p>
            )}
          </>
        )}

        {step === 'review' && plan && (
          <>
            <div>
              <div className="flex items-center gap-2">
                <Package size={15} className="text-shield-400" />
                <p className="text-slate-100 text-sm font-medium">{plan.name}</p>
                <span className="text-slate-600 text-xs">v{plan.version}</span>
              </div>
              <p className="text-slate-500 text-xs mt-1">{plan.author}{plan.description ? ` · ${plan.description}` : ''}</p>
            </div>

            <div className="rounded-lg border border-slate-700/60 bg-slate-800/60 px-3 py-3">
              <p className="text-slate-400 text-xs mb-2">
                Detected type: <span className="text-slate-100 font-medium">{plan.type_label}</span>
                {plan.type_inferred && (
                  <span className="text-amber-300/90"> (worked out from its hooks — its manifest doesn't declare a type)</span>
                )}
              </p>
              <p className="text-slate-500 text-[11px] uppercase tracking-wide mb-1">Will be installed into</p>
              <FolderTree types={types} target={plan.type} pluginId={plan.plugin_id} />
            </div>

            {plan.data_only ? (
              <p className="flex items-start gap-2 text-slate-400 text-xs">
                <Info size={13} className="shrink-0 mt-0.5 text-slate-500" />
                This is a data-only plugin: it contains no code and is never run as a program.
              </p>
            ) : (
              <div className="text-xs text-slate-400 space-y-1">
                <p>Requests permissions: {plan.permissions.length
                  ? plan.permissions.map(p => <code key={p} className="mx-0.5 px-1 rounded bg-slate-800 text-slate-300">{p}</code>)
                  : <span className="text-slate-500">none</span>}</p>
                {plan.outbound_domains?.length > 0 && (
                  <p>Network access to: {plan.outbound_domains.join(', ')}</p>
                )}
              </div>
            )}

            {plan.problems.length > 0 ? (
              <div className="px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs space-y-1">
                <p className="font-medium">This plugin can't be installed:</p>
                <ul className="list-disc ms-4">{plan.problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
              </div>
            ) : (
              <p className="flex items-start gap-2 text-slate-400 text-xs">
                <AlertTriangle size={13} className="shrink-0 mt-0.5 text-amber-400" />
                It will be installed disabled. {plan.enable_requires_super_admin
                  ? 'A super admin has to review and enable it before it does anything.'
                  : 'Enable it from the Plugins page to grant its permissions and run it.'}
              </p>
            )}

            <div className="flex justify-between gap-2 pt-1">
              <button onClick={restart} disabled={busy}
                className="flex items-center gap-1 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
                <ArrowLeft size={13} /> Choose another
              </button>
              <button onClick={install} disabled={busy || !plan.can_install}
                className="px-3 py-1.5 text-sm bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg">
                {busy ? 'Installing…' : `Install into ${plan.destination}`}
              </button>
            </div>
          </>
        )}

        {step === 'done' && result && (
          <>
            <div className="flex items-start gap-2">
              <CheckCircle2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-slate-100 text-sm">Installed into <code className="text-slate-300">{result.destination}</code></p>
                <p className="text-slate-500 text-xs mt-1">
                  {result.enable_requires_super_admin
                    ? 'It is disabled until a super admin reviews and enables it.'
                    : 'It is disabled. Enable it on the Plugins page when you are ready.'}
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={restart}
                className="px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
                Upload another
              </button>
              {onClose && (
                <button onClick={onClose} className="px-3 py-1.5 text-sm bg-shield-600 hover:bg-shield-700 text-white rounded-lg">
                  Done
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )

  if (asPage) return body
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      {body}
    </div>
  )
}

// The plugins folder with one subfolder per type; the destination is highlighted.
function FolderTree({ types, target, pluginId }) {
  const list = types.length ? types : [{ type: target, folder: `${target}/` }]
  return (
    <div className="font-mono text-xs leading-6">
      <p className="text-slate-500 flex items-center gap-1.5"><FolderOpen size={12} /> plugins/</p>
      {list.map(t => {
        const hit = t.type === target
        return (
          <div key={t.type} className="ms-4">
            <p className={`flex items-center gap-1.5 ${hit ? 'text-shield-300' : 'text-slate-600'}`}>
              {hit ? <FolderOpen size={12} /> : <Folder size={12} />} {t.folder}
            </p>
            {hit && (
              <p className="ms-5 flex items-center gap-1.5 text-emerald-300">
                <Package size={12} /> {pluginId}/ <span className="text-emerald-400/70 font-sans">← here</span>
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
