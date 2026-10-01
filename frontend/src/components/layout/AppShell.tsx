import clsx from 'clsx'
import { useEffect, type PropsWithChildren } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'

import { getApiErrorMessage } from '../../api/errors'
import { useCurrentUser, useLogout } from '../../hooks/useAuth'

type NavigationItem = { label: string; to: string }

function getAssignmentId(pathname: string) {
  const match = pathname.match(/\/assignments\/(\d+)/)
  return match?.[1] ?? null
}

export function AppShell({ children }: PropsWithChildren) {
  const { user } = useCurrentUser()
  const logout = useLogout()
  const navigate = useNavigate()
  const location = useLocation()
  const assignmentId = getAssignmentId(location.pathname)

  const navItems: NavigationItem[] = [
    { label: 'Dashboard', to: '/' },
    ...(assignmentId
      ? [
          { label: 'Overview', to: `/assignments/${assignmentId}/overview` },
          { label: 'Questions', to: `/assignments/${assignmentId}/questions` },
          { label: 'Reference answers', to: `/assignments/${assignmentId}/reference-answers` },
          { label: 'Rubric', to: `/assignments/${assignmentId}/rubric` },
          { label: 'Submissions', to: `/assignments/${assignmentId}/submissions` },
          { label: 'Review', to: `/assignments/${assignmentId}/review` },
        ]
      : []),
  ]

  const pageTitle =
    location.pathname === '/'
      ? 'Dashboard'
      : location.pathname.includes('/review/')
        ? 'Student review'
        : location.pathname.endsWith('/review')
          ? 'Review queue'
          : location.pathname.endsWith('/reference-answers')
            ? 'Reference answers'
            : location.pathname.endsWith('/rubric')
              ? 'Rubric builder'
              : location.pathname.endsWith('/submissions')
                ? 'Submission intake'
                : location.pathname.endsWith('/questions')
                  ? 'Question setup'
                  : location.pathname === '/assignments/new'
                    ? 'Create assignment'
                    : 'Assignment overview'

  useEffect(() => {
    document.title = `${pageTitle} | Graider`
  }, [pageTitle])

  return (
    <div className="min-h-screen px-4 py-4 text-white md:px-6 md:py-6">
      <div className="mx-auto grid min-h-[calc(100vh-2rem)] max-w-7xl gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="glass-panel min-w-0 p-6">
          <div>
            <Link to="/" className="block">
              <span className="font-['Space_Grotesk'] text-3xl font-bold">Graider</span>
              <p className="mt-2 text-sm text-fuchsia-50/70">AI-assisted grading</p>
            </Link>

            <nav
              aria-label="Workspace"
              className={clsx(
                'mt-8 grid gap-2 lg:grid-cols-1',
                assignmentId ? 'grid-cols-2' : 'grid-cols-1',
              )}
            >
              {navItems.map((item) => (
                <NavLink
                  key={item.label}
                  to={item.to}
                  className={({ isActive }) =>
                    clsx(
                      'block rounded-2xl px-4 py-3 text-sm transition',
                      isActive
                        ? 'bg-white text-slate-950 shadow-lg'
                        : 'border border-white/10 text-fuchsia-50/80 hover:border-white/25 hover:bg-white/10',
                    )
                  }
                  end={item.to === '/'}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </aside>

        <div className="flex min-h-full min-w-0 flex-col gap-4">
          <header className="glass-panel flex flex-col gap-4 px-6 py-5 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-xs font-semibold tracking-[0.2em] text-fuchsia-100/60 uppercase">
                {assignmentId ? 'Assignment workspace' : 'Your workspace'}
              </p>
              <h2 className="mt-2 font-['Space_Grotesk'] text-2xl font-bold">{pageTitle}</h2>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              {assignmentId ? (
                <div className="rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm text-fuchsia-50/80">
                  Assignment #{assignmentId}
                </div>
              ) : null}
              <div className="rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm">
                {user?.full_name}
              </div>
              <button
                type="button"
                disabled={logout.isPending}
                onClick={() =>
                  logout.mutate(undefined, {
                    onSuccess: () => navigate('/login', { replace: true }),
                  })
                }
                className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-fuchsia-100"
              >
                {logout.isPending ? 'Signing out...' : 'Sign out'}
              </button>
            </div>
          </header>

          <main
            id="main-content"
            className="app-card min-h-[calc(100vh-10rem)] min-w-0 flex-1 p-6 md:p-8"
          >
            {logout.isError ? (
              <div
                role="alert"
                className="mb-5 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700"
              >
                {getApiErrorMessage(logout.error, 'Could not sign out. Please try again.')}
              </div>
            ) : null}
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
