import clsx from 'clsx'
import { useEffect, type PropsWithChildren } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'

import { ProfileMenu } from './ProfileMenu'
import { PublicLinks } from '../PublicLinks'

type NavigationItem = { label: string; to: string | null }

function getAssignmentId(pathname: string) {
  const match = pathname.match(/\/assignments\/(\d+)/)
  return match?.[1] ?? null
}

export function AppShell({ children }: PropsWithChildren) {
  const location = useLocation()
  const assignmentId = getAssignmentId(location.pathname)

  const navItems: NavigationItem[] = [
    { label: 'Dashboard', to: '/' },
    ...[
      { label: 'Assignment overview', path: 'overview' },
      { label: 'Questions', path: 'questions' },
      { label: 'Reference answers', path: 'reference-answers' },
      { label: 'Rubric', path: 'rubric' },
      { label: 'Submissions', path: 'submissions' },
      { label: 'Review', path: 'review' },
    ].map(({ label, path }) => ({
      label,
      to: assignmentId ? `/assignments/${assignmentId}/${path}` : null,
    })),
  ]

  const pageTitle =
    location.pathname === '/'
      ? 'Dashboard'
      : location.pathname === '/profile'
        ? 'Your account'
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

            <nav aria-label="Workspace" className="mt-8 grid grid-cols-2 gap-2 lg:grid-cols-1">
              {navItems.map((item) =>
                item.to ? (
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
                ) : (
                  <button
                    key={item.label}
                    type="button"
                    disabled
                    title="Open an assignment to use this page."
                    className="block cursor-not-allowed rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-left text-sm text-slate-400/60"
                  >
                    {item.label}
                  </button>
                ),
              )}
            </nav>
            <div className="mt-8 border-t border-white/10 pt-6 text-fuchsia-50/80">
              <PublicLinks />
            </div>
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
              <ProfileMenu />
            </div>
          </header>

          <main
            id="main-content"
            className="app-card min-h-[calc(100vh-10rem)] min-w-0 flex-1 p-6 md:p-8"
          >
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
