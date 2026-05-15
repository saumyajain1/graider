import { Navigate, Outlet } from 'react-router-dom'

import { ApiError } from '../api/client'
import { AppShell } from '../components/layout/AppShell'
import { useCurrentUser } from '../hooks/useAuth'
import { LoginPage } from '../pages/LoginPage'

export function ProtectedLayout() {
  const { isLoading, user } = useCurrentUser()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-center text-white">
        <div className="glass-panel max-w-md px-10 py-12">
          <p className="font-medium tracking-[0.2em] text-fuchsia-100/70 uppercase">
            Graider
          </p>
          <h1 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold">
            Loading workspace
          </h1>
          <p className="mt-4 text-sm text-fuchsia-50/70">
            Checking your teacher session and preparing the grading shell.
          </p>
        </div>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  )
}

export function PublicOnly() {
  const { error, isLoading, user } = useCurrentUser()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-white">
        <div className="text-sm text-fuchsia-100/70">Preparing Graider...</div>
      </div>
    )
  }

  if (error instanceof ApiError && error.status !== 401) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-center text-white">
        <div className="glass-panel max-w-md px-10 py-12">
          <p className="font-medium tracking-[0.2em] text-fuchsia-100/70 uppercase">
            Graider
          </p>
          <h1 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold">
            Backend unavailable
          </h1>
          <p className="mt-4 text-sm text-fuchsia-50/70">{error.message}</p>
        </div>
      </div>
    )
  }

  if (user) {
    return <Navigate to="/" replace />
  }

  return <LoginPage />
}
