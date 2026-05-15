import { apiRequest } from './client'

export type CurrentUser = {
  id: number
  email: string
  full_name: string
}

export type AuthPayload = {
  email: string
  password: string
  full_name?: string
}

export async function fetchCurrentUser() {
  return apiRequest<CurrentUser>('/api/auth/me', { timeoutMs: 5000 })
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
