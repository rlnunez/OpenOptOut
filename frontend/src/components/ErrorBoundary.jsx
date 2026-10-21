import { Component } from 'react'
import { AlertTriangle, RotateCcw } from 'lucide-react'
import { tx } from '../i18n/tx'

// The last line of defense against a blank screen. Without this, any
// uncaught error while rendering -- including a server response shaped
// differently than a screen expected -- unmounts the whole app and leaves a
// person looking at an empty black page with no message and nothing to
// click. That's especially bad for someone non-technical: they have no way
// to tell whether the page is still loading, whether they did something
// wrong, or whether to just give up.
//
// This only catches render-time errors in the tree below it (React's rule,
// not a choice here) -- it does not catch errors inside event handlers or
// async code, which already set their own `error` state and render a
// message. Those two layers together are what keep a bad response from
// turning into a blank page.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('Unhandled error in the page:', error, info?.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl text-center">
          <div className="w-12 h-12 mx-auto rounded-full bg-red-500/10 border border-red-800 flex items-center justify-center text-red-400 mb-4">
            <AlertTriangle size={22} />
          </div>
          <h1 className="text-white text-base font-semibold mb-2">
            {tx("Something went wrong")}
          </h1>
          <p className="text-slate-400 text-sm mb-5">
            {tx("This page ran into a problem and can't continue. Nothing was lost — reloading usually fixes it.")}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-shield-600 hover:bg-shield-500 text-white text-sm font-medium transition-colors"
          >
            <RotateCcw size={14} />
            {tx("Reload the page")}
          </button>
        </div>
      </div>
    )
  }
}
