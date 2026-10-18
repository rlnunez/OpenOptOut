import { useEffect, useState, useCallback } from 'react'
import {
  RefreshCw, ArrowUpCircle, AlertTriangle, CheckCircle2,
  Server, Clock, Settings2, ExternalLink, ShieldCheck, EyeOff, Eye, RotateCcw, Calendar
} from 'lucide-react'
import api from '../api'
import { tx } from '../i18n/tx'
import { fmtDateTime } from '../i18n/format'

export default function SystemUpdates() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)
  const [savingPolicy, setSavingPolicy] = useState(false)
  const [policy, setPolicy] = useState('approval_required')
  const [channel, setChannel] = useState('stable')
  const [scheduleType, setScheduleType] = useState('weekly')
  const [scheduleWeekdays, setScheduleWeekdays] = useState([6])
  const [scheduleDayOfMonth, setScheduleDayOfMonth] = useState(1)
  const [scheduleTime, setScheduleTime] = useState('03:00')
  const [scheduleWindowHours, setScheduleWindowHours] = useState(2)
  const [message, setMessage] = useState(null)
  const [applying, setApplying] = useState(false)
  const [rollingBack, setRollingBack] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    api.get('/system/updates')
      .then(r => {
        setData(r.data)
        setPolicy(r.data.policy || 'approval_required')
        setChannel(r.data.channel || 'stable')
        setScheduleType(r.data.schedule_type || 'weekly')
        setScheduleWeekdays(r.data.schedule_weekdays || [6])
        setScheduleDayOfMonth(r.data.schedule_day_of_month || 1)
        setScheduleTime(r.data.schedule_time || '03:00')
        setScheduleWindowHours(r.data.schedule_window_hours || 2)
      })
      .catch(e => {
        setMessage({ type: 'error', text: e.response?.data?.detail || tx("Could not load update information.") })
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Poll when draining or updating
  useEffect(() => {
    if (!data?.state || data.state === 'idle') return
    const interval = setInterval(() => {
      api.get('/system/updates').then(r => {
        setData(r.data)
        if (r.data.state === 'idle' || r.data.state === 'error') {
          clearInterval(interval)
        }
      }).catch(() => {})
    }, 4000)
    return () => clearInterval(interval)
  }, [data?.state])

  const handleCheckNow = async () => {
    setChecking(true)
    setMessage(null)
    try {
      const res = await api.post('/system/updates/check')
      setData(res.data)
      setPolicy(res.data.policy || 'approval_required')
      setChannel(res.data.channel || 'stable')
      if (res.data.schedule_type) setScheduleType(res.data.schedule_type)
      if (res.data.schedule_weekdays) setScheduleWeekdays(res.data.schedule_weekdays)
      if (res.data.schedule_day_of_month) setScheduleDayOfMonth(res.data.schedule_day_of_month)
      if (res.data.schedule_time) setScheduleTime(res.data.schedule_time)
      if (res.data.schedule_window_hours) setScheduleWindowHours(res.data.schedule_window_hours)
      setMessage({ type: 'success', text: tx("Release check completed.") })
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || tx("Failed to check for updates.") })
    } finally {
      setChecking(false)
    }
  }

  const toggleWeekday = (dayIndex) => {
    if (scheduleWeekdays.includes(dayIndex)) {
      if (scheduleWeekdays.length === 1) return
      setScheduleWeekdays(scheduleWeekdays.filter(d => d !== dayIndex).sort((a, b) => a - b))
    } else {
      setScheduleWeekdays([...scheduleWeekdays, dayIndex].sort((a, b) => a - b))
    }
  }

  const handleSavePolicy = async () => {
    setSavingPolicy(true)
    setMessage(null)
    try {
      const res = await api.post('/system/updates/policy', {
        policy,
        channel,
        schedule_type: scheduleType,
        schedule_weekdays: scheduleWeekdays,
        schedule_day_of_month: parseInt(scheduleDayOfMonth, 10) || 1,
        schedule_time: scheduleTime,
        schedule_window_hours: parseInt(scheduleWindowHours, 10) || 2,
      })
      setData(res.data)
      setMessage({ type: 'success', text: tx("Update policy and schedule saved.") })
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || tx("Failed to save update policy.") })
    } finally {
      setSavingPolicy(false)
    }
  }

  const handleIgnore = async (tag) => {
    try {
      const res = await api.post('/system/updates/ignore', { tag })
      setData(res.data)
      setMessage({ type: 'success', text: tx("Release ignored.") })
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || tx("Failed to ignore release.") })
    }
  }

  const handleUnignore = async (tag) => {
    try {
      const res = await api.post('/system/updates/unignore', { tag })
      setData(res.data)
      setMessage({ type: 'success', text: tx("Release restored to update list.") })
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || tx("Failed to restore release.") })
    }
  }

  const handleApplyUpdate = async () => {
    if (!window.confirm(tx("Are you sure you want to install this update? Active removals will be paused and containers restarted."))) {
      return
    }
    setApplying(true)
    setMessage(null)
    try {
      const res = await api.post('/system/updates/apply', { tag: data?.latest_release?.tag_name })
      setData(prev => ({ ...prev, state: res.data.state }))
      setMessage({ type: 'info', text: tx("Update initiated. Workers are draining.") })
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || tx("Failed to initiate update.") })
    } finally {
      setApplying(false)
    }
  }

  const handleRollback = async () => {
    const prev = data?.rollback_info?.previous_version || tx("the previous version")
    if (!window.confirm(tx("Are you sure you want to revert to {version}? Active removals will be paused and previous containers restored.", { version: prev }))) {
      return
    }
    setRollingBack(true)
    setMessage(null)
    try {
      const res = await api.post('/system/updates/rollback')
      setData(prevData => ({ ...prevData, state: res.data.state }))
      setMessage({ type: 'info', text: tx("Rollback initiated. Restoring previous containers.") })
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || tx("Failed to initiate rollback.") })
    } finally {
      setRollingBack(false)
    }
  }

  if (loading && !data) {
    return (
      <div className="p-6 max-w-5xl">
        <p className="text-slate-400 text-sm">{tx("Checking update status…")}</p>
      </div>
    )
  }

  const dockerInfo = data?.docker_info
  const latest = data?.latest_release
  const hasUpdate = data?.has_update
  const isIgnored = data?.is_ignored

  return (
    <div className="p-4 md:p-6 max-w-5xl space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-white text-xl font-semibold flex items-center gap-2">
            <ArrowUpCircle size={22} className="text-shield-500" />
            {tx("System updates")}
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            {tx("Manage application updates, automated release checks, and container maintenance.")}
          </p>
        </div>
        <button
          onClick={handleCheckNow}
          disabled={checking || data?.state === 'draining' || data?.state === 'updating'}
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium border border-slate-700/60 disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={15} className={checking ? 'animate-spin' : ''} />
          {tx("Check for updates")}
        </button>
      </div>

      {/* Notifications / Feedback */}
      {message && (
        <div className={`p-4 rounded-lg border text-sm flex items-center gap-2.5 ${
          message.type === 'error' ? 'bg-red-950/40 border-red-800 text-red-200' :
          message.type === 'info' ? 'bg-sky-950/40 border-sky-800 text-sky-200' :
          'bg-emerald-950/40 border-emerald-800 text-emerald-200'
        }`}>
          {message.type === 'error' ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
          <span>{message.text}</span>
        </div>
      )}

      {/* Host Docker Engine Audit Banner */}
      {dockerInfo?.needs_host_update && (
        <div className="p-4 rounded-lg bg-amber-950/40 border border-amber-800 text-amber-200 space-y-2">
          <div className="flex items-center gap-2 font-semibold text-sm">
            <Server size={17} className="text-amber-400" />
            <span>{tx("Host Docker engine is outdated")}</span>
          </div>
          <p className="text-xs text-amber-300/90 leading-relaxed">
            {tx("Your host server is running Docker {version}. OpenOptOut requires Docker 24 or newer for isolated in-memory tmpfs mounts and sandboxed workers. Please update the Docker package on your host server.", { version: dockerInfo.version })}
          </p>
        </div>
      )}

      {/* Progress State Banner */}
      {data?.state === 'draining' && (
        <div className="p-4 rounded-lg bg-amber-950/40 border border-amber-800 text-amber-200 flex items-center gap-3">
          <RefreshCw size={18} className="animate-spin text-amber-400" />
          <div className="text-sm">
            <span className="font-semibold">{tx("Preparing update:")} </span>
            <span>{data.state_message || tx("Pausing active removals and draining worker fleet...")}</span>
          </div>
        </div>
      )}

      {data?.state === 'updating' && (
        <div className="p-4 rounded-lg bg-sky-950/40 border border-sky-800 text-sky-200 flex items-center gap-3">
          <RefreshCw size={18} className="animate-spin text-sky-400" />
          <div className="text-sm">
            <span className="font-semibold">{tx("Applying update:")} </span>
            <span>{data.state_message || tx("Pulling containers and applying update...")}</span>
          </div>
        </div>
      )}

      {data?.state === 'reverting' && (
        <div className="p-4 rounded-lg bg-amber-950/40 border border-amber-800 text-amber-200 flex items-center gap-3">
          <RefreshCw size={18} className="animate-spin text-amber-400" />
          <div className="text-sm">
            <span className="font-semibold">{tx("Reverting update:")} </span>
            <span>{data.state_message || tx("Reverting to previous release and verifying application health...")}</span>
          </div>
        </div>
      )}

      {data?.state === 'reverted' && (
        <div className="p-4 rounded-lg bg-amber-950/40 border border-amber-800 text-amber-200 flex items-center gap-3">
          <AlertTriangle size={18} className="text-amber-400" />
          <div className="text-sm">
            <span className="font-semibold">{tx("Update reverted:")} </span>
            <span>{data.state_message || tx("The update was automatically reverted to the previous release.")}</span>
          </div>
        </div>
      )}

      {/* Status Overview Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">{tx("Current version")}</p>
          <p className="text-lg font-bold text-white mt-1">v{data?.current_version || 'unknown'}</p>
          {dockerInfo?.available && (
            <p className="text-xs text-slate-500 mt-2 flex items-center gap-1">
              <Server size={12} />
              <span>{tx("Docker engine:")} {dockerInfo.version}</span>
            </p>
          )}
        </div>

        <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">{tx("Latest release")}</p>
          <p className="text-lg font-bold text-white mt-1">
            {latest?.tag_name ? latest.tag_name : tx("Up to date")}
          </p>
          <p className="text-xs text-slate-500 mt-2 flex items-center gap-1">
            <Clock size={12} />
            <span>{tx("Last checked:")} {data?.last_checked ? fmtDateTime(data.last_checked) : tx("Never")}</span>
          </p>
        </div>

        <div className="p-4 rounded-lg bg-slate-900 border border-slate-800">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">{tx("Update policy")}</p>
          <p className="text-lg font-bold text-shield-400 mt-1 capitalize">
            {policy === 'approval_required' ? tx("Approval required") :
             policy === 'notify_only' ? tx("Notification only") :
             policy === 'auto_install' ? tx("Automatic install") :
             tx("Disabled")}
          </p>
          <p className="text-xs text-slate-500 mt-2 capitalize">
            {channel === 'pre_release' ? tx("Pre-release channel") : tx("Stable channel")}
          </p>
          {policy === 'auto_install' && data?.next_window && (
            <p className="text-xs text-slate-400 mt-1.5 flex items-center gap-1 truncate" title={fmtDateTime(data.next_window)}>
              <Clock size={11} className="shrink-0 text-shield-400" />
              <span>{fmtDateTime(data.next_window)}</span>
            </p>
          )}
        </div>
      </div>

      {/* New Update Available Card */}
      {hasUpdate && latest && (
        <div className="p-5 rounded-lg bg-slate-900 border border-shield-500/40 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <span className="p-2 rounded-full bg-shield-500/10 text-shield-400">
                <ArrowUpCircle size={22} />
              </span>
              <div>
                <h2 className="text-base font-semibold text-white">
                  {tx("A new version ({v}) is available!", { v: latest.tag_name })}
                </h2>
                {latest.published_at && (
                  <p className="text-xs text-slate-400 mt-0.5">
                    {tx("Published:")} {fmtDateTime(latest.published_at)}
                  </p>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => handleIgnore(latest.tag_name)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition-colors"
                title={tx("Ignore this release")}
              >
                <EyeOff size={14} />
                {tx("Ignore this release")}
              </button>
              <button
                onClick={handleApplyUpdate}
                disabled={applying || data?.state === 'draining' || data?.state === 'updating'}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-shield-600 hover:bg-shield-500 text-white text-sm font-medium transition-colors shadow-sm disabled:opacity-50"
              >
                <ArrowUpCircle size={16} className={applying ? 'animate-spin' : ''} />
                {tx("Install update")}
              </button>
            </div>
          </div>

          {latest.body && (
            <div className="mt-3 p-3.5 rounded-md bg-slate-950/70 border border-slate-800/80 text-xs text-slate-300 space-y-1.5">
              <div className="flex items-center justify-between font-semibold text-slate-400 mb-1">
                <span>{tx("Release notes")}</span>
                {latest.html_url && (
                  <a
                    href={latest.html_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-shield-400 hover:underline"
                  >
                    <span>{tx("View on GitHub")}</span>
                    <ExternalLink size={12} />
                  </a>
                )}
              </div>
              <div className="whitespace-pre-wrap font-sans text-slate-300 leading-relaxed max-h-48 overflow-y-auto pe-2">
                {latest.body}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Ignored Release Banner */}
      {isIgnored && latest && (
        <div className="p-4 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5 text-sm text-slate-400">
            <EyeOff size={16} className="text-slate-500" />
            <span>{tx("This release ({v}) is currently ignored.", { v: latest.tag_name })}</span>
          </div>
          <button
            onClick={() => handleUnignore(latest.tag_name)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition-colors"
          >
            <Eye size={14} />
            {tx("Unignore release")}
          </button>
        </div>
      )}

      {/* Previous Version Snapshot / Rollback Card */}
      {data?.can_rollback && data?.rollback_info && (
        <div className="p-4 rounded-lg bg-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
          <div className="space-y-1">
            <p className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <RotateCcw size={16} className="text-amber-400" />
              {tx("Previous version snapshot")}
            </p>
            <p className="text-xs text-slate-400">
              {tx("Safety snapshot available for {version}. You can revert if you encounter issues.", { version: data.rollback_info.previous_version })}
            </p>
          </div>
          <button
            onClick={handleRollback}
            disabled={rollingBack || data?.state === 'draining' || data?.state === 'updating' || data?.state === 'reverting'}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-amber-900/30 hover:bg-amber-900/50 text-amber-200 text-xs font-medium border border-amber-800/60 transition-colors disabled:opacity-50"
          >
            <RotateCcw size={14} className={rollingBack ? 'animate-spin' : ''} />
            {tx("Revert to {version}", { version: data.rollback_info.previous_version })}
          </button>
        </div>
      )}

      {/* Policy Configuration Form */}
      <div className="p-5 rounded-lg bg-slate-900 border border-slate-800 space-y-4">
        <div className="flex items-center gap-2 font-semibold text-white text-base">
          <Settings2 size={18} className="text-shield-400" />
          <span>{tx("Automatic updater settings")}</span>
        </div>
        <p className="text-xs text-slate-400 leading-relaxed">
          {tx("Configure how OpenOptOut discovers and installs updates. When an install begins, all background broker removals are paused safely until workers finish their current tasks.")}
        </p>

        <div className="space-y-3 pt-2">
          {/* Policy Option: approval_required */}
          <label className="flex items-start gap-3 p-3 rounded-lg border border-slate-800 bg-slate-950/40 hover:bg-slate-950/80 cursor-pointer transition-colors">
            <input
              type="radio"
              name="policy"
              value="approval_required"
              checked={policy === 'approval_required'}
              onChange={(e) => setPolicy(e.target.value)}
              className="mt-1 text-shield-600 focus:ring-shield-500 bg-slate-900 border-slate-700"
            />
            <div>
              <p className="text-sm font-medium text-white">
                {tx("Download and notify (require install approval)")}
              </p>
              <p className="text-xs text-slate-400 mt-0.5">
                {tx("Checks for new releases automatically, notifies administrators, but waits for approval before installing.")}
              </p>
            </div>
          </label>

          {/* Policy Option: notify_only */}
          <label className="flex items-start gap-3 p-3 rounded-lg border border-slate-800 bg-slate-950/40 hover:bg-slate-950/80 cursor-pointer transition-colors">
            <input
              type="radio"
              name="policy"
              value="notify_only"
              checked={policy === 'notify_only'}
              onChange={(e) => setPolicy(e.target.value)}
              className="mt-1 text-shield-600 focus:ring-shield-500 bg-slate-900 border-slate-700"
            />
            <div>
              <p className="text-sm font-medium text-white">
                {tx("Notification only")}
              </p>
              <p className="text-xs text-slate-400 mt-0.5">
                {tx("Notifies administrators when a release is available without staging container downloads.")}
              </p>
            </div>
          </label>

          {/* Policy Option: auto_install */}
          <div>
            <label className="flex items-start gap-3 p-3 rounded-lg border border-slate-800 bg-slate-950/40 hover:bg-slate-950/80 cursor-pointer transition-colors">
              <input
                type="radio"
                name="policy"
                value="auto_install"
                checked={policy === 'auto_install'}
                onChange={(e) => setPolicy(e.target.value)}
                className="mt-1 text-shield-600 focus:ring-shield-500 bg-slate-900 border-slate-700"
              />
              <div>
                <p className="text-sm font-medium text-white">
                  {tx("Automatic install")}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {tx("Automatically pauses active removal jobs, drains background workers, and applies updates during scheduled maintenance.")}
                </p>
              </div>
            </label>

            {policy === 'auto_install' && (
              <div className="ms-6 mt-2 p-4 rounded-lg bg-slate-950/70 border border-slate-800 space-y-3.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
                    <Clock size={14} className="text-shield-400" />
                    <span>{tx("Check and install window")}</span>
                  </div>
                  {data?.in_update_window && (
                    <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-700/60">
                      {tx("Window currently active")}
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">{tx("Schedule frequency")}</label>
                    <select
                      value={scheduleType}
                      onChange={(e) => setScheduleType(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-shield-500"
                    >
                      <option value="weekly">{tx("Every week (select days)")}</option>
                      <option value="monthly">{tx("Every month (select day)")}</option>
                    </select>
                  </div>

                  {scheduleType === 'monthly' ? (
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">{tx("Day of the month")}</label>
                      <select
                        value={scheduleDayOfMonth}
                        onChange={(e) => setScheduleDayOfMonth(parseInt(e.target.value, 10))}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-shield-500"
                      >
                        {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                          <option key={d} value={d}>
                            {tx("Day {day} of the month", { day: d })}
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">{tx("Days of the week")}</label>
                      <div className="flex flex-wrap gap-1">
                        {[
                          { index: 0, label: tx("Mon") },
                          { index: 1, label: tx("Tue") },
                          { index: 2, label: tx("Wed") },
                          { index: 3, label: tx("Thu") },
                          { index: 4, label: tx("Fri") },
                          { index: 5, label: tx("Sat") },
                          { index: 6, label: tx("Sun") },
                        ].map(({ index, label }) => {
                          const active = scheduleWeekdays.includes(index)
                          return (
                            <button
                              key={index}
                              type="button"
                              onClick={() => toggleWeekday(index)}
                              className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
                                active
                                  ? 'bg-shield-600 text-white'
                                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200'
                              }`}
                            >
                              {label}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-800/80">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">{tx("Install start time")}</label>
                    <input
                      type="time"
                      value={scheduleTime}
                      onChange={(e) => setScheduleTime(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-shield-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-slate-400 mb-1">{tx("Window duration")}</label>
                    <select
                      value={scheduleWindowHours}
                      onChange={(e) => setScheduleWindowHours(parseInt(e.target.value, 10))}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-shield-500"
                    >
                      <option value={1}>{tx("1 hour")}</option>
                      <option value={2}>{tx("2 hours")}</option>
                      <option value={3}>{tx("3 hours")}</option>
                      <option value={4}>{tx("4 hours")}</option>
                      <option value={6}>{tx("6 hours")}</option>
                    </select>
                  </div>
                </div>

                {data?.next_window && (
                  <p className="text-xs text-slate-400 flex items-center gap-1.5 pt-1">
                    <Clock size={12} className="text-shield-400 shrink-0" />
                    <span>
                      {tx("Next scheduled check and install window: {time}", {
                        time: fmtDateTime(data.next_window),
                      })}
                    </span>
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Policy Option: disabled */}
          <label className="flex items-start gap-3 p-3 rounded-lg border border-slate-800 bg-slate-950/40 hover:bg-slate-950/80 cursor-pointer transition-colors">
            <input
              type="radio"
              name="policy"
              value="disabled"
              checked={policy === 'disabled'}
              onChange={(e) => setPolicy(e.target.value)}
              className="mt-1 text-shield-600 focus:ring-shield-500 bg-slate-900 border-slate-700"
            />
            <div>
              <p className="text-sm font-medium text-white">
                {tx("Disabled (ignore all new releases)")}
              </p>
              <p className="text-xs text-slate-400 mt-0.5">
                {tx("Turns off automated checks and ignores all new releases.")}
              </p>
            </div>
          </label>
        </div>

        {/* Channel Selection */}
        <div className="pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="text-xs font-medium text-slate-300">{tx("Release channel:")}</span>
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-shield-500"
            >
              <option value="stable">{tx("Stable releases only")}</option>
              <option value="pre_release">{tx("Include pre-releases (testing)")}</option>
            </select>
          </div>

          <button
            onClick={handleSavePolicy}
            disabled={savingPolicy}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-shield-600 hover:bg-shield-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
          >
            <ShieldCheck size={14} />
            {savingPolicy ? tx("Saving…") : tx("Save settings")}
          </button>
        </div>
      </div>
    </div>
  )
}

