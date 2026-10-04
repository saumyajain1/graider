import { getApiErrorMessage } from '../api/errors'
import { ApiError } from '../api/client'

export function QueryError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700"
    >
      <p>
        {error instanceof ApiError && error.status === 404
          ? "This item is unavailable or you don't have access to it."
          : getApiErrorMessage(error, 'Could not load this page. Please try again.')}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 rounded-full border border-rose-300 px-4 py-2 font-semibold hover:bg-rose-100"
      >
        Try again
      </button>
    </div>
  )
}
