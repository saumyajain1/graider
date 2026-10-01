import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { getAssignment } from '../api/assignments'
import { listSubmissions } from '../api/grading'

function getStatusTone(status: string) {
  switch (status) {
    case 'graded':
    case 'reviewed':
    case 'finalized':
      return 'bg-emerald-50 text-emerald-700'
    case 'failed':
      return 'bg-rose-50 text-rose-700'
    case 'grading':
      return 'bg-amber-50 text-amber-700'
    default:
      return 'bg-slate-100 text-slate-600'
  }
}

export function AssignmentReviewPage() {
  const { assignmentId } = useParams()

  const assignmentQuery = useQuery({
    queryKey: ['assignments', assignmentId],
    queryFn: () => getAssignment(assignmentId!),
    enabled: Boolean(assignmentId),
  })

  const submissionsQuery = useQuery({
    queryKey: ['assignments', assignmentId, 'submissions'],
    queryFn: () => listSubmissions(assignmentId!),
    enabled: Boolean(assignmentId),
  })

  if (assignmentQuery.isPending || submissionsQuery.isPending) {
    return <div className="text-sm text-slate-600">Loading review queue...</div>
  }

  const assignment = assignmentQuery.data
  const submissions = submissionsQuery.data ?? []

  if (!assignment) {
    return <div className="text-sm text-rose-700">Assignment not found.</div>
  }

  const reviewedCount = submissions.filter((submission) =>
    ['reviewed', 'finalized'].includes(submission.grading_status),
  ).length
  const gradedCount = submissions.filter((submission) =>
    ['graded', 'reviewed', 'finalized'].includes(submission.grading_status),
  ).length

  return (
    <div className="space-y-8">
      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[2rem] border border-slate-200 p-6">
          <p className="text-sm font-semibold tracking-[0.18em] text-slate-400 uppercase">
            Review and finalize
          </p>
          <h1 className="mt-3 section-title">{assignment.title}</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Review AI output student by student, adjust scores or feedback, then finalize results
            and export a CSV for the assignment.
          </p>

          <div className="mt-5 flex flex-wrap gap-3 text-xs font-semibold">
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
              {submissions.length} submissions
            </span>
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">
              {gradedCount} ready for review
            </span>
            <span className="rounded-full bg-fuchsia-50 px-3 py-1 text-fuchsia-700">
              {reviewedCount} reviewed or finalized
            </span>
          </div>
        </div>

        <div className="rounded-[2rem] bg-slate-950 px-6 py-7 text-white">
          <p className="text-sm font-semibold tracking-[0.18em] text-fuchsia-200/65 uppercase">
            Export
          </p>
          <h2 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold">
            Download a simple CSV once the marks look right.
          </h2>
          <p className="mt-4 text-sm leading-6 text-fuchsia-100/72">
            The export includes each student’s status, total score, and per-question score and
            feedback columns.
          </p>
          <a
            href={`/api/assignments/${assignment.id}/export.csv`}
            className="mt-6 inline-flex rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-fuchsia-100"
          >
            Export CSV
          </a>
        </div>
      </section>

      {submissions.length > 0 ? (
        <section className="grid gap-4 md:grid-cols-2">
          {submissions.map((submission) => (
            <article
              key={submission.id}
              className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold tracking-[0.18em] text-slate-400 uppercase">
                    {submission.student_identifier || 'No identifier'}
                  </p>
                  <h2 className="mt-2 font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
                    {submission.student_name}
                  </h2>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${getStatusTone(submission.grading_status)}`}
                >
                  {submission.grading_status.replace('_', ' ')}
                </span>
              </div>

              <div className="mt-5 flex flex-wrap gap-3 text-xs font-semibold text-slate-500">
                <span className="rounded-full bg-slate-100 px-3 py-1">
                  {submission.total_score ? `${submission.total_score} total` : 'Not graded'}
                </span>
                <span className="rounded-full bg-slate-100 px-3 py-1">
                  {submission.upload_source === 'csv'
                    ? 'CSV import'
                    : submission.upload_source === 'file'
                      ? 'Uploaded file'
                      : 'Manual entry'}
                </span>
              </div>

              {submission.last_error ? (
                <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {submission.last_error}
                </div>
              ) : (
                <p className="mt-4 line-clamp-3 text-sm leading-6 text-slate-600">
                  {submission.raw_response_text || 'No raw response text stored yet.'}
                </p>
              )}

              <div className="mt-6 flex flex-wrap gap-3">
                <Link
                  to={`/assignments/${assignment.id}/review/${submission.id}`}
                  className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-fuchsia-700"
                >
                  Open review
                </Link>
                <Link
                  to={`/assignments/${assignment.id}/submissions`}
                  className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
                >
                  Back to submissions
                </Link>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <section className="rounded-[2rem] border border-dashed border-slate-300 bg-slate-50 p-8">
          <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            No submissions to review
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
            Add and grade at least one student response before using the review and export tools.
          </p>
          <Link
            to={`/assignments/${assignment.id}/submissions`}
            className="mt-6 inline-flex rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-fuchsia-700"
          >
            Open submissions
          </Link>
        </section>
      )}
    </div>
  )
}
