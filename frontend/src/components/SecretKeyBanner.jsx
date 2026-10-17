import { useEffect, useRef, useState } from 'react'
import { ShieldAlert, Key, Lock, Sparkles, MousePointer, Image, Check, Copy, RefreshCw, Terminal, X } from 'lucide-react'
import api from '../api'
import { useAuth, can } from '../hooks/useAuth'
import { tx } from '../i18n/tx'

const KEY_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()-_=+[]{}|;:,.<>?'

function pickRandomKeyLength(seedBytes = []) {
  const r = new Uint32Array(1)
  if (window.crypto && window.crypto.getRandomValues) {
    window.crypto.getRandomValues(r)
  } else {
    r[0] = Math.floor(Math.random() * 0xffffffff)
  }
  let seedMix = 0
  for (let i = 0; i < seedBytes.length; i++) {
    seedMix = ((seedMix * 33) ^ (seedBytes[i] || 0)) >>> 0
  }
  const span = 512 - 128 + 1 // 385 possible lengths (128..512 inclusive)
  return 128 + (((r[0] ^ seedMix) >>> 0) % span)
}

function mixBytesToKey(seedBytes, targetLen = 128) {
  const rand = new Uint8Array(targetLen * 2)
  if (window.crypto && window.crypto.getRandomValues) {
    window.crypto.getRandomValues(rand)
  }
  const out = []
  const seedLen = seedBytes.length || 1
  let acc = 0x5a
  for (let i = 0; i < targetLen; i++) {
    const s = seedBytes[i % seedLen] || 0
    const s2 = seedBytes[(i * 7 + 13) % seedLen] || 0
    acc = (acc * 31 + s + s2 + rand[i] + i) & 0xff
    const idx = (acc ^ rand[targetLen + i]) % KEY_ALPHABET.length
    out.push(KEY_ALPHABET[idx])
  }
  return out.join('')
}

export function SecretKeyGeneratorPanel({ status, onStatusChange, compact = false }) {
  const [tab, setTab] = useState('images') // 'images' | 'mouse'
  const [keyInput, setKeyInput] = useState('')
  const [imageCount, setImageCount] = useState(5)
  const [images, setImages] = useState([])
  const [stage, setStage] = useState(0) // 0=idle, 1=select, 2=sort, 3=code, 4=merge, 5=shuffle, 6=done
  const [displayOrder, setDisplayOrder] = useState([])
  const [mergedChunks, setMergedChunks] = useState([])
  const [scramblePreview, setScramblePreview] = useState('')
  const [generating, setGenerating] = useState(false)

  // Mouse & keyboard entropy collector state
  const [entropyPoints, setEntropyPoints] = useState([])
  const [entropyProgress, setEntropyProgress] = useState(0)
  const entropyPoolRef = useRef([])
  const mouseTargetLenRef = useRef(pickRandomKeyLength([]))
  const canvasRef = useRef(null)

  const [saving, setSaving] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState('')
  const [savedNotice, setSavedNotice] = useState('')
  const [copiedCmd, setCopiedCmd] = useState('')
  const timersRef = useRef([])

  useEffect(() => {
    return () => {
      timersRef.current.forEach(t => clearTimeout(t))
    }
  }, [])

  const clearTimers = () => {
    timersRef.current.forEach(t => clearTimeout(t))
    timersRef.current = []
  }

  const runImageChaosGenerator = async () => {
    clearTimers()
    setError('')
    setSavedNotice('')
    setGenerating(true)
    setStage(1)
    setImages([])
    setDisplayOrder([])
    setMergedChunks([])
    setScramblePreview('')

    let fetched = []
    try {
      const r = await api.get(`/settings/security/entropy-images?count=${imageCount}`)
      fetched = r.data?.images || []
    } catch {
      fetched = []
    }

    if (!fetched.length) {
      // Pure client-side fallback if API call fails
      for (let i = 0; i < imageCount; i++) {
        const rnd = new Uint8Array(64)
        window.crypto.getRandomValues(rnd)
        const hex = Array.from(rnd).map(b => b.toString(16).padStart(2, '0')).join('')
        fetched.push({
          id: `local-${i}`,
          index: i + 1,
          label: `Entropy Frame #${i + 1}`,
          source_type: 'lava-lamp-rng',
          byte_length: 4096,
          data_url: '',
          sha512: hex,
          chunks: [hex.slice(0, 16), hex.slice(16, 32), hex.slice(32, 48), hex.slice(48, 64)],
        })
      }
    }

    setImages(fetched)
    setDisplayOrder(fetched.map((_, idx) => idx))

    // Stage 2: Sort images at random
    timersRef.current.push(setTimeout(() => {
      const order = fetched.map((_, idx) => idx)
      for (let i = order.length - 1; i > 0; i--) {
        const r = new Uint32Array(1)
        window.crypto.getRandomValues(r)
        const j = r[0] % (i + 1)
        const tmp = order[i]
        order[i] = order[j]
        order[j] = tmp
      }
      setDisplayOrder(order)
      setStage(2)

      // Stage 3: Turn images into code
      timersRef.current.push(setTimeout(() => {
        setStage(3)

        // Stage 4: Merge at random chunks
        timersRef.current.push(setTimeout(() => {
          const allChunks = []
          order.forEach((imgIdx, rank) => {
            const img = fetched[imgIdx]
            ;(img.chunks || []).slice(0, 3).forEach((ch, cIdx) => {
              allChunks.push({
                id: `${img.id}-${cIdx}`,
                sourceIndex: img.index,
                rank: rank + 1,
                text: ch.slice(0, 12),
              })
            })
          })
          // Interleave / shuffle chunks
          for (let i = allChunks.length - 1; i > 0; i--) {
            const r = new Uint32Array(1)
            window.crypto.getRandomValues(r)
            const j = r[0] % (i + 1)
            const tmp = allChunks[i]
            allChunks[i] = allChunks[j]
            allChunks[j] = tmp
          }
          setMergedChunks(allChunks)
          setStage(4)

          // Stage 5: Shuffle into final key of random length in [128, 512]
          timersRef.current.push(setTimeout(() => {
            setStage(5)
            const rawBytes = []
            allChunks.forEach(c => {
              for (let k = 0; k < c.text.length; k++) {
                rawBytes.push(c.text.charCodeAt(k))
              }
            })
            fetched.forEach(img => {
              const s = img.sha512 || ''
              for (let k = 0; k < s.length; k++) {
                rawBytes.push(s.charCodeAt(k))
              }
            })

            const targetLen = pickRandomKeyLength(rawBytes)
            let ticks = 0
            const stepScramble = () => {
              ticks += 1
              const candidate = mixBytesToKey(rawBytes, targetLen)
              setScramblePreview(candidate)
              if (ticks < 6) {
                timersRef.current.push(setTimeout(stepScramble, 90))
              } else {
                setKeyInput(candidate)
                setStage(6)
                setGenerating(false)
              }
            }
            stepScramble()
          }, 650))
        }, 650))
      }, 650))
    }, 650))
  }

  const recordEntropyEvent = (x, y, code) => {
    const now = performance.now()
    entropyPoolRef.current.push(
      (x & 0xff),
      (y & 0xff),
      (code & 0xff),
      (Math.floor(now * 1000) & 0xff)
    )
    const count = Math.min(240, entropyPoolRef.current.length)
    const pct = Math.min(100, Math.round((count / 240) * 100))
    setEntropyProgress(pct)
    setEntropyPoints(prev => [...prev.slice(-35), { x, y }])

    if (canvasRef.current) {
      const ctx = canvasRef.current.getContext('2d')
      if (ctx) {
        ctx.fillStyle = 'rgba(15, 23, 42, 0.18)'
        ctx.fillRect(0, 0, canvasRef.current.width, canvasRef.current.height)
        ctx.beginPath()
        ctx.arc(x % canvasRef.current.width, y % canvasRef.current.height, 6, 0, Math.PI * 2)
        ctx.fillStyle = pct >= 100 ? '#34d399' : '#38bdf8'
        ctx.fill()
      }
    }

    if (pct === 100 && entropyPoolRef.current.length === 240) {
      mouseTargetLenRef.current = pickRandomKeyLength(entropyPoolRef.current)
    }
    const preview = mixBytesToKey(entropyPoolRef.current, mouseTargetLenRef.current)
    setScramblePreview(preview)
    if (pct >= 100 && keyInput.length < 128) {
      setKeyInput(preview)
    }
  }

  const handleMouseMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = Math.max(0, Math.floor(e.clientX - rect.left))
    const y = Math.max(0, Math.floor(e.clientY - rect.top))
    recordEntropyEvent(x, y, (x ^ y) & 0xff)
  }

  const handleKeyDown = (e) => {
    const code = e.key ? e.key.charCodeAt(0) : 42
    recordEntropyEvent(code * 7, code * 13, code)
  }

  const resetMouseEntropy = () => {
    entropyPoolRef.current = []
    mouseTargetLenRef.current = pickRandomKeyLength([])
    setEntropyProgress(0)
    setEntropyPoints([])
    setScramblePreview('')
  }

  const saveKey = async () => {
    setError('')
    setSavedNotice('')
    const trimmed = keyInput.trim()
    if (trimmed.length < 128) {
      setError(tx("Master secret key must be at least 128 characters long."))
      return
    }
    setSaving(true)
    try {
      const r = await api.post('/settings/security/secret-key', { key: trimmed })
      if (r.data?.access_token) {
        localStorage.setItem('token', r.data.access_token)
      }
      setSavedNotice(tx("Master secret key saved to file. Next, run the file permission command below so only the service owner can read it."))
      if (onStatusChange) onStatusChange(r.data)
    } catch (e) {
      setError(e.response?.data?.detail || tx("Could not save the master secret key."))
    } finally {
      setSaving(false)
    }
  }

  const verifyPermissions = async () => {
    setVerifying(true)
    setError('')
    try {
      const r = await api.get('/settings/security/secret-key')
      if (onStatusChange) onStatusChange(r.data)
      if (r.data?.permissions_secure && !r.data?.needs_key) {
        setSavedNotice(tx("File permissions verified (0600). Your master secret key is locked down."))
      } else if (r.data?.permissions_insecure) {
        setError(tx("File permissions are still open. Run the chmod / icacls command below and try again."))
      }
    } catch {
      setError(tx("Could not check file permissions."))
    } finally {
      setVerifying(false)
    }
  }

  const copyCommand = (label, cmd) => {
    if (!cmd) return
    navigator.clipboard?.writeText(cmd)
    setCopiedCmd(label)
    setTimeout(() => setCopiedCmd(''), 2000)
  }

  const stageLabels = [
    tx("Ready to generate"),
    tx("1. Selecting random images…"),
    tx("2. Sorting images at random…"),
    tx("3. Turning image pixels into code…"),
    tx("4. Merging random byte chunks…"),
    tx("5. Shuffling & mixing into key…"),
    tx("6. 128-character master key ready!"),
  ]

  const chunkColors = [
    'bg-rose-500/20 border-rose-500/40 text-rose-200',
    'bg-sky-500/20 border-sky-500/40 text-sky-200',
    'bg-emerald-500/20 border-emerald-500/40 text-emerald-200',
    'bg-amber-500/20 border-amber-500/40 text-amber-200',
    'bg-purple-500/20 border-purple-500/40 text-purple-200',
    'bg-teal-500/20 border-teal-500/40 text-teal-200',
  ]

  return (
    <div className={compact ? "space-y-4" : "space-y-5"}>
      {/* Current File & Permission Status */}
      {status && (
        <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3.5 text-xs space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Key size={14} className="text-sky-400 shrink-0" />
              <span className="text-slate-300 font-medium">{tx("Key file location:")}</span>
              <code className="px-1.5 py-0.5 rounded bg-slate-900 text-sky-300 font-mono">{status.file_path}</code>
            </div>
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded font-medium ${status.has_valid_file_key ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-red-500/20 text-red-300 border border-red-500/30'}`}>
                {status.has_valid_file_key ? tx("Key Saved (128+ chars)") : tx("Key Not Set")}
              </span>
              {status.file_exists && (
                <span className={`px-2 py-0.5 rounded font-mono ${status.permissions_secure ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-red-500/20 text-red-300 border border-red-500/30'}`}>
                  {tx("Permissions:")} {status.mode_octal || '0644'}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Generator Mode Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
        <div className="flex items-center gap-2" role="tablist" aria-label={tx("Key generation method")}>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'images'}
            onClick={() => setTab('images')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              tab === 'images'
                ? 'bg-sky-600 text-white'
                : 'bg-slate-800/80 text-slate-300 hover:bg-slate-800'
            }`}
          >
            <Image size={14} />
            {tx("Image Chaos Mixer (Lava Lamp Style)")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'mouse'}
            onClick={() => setTab('mouse')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              tab === 'mouse'
                ? 'bg-sky-600 text-white'
                : 'bg-slate-800/80 text-slate-300 hover:bg-slate-800'
            }`}
          >
            <MousePointer size={14} />
            {tx("Mouse & Keyboard Entropy")}
          </button>
        </div>

        {tab === 'images' && (
          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="entropy-image-count" className="text-slate-400">{tx("Images:")}</label>
            <select
              id="entropy-image-count"
              value={imageCount}
              onChange={e => setImageCount(Number(e.target.value))}
              disabled={generating}
              className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white text-xs"
            >
              <option value={4}>4</option>
              <option value={5}>5</option>
              <option value={6}>6</option>
            </select>
            <button
              type="button"
              onClick={runImageChaosGenerator}
              disabled={generating}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium text-xs transition-colors"
            >
              <Sparkles size={14} />
              {generating ? tx("Mixing Entropy…") : tx("Generate Key from Images")}
            </button>
          </div>
        )}
      </div>

      {/* Tab 1: Image Chaos Visual Pipeline */}
      {tab === 'images' && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-4">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-slate-300 font-medium">
              {stageLabels[stage] || stageLabels[0]}
            </p>
            {stage > 0 && (
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5, 6].map(s => (
                  <span
                    key={s}
                    className={`h-1.5 w-5 rounded-full transition-all ${
                      stage >= s ? 'bg-emerald-400' : 'bg-slate-800'
                    }`}
                  />
                ))}
              </div>
            )}
          </div>

          {images.length === 0 ? (
            <p className="text-xs text-slate-400">
              {tx("Click \"Generate Key from Images\" to pull 4 to 6 random images, sort them at random, convert their pixels into code, merge random byte chunks, shuffle them, and crystallize a 128-character master key.")}
            </p>
          ) : (
            <div className="space-y-3">
              {/* Image Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2.5">
                {displayOrder.map((imgIdx, orderPos) => {
                  const img = images[imgIdx]
                  if (!img) return null
                  return (
                    <div
                      key={img.id}
                      className="rounded-lg border border-slate-700/80 bg-slate-950 p-2 flex flex-col gap-1.5 transition-all duration-300"
                    >
                      <div className="relative h-14 w-full rounded overflow-hidden bg-slate-900 flex items-center justify-center">
                        {img.data_url ? (
                          <img
                            src={img.data_url}
                            alt={img.label}
                            className={`h-full w-full object-cover transition-all duration-300 ${
                              stage >= 3 ? 'opacity-40 scale-105' : 'opacity-100'
                            }`}
                          />
                        ) : (
                          <Image size={20} className="text-sky-400" />
                        )}
                        <span className="absolute top-1 start-1 px-1.5 py-0.5 rounded bg-slate-950/85 text-[10px] font-mono text-sky-300 border border-slate-700">
                          #{orderPos + 1}
                        </span>
                        {stage >= 3 && (
                          <div className="absolute inset-0 flex items-center justify-center p-1 bg-slate-950/60">
                            <code className="text-[10px] leading-tight font-mono text-emerald-300 break-all">
                              {img.sha512?.slice(0, 24)}
                            </code>
                          </div>
                        )}
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-slate-400">
                        <span className="truncate">{img.label}</span>
                        <span className="font-mono text-slate-500">{img.byte_length}B</span>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Stage 4: Merged Chunks */}
              {stage >= 4 && mergedChunks.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-[11px] text-slate-400 font-medium">{tx("Merged & interleaved byte chunks:")}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {mergedChunks.map((ch) => (
                      <span
                        key={ch.id}
                        className={`px-2 py-0.5 rounded border font-mono text-[10px] transition-all ${
                          chunkColors[(ch.sourceIndex - 1) % chunkColors.length]
                        }`}
                      >
                        [{ch.sourceIndex}] {ch.text}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Stage 5/6: Live Scramble / Resulting Key Stream */}
              {stage >= 5 && scramblePreview && (
                <div className="rounded-lg border border-emerald-500/30 bg-slate-950 p-2.5">
                  <p className="text-[10px] uppercase tracking-wider text-emerald-400 mb-1">
                    {stage === 5 ? tx("Shuffling chunks into key…") : tx("Synthesized 128-character key:")}
                  </p>
                  <code className="block text-xs font-mono text-emerald-300 break-all select-all">
                    {stage === 5 ? scramblePreview : keyInput}
                  </code>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Mouse & Keyboard Entropy Collector */}
      {tab === 'mouse' && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-slate-300">
              {tx("Move your mouse inside the box below or type random keys on your keyboard to collect unpredictable entropy.")}
            </p>
            <button
              type="button"
              onClick={resetMouseEntropy}
              className="text-xs text-slate-400 hover:text-white flex items-center gap-1 shrink-0"
            >
              <RefreshCw size={12} />
              {tx("Reset")}
            </button>
          </div>

          <div
            tabIndex={0}
            role="application"
            aria-label={tx("Mouse and keyboard entropy pad")}
            onMouseMove={handleMouseMove}
            onKeyDown={handleKeyDown}
            className="relative h-28 w-full rounded-lg border border-dashed border-sky-500/40 bg-slate-950 overflow-hidden cursor-crosshair focus:outline-hidden focus:ring-2 focus:ring-sky-500 flex items-center justify-center"
          >
            <canvas ref={canvasRef} width={520} height={112} className="absolute inset-0 w-full h-full pointer-events-none" />
            <div className="relative z-10 text-center pointer-events-none px-4">
              <p className="text-xs font-medium text-sky-200">
                {entropyProgress < 100
                  ? `${tx("Entropy collected:")} ${entropyProgress}% (${entropyPoints.length} ${tx("samples")})`
                  : tx("100% Entropy collected — 128-character key generated!")}
              </p>
              <p className="text-[11px] text-slate-400 mt-0.5">
                {tx("Click here and type random keys or wiggle your cursor")}
              </p>
            </div>
          </div>

          <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-sky-500 to-emerald-400 transition-all duration-150"
              style={{ width: `${entropyProgress}%` }}
            />
          </div>

          {scramblePreview && (
            <div className="flex items-center justify-between gap-2">
              <code className="text-[11px] font-mono text-emerald-300 truncate flex-1">
                {scramblePreview}
              </code>
              <button
                type="button"
                onClick={() => setKeyInput(scramblePreview)}
                className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium shrink-0"
              >
                {tx("Use This Key")}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Key Input & Minimum 128-Character Validation */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label htmlFor="master-secret-key-input" className="text-xs font-medium text-slate-200">
            {tx("Master Secret Key (minimum 128 characters)")}
          </label>
          <span className={`text-xs font-mono ${keyInput.trim().length >= 128 && keyInput.trim().length <= 512 ? 'text-emerald-400' : 'text-amber-400'}`}>
            {keyInput.trim().length} / 128–512 {tx("characters")}
          </span>
        </div>
        <textarea
          id="master-secret-key-input"
          rows={2}
          maxLength={512}
          value={keyInput}
          onChange={e => setKeyInput(e.target.value)}
          placeholder={tx("Generate a key above or enter your own 128+ character random key…")}
          className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-hidden focus:border-sky-500"
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[11px] text-slate-400">
            {tx("Saved directly to the master key file. Never use 'change-me-please' or short passwords.")}
          </p>
          <button
            type="button"
            onClick={saveKey}
            disabled={saving || keyInput.trim().length < 128 || keyInput.trim().length > 512}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-semibold transition-colors"
          >
            <Lock size={14} />
            {saving ? tx("Saving Key…") : tx("Save Master Key to File")}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-950/60 px-3 py-2 text-xs text-red-200">
          {error}
        </div>
      )}
      {savedNotice && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-950/60 px-3 py-2 text-xs text-emerald-200">
          {savedNotice}
        </div>
      )}

      {/* File Permission Lockdown Instructions */}
      {status?.commands && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Terminal size={15} className="text-amber-400 shrink-0" />
              <h4 className="text-xs font-semibold text-amber-200">
                {tx("Lock down key file permissions (required)")}
              </h4>
            </div>
            <button
              type="button"
              onClick={verifyPermissions}
              disabled={verifying}
              className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs font-medium transition-colors"
            >
              <RefreshCw size={12} className={verifying ? 'animate-spin' : ''} />
              {verifying ? tx("Checking…") : tx("Verify File Permissions")}
            </button>
          </div>
          <p className="text-xs text-slate-300">
            {tx("After saving the key, run the command for your setup so only the service owner can read the key file (mode 0600). The critical red banner will clear once permissions are restricted.")}
          </p>

          <div className="space-y-2 text-xs">
            {[
              { id: 'docker', label: tx("Docker Compose:"), cmd: status.commands.docker },
              { id: 'linux', label: tx("Linux / macOS:"), cmd: status.commands.linux },
              { id: 'windows', label: tx("Windows (PowerShell):"), cmd: status.commands.windows },
            ].map(item => (
              <div key={item.id} className="flex items-center justify-between gap-2 rounded-lg bg-slate-950 border border-slate-800 px-3 py-1.5">
                <div className="min-w-0 flex-1">
                  <span className="text-[11px] text-slate-400 me-2">{item.label}</span>
                  <code className="text-xs font-mono text-amber-300 break-all select-all">{item.cmd}</code>
                </div>
                <button
                  type="button"
                  onClick={() => copyCommand(item.id, item.cmd)}
                  className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 shrink-0"
                  aria-label={tx("Copy command")}
                >
                  {copiedCmd === item.id ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function SecretKeyBanner() {
  const { user } = useAuth()
  const [status, setStatus] = useState(null)
  const [expanded, setExpanded] = useState(false)
  const [checking, setChecking] = useState(false)

  const isAdmin = can(user, 'settings.system')

  useEffect(() => {
    if (!isAdmin) return
    api.get('/settings/security/secret-key')
      .then(r => setStatus(r.data))
      .catch(() => {})
  }, [isAdmin])

  if (!isAdmin || !status || !status.banner_required) return null

  const recheckNow = async () => {
    setChecking(true)
    try {
      const r = await api.get('/settings/security/secret-key')
      setStatus(r.data)
    } catch {
      // ignore
    } finally {
      setChecking(false)
    }
  }

  return (
    <div role="alert" className="bg-red-950/95 border-b-2 border-red-500 text-red-100 px-4 py-3 shrink-0">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-start gap-2.5 min-w-0 flex-1">
            <ShieldAlert size={20} className="text-red-400 shrink-0 mt-0.5" />
            <div className="text-xs sm:text-sm">
              <span className="font-bold text-white me-1.5">
                {tx("Critical Security Action Required:")}
              </span>
              {status.needs_key ? (
                <span>
                  {tx("Your server does not have a permanent 128+ character master secret key saved yet. Generate or enter a master key and restrict its file permissions.")}
                </span>
              ) : (
                <span>
                  {tx("Your master secret key file permissions are too open")} ({status.mode_octal || '0644'}). {tx("Run")}{' '}
                  <code className="px-1.5 py-0.5 rounded bg-red-900/80 text-amber-200 font-mono text-xs">
                    {status.commands?.linux}
                  </code>{' '}
                  {tx("(or the Docker command) to restrict access to 0600.")}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {status.permissions_insecure && (
              <button
                type="button"
                onClick={recheckNow}
                disabled={checking}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-900 hover:bg-red-800 border border-red-400/40 text-white text-xs font-medium transition-colors"
              >
                <RefreshCw size={13} className={checking ? 'animate-spin' : ''} />
                {tx("Verify File Permissions")}
              </button>
            )}
            <button
              type="button"
              onClick={() => setExpanded(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-semibold transition-colors"
            >
              {expanded ? <X size={14} /> : <Key size={14} />}
              {expanded
                ? tx("Hide Key Setup")
                : status.needs_key
                  ? tx("Generate & Save Master Key")
                  : tx("Show Permission Commands")}
            </button>
          </div>
        </div>

        {expanded && (
          <div className="mt-4 rounded-xl border border-red-500/40 bg-slate-950 p-4 text-slate-100 shadow-xl">
            <SecretKeyGeneratorPanel
              status={status}
              onStatusChange={newStatus => {
                setStatus(newStatus)
                if (!newStatus?.banner_required) setExpanded(false)
              }}
              compact
            />
          </div>
        )}
      </div>
    </div>
  )
}

