import { useSearchParams } from 'react-router-dom'

const messages: Record<string, string> = {
  rate_limited: 'Too many accounts have been created from this connection. Please try again later.',
  connected: 'Your Google account is connected. You can now use it to sign in.',
  existing_account:
    'An account already uses this email. Sign in with your password, then connect Google from your profile.',
  already_connected:
    'This Google account is connected to another Graider account. Choose a different Google account.',
  different_google: 'You already have a Google account connected to Graider.',
  session_changed: 'Your Graider session changed. Sign in again before connecting Google.',
  unverified_email: 'Google needs to verify your email before you can create an account.',
  cancelled: 'Google sign-in was cancelled. You can try again whenever you’re ready.',
  failed: 'Google sign-in could not be completed. Please try again.',
  unavailable: 'Sign-in is unavailable for this account. Please try another sign-in method.',
}

export function AuthNotice() {
  const [params, setParams] = useSearchParams()
  const code = params.get('auth') ?? ''
  const message = messages[code]
  if (!message) return null

  return (
    <div
      role="status"
      className={`flex items-start justify-between gap-4 rounded-2xl border px-4 py-3 text-sm ${
        code === 'connected'
          ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
          : 'border-amber-200 bg-amber-50 text-amber-900'
      }`}
    >
      <p>{message}</p>
      <button
        type="button"
        aria-label="Dismiss message"
        onClick={() => {
          const next = new URLSearchParams(params)
          next.delete('auth')
          setParams(next, { replace: true })
        }}
        className="shrink-0 px-1 font-semibold"
      >
        ×
      </button>
    </div>
  )
}
