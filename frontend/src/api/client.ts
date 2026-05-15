export class ApiError extends Error {
  status: number
  data: unknown

  constructor(message: string, status: number, data: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

function getCookie(name: string) {
  const cookies = document.cookie ? document.cookie.split('; ') : []
  const match = cookies.find((cookie) => cookie.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : null
}

type RequestOptions = {
  body?: BodyInit | null
  headers?: HeadersInit
  method?: string
  timeoutMs?: number
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}) {
  const headers = new Headers(options.headers)
  const csrfToken = getCookie('csrftoken')
  const controller = new AbortController()
  const timeoutId =
    typeof options.timeoutMs === 'number'
      ? window.setTimeout(() => controller.abort(), options.timeoutMs)
      : null

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  if (csrfToken) {
    headers.set('X-CSRFToken', csrfToken)
  }

  let response: Response
  try {
    response = await fetch(path, {
      method: options.method ?? 'GET',
      body: options.body ?? null,
      credentials: 'include',
      headers,
      signal: controller.signal,
    })
  } catch (error) {
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId)
    }

    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(
        'Request timed out. Make sure the Django backend is running and refresh the page.',
        0,
        null,
      )
    }

    throw new ApiError(
      'Could not reach the Graider backend. Make sure both the backend and Vite dev server are running.',
      0,
      null,
    )
  }

  if (timeoutId !== null) {
    window.clearTimeout(timeoutId)
  }

  const contentType = response.headers.get('content-type') ?? ''
  const data = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    const message =
      typeof data === 'object' && data !== null && 'detail' in data
        ? String((data as { detail: string }).detail)
        : `Request failed with status ${response.status}`
    throw new ApiError(message, response.status, data)
  }

  return data as T
}
