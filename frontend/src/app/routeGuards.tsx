import { Navigate, Outlet } from 'react-router-dom'

import { ApiError } from '../api/client'
import { AppShell } from '../components/layout/AppShell'
import { QueryError } from '../components/QueryError'
import { useCurrentUser } from '../hooks/useAuth'
import { useDraftSaves, WorkflowDraftProvider } from '../hooks/useDraftSaves'
import { UnsavedChangesGuard } from '../components/UnsavedChangesGuard'
import { LoginPage } from '../pages/LoginPage'

export function ProtectedLayout() {
  const drafts = useDraftSaves()
  const { error, isLoading, user, refetch } = useCurrentUser()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-center text-white">
        <div className="glass-panel max-w-md px-10 py-12">
          <p className="font-medium tracking-[0.2em] text-fuchsia-100/70 uppercase">Graider</p>
          <h1 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold">Loading workspace</h1>
          <p className="mt-4 text-sm text-fuchsia-50/70">
            Signing you in and loading your assignments.
          </p>
        </div>
      </div>
    )
  }

  if (error && !(error instanceof ApiError && error.status === 401)) {
    return (
      <SessionError
        error={error}
        onRetry={() => {
          void refetch()
        }}
      />
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return (
    <WorkflowDraftProvider value={drafts}>
      <UnsavedChangesGuard>
        <AppShell>
          <Outlet />
        </AppShell>
      </UnsavedChangesGuard>
    </WorkflowDraftProvider>
  )
}

export function PublicOnly() {
  const { error, isLoading, user, refetch } = useCurrentUser()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-white">
        <div className="text-sm text-fuchsia-100/70">Preparing Graider...</div>
      </div>
    )
  }

  if (error && !(error instanceof ApiError && error.status === 401)) {
    return (
      <SessionError
        error={error}
        onRetry={() => {
          void refetch()
        }}
      />
    )
  }

  if (user) {
    return <Navigate to="/" replace />
  }

  return <LoginPage />
}

function SessionError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="app-card w-full max-w-md p-8">
        <h1 className="mb-5 font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
          Could not load Graider
        </h1>
        <QueryError error={error} onRetry={onRetry} />
      </div>
    </div>
  )
}
