import { useId, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { StudentSubmission } from '../api/grading'
import { formatStatus } from '../lib/format'

const statuses = ['pending', 'grading', 'graded', 'reviewed', 'finalized', 'failed'] as const

export function SubmissionTable({
  submissions,
  assignmentId,
  gradeAction,
}: {
  submissions: StudentSubmission[]
  assignmentId: number
  gradeAction?: (submission: StudentSubmission) => ReactNode
}) {
  const id = useId()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const query = search.trim().toLocaleLowerCase()
  const rows = submissions.filter(
    (submission) =>
      (!status || submission.grading_status === status) &&
      (!query ||
        submission.student_name.toLocaleLowerCase().includes(query) ||
        submission.student_identifier.toLocaleLowerCase().includes(query)),
  )
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-4">
        <label
          htmlFor={`${id}-search`}
          className="min-w-52 flex-1 text-sm font-medium text-slate-700"
        >
          Search students
          <input
            id={`${id}-search`}
            type="search"
            placeholder="Name or student number"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="mt-2 block w-full rounded-xl border border-slate-300 px-4 py-2 focus:border-fuchsia-500"
          />
        </label>
        <label htmlFor={`${id}-status`} className="text-sm font-medium text-slate-700">
          Status
          <select
            id={`${id}-status`}
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="mt-2 block rounded-xl border border-slate-300 px-4 py-2"
          >
            <option value="">All statuses</option>
            {statuses.map((value) => (
              <option key={value} value={value}>
                {formatStatus(value)}
              </option>
            ))}
          </select>
        </label>
        <p role="status" className="pb-2 text-sm text-slate-500">
          {rows.length} of {submissions.length} students
        </p>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Student submissions, grades, and review actions</caption>
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              {[
                'Student name',
                'Student number',
                'Grade',
                'Status',
                'Source',
                'Submitted',
                'Actions',
              ].map((heading) => (
                <th key={heading} scope="col" className="whitespace-nowrap px-4 py-3 font-semibold">
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {rows.map((submission) => (
              <tr key={submission.id} className="align-top hover:bg-fuchsia-50/40">
                <th scope="row" className="px-4 py-4 font-medium text-slate-950">
                  {submission.student_name}
                </th>
                <td className="px-4 py-4 text-slate-600">{submission.student_identifier || '—'}</td>
                <td className="whitespace-nowrap px-4 py-4 tabular-nums">
                  {submission.total_score ?? 'Not graded'}
                </td>
                <td className="px-4 py-4">
                  <span
                    className={`inline-block whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold ${submission.grading_status === 'failed' ? 'bg-rose-50 text-rose-700' : submission.grading_status === 'grading' ? 'bg-amber-50 text-amber-800' : ['graded', 'reviewed', 'finalized'].includes(submission.grading_status) ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}
                  >
                    {formatStatus(submission.grading_status)}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-600">
                  {submission.upload_source === 'csv'
                    ? 'CSV'
                    : submission.upload_source === 'file'
                      ? 'File'
                      : 'Manual'}
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-600">
                  <time dateTime={submission.created_at}>
                    {new Date(submission.created_at).toLocaleDateString()}
                  </time>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {gradeAction?.(submission)}
                    <Link
                      to={`/assignments/${assignmentId}/review/${submission.id}`}
                      aria-label={`Review ${submission.student_name}`}
                      className="rounded-full border border-slate-300 px-4 py-2 font-semibold text-slate-700 transition hover:border-fuchsia-700 hover:text-fuchsia-700"
                    >
                      Review
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
            {!rows.length ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-600">
                  {submissions.length
                    ? 'No students match your search and status filter.'
                    : 'No submissions yet.'}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  )
}
