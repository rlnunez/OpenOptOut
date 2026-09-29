import { useEffect, useState } from 'react'
import {
  ShieldAlert, CheckCircle, ExternalLink, Eye, X,
  RefreshCw, AlertCircle, KeyRound, RotateCcw,
  FileImage, Clock, Check
} from 'lucide-react'
import api from '../api'
import Badge from '../components/Badge'

export default function CaptchaQueue() {
  const [challenges, setChallenges] = useState([])
  const [stats, setStats] = useState({ pending: 0, resolved: 0, dismissed: 0, total: 0 })
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('pending')
  const [selectedShot, setSelectedShot] = useState(null)
  const [resolvingId, setResolvingId] = useState(null)
  const [tokenInput, setTokenInput] = useState('')
  const [notesInput, setNotesInput] = useState('')
  const [showTokenModal, setShowTokenModal] = useState(false)
  const [actionInProgress, setActionInProgress] = useState(false)

  const loadData = async () => {
    setLoading(true)
    try {
      const [resList, resStats] = await Promise.all([
        api.get(`/captcha/challenges?status=${activeTab}`),
        api.get('/captcha/stats')
      ])
      setChallenges(resList.data || [])
      setStats(resStats.data || { pending: 0, resolved: 0, dismissed: 0, total: 0 })
    } catch (err) {
      console.error('Failed to load challenges:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [activeTab])

  const handleResolveManual = async (challengeId) => {
    if (!window.confirm('Mark this opt-out as manually verified and completed on the broker site?')) return
    setActionInProgress(true)
    try {
      await api.post(`/captcha/challenges/${challengeId}/resolve`, {
        resolution_type: 'manual_completed',
        notes: 'Operator manually completed opt-out and verified CAPTCHA on site'
      })
      loadData()
    } catch (err) {
      alert('Failed to resolve challenge: ' + (err.response?.data?.detail || err.message))
    } finally {
      setActionInProgress(false)
    }
  }

  const handleResolveWithToken = async () => {
    if (!resolvingId) return
    setActionInProgress(true)
    try {
      await api.post(`/captcha/challenges/${resolvingId}/resolve`, {
        resolution_type: 'token',
        token: tokenInput,
        notes: notesInput || 'Token provided by human operator'
      })
      setShowTokenModal(false)
      setResolvingId(null)
      setTokenInput('')
      setNotesInput('')
      loadData()
    } catch (err) {
      alert('Failed to submit solution token: ' + (err.response?.data?.detail || err.message))
    } finally {
      setActionInProgress(false)
    }
  }

  const handleDismiss = async (challengeId) => {
    const reason = window.prompt('Reason for dismissing challenge (optional):', 'Operator dismissed')
    if (reason === null) return
    setActionInProgress(true)
    try {
      await api.post(`/captcha/challenges/${challengeId}/dismiss`, { notes: reason })
      loadData()
    } catch (err) {
      alert('Failed to dismiss challenge: ' + (err.response?.data?.detail || err.message))
    } finally {
      setActionInProgress(false)
    }
  }

  const handleRetry = async (challengeId) => {
    setActionInProgress(true)
    try {
      await api.post(`/captcha/challenges/${challengeId}/retry`)
      loadData()
    } catch (err) {
      alert('Failed to retry challenge: ' + (err.response?.data?.detail || err.message))
    } finally {
      setActionInProgress(false)
    }
  }

  return (
    <div className="p-4 md:p-6 max-w-6xl">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <ShieldAlert className="text-amber-400" size={24} />
            <h1 className="text-white text-xl font-semibold">CAPTCHA & Challenge Queue</h1>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            Human-in-the-loop fallback for opt-out requests paused by CAPTCHA walls or verification challenges.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-800 pb-3 mb-6">
        {[
          { key: 'pending', label: 'Pending', count: stats.pending, color: 'text-amber-400' },
          { key: 'resolved', label: 'Resolved', count: stats.resolved, color: 'text-emerald-400' },
          { key: 'dismissed', label: 'Dismissed', count: stats.dismissed, color: 'text-slate-400' },
          { key: 'all', label: 'All', count: stats.total, color: 'text-sky-400' }
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-slate-800 text-white border border-slate-700'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
            }`}
          >
            <span>{tab.label}</span>
            <span className={`px-1.5 py-0.2 rounded-full text-xs bg-slate-900 ${tab.color}`}>
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="p-12 text-center text-slate-500">
          <RefreshCw className="animate-spin inline-block mr-2" size={16} /> Loading challenges...
        </div>
      ) : challenges.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-400">
          <CheckCircle className="mx-auto text-emerald-400 mb-3" size={32} />
          <h3 className="text-white font-medium text-base">No {activeTab !== 'all' ? activeTab : ''} challenges</h3>
          <p className="text-slate-500 text-xs mt-1">
            {activeTab === 'pending'
              ? 'All automated opt-outs are running cleanly without manual intervention.'
              : `No ${activeTab} challenges recorded.`}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {challenges.map(c => (
            <div
              key={c.id}
              className="bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-xl p-4 transition-colors"
            >
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 mb-1.5">
                    <span className="text-white font-medium text-base">{c.broker_name}</span>
                    <span className="text-slate-500 text-xs">•</span>
                    <span className="text-slate-300 text-sm font-medium">{c.member_name}</span>
                    <Badge value={c.status} />
                    <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-amber-300 border border-slate-700 font-mono">
                      {c.challenge_type}
                    </span>
                  </div>

                  <p className="text-slate-400 text-xs flex items-center gap-1.5 mt-1">
                    <Clock size={12} className="text-slate-500" />
                    Detected: {new Date(c.created_at).toLocaleString()}
                    {c.resolved_at && ` • Resolved: ${new Date(c.resolved_at).toLocaleString()} by ${c.resolved_by_name || 'operator'}`}
                  </p>

                  {c.notes && (
                    <p className="text-slate-400 text-xs mt-2 bg-slate-950/60 p-2 rounded border border-slate-800">
                      <strong>Notes:</strong> {c.notes}
                    </p>
                  )}

                  {/* URLs & Details */}
                  <div className="flex flex-wrap items-center gap-3 mt-3 text-xs">
                    {(c.page_url || c.broker_opt_out_url) && (
                      <a
                        href={c.page_url || c.broker_opt_out_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-shield-400 hover:text-shield-300 underline"
                      >
                        <ExternalLink size={12} />
                        Open broker opt-out form
                      </a>
                    )}
                    {c.site_key && (
                      <span className="text-slate-500 font-mono truncate max-w-xs">
                        SiteKey: {c.site_key}
                      </span>
                    )}
                  </div>
                </div>

                {/* Right Column: Screenshot thumbnail & Actions */}
                <div className="flex flex-col items-end gap-3 shrink-0">
                  {c.has_screenshot && (
                    <button
                      onClick={() => setSelectedShot(`/api/captcha/challenges/${c.id}/screenshot`)}
                      className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg transition-colors"
                      title="Inspect challenge screenshot"
                    >
                      <FileImage size={13} className="text-amber-400" />
                      View Screenshot
                    </button>
                  )}

                  {c.status === 'pending' ? (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <button
                        onClick={() => handleResolveManual(c.id)}
                        disabled={actionInProgress}
                        className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-emerald-300 bg-emerald-950/40 border border-emerald-800 hover:bg-emerald-900/60 rounded-lg transition-colors"
                      >
                        <Check size={12} /> Mark Solved
                      </button>
                      <button
                        onClick={() => {
                          setResolvingId(c.id)
                          setShowTokenModal(true)
                        }}
                        disabled={actionInProgress}
                        className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-sky-300 bg-sky-950/40 border border-sky-800 hover:bg-sky-900/60 rounded-lg transition-colors"
                      >
                        <KeyRound size={12} /> Submit Token
                      </button>
                      <button
                        onClick={() => handleDismiss(c.id)}
                        disabled={actionInProgress}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-slate-400 hover:text-slate-200 border border-slate-800 hover:bg-slate-800 rounded-lg transition-colors"
                      >
                        <X size={12} /> Dismiss
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => handleRetry(c.id)}
                      disabled={actionInProgress}
                      className="flex items-center gap-1 px-2.5 py-1 text-xs text-slate-400 hover:text-white border border-slate-800 hover:bg-slate-800 rounded-lg transition-colors"
                    >
                      <RotateCcw size={12} /> Re-queue
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Screenshot Viewer Modal */}
      {selectedShot && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 backdrop-blur-sm"
          onClick={() => setSelectedShot(null)}
        >
          <div
            className="bg-slate-900 border border-slate-700 rounded-xl p-4 max-w-4xl max-h-[90vh] flex flex-col shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
              <span className="text-white font-medium text-sm">Challenge Screenshot</span>
              <button
                onClick={() => setSelectedShot(null)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X size={18} />
              </button>
            </div>
            <div className="overflow-auto flex-1 text-center">
              <img
                src={selectedShot}
                alt="CAPTCHA Challenge"
                className="max-h-[75vh] w-auto inline-block rounded border border-slate-800 shadow"
              />
            </div>
          </div>
        </div>
      )}

      {/* Token Submission Modal */}
      {showTokenModal && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 backdrop-blur-sm"
          onClick={() => setShowTokenModal(false)}
        >
          <div
            className="bg-slate-900 border border-slate-700 rounded-xl p-5 max-w-md w-full shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
              <div className="flex items-center gap-2">
                <KeyRound size={16} className="text-sky-400" />
                <span className="text-white font-medium text-sm">Provide Solution Token</span>
              </div>
              <button
                onClick={() => setShowTokenModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X size={18} />
              </button>
            </div>
            <p className="text-slate-400 text-xs mb-3">
              Paste the solution response token obtained from a manual browser inspection or external solving service:
            </p>
            <textarea
              rows={4}
              value={tokenInput}
              onChange={e => setTokenInput(e.target.value)}
              placeholder="e.g. 03AFcWeA..."
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 font-mono mb-3 focus:outline-none focus:border-sky-500"
            />
            <input
              type="text"
              value={notesInput}
              onChange={e => setNotesInput(e.target.value)}
              placeholder="Optional notes or reference..."
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 mb-4 focus:outline-none focus:border-sky-500"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowTokenModal(false)}
                className="px-3 py-1.5 text-xs text-slate-400 hover:text-white border border-slate-800 rounded-lg hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={handleResolveWithToken}
                disabled={!tokenInput.trim() || actionInProgress}
                className="px-4 py-1.5 text-xs font-medium text-white bg-shield-600 hover:bg-shield-500 disabled:opacity-40 rounded-lg transition-colors"
              >
                Submit & Resolve
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
