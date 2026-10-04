import { apiRequest } from './client'

export type CurrentUser = {
  id: number
  email: string
  full_name: string
  has_password: boolean
  connected_accounts: { provider: string; email: string }[]
}

export type AuthPayload = {
  email: string
  password: string
  full_name?: string
}

export async function fetchCurrentUser() {
  return apiRequest<CurrentUser>('/api/auth/me', { timeoutMs: 90000 })
}

export async function login(payload: AuthPayload) {
  return apiRequest<CurrentUser>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({
      email: payload.email,
      password: payload.password,
    }),
  })
}

export async function register(payload: AuthPayload) {
  return apiRequest<CurrentUser>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function logout() {
  return apiRequest<void>('/api/auth/logout', { method: 'POST' })
}

export async function fetchAuthOptions() {
  return apiRequest<{ google_enabled: boolean; password_reset_enabled: boolean }>(
    '/api/auth/options',
  )
}

export async function startGoogleAuth(process: 'login' | 'connect') {
  return apiRequest<{ redirect_url: string }>('/api/auth/google', {
    method: 'POST',
    body: JSON.stringify({ process }),
  })
}

export function updateProfile(full_name: string) {
  return apiRequest<CurrentUser>('/api/auth/profile', {
    method: 'PATCH',
    body: JSON.stringify({ full_name }),
  })
}
export function changePassword(payload: {
  current_password: string
  new_password: string
  confirm_password: string
}) {
  return apiRequest<CurrentUser>('/api/auth/password/change', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
export function requestPasswordReset(email: string) {
  return apiRequest<{ detail: string }>('/api/auth/password/reset', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}
export function confirmPasswordReset(payload: {
  uid: string
  token: string
  new_password: string
  confirm_password: string
}) {
  return apiRequest<{ detail: string }>('/api/auth/password/reset/confirm', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
export function disconnectGoogle(current_password: string) {
  return apiRequest<CurrentUser>('/api/auth/accounts/disconnect', {
    method: 'POST',
    body: JSON.stringify({ provider: 'google', current_password }),
  })
}
