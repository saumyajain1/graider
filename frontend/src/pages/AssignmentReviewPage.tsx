import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { WorkflowBack } from '../components/WorkflowNavigation'
import { QueryError } from '../components/QueryError'
import { SubmissionTable } from '../components/SubmissionTable'

import { getAssignment } from '../api/assignments'
import { listSubmissions } from '../api/grading'

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

  if (assignmentQuery.isError || submissionsQuery.isError) {
    return (
      <QueryError
        error={assignmentQuery.error || submissionsQuery.error}
        onRetry={() => {
          void assignmentQuery.refetch()
          void submissionsQuery.refetch()
        }}
      />
    )
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
        <SubmissionTable submissions={submissions} assignmentId={assignment.id} />
      ) : (
        <section className="rounded-[2rem] border border-dashed border-slate-300 bg-slate-50 p-8">
          <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            No submissions to review
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
            Add a student response to start reviewing. You can enter marks manually or grade with
            AI.
          </p>
          <Link
            to={`/assignments/${assignment.id}/submissions`}
            className="mt-6 inline-flex rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-fuchsia-700"
          >
            Open submissions
          </Link>
        </section>
      )}
      <WorkflowBack to={`/assignments/${assignment.id}/submissions`}>
        Back to submissions
      </WorkflowBack>
    </div>
  )
}
