import { getApiErrorMessage } from '../api/errors'
import { useAuthOptions, useGoogleAuth } from '../hooks/useAuth'

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
        <svg aria-hidden="true" viewBox="0 0 48 48" className="h-5 w-5 shrink-0">
          <path
            fill="#EA4335"
            d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5Z"
          />
          <path
            fill="#4285F4"
            d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6C44.4 38.04 46.98 31.88 46.98 24.55Z"
          />
          <path
            fill="#FBBC05"
            d="M10.53 28.59A14.4 14.4 0 0 1 9.75 24c0-1.59.27-3.13.76-4.59l-7.98-6.19A23.87 23.87 0 0 0 0 24c0 3.87.93 7.53 2.56 10.78l7.97-6.19Z"
          />
          <path
            fill="#34A853"
            d="M24 48c6.48 0 11.93-2.13 15.91-5.8l-7.73-6C30.03 37.65 27.26 38.5 24 38.5c-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48Z"
          />
        </svg>
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
