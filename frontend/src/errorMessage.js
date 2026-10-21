// FastAPI's `detail` is a plain string for most errors, but for a 422 it's a
// LIST of pydantic validation-error objects ({type, loc, msg, input, ctx}),
// and occasionally a single such object. Every screen in this app shows
// `err.response?.data?.detail` straight in a `{error}` JSX expression --
// React throws ("Objects are not valid as a React child") on a plain object,
// and on an array of them, the instant the backend returns one of those
// shapes instead of a string. The whole page goes blank with no message and
// no way back, which is exactly what a non-technical person must never hit.
//
// detailText() returns the same thing `err.response?.data?.detail` would for
// the plain-string case, so a call site's existing `detailText(err) ||
// tx(someFallbackPhrase)` chain behaves exactly as it did when written
// `err.response?.data?.detail || tx(someFallbackPhrase)` -- but it turns the
// structured-validation-error shapes into a safe string instead of
// returning them as-is.
export function detailText(err) {
  const d = err?.response?.data?.detail
  if (typeof d === 'string') return d || undefined
  if (Array.isArray(d)) {
    const msgs = d
      .map(item => (item && typeof item === 'object' && typeof item.msg === 'string') ? item.msg : null)
      .filter(Boolean)
    return msgs.length ? msgs.join(' ') : undefined
  }
  if (d && typeof d === 'object' && typeof d.msg === 'string') return d.msg || undefined
  return undefined
}
