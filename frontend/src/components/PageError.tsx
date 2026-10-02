import { isRouteErrorResponse, Link, useLocation, useRouteError } from 'react-router-dom'
import { Icon } from './Icon'

export function PageError({ standalone = false }: { standalone?: boolean }) {
  const error = useRouteError()
  const { pathname } = useLocation()
  const assignmentId = pathname.match(/^\/assignments\/(\d+)(?:\/|$)/)?.[1]
  const unavailable = isRouteErrorResponse(error) && error.status === 404
  const content = (
    <section
      role="alert"
      className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-slate-900"
    >
      <h1 className="font-['Space_Grotesk'] text-2xl font-bold">
        {unavailable ? 'Page unavailable' : 'We couldn’t open this page'}
      </h1>
      <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
        {unavailable
          ? 'This page may have moved or you may not have access to it.'
          : 'Something went wrong while displaying this page. Refresh to try again, or return to your workspace.'}
      </p>
      <div className="mt-5 flex flex-wrap gap-3">
        <button type="button" onClick={() => window.location.reload()} className="workflow-button">
          Refresh page
        </button>
        <Link
          to={assignmentId ? `/assignments/${assignmentId}/submissions` : '/'}
          className="workflow-button"
        >
          <Icon name="back" />
          {assignmentId ? 'Back to submissions' : 'Back to dashboard'}
        </Link>
      </div>
    </section>
  )
  return standalone ? (
    <main className="flex min-h-screen items-center justify-center px-6">
      <div className="app-card w-full max-w-2xl p-6">{content}</div>
    </main>
  ) : (
    content
  )
}
