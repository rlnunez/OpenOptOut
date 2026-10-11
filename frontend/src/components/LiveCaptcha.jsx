import { useCallback, useEffect, useRef, useState } from 'react'
import { X, MousePointerClick, CheckCircle2, Loader2, CornerDownLeft } from 'lucide-react'
import api from '../api'

// Solve a CAPTCHA in the real page. OpenOptOut runs the opt-out again in its
// own browser up to the CAPTCHA, shows the page here, and passes your clicks
// and typing to it. When you're done, the opt-out finishes by itself.

const W = 1280, H = 800

export default function LiveCaptcha({ challenge, onClose, onFinished }) {
  const [st, setSt] = useState(null)
  const [frame, setFrame] = useState('')
  const [text, setText] = useState('')
  const [err, setErr] = useState('')
  const imgRef = useRef(null)
  const id = challenge.id
  const live = st?.active

  const poll = useCallback(async () => {
    try {
      const { data } = await api.get(`/captcha/challenges/${id}/live`)
      setSt(data)
      if (data.state === 'done' || data.state === 'needs_you') onFinished?.()
    } catch (e) { setErr(e.response?.data?.detail || "Couldn't reach the live page.") }
  }, [id, onFinished])

  useEffect(() => {
    api.post(`/captcha/challenges/${id}/live`).then(r => setSt(r.data))
      .catch(e => setErr(e.response?.data?.detail || "Couldn't start the live page."))
  }, [id])

  useEffect(() => {
    if (st && !st.active) return
    const t = setInterval(poll, 1500)
    return () => clearInterval(t)
  }, [st, poll])

  useEffect(() => {
    if (!st?.can_interact) return
    let stop = false, url = ''
    const tick = async () => {
      try {
        const r = await api.get(`/captcha/challenges/${id}/live/frame`, { responseType: 'blob' })
        if (r.status === 200 && r.data.size) {
          const next = URL.createObjectURL(r.data)
          setFrame(prev => { if (prev) URL.revokeObjectURL(prev); return next }); url = next
        }
      } catch { /* the next tick tries again */ }
      if (!stop) setTimeout(tick, 900)
    }
    tick()
    return () => { stop = true; if (url) URL.revokeObjectURL(url) }
  }, [st?.can_interact, id])

  const send = async ev => {
    setErr('')
    try { await api.post(`/captcha/challenges/${id}/live/input`, ev) }
    catch (e) { setErr(e.response?.data?.detail || "That didn't reach the page.") }
  }
  const click = e => {
    const r = imgRef.current.getBoundingClientRect()
    send({ type: 'click', x: ((e.clientX - r.left) / r.width) * W, y: ((e.clientY - r.top) / r.height) * H })
  }
  const solved = async () => {
    try { await api.post(`/captcha/challenges/${id}/live/solved`); poll() }
    catch (e) { setErr(e.response?.data?.detail || "Couldn't continue.") }
  }
  const stop = async () => { try { await api.delete(`/captcha/challenges/${id}/live`) } catch { /* closing anyway */ } onClose() }

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-2 md:p-6" role="dialog" aria-modal="true" aria-labelledby="live-h">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-6xl max-h-[96vh] overflow-y-auto p-4">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <h2 id="live-h" className="text-white font-semibold">Solve it here: {challenge.broker_name} for {challenge.member_name}</h2>
            <p className="text-slate-300 text-sm mt-0.5 flex items-center gap-1.5" role="status">
              {live && !st?.can_interact && <Loader2 size={14} className="animate-spin" aria-hidden="true" />}
              {st?.state === 'done' && <CheckCircle2 size={14} className="text-emerald-400" aria-hidden="true" />}
              {st?.message || 'Starting…'}
            </p>
            {st?.detail && !st?.active && <p className="text-slate-500 text-xs mt-0.5">{st.detail}</p>}
          </div>
          <button onClick={st?.active ? stop : onClose} aria-label="Close" className="p-1.5 text-slate-400 hover:text-white"><X size={18} /></button>
        </div>
        {err && <p role="alert" className="text-red-400 text-sm mb-2">{err}</p>}

        {st?.can_interact && (
          <>
            <div className="relative border border-slate-700 rounded-lg overflow-hidden bg-black">
              {frame
                ? <img ref={imgRef} src={frame} alt="The site's page. Click on it to click in the page."
                    onClick={click} onWheel={e => send({ type: 'scroll', dy: e.deltaY })}
                    className="w-full cursor-pointer select-none" draggable={false} />
                : <div className="aspect-[16/10] flex items-center justify-center text-slate-400 text-sm">Loading the page…</div>}
            </div>
            <div className="flex flex-wrap items-center gap-2 mt-3">
              <span className="text-slate-400 text-xs flex items-center gap-1"><MousePointerClick size={13} aria-hidden="true" /> Click in the picture to click in the page.</span>
              <form onSubmit={e => { e.preventDefault(); if (text) { send({ type: 'text', text }); setText('') } }} className="flex gap-1.5">
                <label htmlFor="live-type" className="sr-only">Type into the page</label>
                <input id="live-type" value={text} onChange={e => setText(e.target.value)} placeholder="Type into the page"
                  className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-100 w-48" />
                <button className="px-2.5 py-1.5 text-sm text-slate-200 border border-slate-600 rounded-lg hover:bg-slate-700">Type</button>
              </form>
              {['Enter', 'Tab', 'Backspace'].map(k => (
                <button key={k} onClick={() => send({ type: 'key', key: k })}
                  className="px-2.5 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800 flex items-center gap-1">
                  {k === 'Enter' && <CornerDownLeft size={12} aria-hidden="true" />}{k}</button>
              ))}
              <button onClick={solved} className="ml-auto px-4 py-2 text-sm font-medium bg-emerald-600 text-white rounded-lg hover:bg-emerald-500">
                I've solved it
              </button>
            </div>
          </>
        )}
        {!st?.active && st && (
          <div className="flex gap-2 mt-2">
            {(st.state === 'failed' || st.state === 'timed_out') &&
              <button onClick={() => { setSt(null); api.post(`/captcha/challenges/${id}/live`).then(r => setSt(r.data)).catch(e => setErr(e.response?.data?.detail || "Couldn't start again.")) }}
                className="px-3 py-1.5 text-sm bg-shield-600 text-white rounded-lg hover:bg-shield-700">Try again</button>}
            <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-300 border border-slate-700 rounded-lg hover:bg-slate-800">Close</button>
          </div>
        )}
        <p className="text-slate-500 text-xs mt-3">Nothing from this page is saved. It closes on its own after 10 minutes without you.</p>
      </div>
    </div>
  )
}
