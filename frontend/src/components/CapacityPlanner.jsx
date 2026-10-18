import { useState, useEffect, useMemo } from 'react'
import {
  Cpu, HardDrive, Gauge, Server, CheckCircle2, AlertTriangle,
  Layers, Globe, Database, ArrowUpRight, Sliders
} from 'lucide-react'
import api from '../api'
import { tx } from '../i18n/tx'
import { fmtNumber } from '../i18n/format'

const PRESETS = [
  { label: 'Household (10)', profiles: 10, brokers: 80, days: 7 },
  { label: 'Housing Authority (500)', profiles: 500, brokers: 80, days: 7 },
  { label: 'Public Library (2,500)', profiles: 2500, brokers: 80, days: 14 },
  { label: 'Consortium (10,000)', profiles: 10000, brokers: 80, days: 30 },
]

export default function CapacityPlanner({ fleetStats }) {
  const [profiles, setProfiles] = useState(500)
  const [brokers, setBrokers] = useState(80)
  const [targetDays, setTargetDays] = useState(7)
  const [usePostgres, setUsePostgres] = useState(false)
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(false)

  // Current fleet capacity from parent telemetry
  const currentSlots = fleetStats?.total_slots || 0

  // Calculate capacity plan whenever inputs change
  useEffect(() => {
    let cancelled = false
    setLoading(true)

    api.get('/workers/capacity-plan', {
      params: {
        profiles,
        brokers,
        target_days: targetDays,
        form_ratio: 0.85,
        use_postgres: usePostgres,
      }
    })
      .then((res) => {
        if (!cancelled) {
          setPlan(res.data)
        }
      })
      .catch((err) => {
        console.error('Failed to fetch capacity plan:', err)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [profiles, brokers, targetDays, usePostgres])

  const rec = plan?.recommended_profile
  const isDistributed = rec?.topology === 'distributed'
  const deficit = plan?.current_fleet_deficit_slots ?? (currentSlots > 0 ? Math.max(0, (plan?.required_slots || 1) - currentSlots) : null)
  const isSufficient = currentSlots > 0 && (currentSlots >= (plan?.required_slots || 1))

  return (
    <div className="space-y-6">
      {/* Intro Banner */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Sliders size={18} className="text-shield-400" />
              {tx("Infrastructure Capacity Planner")}
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              {tx("Estimate empirical hardware, concurrency, tmpfs RAM, and bandwidth requirements based on community size and completion deadlines.")}
            </p>
          </div>

          {/* Quick Presets */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold me-1">
              {tx("Presets:")}
            </span>
            {PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => {
                  setProfiles(p.profiles)
                  setBrokers(p.brokers)
                  setTargetDays(p.days)
                }}
                className={`text-xs px-2.5 py-1 rounded-md transition-colors border ${
                  profiles === p.profiles && brokers === p.brokers && targetDays === p.days
                    ? 'bg-shield-600/30 border-shield-500 text-shield-300 font-medium'
                    : 'bg-slate-800/60 border-slate-700/60 text-slate-300 hover:bg-slate-700/60'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Grid: Inputs on Left, Results on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Workload Inputs */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-5">
          <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2 border-b border-slate-800 pb-3">
            <Sliders size={15} className="text-indigo-400" />
            {tx("Workload Parameters")}
          </h3>

          {/* Profiles Input */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <label htmlFor="cap-profiles" className="text-slate-300 font-medium">
                {tx("Family / Patron Profiles")}
              </label>
              <span className="text-shield-400 font-bold font-mono">
                {fmtNumber(profiles)}
              </span>
            </div>
            <input
              id="cap-profiles"
              type="range"
              min="1"
              max="10000"
              step={profiles < 100 ? 5 : profiles < 1000 ? 25 : 100}
              value={profiles}
              onChange={(e) => setProfiles(Number(e.target.value))}
              className="w-full accent-shield-500 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-400 font-mono">
              <span>1</span>
              <span>100</span>
              <span>1,000</span>
              <span>5,000</span>
              <span>10,000</span>
            </div>
          </div>

          {/* Active Brokers Input */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <label htmlFor="cap-brokers" className="text-slate-300 font-medium">
                {tx("Active Data Brokers")}
              </label>
              <span className="text-shield-400 font-bold font-mono">
                {brokers}
              </span>
            </div>
            <input
              id="cap-brokers"
              type="range"
              min="10"
              max="120"
              step="5"
              value={brokers}
              onChange={(e) => setBrokers(Number(e.target.value))}
              className="w-full accent-shield-500 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-400 font-mono">
              <span>10</span>
              <span>40</span>
              <span>80 (Default)</span>
              <span>120</span>
            </div>
          </div>

          {/* Target Completion Window */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <label htmlFor="cap-target-days" className="text-slate-300 font-medium">
                {tx("Target Completion Window (Days)")}
              </label>
              <span className="text-shield-400 font-bold font-mono">
                {targetDays} {tx("days")} ({targetDays * 24}h)
              </span>
            </div>
            <div className="grid grid-cols-5 gap-1.5">
              {[1, 3, 7, 14, 30].map((d) => (
                <button
                  key={d}
                  onClick={() => setTargetDays(d)}
                  className={`py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                    targetDays === d
                      ? 'bg-shield-500/20 border-shield-500 text-shield-300'
                      : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          {/* Database Engine Toggle */}
          <div className="pt-2 border-t border-slate-800/80">
            <label className="flex items-center justify-between text-xs cursor-pointer text-slate-300">
              <span className="flex items-center gap-1.5">
                <Database size={14} className="text-slate-400" />
                {tx("Database Engine")}
              </span>
              <span className="text-slate-400 flex items-center gap-2">
                <span className={!usePostgres ? 'text-white font-semibold' : ''}>SQLite</span>
                <input
                  type="checkbox"
                  checked={usePostgres}
                  onChange={(e) => setUsePostgres(e.target.checked)}
                  className="rounded-sm bg-slate-800 border-slate-700 text-shield-500 focus:ring-0"
                />
                <span className={usePostgres ? 'text-white font-semibold' : ''}>PostgreSQL</span>
              </span>
            </label>
          </div>
        </div>

        {/* Output Recommendations & Sizing */}
        <div className="lg:col-span-7 space-y-6">
          {/* Top Metric Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
              <span className="text-[10px] text-slate-400 uppercase font-semibold block">{tx("Total Workload")}</span>
              <span className="text-xl font-bold text-white mt-1 block">
                {fmtNumber(plan?.total_jobs || 0)}
              </span>
              <span className="text-[10px] text-slate-400">{tx("removal jobs")}</span>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
              <span className="text-[10px] text-indigo-400 uppercase font-semibold block">{tx("Target Throughput")}</span>
              <span className="text-xl font-bold text-white mt-1 block">
                {plan?.required_throughput_per_hr || 0}
              </span>
              <span className="text-[10px] text-slate-400">{tx("removals / hr")}</span>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
              <span className="text-[10px] text-shield-400 uppercase font-semibold block">{tx("Required Slots")}</span>
              <span className="text-xl font-bold text-shield-300 mt-1 block">
                {plan?.required_slots || 1}
              </span>
              <span className="text-[10px] text-slate-400">{tx("concurrent slots")}</span>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
              <span className="text-[10px] text-emerald-400 uppercase font-semibold block">{tx("Proxy Egress")}</span>
              <span className="text-xl font-bold text-emerald-300 mt-1 block">
                ~{plan?.estimated_proxy_bandwidth_gb || 0} GB
              </span>
              <span className="text-[10px] text-slate-400">{tx("estimated traffic")}</span>
            </div>
          </div>

          {/* Recommended Hardware Architecture Card */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
              <div>
                <span className="text-xs uppercase tracking-wider font-semibold text-slate-400 block">
                  {tx("Recommended Architecture")}
                </span>
                <h4 className="text-base font-bold text-white mt-0.5">
                  {rec?.name || tx("Standalone Profile")}
                </h4>
              </div>
              <span className={`px-2.5 py-1 text-xs font-semibold rounded-md uppercase tracking-wider self-start sm:self-auto border ${
                isDistributed
                  ? 'bg-purple-950/40 border-purple-800 text-purple-300'
                  : 'bg-shield-950/40 border-shield-800 text-shield-300'
              }`}>
                {rec?.topology === 'distributed' ? tx("Distributed Cluster") : tx("Standalone Node")}
              </span>
            </div>

            <p className="text-xs text-slate-300">
              {rec?.description}
            </p>

            {/* Hardware Specifications Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
              <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
                <span className="text-[11px] text-slate-400 flex items-center gap-1 font-medium">
                  <Cpu size={13} className="text-sky-400" />
                  {tx("vCPU Cores")}
                </span>
                <span className="text-sm font-bold text-white mt-1 block">
                  {rec?.vcpu_min}–{rec?.vcpu_recommended} {tx("Cores")}
                </span>
                <span className="text-[10px] text-slate-400">
                  {isDistributed ? tx("per worker node") : tx("host machine")}
                </span>
              </div>

              <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
                <span className="text-[11px] text-slate-400 flex items-center gap-1 font-medium">
                  <Server size={13} className="text-indigo-400" />
                  {tx("System RAM")}
                </span>
                <span className="text-sm font-bold text-white mt-1 block">
                  {rec?.ram_gb_min}–{rec?.ram_gb_recommended} GB
                </span>
                <span className="text-[10px] text-slate-400">
                  {tx("Model: {v} MB", { v: Math.round(plan?.standalone_ram_mb || 1024) })}
                </span>
              </div>

              <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
                <span className="text-[11px] text-slate-400 flex items-center gap-1 font-medium">
                  <Gauge size={13} className="text-amber-400" />
                  {tx("tmpfs RAM")}
                </span>
                <span className="text-sm font-bold text-white mt-1 block">
                  {plan?.ephemeral_tmpfs_mb || 512} MB
                </span>
                <span className="text-[10px] text-slate-400">
                  {tx("ephemeral /tmp")}
                </span>
              </div>

              <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3">
                <span className="text-[11px] text-slate-400 flex items-center gap-1 font-medium">
                  <HardDrive size={13} className="text-emerald-400" />
                  {tx("Storage (SSD)")}
                </span>
                <span className="text-sm font-bold text-white mt-1 block">
                  {rec?.storage_ssd_gb_min}–{rec?.storage_ssd_gb_recommended} GB
                </span>
                <span className="text-[10px] text-slate-400">
                  {tx("encrypted disk")}
                </span>
              </div>
            </div>

            {/* Distributed Topology Breakdown (if cluster) */}
            {isDistributed && (
              <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-3 text-xs space-y-1.5 text-slate-300">
                <div className="font-semibold text-white flex items-center gap-1.5">
                  <Layers size={13} className="text-purple-400" />
                  {tx("Cluster Node Breakdown:")}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                  <div>• {tx("Control Plane:")} 1x (2–4 vCPU, 4 GB RAM, WORKER_CONCURRENCY=0)</div>
                  <div>• {tx("Worker Fleet:")} {plan?.cluster_worker_nodes_needed}x {tx("nodes")} ({plan?.cluster_total_worker_slots} {tx("total slots")})</div>
                </div>
              </div>
            )}
          </div>

          {/* Live Fleet Comparison Status */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-2">
              <Server size={14} className="text-slate-400" />
              {tx("Live Fleet Telemetry Comparison")}
            </h4>
            {currentSlots > 0 ? (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                <div>
                  <span className="text-slate-300 font-medium">
                    {tx("Current Active Fleet Capacity:")}{" "}
                  </span>
                  <span className="text-white font-bold font-mono">
                    {currentSlots} {tx("slot(s)")}
                  </span>
                  <span className="text-slate-400 ms-2">
                    {tx("(Required: {v} slots)", { v: plan?.required_slots || 1 })}
                  </span>
                </div>

                {isSufficient ? (
                  <span className="flex items-center gap-1.5 text-emerald-400 font-medium bg-emerald-950/40 border border-emerald-800/60 px-2.5 py-1 rounded-md self-start sm:self-auto">
                    <CheckCircle2 size={13} />
                    {tx("Fleet capacity is sufficient")}
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-amber-400 font-medium bg-amber-950/40 border border-amber-800/60 px-2.5 py-1 rounded-md self-start sm:self-auto">
                    <AlertTriangle size={13} />
                    {tx("Capacity deficit: {v} slot(s)", { v: deficit || 1 })}
                  </span>
                )}
              </div>
            ) : (
              <div className="text-xs text-slate-400 flex items-center gap-2">
                <AlertTriangle size={13} className="text-slate-500" />
                {tx("No remote worker nodes currently registered. Single-node local execution will run at WORKER_CONCURRENCY.")}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
