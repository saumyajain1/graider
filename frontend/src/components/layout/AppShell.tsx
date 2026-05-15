import type { PropsWithChildren } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useCurrentUser, useLogout } from '../../hooks/useAuth'

export function AppShell({ children }: PropsWithChildren) {
  const { user } = useCurrentUser()
  const logout = useLogout()
  const navigate = useNavigate()

  return (
    <div className="min-h-screen px-4 py-4 text-white md:px-6 md:py-6">
      <div className="mx-auto flex min-h-[calc(100vh-2rem)] max-w-7xl flex-col gap-4">
        <header className="glass-panel flex flex-col gap-4 px-6 py-5 md:flex-row md:items-center md:justify-between">
          <Link to="/" className="block">
            <p className="text-sm font-semibold tracking-[0.28em] text-fuchsia-100/60 uppercase">
              Graider
            </p>
            <h1 className="mt-2 font-['Space_Grotesk'] text-2xl font-bold">
              Teacher workspace
            </h1>
          </Link>
          <div className="flex items-center gap-3">
            <div className="rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm">
              {user?.full_name}
            </div>
            <button
              type="button"
              onClick={async () => {
                await logout.mutateAsync()
                navigate('/login')
              }}
              className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-fuchsia-100"
            >
              Sign out
            </button>
          </div>
        </header>

        <main className="app-card min-h-[calc(100vh-10rem)] flex-1 p-6 md:p-8">
          {children}
        </main>
      </div>
    </div>
  )
}
