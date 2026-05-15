import { ApiError } from './client'

export function getApiErrorMessage(error: unknown, fallback = 'Request failed.') {
  if (!(error instanceof ApiError)) {
    return fallback
  }

  if (typeof error.data === 'object' && error.data !== null) {
    if ('detail' in error.data) {
      return String((error.data as { detail: unknown }).detail)
    }

    const entries = Object.entries(error.data as Record<string, unknown>)
    if (entries.length > 0) {
      const [, value] = entries[0]
      if (Array.isArray(value) && value.length > 0) {
        return String(value[0])
      }
      if (typeof value === 'string') {
        return value
      }
    }
  }

  return error.message
}
