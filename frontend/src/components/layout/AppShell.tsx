import clsx from 'clsx'
import type { PropsWithChildren } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'

import { useCurrentUser, useLogout } from '../../hooks/useAuth'

type NavigationItem =
  | {
      label: string
      to: string
      disabled?: false
    }
  | {
      label: string
      disabled: true
    }

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
    {
      label: 'Assignments',
      to: assignmentId ? `/assignments/${assignmentId}/overview` : '/assignments/new',
    },
    assignmentId
      ? { label: 'Questions', to: `/assignments/${assignmentId}/questions` }
      : { label: 'Questions', disabled: true },
    assignmentId
      ? { label: 'Reference Answers', to: `/assignments/${assignmentId}/reference-answers` }
      : { label: 'Reference Answers', disabled: true },
    assignmentId
      ? { label: 'Rubric', to: `/assignments/${assignmentId}/rubric` }
      : { label: 'Rubric', disabled: true },
    assignmentId
      ? { label: 'Submissions', to: `/assignments/${assignmentId}/submissions` }
      : { label: 'Submissions', disabled: true },
    assignmentId
      ? { label: 'Review', to: `/assignments/${assignmentId}/review` }
      : { label: 'Review', disabled: true },
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
                  : location.pathname.includes('/assignments/')
                    ? 'Assignment setup'
                    : 'Build your first assignment'
  const footerTitle = assignmentId ? 'Workflow' : 'Start here'
  const footerText = assignmentId
    ? 'Questions, reference answers, rubric, submissions, and review all belong to the current assignment.'
    : 'Create or open an assignment to unlock the full grading workflow.'

  return (
    <div className="min-h-screen px-4 py-4 text-white md:px-6 md:py-6">
      <div className="mx-auto grid min-h-[calc(100vh-2rem)] max-w-7xl gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="glass-panel flex flex-col justify-between p-6">
          <div>
            <Link to="/" className="block">
              <p className="text-sm font-semibold tracking-[0.28em] text-fuchsia-100/60 uppercase">
                Graider
              </p>
              <h1 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold leading-tight">
                Structured
                <br />
                grading workspace
              </h1>
            </Link>

            <div className="mt-10 space-y-2">
              {navItems.map((item) =>
                item.disabled ? (
                  <div
                    key={item.label}
                    className="rounded-2xl border border-white/10 px-4 py-3 text-sm text-fuchsia-50/45"
                  >
                    {item.label}
                  </div>
                ) : (
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
                ),
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-fuchsia-50/70">
            <p className="font-semibold text-white">{footerTitle}</p>
            <p className="mt-2">{footerText}</p>
          </div>
        </aside>

        <div className="flex min-h-full flex-col gap-4">
          <header className="glass-panel flex flex-col gap-4 px-6 py-5 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-xs font-semibold tracking-[0.2em] text-fuchsia-100/60 uppercase">
                Assignment workspace
              </p>
              <h2 className="mt-2 font-['Space_Grotesk'] text-2xl font-bold">
                {pageTitle}
              </h2>
            </div>
            <div className="flex items-center gap-3">
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
    </div>
  )
}
