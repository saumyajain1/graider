import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { deleteAssignment, listAssignments } from '../api/assignments'
import { getApiErrorMessage } from '../api/errors'
import { QueryError } from '../components/QueryError'
import { formatStatus } from '../lib/format'

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(value))
}

export function DashboardPage() {
  const queryClient = useQueryClient()
  const assignmentsQuery = useQuery({
    queryKey: ['assignments'],
    queryFn: listAssignments,
  })
  const deleteMutation = useMutation({
    mutationFn: (assignmentId: string) => deleteAssignment(assignmentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
  })
  const assignments = assignmentsQuery.data ?? []
  const stats = {
    total: assignments.length,
    inSetup: assignments.filter((assignment) =>
      ['draft', 'questions_ready', 'reference_answers_ready', 'rubric_ready'].includes(
        assignment.status,
      ),
    ).length,
    needsReview: assignments.filter((assignment) => assignment.status === 'review_ready').length,
    finalized: assignments.filter((assignment) => assignment.status === 'finalized').length,
  }

  return (
    <div className="space-y-8">
      <section className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <div className="rounded-[2rem] bg-slate-950 px-7 py-8 text-white">
          <p className="text-xs font-semibold tracking-[0.24em] text-fuchsia-200/65 uppercase">
            Dashboard
          </p>
          <h1 className="mt-3 font-['Space_Grotesk'] text-4xl font-bold leading-tight">
            Your assignments
          </h1>
          <p className="mt-4 max-w-2xl text-sm text-fuchsia-100/72 md:text-base">
            Create an assignment or pick up where you left off.
          </p>
          <div className="mt-8">
            <Link
              to="/assignments/new"
              className="inline-flex items-center rounded-full bg-white px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-fuchsia-100"
            >
              Create assignment
            </Link>
          </div>
        </div>

        <div className="rounded-[2rem] border border-slate-200 bg-slate-50 p-6">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">
            At a glance
          </p>
          <div className="mt-5 space-y-4">
            {[
              ['Total assignments', String(stats.total)],
              ['Still in setup', String(stats.inSetup)],
              ['Ready for review', String(stats.needsReview)],
              ['Finalized', String(stats.finalized)],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex items-center justify-between rounded-2xl bg-white px-4 py-4 shadow-sm"
              >
                <span className="text-sm font-medium text-slate-600">{label}</span>
                <span className="rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold text-white tabular-nums">
                  {assignmentsQuery.isPending || assignmentsQuery.isError ? '—' : value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="section-title">Assignments</h2>
            <p className="mt-2 text-sm text-slate-600">
              Manage questions, submissions, and results for each assignment.
            </p>
          </div>
          {assignments.length > 0 ? (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
              {assignments.length} total
            </span>
          ) : null}
        </div>

        {deleteMutation.isError ? (
          <div
            role="alert"
            className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700"
          >
            {getApiErrorMessage(
              deleteMutation.error,
              'Could not delete the assignment. Please try again.',
            )}
          </div>
        ) : null}

        {assignmentsQuery.isPending ? (
          <div
            role="status"
            className="mt-5 rounded-[1.75rem] border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600"
          >
            Loading assignments...
          </div>
        ) : assignmentsQuery.isError ? (
          <div className="mt-5">
            <QueryError
              error={assignmentsQuery.error}
              onRetry={() => void assignmentsQuery.refetch()}
            />
          </div>
        ) : assignments.length > 0 ? (
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {assignments.map((assignment) => (
              <article
                key={assignment.id}
                className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-semibold tracking-[0.18em] text-slate-400 uppercase">
                      {assignment.course_name || 'Unassigned course'}
                    </p>
                    <h3 className="mt-2 font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
                      {assignment.title}
                    </h3>
                  </div>
                  <span className="rounded-full bg-fuchsia-50 px-3 py-1 text-xs font-semibold text-fuchsia-700">
                    {formatStatus(assignment.status)}
                  </span>
                </div>

                <p className="mt-4 line-clamp-3 text-sm leading-6 text-slate-600">
                  {assignment.description || 'No description yet.'}
                </p>

                <div className="mt-5 flex flex-wrap gap-3 text-xs font-medium text-slate-500">
                  <span className="rounded-full bg-slate-100 px-3 py-1">
                    {assignment.question_count} questions
                  </span>
                  <span className="rounded-full bg-slate-100 px-3 py-1">
                    {assignment.submission_count} submissions
                  </span>
                  <span className="rounded-full bg-slate-100 px-3 py-1">
                    Updated {formatTimestamp(assignment.updated_at)}
                  </span>
                </div>

                <div className="mt-6 flex flex-wrap gap-3">
                  <Link
                    to={`/assignments/${assignment.id}/overview`}
                    className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-fuchsia-700"
                  >
                    Open assignment overview
                  </Link>
                  <Link
                    to={`/assignments/${assignment.id}/questions`}
                    className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
                  >
                    Edit questions
                  </Link>
                  <button
                    type="button"
                    disabled={deleteMutation.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Delete "${assignment.title}" and its questions, answers, rubric, submissions, and results?`,
                        )
                      ) {
                        deleteMutation.mutate(String(assignment.id))
                      }
                    }}
                    className="rounded-full border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-700 transition hover:bg-rose-50 disabled:opacity-60"
                  >
                    {deleteMutation.isPending && deleteMutation.variables === String(assignment.id)
                      ? 'Deleting...'
                      : 'Delete'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="mt-5 rounded-[1.75rem] border border-dashed border-slate-300 bg-slate-50 p-8">
            <h3 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
              No assignments yet
            </h3>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
              Create an assignment to get started.
            </p>
          </div>
        )}
      </section>
    </div>
  )
}
