import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Puzzle, RefreshCw, Upload, Shield, AlertTriangle, CheckCircle2,
  XCircle, Play, Square, Trash2, ChevronDown, ChevronRight,
  Lock, Cpu, Activity, FileWarning, Info, Package, Ban, Eye, ShieldAlert, ShieldCheck, Globe, BookOpen,
  Download, ArrowUpCircle, ExternalLink, Search, Sparkles
} from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'
import PluginUploadWizard from '../components/PluginUploadWizard'
import Markdown from '../components/Markdown'
import { tx, txn, txr } from '../i18n/tx'
import { fmtDateTime } from '../i18n/format'
import { detailText } from '../errorMessage'

const inp = "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-hidden focus:border-shield-500"

const RISK_STYLES = {
  high:   { badge: 'bg-red-900/30 text-red-300 border-red-800',       dot: 'bg-red-400' },
  medium: { badge: 'bg-amber-900/30 text-amber-300 border-amber-800', dot: 'bg-amber-400' },
  low:    { badge: 'bg-slate-800 text-slate-400 border-slate-700',    dot: 'bg-slate-500' },
}

const STATUS_STYLES = {
  running:  { label: tx("Running"),  cls: 'text-emerald-400', dot: 'bg-emerald-400' },
  stopped:  { label: tx("Stopped"),  cls: 'text-slate-400',   dot: 'bg-slate-500' },
  data:     { label: tx("Enabled (data only)"), cls: 'text-emerald-400', dot: 'bg-emerald-400' },
  starting: { label: tx("Starting"), cls: 'text-blue-400',    dot: 'bg-blue-400 animate-pulse' },
  crashed:  { label: tx("Crashed"),  cls: 'text-red-400',     dot: 'bg-red-400' },
  disabled: { label: tx("Disabled"), cls: 'text-amber-400',   dot: 'bg-amber-400' },
}

// ── Sandbox posture banner ────────────────────────────────────────────────────
function SandboxBanner({ status }) {
  if (!status?.active) {
    return (
      <div className="flex items-start gap-2 px-4 py-3 rounded-xl border border-amber-800 bg-amber-900/10 mb-5">
        <Ban size={15} className="text-amber-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-amber-300 text-sm font-medium">{tx("Plugin system not active")}</p>
          <p className="text-amber-500/80 text-xs mt-0.5">
            {status?.reason || tx("Turn it on in Settings → Plugins, then restart OpenOptOut. (The server also needs the gRPC package, which the standard install includes.)")}
          </p>
        </div>
      </div>
    )
  }
  const full = status.sandbox?.posture === 'full'
  return (
    <div className={`flex items-start gap-2 px-4 py-3 rounded-xl border mb-5 ${full ? 'border-emerald-800 bg-emerald-900/10' : 'border-amber-800 bg-amber-900/10'}`}>
      <Shield size={15} className={`${full ? 'text-emerald-400' : 'text-amber-400'} shrink-0 mt-0.5`} />
      <div className="flex-1">
        <p className={`text-sm font-medium ${full ? 'text-emerald-300' : 'text-amber-300'}`}>
          {tx("Sandbox:")}{" "}{full ? tx("Full isolation active") : tx("Partial isolation")}
        </p>
        <p className={`text-xs mt-0.5 ${full ? 'text-emerald-500/80' : 'text-amber-500/80'}`}>
          {tx("Controls: {v} · Platform: {platform}", { v: status.sandbox?.controls || 'none', platform: status.sandbox?.platform })}
          {!full && tx("— untrusted third-party plugins are NOT fully contained. Deploy on Linux with bubblewrap for full isolation.")}
        </p>
      </div>
    </div>
  )
}

// ── Monitor + lockdown status banner ──────────────────────────────────────────
function MonitorBanner({ status }) {
  if (!status?.active) return null
  const mon = status.monitor || {}
  const lockdown = status.lockdown_mode
  const fullDetect = mon.proc_inspection
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
      <div className={`flex items-start gap-2 px-4 py-3 rounded-xl border ${fullDetect ? 'border-slate-700 bg-slate-800/40' : 'border-amber-800 bg-amber-900/10'}`}>
        <Eye size={15} className={`${fullDetect ? 'text-slate-400' : 'text-amber-400'} shrink-0 mt-0.5`} />
        <div>
          <p className="text-slate-200 text-sm font-medium">{tx("Runtime monitor")}</p>
          <p className="text-slate-500 text-xs mt-0.5">
            {fullDetect
              ? tx("Watching for process spawns, external file writes, network sockets, and memory abuse.")
              : (mon.note || tx("Limited detection on this host — run only trusted plugins."))}
          </p>
        </div>
      </div>
      <div className={`flex items-start gap-2 px-4 py-3 rounded-xl border ${lockdown ? 'border-amber-700 bg-amber-900/15' : 'border-slate-700 bg-slate-800/40'}`}>
        <ShieldAlert size={15} className={`${lockdown ? 'text-amber-400' : 'text-slate-500'} shrink-0 mt-0.5`} />
        <div>
          <p className="text-slate-200 text-sm font-medium">
            {tx("Lockdown mode {v}", { v: lockdown ? 'ON' : 'off' })}
          </p>
          <p className="text-slate-500 text-xs mt-0.5">
            {lockdown
              ? tx("If a plugin breaks a single rule, it's switched off straight away.")
              : tx("Plugins that break a rule are switched off. For the strictest setting, turn on lockdown in Settings.")}
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Violations feed ───────────────────────────────────────────────────────────
const SEVERITY_STYLES = {
  critical: 'border-red-800 bg-red-900/15 text-red-300',
  high:     'border-orange-800 bg-orange-900/15 text-orange-300',
  medium:   'border-amber-800 bg-amber-900/10 text-amber-300',
}

function ViolationsFeed({ violations }) {
  if (!violations || violations.length === 0) return null
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle size={14} className="text-red-400" />
        <p className="text-slate-300 text-xs font-medium uppercase tracking-wide">
          {tx("Security violations ({length})", { length: violations.length })}
        </p>
      </div>
      <div className="space-y-2">
        {violations.map((v, i) => {
          const sev = SEVERITY_STYLES[v.severity] || SEVERITY_STYLES.medium
          return (
            <div key={i} className={`flex items-start gap-3 px-4 py-2.5 rounded-lg border ${sev}`}>
              <FileWarning size={13} className="shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium">{v.plugin_id}</span>
                  <span className="text-xs opacity-80">· {v.label}</span>
                  <span className="text-[10px] uppercase px-1.5 py-0.5 rounded-sm border border-current/30">{v.severity}</span>
                </div>
                <p className="text-xs opacity-75 mt-0.5 font-mono break-all">{v.detail}</p>
                {v.action_taken && (
                  <p className="text-[11px] opacity-70 mt-0.5">{tx("Action:")}{" "}{v.action_taken.replace('_', ' ')}</p>
                )}
              </div>
              <span className="text-[11px] opacity-60 shrink-0">{fmtDateTime(v.created_at)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Permission chip ───────────────────────────────────────────────────────────
function PermChip({ perm, info, granted }) {
  const meta = info?.[perm] || { label: perm, risk: 'low', description: '' }
  const s = RISK_STYLES[meta.risk] || RISK_STYLES.low
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-sm border text-xs ${s.badge} ${granted === false ? 'opacity-40' : ''}`}
      title={meta.description}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {meta.label}
    </span>
  )
}

// ── Enable modal (permission grant) ───────────────────────────────────────────
function EnableModal({ plugin, permInfo, onClose, onEnabled }) {
  // Start with all requested permissions checked; admin can uncheck, but
  // hook-required perms will be validated server-side.
  const [granted, setGranted] = useState(new Set(plugin.permissions_requested))
  const [saving, setSaving]   = useState(false)
  const [error, setError]     = useState('')
  const [confirmPiiNetwork, setConfirmPiiNetwork] = useState(false)

  const toggle = (p) => {
    setGranted(prev => {
      const next = new Set(prev)
      next.has(p) ? next.delete(p) : next.add(p)
      return next
    })
  }

  // The one combination that can exfiltrate member data. Blocked by default —
  // only reachable if the manifest itself declared the narrow exception.
  const wantsPiiNetwork = granted.has('read_pii') && granted.has('network')
  // A CAPTCHA solver with network reaches an OUTSIDE service (sends the challenge
  // + page context off-box). Without network it's a LOCAL solver — safe. Surface
  // the distinction so the operator chooses knowingly.
  const captchaWithNetwork = granted.has('solve_captcha') && granted.has('network')
  const captchaLocalOnly   = granted.has('solve_captcha') && !granted.has('network')
  const manifestAllowsException = plugin.requires_pii_network_exception
  const piiNetworkBlocked = wantsPiiNetwork && !manifestAllowsException

  const enable = async () => {
    setSaving(true); setError('')
    try {
      await api.post(`/plugins/${plugin.plugin_id}/enable`, {
        granted_permissions: [...granted],
        acknowledge_methods: true,   // admin has reviewed the declared method list below
        confirm_pii_network_exception: wantsPiiNetwork ? confirmPiiNetwork : false,
      })
      onEnabled()
    } catch (e) {
      setError(detailText(e) || tx("Couldn't turn the plugin on. Please try again."))
    } finally { setSaving(false) }
  }

  const hasHigh = plugin.permissions_requested.some(p => (permInfo?.[p]?.risk === 'high'))
  const canSubmit = !piiNetworkBlocked && (!wantsPiiNetwork || confirmPiiNetwork)

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-slate-900 rounded-2xl border border-slate-700 max-w-lg w-full max-h-[85vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-slate-700/50">
          <h3 className="text-white font-semibold">{tx("Enable")}{" "}{plugin.name}</h3>
          <p className="text-slate-500 text-xs mt-0.5">{tx("v{version} ·", { version: plugin.version })}{" "}{plugin.author}</p>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* Trust warning */}
          <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg border border-amber-800 bg-amber-900/10">
            <AlertTriangle size={13} className="text-amber-400 shrink-0 mt-0.5" />
            <p className="text-amber-300/90 text-xs">
              {tx("Enabling runs this plugin's code in a sandboxed subprocess. You are trusting the author. Only enable plugins from sources you trust, and grant the fewest permissions needed.")}
              {hasHigh && tx("This plugin requests HIGH-RISK permissions — review them carefully.")}
            </p>
          </div>

          <div>
            <p className="text-slate-400 text-xs font-medium uppercase tracking-wide mb-2">{tx("Requested permissions")}</p>
            <div className="space-y-1.5">
              {plugin.permissions_requested.map(p => {
                const meta = permInfo?.[p] || { label: p, risk: 'low', description: '' }
                const s = RISK_STYLES[meta.risk] || RISK_STYLES.low
                return (
                  <label key={p} className="flex items-start gap-2.5 px-3 py-2 rounded-lg border border-slate-700/50 bg-slate-800/50 cursor-pointer hover:border-slate-600">
                    <input type="checkbox" checked={granted.has(p)} onChange={() => toggle(p)}
                      className="mt-0.5 w-3.5 h-3.5 rounded-sm accent-shield-500" />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-slate-200 text-sm">{meta.label}</span>
                        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm border text-[10px] uppercase ${s.badge}`}>
                          {meta.risk}
                        </span>
                      </div>
                      <p className="text-slate-500 text-xs mt-0.5">{meta.description}</p>
                    </div>
                  </label>
                )
              })}
            </div>
            <p className="text-slate-600 text-xs mt-2">
              {tx("Hooks this plugin declares ({v}) require their matching permissions — unchecking those will be rejected.", { v: plugin.hooks.join(', ') || 'none' })}
            </p>
          </div>

          {/* Declared API access — the exact host methods the plugin may call. */}
          <div>
            <p className="text-slate-400 text-xs font-medium uppercase tracking-wide mb-2">
              {tx("Declared API access")}
            </p>
            <p className="text-slate-500 text-xs mb-2">
              {tx("This plugin may ONLY call the host methods it declares below. If it attempts any other method, it is flagged as a violation, disabled immediately, and cannot run again until you re-approve it.")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {(plugin.methods && plugin.methods.length > 0)
                ? plugin.methods.map(m => (
                    <span key={m} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-sm border border-slate-700 bg-slate-800 text-slate-300 text-xs font-mono">
                      <Lock size={10} className="text-slate-500" /> {m}
                    </span>
                  ))
                : <span className="text-slate-600 text-xs">{tx("No host methods declared (cannot call storage, settings, log, or events).")}</span>
              }
            </div>

            {plugin.events && plugin.events.length > 0 && (
              <div className="mt-3">
                <p className="text-slate-500 text-xs mb-1">{tx("Event types it expects to receive:")}</p>
                <div className="flex flex-wrap gap-1.5">
                  {plugin.events.map(ev => (
                    <span key={ev} className="px-2 py-0.5 rounded-sm border border-slate-700 bg-slate-800 text-slate-400 text-xs font-mono">{ev}</span>
                  ))}
                </div>
              </div>
            )}

            {plugin.outbound_domains && plugin.outbound_domains.length > 0 && (
              <div className="mt-3">
                <p className="text-red-400/80 text-xs mb-1 flex items-center gap-1">
                  <Globe size={11} />{" "}{tx("Declared outbound domains (network egress):")}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {plugin.outbound_domains.map(d => (
                    <span key={d} className="px-2 py-0.5 rounded-sm border border-red-800/50 bg-red-900/10 text-red-300 text-xs font-mono">{d}</span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {plugin.needs_reapproval && (
            <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg border border-red-800 bg-red-900/15">
              <ShieldAlert size={13} className="text-red-400 shrink-0 mt-0.5" />
              <p className="text-red-300/90 text-xs">
                {tx("This plugin was disabled for calling a host method it had NOT declared. Re-enabling means you have reviewed its declared API access above and accept it. Enabling here re-approves the current manifest.")}
              </p>
            </div>
          )}

          {/* read_pii + network is blocked by default — the one combination that can
              exfiltrate member data. Only reachable if the manifest declared the
              narrow exception; even then it requires a SEPARATE typed confirmation. */}
          {wantsPiiNetwork && (
            <div className="rounded-lg border-2 border-red-700 bg-red-950/40 overflow-hidden">
              <div className="flex items-start gap-2 px-3 py-2.5 bg-red-900/30">
                <ShieldAlert size={15} className="text-red-400 shrink-0 mt-0.5" />
                <p className="text-red-200 text-sm font-medium">
                  {tx("Read PII + Network — the exfiltration-risk combination")}
                </p>
              </div>
              <div className="px-3 py-3 space-y-2.5">
                {piiNetworkBlocked ? (
                  <p className="text-red-300 text-xs">
                    {txr("<0>Blocked.</0> This plugin's manifest did not declare the narrow exception for requesting both permissions together. It cannot be granted — the plugin author must update the manifest to request this exception with a written justification before you can consider granting it. Uncheck one of \"Read personal data\" or \"Network access\" to proceed without this combination.", [<strong />])}
                  </p>
                ) : (
                  <>
                    <p className="text-red-300/90 text-xs">
                      {txr("This plugin can see member data <0>and</0> reach the network — the only combination in the plugin system that can send that data somewhere. The author declared a narrow exception with the justification below.", [<em />])}
                    </p>
                    <div className="px-2.5 py-2 rounded-sm bg-slate-900/60 border border-red-900/50">
                      <p className="text-slate-400 text-[11px] uppercase tracking-wide mb-1">{tx("Author's justification")}</p>
                      <p className="text-slate-300 text-xs">{plugin.pii_network_justification || tx("(none provided)")}</p>
                    </div>
                    <div className="px-2.5 py-2 rounded-sm bg-slate-900/60 border border-red-900/50">
                      <p className="text-slate-400 text-[11px] uppercase tracking-wide mb-1">{tx("Declared outbound domains")}</p>
                      <p className="text-slate-300 text-xs font-mono">{(plugin.outbound_domains || []).join(', ') || '(none)'}</p>
                    </div>
                    <p className="text-red-300/80 text-xs">
                      {txr("If granted, this plugin runs under <0>heavy monitoring</0>: tighter network-socket tolerance and continuous egress byte-volume tracking, with immediate disable if it sends more than a few MB or contacts anything outside the domains above.", [<strong />])}
                    </p>
                    <label className="flex items-start gap-2.5 pt-1 cursor-pointer">
                      <input type="checkbox" checked={confirmPiiNetwork}
                        onChange={e => setConfirmPiiNetwork(e.target.checked)}
                        className="mt-0.5 w-3.5 h-3.5 rounded-sm accent-red-500" />
                      <span className="text-red-200 text-xs">
                        {tx("I understand this plugin will be able to see member personal data and send it over the network, and I accept the justification above. Grant this specific combination.")}
                      </span>
                    </label>
                  </>
                )}
              </div>
            </div>
          )}

          {/* CAPTCHA solver: local (safe) vs. network (sends challenge off-box). */}
          {captchaWithNetwork && (
            <div className="rounded-lg border border-amber-700 bg-amber-950/30 px-3 py-3">
              <div className="flex items-start gap-2">
                <ShieldAlert size={14} className="text-amber-400 shrink-0 mt-0.5" />
                <div className="text-amber-200 text-xs space-y-1">
                  <p className="font-medium">{tx("Remote CAPTCHA solver (uses the network)")}</p>
                  <p className="text-amber-300/90">
                    {txr("This solver has network access, so it sends CAPTCHA challenges — and possibly page context — to an outside service to be solved. That data leaves your server. Declared outbound domains: <0/>. A <1>local</1> solver (one without network access) keeps everything on-box and leaks nothing — prefer that when possible.", [<span className="font-mono">{(plugin.outbound_domains || []).join(', ') || '(none)'}</span>, <strong />])}
                  </p>
                </div>
              </div>
            </div>
          )}
          {captchaLocalOnly && (
            <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/20 px-3 py-2.5">
              <div className="flex items-start gap-2">
                <ShieldCheck size={14} className="text-emerald-400 shrink-0 mt-0.5" />
                <p className="text-emerald-200/90 text-xs">
                  {txr("<0>Local CAPTCHA solver.</0> This solver has no network access, so it runs entirely on your server (a bundled model or a local human-in-the-loop) — nothing about the challenge leaves your system.", [<span className="font-medium" />])}
                </p>
              </div>
            </div>
          )}

          {error && (
            <div className="px-3 py-2 rounded-lg border border-red-800 bg-red-900/20 text-red-300 text-xs">
              {error}
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-slate-700/50 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-slate-400 hover:text-slate-200">{tx("Cancel")}</button>
          <button onClick={enable} disabled={saving || !canSubmit}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-sm rounded-lg">
            {saving ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
            {saving ? tx("Enabling…") : tx("Grant & enable")}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Plugin card ───────────────────────────────────────────────────────────────
function PluginCard({ plugin, permInfo, onEnable, onDisable, onUninstall, onViewAudit, canManage }) {
  const [expanded, setExpanded] = useState(false)
  const st = STATUS_STYLES[plugin.status] || STATUS_STYLES.stopped

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-slate-700/50 flex items-center justify-center shrink-0">
              <Puzzle size={16} className="text-shield-400" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-slate-100 text-sm font-medium truncate">{plugin.name}</p>
                <span className="text-slate-600 text-xs">{"v"}{plugin.version}</span>
              </div>
              <p className="text-slate-500 text-xs mt-0.5 line-clamp-2">{plugin.description}</p>
              <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
                <span className={`text-xs ${st.cls}`}>{st.label}</span>
                {plugin.crash_count > 0 && (
                  <span className="text-red-400 text-xs">· {txn(plugin.crash_count, "{n} crash", "{n} crashes")}</span>
                )}
                {plugin.needs_reapproval && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm border border-red-800 bg-red-900/20 text-red-300 text-[10px]">
                    <ShieldAlert size={9} />{" "}{tx("re-approval required")}
                  </span>
                )}
                <span className="text-slate-600 text-xs">· {plugin.author}</span>
                <span className="text-slate-600 text-xs font-mono">· {plugin.type}/{plugin.plugin_id}/</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {/* Enabling, disabling and uninstalling stay with super admins. */}
            {canManage && (plugin.enabled ? (
              <button onClick={() => onDisable(plugin)}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-amber-400 border border-amber-800/50 rounded-lg hover:bg-amber-900/20">
                <Square size={11} />{" "}{tx("Disable")}
              </button>
            ) : (
              <button onClick={() => onEnable(plugin)}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-emerald-400 border border-emerald-800/50 rounded-lg hover:bg-emerald-900/20">
                <Play size={11} />{" "}{tx("Enable")}
              </button>
            ))}
            <button onClick={() => setExpanded(e => !e)}
              aria-label={expanded ? tx("Collapse plugin details") : tx("Expand plugin details")}
              className="p-1.5 text-slate-500 hover:text-slate-300">
              {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
            </button>
          </div>
        </div>

        {/* Permission chips */}
        <div className="flex flex-wrap gap-1.5 mt-3">
          {plugin.permissions_requested.map(p => (
            <PermChip key={p} perm={p} info={permInfo}
              granted={plugin.enabled ? plugin.permissions_granted.includes(p) : undefined} />
          ))}
        </div>
      </div>

      {expanded && (
        <div className="px-5 py-4 border-t border-slate-700/50 bg-slate-900/30 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <p className="text-slate-500 mb-1">{tx("Hooks")}</p>
              <p className="text-slate-300">{plugin.hooks.join(', ') || 'none'}</p>
            </div>
            <div>
              <p className="text-slate-500 mb-1">{tx("Granted permissions")}</p>
              <p className="text-slate-300">{plugin.permissions_granted.join(', ') || 'none'}</p>
            </div>
          </div>
          {plugin.last_error && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg border border-red-800/50 bg-red-900/10">
              <FileWarning size={12} className="text-red-400 shrink-0 mt-0.5" />
              <p className="text-red-300/90 text-xs font-mono">{plugin.last_error}</p>
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={() => onViewAudit(plugin)}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-slate-400 border border-slate-700 rounded-lg hover:bg-slate-700/50">
              <Activity size={11} />{" "}{tx("Audit log")}
            </button>
            {canManage && (
              <button onClick={() => onUninstall(plugin)}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-red-400 border border-red-800/50 rounded-lg hover:bg-red-900/20">
                <Trash2 size={11} />{" "}{tx("Uninstall")}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Audit modal ───────────────────────────────────────────────────────────────
function AuditModal({ plugin, onClose }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    api.get(`/plugins/${plugin.plugin_id}/audit`).then(r => setRows(r.data)).finally(() => setLoading(false))
  }, [plugin.plugin_id])
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-slate-900 rounded-2xl border border-slate-700 max-w-lg w-full max-h-[80vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-slate-700/50">
          <h3 className="text-white font-semibold">{tx("Audit log —")}{" "}{plugin.name}</h3>
        </div>
        <div className="px-5 py-4">
          {loading ? <p className="text-slate-500 text-sm">{tx("Loading…")}</p>
            : rows.length === 0 ? <p className="text-slate-500 text-sm">{tx("No audit entries.")}</p>
            : (
              <div className="space-y-1.5">
                {rows.map((r, i) => (
                  <div key={i} className="flex items-start gap-3 px-3 py-2 rounded-lg bg-slate-800/50 text-xs">
                    <span className="text-slate-300 font-mono w-32 shrink-0">{r.action}</span>
                    <span className="text-slate-500 flex-1">{r.detail}</span>
                    <span className="text-slate-600 shrink-0">{fmtDateTime(r.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
        </div>
      </div>
    </div>
  )
}

// ── Catalog Plugin Card ───────────────────────────────────────────────────────
function CatalogPluginCard({ item, onSelect, onInstall, canManage, installing }) {
  const isInstalled = item.is_installed
  const hasUpdate = item.has_update

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/60 p-4 flex flex-col justify-between hover:border-slate-600 transition-colors">
      <div>
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-slate-100 text-sm font-semibold truncate">{item.name}</p>
              <span className="text-slate-400 font-mono text-xs">{"v"}{item.version}</span>
              {item.tier === 1 && (
                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-sm border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 text-[10px] font-medium">
                  <Sparkles size={10} /> {tx("Curated")}
                </span>
              )}
            </div>
            <p className="text-slate-500 text-xs mt-0.5">
              {item.author || tx("Community")} · <span className="font-mono">{item.type}</span>
            </p>
          </div>
          {isInstalled && (
            hasUpdate ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-300 text-[11px] font-medium shrink-0">
                <ArrowUpCircle size={11} /> {tx("Update available")}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-[11px] font-medium shrink-0">
                <CheckCircle2 size={11} /> {tx("Installed")}
              </span>
            )
          )}
        </div>
        <p className="text-slate-400 text-xs line-clamp-2 mb-3">{item.description}</p>
      </div>

      <div className="flex items-center justify-between pt-3 border-t border-slate-700/50 gap-2">
        <button
          onClick={() => onSelect(item)}
          className="text-xs text-shield-400 hover:text-shield-300 font-medium py-1 px-2 rounded-md hover:bg-slate-700/50 transition-colors"
        >
          {tx("View details")}
        </button>

        {canManage && (
          isInstalled ? (
            hasUpdate && (
              <button
                onClick={() => onInstall(item, true)}
                disabled={installing}
                className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-40 rounded-lg transition-colors"
              >
                {installing ? <RefreshCw size={11} className="animate-spin" /> : <ArrowUpCircle size={11} />}
                {tx("Update")}
              </button>
            )
          ) : (
            <button
              onClick={() => onInstall(item, false)}
              disabled={installing}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-white bg-shield-600 hover:bg-shield-700 disabled:opacity-40 rounded-lg transition-colors"
            >
              {installing ? <RefreshCw size={11} className="animate-spin" /> : <Download size={11} />}
              {tx("Install")}
            </button>
          )
        )}
      </div>
    </div>
  )
}

// ── Catalog Detail Modal ──────────────────────────────────────────────────────
function CatalogDetailModal({ plugin, onClose, onInstall, canManage, installing }) {
  if (!plugin) return null

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 z-50">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-800 flex items-start justify-between gap-4 bg-slate-950/40">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2 className="text-white text-lg font-semibold truncate">{plugin.name}</h2>
              <span className="px-2 py-0.5 rounded-sm bg-slate-800 text-slate-300 text-xs font-mono">
                {"v"}{plugin.version}
              </span>
              {plugin.tier === 1 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-sm border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 text-xs font-medium">
                  <Sparkles size={11} /> {tx("Curated")}
                </span>
              )}
            </div>
            <p className="text-slate-400 text-xs mt-1">
              {tx("By {author} · Type: {type}", { author: plugin.author || tx("Community"), type: plugin.type })}
              {plugin.repo && (
                <>
                  {" · "}
                  <a
                    href={`https://github.com/${plugin.repo}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-shield-400 hover:underline"
                  >
                    {plugin.repo} <ExternalLink size={10} />
                  </a>
                </>
              )}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label={tx("Close")}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <XCircle size={20} />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          <p className="text-slate-300 text-sm leading-relaxed">{plugin.description}</p>

          {plugin.readme ? (
            <div className="pt-4 border-t border-slate-800">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                {tx("Documentation")}
              </p>
              <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 max-h-96 overflow-y-auto">
                <Markdown content={plugin.readme} />
              </div>
            </div>
          ) : (
            <div className="pt-4 border-t border-slate-800 text-center py-6 text-slate-500 text-xs">
              {tx("No additional documentation provided for this plugin.")}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/40 flex items-center justify-between gap-3">
          <span className="text-xs text-slate-500 font-mono truncate max-w-xs">
            {plugin.sha256 ? `SHA: ${plugin.sha256.substring(0, 16)}…` : ""}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-1.5 text-sm text-slate-300 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
            >
              {tx("Close")}
            </button>
            {canManage && (
              plugin.is_installed ? (
                plugin.has_update ? (
                  <button
                    onClick={() => onInstall(plugin, true)}
                    disabled={installing}
                    className="flex items-center gap-1.5 px-4 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-40 text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    {installing ? <RefreshCw size={13} className="animate-spin" /> : <ArrowUpCircle size={13} />}
                    {tx("Update to {v}", { v: plugin.version })}
                  </button>
                ) : (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                    <CheckCircle2 size={13} /> {tx("Installed")}
                  </span>
                )
              ) : (
                <button
                  onClick={() => onInstall(plugin, false)}
                  disabled={installing}
                  className="flex items-center gap-1.5 px-4 py-1.5 bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  {installing ? <RefreshCw size={13} className="animate-spin" /> : <Download size={13} />}
                  {tx("Install Plugin")}
                </button>
              )
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
const MARKET_CATEGORIES = [
  { id: 'all', label: 'All' },
  { id: 'brokers', label: 'Brokers' },
  { id: 'themes', label: 'Themes' },
  { id: 'languages', label: 'Languages' },
  { id: 'captcha', label: 'CAPTCHA' },
  { id: 'email', label: 'Email' },
]

export default function Plugins() {
  const { user } = useAuth()
  const canManage = user?.role === 'super_admin'   // install / enable / disable / uninstall
  const canUpload = can(user, 'plugins.upload')
  const [activeTab, setActiveTab] = useState('installed') // 'installed' | 'market'
  const [status, setStatus]     = useState(null)
  const [installed, setInstalled] = useState([])
  const [available, setAvailable] = useState([])
  const [permInfo, setPermInfo] = useState({})
  const [loading, setLoading]   = useState(true)
  const [enableTarget, setEnableTarget] = useState(null)
  const [auditTarget, setAuditTarget]   = useState(null)
  const [showUpload, setShowUpload] = useState(false)
  const [types, setTypes] = useState([])
  const [violations, setViolations] = useState([])

  // Marketplace state
  const [catalog, setCatalog] = useState([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState('')
  const [catalogOffline, setCatalogOffline] = useState(false)
  const [catalogCategory, setCatalogCategory] = useState('all')
  const [catalogSearch, setCatalogSearch] = useState('')
  const [detailPlugin, setDetailPlugin] = useState(null)
  const [catalogActionRunning, setCatalogActionRunning] = useState(false)
  const [catalogToast, setCatalogToast] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const [s, list, avail, perms, viol, typeList] = await Promise.all([
        api.get('/plugins/status').catch(() => ({ data: { active: false } })),
        api.get('/plugins').catch(() => ({ data: [] })),
        api.get('/plugins/available').catch(() => ({ data: [] })),
        api.get('/plugins/permissions').catch(() => ({ data: {} })),
        api.get('/plugins/violations/all?limit=50').catch(() => ({ data: [] })),
        api.get('/plugins/types').catch(() => ({ data: [] })),
      ])
      // Merge live status (running plugins) into installed rows
      const runningMap = {}
      ;(s.data?.running || []).forEach(r => { runningMap[r.plugin_id] = r })
      setStatus(s.data)
      setInstalled(list.data.map(p => ({
        ...p,
        status: runningMap[p.plugin_id] ? 'running' : p.status,
      })))
      setAvailable(avail.data)
      setPermInfo(perms.data)
      setViolations(viol.data)
      setTypes(typeList.data)
    } finally { setLoading(false) }
  }

  const loadCatalog = async (forceRefresh = false) => {
    setCatalogLoading(true)
    setCatalogError('')
    try {
      const url = `/plugins/catalog?force_refresh=${forceRefresh}`
      const res = await api.get(url)
      setCatalog(res.data?.plugins || [])
      setCatalogOffline(Boolean(res.data?.offline))
    } catch (err) {
      setCatalogError(detailText(err) || tx("Failed to load community catalog"))
    } finally {
      setCatalogLoading(false)
    }
  }

  useEffect(() => {
    load()
    loadCatalog(false)
  }, [])

  const doInstall = async (path) => {
    await api.post(`/plugins/install?path=${encodeURIComponent(path)}`)
    load()
  }
  const doDisable = async (p) => { await api.post(`/plugins/${p.plugin_id}/disable`); load() }
  const doUninstall = async (p) => {
    if (!confirm(tx("Uninstall {name}? This stops it and removes its registration.", { name: p.name }))) return
    await api.delete(`/plugins/${p.plugin_id}?remove_files=false`); load()
  }

  const doCatalogInstall = async (plugin, isUpdate = false) => {
    setCatalogActionRunning(true)
    try {
      const endpoint = isUpdate ? '/plugins/catalog/update' : '/plugins/catalog/install'
      const res = await api.post(endpoint, { plugin_id: plugin.id })
      setCatalogToast(res.data?.message || tx("Plugin operation completed successfully."))
      setTimeout(() => setCatalogToast(''), 6000)
      if (detailPlugin?.id === plugin.id) setDetailPlugin(null)
      await load()
      await loadCatalog(false)
    } catch (err) {
      alert(detailText(err) || tx("Failed to install plugin from catalog"))
    } finally {
      setCatalogActionRunning(false)
    }
  }

  // Installed plugins grouped by type, in the server's type order.
  const groups = (types.length ? types : [...new Set(installed.map(p => p.type))].map(t => ({ type: t, label: t, folder: `${t}/` })))
    .map(t => ({ ...t, plugins: installed.filter(p => p.type === t.type) }))
    .filter(g => g.plugins.length > 0)

  // Catalog filtering
  const updateCount = catalog.filter(p => p.has_update).length
  const filteredCatalog = catalog.filter(p => {
    if (catalogCategory !== 'all' && (p.type || '').toLowerCase() !== catalogCategory) return false
    if (catalogSearch.trim()) {
      const q = catalogSearch.toLowerCase()
      const n = (p.name || '').toLowerCase()
      const d = (p.description || '').toLowerCase()
      const a = (p.author || '').toLowerCase()
      const id = (p.id || '').toLowerCase()
      if (!n.includes(q) && !d.includes(q) && !a.includes(q) && !id.includes(q)) return false
    }
    return true
  })

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-xl font-semibold">{tx("Plugins")}</h1>
          <p className="text-slate-400 text-sm mt-0.5">{tx("Extend OpenOptOut with sandboxed, permission-gated plugins")}</p>
        </div>
        <div className="flex gap-2">
          <Link to="/plugin-help"
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
            <BookOpen size={13} />{" "}{tx("Docs")}
          </Link>
          {canUpload && (
            <button onClick={() => setShowUpload(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
              <Upload size={13} />{" "}{tx("Upload plugin")}
            </button>
          )}
          <button onClick={() => { load(); if (activeTab === 'market') loadCatalog(true); }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">
            <RefreshCw size={13} />{" "}{tx("Refresh")}
          </button>
        </div>
      </div>

      <SandboxBanner status={status} />
      <MonitorBanner status={status} />
      <ViolationsFeed violations={violations} />

      {/* Tabs */}
      <div className="flex border-b border-slate-700/60 mb-6 gap-2">
        <button
          onClick={() => setActiveTab('installed')}
          className={`flex items-center gap-2 pb-3 px-1 border-b-2 font-medium text-sm transition-colors ${
            activeTab === 'installed'
              ? 'border-shield-500 text-shield-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Package size={15} />
          {tx("Installed")}
          <span className="ms-1 px-1.5 py-0.5 rounded-full text-xs bg-slate-800 text-slate-300">
            {installed.length}
          </span>
        </button>
        <button
          onClick={() => setActiveTab('market')}
          className={`flex items-center gap-2 pb-3 px-1 border-b-2 font-medium text-sm transition-colors ${
            activeTab === 'market'
              ? 'border-shield-500 text-shield-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Globe size={15} />
          {tx("Community Marketplace")}
          {updateCount > 0 ? (
            <span className="ms-1 px-1.5 py-0.5 rounded-full text-[11px] bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30">
              {updateCount}
            </span>
          ) : (
            catalog.length > 0 && (
              <span className="ms-1 px-1.5 py-0.5 rounded-full text-xs bg-slate-800 text-slate-400">
                {catalog.length}
              </span>
            )
          )}
        </button>
      </div>

      {catalogToast && (
        <div className="mb-4 px-4 py-2.5 rounded-xl border border-emerald-800 bg-emerald-950/30 text-emerald-300 text-xs flex items-center justify-between">
          <span>{catalogToast}</span>
          <button onClick={() => setCatalogToast('')} className="text-emerald-400 hover:text-white ms-2 font-bold">×</button>
        </div>
      )}

      {activeTab === 'installed' ? (
        loading ? <p className="text-slate-500 text-sm">{tx("Loading…")}</p> : (
          <>
            {/* Installed */}
            <div className="mb-6">
              <p className="text-slate-400 text-xs font-medium uppercase tracking-wide mb-3">
                {tx("Installed ({length})", { length: installed.length })}
              </p>
              {installed.length === 0 ? (
                <div className="text-center py-10 border border-dashed border-slate-700 rounded-xl">
                  <Package size={24} className="text-slate-700 mx-auto mb-2" />
                  <p className="text-slate-500 text-sm">{tx("No plugins installed yet.")}</p>
                  <p className="text-slate-600 text-xs mt-1">{tx("Browse the Community Marketplace tab or upload a .zip bundle.")}</p>
                </div>
              ) : (
                <div className="space-y-5">
                  {groups.map(g => (
                    <div key={g.type}>
                      <p className="text-slate-500 text-xs mb-2">
                        {g.label} <span className="font-mono text-slate-600">{tx("· plugins/")}{g.folder}</span>
                      </p>
                      <div className="space-y-3">
                        {g.plugins.map(p => (
                          <PluginCard key={p.plugin_id} plugin={p} permInfo={permInfo}
                            onEnable={setEnableTarget} onDisable={doDisable}
                            onUninstall={doUninstall} onViewAudit={setAuditTarget} canManage={canManage} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Available (on disk, not registered) */}
            {available.length > 0 && (
              <div>
                <p className="text-slate-400 text-xs font-medium uppercase tracking-wide mb-3">
                  {tx("Discovered on disk ({length})", { length: available.length })}
                </p>
                <div className="space-y-2">
                  {available.map(p => (
                    <div key={p.plugin_id} className="flex items-center justify-between px-4 py-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-slate-200 text-sm truncate">{p.name}</p>
                          <span className="text-slate-600 text-xs">{"v"}{p.version}</span>
                          {!p.valid && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm border border-red-800 bg-red-900/20 text-red-300 text-[10px]">
                              <XCircle size={9} />{" "}{tx("invalid")}
                            </span>
                          )}
                        </div>
                        <p className="text-slate-500 text-xs mt-0.5">
                          {tx("{author} · {type_label} · {length} permissions", { author: p.author, type_label: p.type_label, length: p.permissions.length })}
                          {p.legacy_location && <span className="text-amber-300/90">{" "}{tx("· will be moved to plugins/")}{p.destination}</span>}
                        </p>
                        {!p.valid && p.errors?.length > 0 && (
                          <p className="text-red-400/80 text-xs mt-1">{p.errors.join('; ')}</p>
                        )}
                      </div>
                      {canManage && <button onClick={() => doInstall(p.path)} disabled={!p.valid}
                        className="flex items-center gap-1 px-3 py-1.5 text-xs bg-shield-600 hover:bg-shield-700 disabled:opacity-40 text-white rounded-lg shrink-0">
                        <Package size={11} />{" "}{tx("Install")}
                      </button>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )
      ) : (
        /* Marketplace Tab */
        <div className="space-y-5">
          {catalogOffline && (
            <div className="px-4 py-3 rounded-xl border border-amber-800 bg-amber-950/20 text-amber-300 text-xs flex items-center justify-between">
              <div>
                <p className="font-medium">{tx("Offline / Air-Gapped Mode")}</p>
                <p className="text-amber-400/80 mt-0.5">{tx("Showing cached community plugins. Network refresh unavailable.")}</p>
              </div>
              <button
                onClick={() => loadCatalog(true)}
                className="px-2.5 py-1 bg-amber-900/40 hover:bg-amber-800/40 border border-amber-700/50 rounded-lg text-amber-200 text-xs font-medium"
              >
                {tx("Retry")}
              </button>
            </div>
          )}

          {catalogError && (
            <div className="px-4 py-3 rounded-xl border border-red-800 bg-red-950/20 text-red-300 text-xs">
              {catalogError}
            </div>
          )}

          {/* Search & Categories Bar */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="relative flex-1">
              <Search size={14} className="absolute start-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={catalogSearch}
                onChange={e => setCatalogSearch(e.target.value)}
                placeholder={tx("Search plugins by name, author, or description…")}
                className="w-full bg-slate-800 border border-slate-700/70 rounded-lg ps-9 pe-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-hidden focus:border-shield-500"
              />
            </div>

            <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0">
              {MARKET_CATEGORIES.map(c => (
                <button
                  key={c.id}
                  onClick={() => setCatalogCategory(c.id)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                    catalogCategory === c.id
                      ? 'bg-shield-600 text-white'
                      : 'bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-700'
                  }`}
                >
                  {c.id === 'all' ? tx("All") : c.id === 'brokers' ? tx("Brokers") : c.id === 'themes' ? tx("Themes") : c.id === 'languages' ? tx("Languages") : c.id === 'captcha' ? tx("CAPTCHA") : tx("Email")}
                </button>
              ))}
            </div>
          </div>

          {/* Catalog Grid */}
          {catalogLoading ? (
            <div className="text-center py-16 text-slate-500 text-sm flex items-center justify-center gap-2">
              <RefreshCw size={15} className="animate-spin" /> {tx("Loading marketplace…")}
            </div>
          ) : filteredCatalog.length === 0 ? (
            <div className="text-center py-14 border border-dashed border-slate-700 rounded-xl">
              <Globe size={24} className="text-slate-700 mx-auto mb-2" />
              <p className="text-slate-400 text-sm">{tx("No plugins match your search or filter.")}</p>
              <button
                onClick={() => { setCatalogSearch(''); setCatalogCategory('all'); }}
                className="text-xs text-shield-400 hover:underline mt-2 inline-block"
              >
                {tx("Clear filters")}
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {filteredCatalog.map(item => (
                <CatalogPluginCard
                  key={item.id}
                  item={item}
                  onSelect={setDetailPlugin}
                  onInstall={doCatalogInstall}
                  canManage={canManage}
                  installing={catalogActionRunning}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {enableTarget && (
        <EnableModal plugin={enableTarget} permInfo={permInfo}
          onClose={() => setEnableTarget(null)}
          onEnabled={() => { setEnableTarget(null); load() }} />
      )}
      {auditTarget && (
        <AuditModal plugin={auditTarget} onClose={() => setAuditTarget(null)} />
      )}
      {showUpload && (
        <PluginUploadWizard onClose={() => setShowUpload(false)} onInstalled={load} />
      )}
      {detailPlugin && (
        <CatalogDetailModal
          plugin={detailPlugin}
          onClose={() => setDetailPlugin(null)}
          onInstall={doCatalogInstall}
          canManage={canManage}
          installing={catalogActionRunning}
        />
      )}
    </div>
  )
}
