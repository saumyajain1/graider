import { getApiErrorMessage } from '../api/errors'
import { useAuthOptions, useGoogleAuth } from '../hooks/useAuth'
import { GoogleIcon } from './GoogleIcon'

export function GoogleButton({
  process,
  disabled = false,
}: {
  process: 'login' | 'connect'
  disabled?: boolean
}) {
  const options = useAuthOptions()
  const google = useGoogleAuth()

  if (!options.data?.google_enabled) return null

  return (
    <div>
      <button
        type="button"
        disabled={disabled || google.isPending}
        onClick={() => google.mutate(process)}
        className="flex w-full items-center justify-center gap-3 rounded-2xl border border-slate-300 bg-white px-4 py-3 font-semibold text-slate-800 transition hover:bg-slate-50 disabled:opacity-60"
      >
        <GoogleIcon />
        {google.isPending
          ? 'Opening Google…'
          : process === 'connect'
            ? 'Connect Google'
            : 'Continue with Google'}
      </button>
      {google.isError ? (
        <p role="alert" className="mt-3 text-sm text-rose-700">
          {getApiErrorMessage(google.error, 'Could not open Google. Please try again.')}
        </p>
      ) : null}
    </div>
  )
}
