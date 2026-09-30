import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getAssignment } from '../api/assignments'
import { getApiErrorMessage } from '../api/errors'
import {
  createSubmission,
  gradeAllSubmissions,
  gradeSubmission,
  importSubmissionsCsv,
  listSubmissionImports,
  listSubmissions,
  type StudentSubmission,
} from '../api/grading'

function getStatusTone(status: StudentSubmission['grading_status']) {
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

function getGradeActionLabel(status: StudentSubmission['grading_status']) {
  if (status === 'grading') {
    return 'Grading...'
  }
  if (status === 'graded' || status === 'reviewed' || status === 'finalized') {
    return 'Regrade'
  }
  return 'Grade'
}

export function AssignmentSubmissionsPage() {
  const { assignmentId } = useParams()
  const queryClient = useQueryClient()
  const [manualForm, setManualForm] = useState({
    student_name: '',
    student_identifier: '',
    raw_response_text: '',
    response_file: null as File | null,
  })
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)

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

  const importsQuery = useQuery({
    queryKey: ['assignments', assignmentId, 'imports'],
    queryFn: () => listSubmissionImports(assignmentId!),
    enabled: Boolean(assignmentId),
  })

  const refreshAssignmentData = async () => {
    await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'submissions'] })
    await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'imports'] })
    await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
    await queryClient.invalidateQueries({ queryKey: ['assignments'] })
  }

  const createMutation = useMutation({
    mutationFn: (payload: {
      student_name: string
      student_identifier?: string
      raw_response_text?: string
      response_file?: File | null
    }) => createSubmission(assignmentId!, payload),
    onSuccess: async () => {
      setErrorMessage(null)
      setStatusMessage('Submission added.')
      setManualForm({
        student_name: '',
        student_identifier: '',
        raw_response_text: '',
        response_file: null,
      })
      await refreshAssignmentData()
    },
    onError: (error) => {
      setStatusMessage(null)
      setErrorMessage(getApiErrorMessage(error))
    },
  })

  const importMutation = useMutation({
    mutationFn: (file: File) => importSubmissionsCsv(assignmentId!, file),
    onSuccess: async (submissions) => {
      setErrorMessage(null)
      setStatusMessage(
        `${submissions.length} submission${submissions.length === 1 ? '' : 's'} imported.`,
      )
      setCsvFile(null)
      await refreshAssignmentData()
    },
    onError: (error) => {
      setStatusMessage(null)
      setErrorMessage(getApiErrorMessage(error))
    },
  })

  const gradeMutation = useMutation({
    mutationFn: (submissionId: number) => gradeSubmission(submissionId),
    onSuccess: async (submission) => {
      setErrorMessage(null)
      setStatusMessage(`Graded ${submission.student_name}.`)
      await refreshAssignmentData()
    },
    onError: async (error) => {
      setStatusMessage(null)
      setErrorMessage(getApiErrorMessage(error))
      await refreshAssignmentData()
    },
  })

  const gradeAllMutation = useMutation({
    mutationFn: () => gradeAllSubmissions(assignmentId!),
    onSuccess: async (result) => {
      setErrorMessage(null)
      setStatusMessage(
        `Graded ${result.graded_count} submission${result.graded_count === 1 ? '' : 's'} with ${result.failed_count} failure${result.failed_count === 1 ? '' : 's'}.`,
      )
      await refreshAssignmentData()
    },
    onError: async (error) => {
      setStatusMessage(null)
      setErrorMessage(getApiErrorMessage(error))
      await refreshAssignmentData()
    },
  })

  const submissions = useMemo(() => submissionsQuery.data ?? [], [submissionsQuery.data])
  const stats = useMemo(() => {
    return {
      graded: submissions.filter((submission) =>
        ['graded', 'reviewed', 'finalized'].includes(submission.grading_status),
      ).length,
      failed: submissions.filter((submission) => submission.grading_status === 'failed').length,
      pending: submissions.filter((submission) =>
        ['pending', 'grading'].includes(submission.grading_status),
      ).length,
    }
  }, [submissions])

  if (assignmentQuery.isPending || submissionsQuery.isPending) {
    return <div className="text-sm text-slate-600">Loading submissions...</div>
  }

  const assignment = assignmentQuery.data
  if (!assignment) {
    return <div className="text-sm text-rose-700">Assignment not found.</div>
  }

  return (
    <div className="space-y-8">
      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[2rem] border border-slate-200 p-6">
          <p className="text-sm font-semibold tracking-[0.18em] text-slate-400 uppercase">
            Submissions intake
          </p>
          <h1 className="mt-3 section-title">{assignment.title}</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Add a single student response manually, upload a PDF/TXT submission, or import a simple
            CSV. Once responses are in, trigger grading per student or across the full roster.
          </p>

          <div className="mt-5 flex flex-wrap gap-3 text-xs font-semibold">
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
              {assignment.question_count} questions ready
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
              {submissions.length} submissions loaded
            </span>
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">
              {stats.graded} graded
            </span>
          </div>
        </div>

        <div className="rounded-[2rem] bg-slate-950 px-6 py-7 text-white">
          <p className="text-sm font-semibold tracking-[0.18em] text-fuchsia-200/65 uppercase">
            Batch action
          </p>
          <h2 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold">
            Grade the entire roster once the rubric is stable.
          </h2>
          <p className="mt-4 text-sm leading-6 text-fuchsia-100/72">
            Failed rows remain visible with their latest error so you can retry after fixing the
            source material or AI configuration.
          </p>
          <button
            type="button"
            disabled={submissions.length === 0 || gradeAllMutation.isPending}
            onClick={() => void gradeAllMutation.mutateAsync()}
            className="mt-6 inline-flex rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-fuchsia-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {gradeAllMutation.isPending ? 'Grading roster...' : 'Grade all submissions'}
          </button>
        </div>
      </section>

      {errorMessage ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {errorMessage}
        </div>
      ) : null}

      {statusMessage ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {statusMessage}
        </div>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <form
          className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm"
          onSubmit={async (event) => {
            event.preventDefault()
            await createMutation.mutateAsync(manualForm)
          }}
        >
          <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            Add one submission
          </h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">Student name</span>
              <input
                required
                value={manualForm.student_name}
                onChange={(event) =>
                  setManualForm((current) => ({ ...current, student_name: event.target.value }))
                }
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
                placeholder="Saumya Jain"
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">
                Student identifier
              </span>
              <input
                value={manualForm.student_identifier}
                onChange={(event) =>
                  setManualForm((current) => ({
                    ...current,
                    student_identifier: event.target.value,
                  }))
                }
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
                placeholder="1001"
              />
            </label>
          </div>

          <label className="mt-4 block">
            <span className="mb-2 block text-sm font-medium text-slate-700">Submission file</span>
            <input
              type="file"
              accept=".pdf,.txt,application/pdf,text/plain"
              onChange={(event) =>
                setManualForm((current) => ({
                  ...current,
                  response_file: event.target.files?.[0] ?? null,
                }))
              }
              className="block w-full rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-4 text-sm text-slate-500"
            />
          </label>

          {manualForm.response_file ? (
            <div className="mt-4 rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
              Selected file: {manualForm.response_file.name}
            </div>
          ) : null}

          <label className="mt-4 block">
            <span className="mb-2 block text-sm font-medium text-slate-700">Raw response text</span>
            <textarea
              rows={9}
              value={manualForm.raw_response_text}
              onChange={(event) =>
                setManualForm((current) => ({ ...current, raw_response_text: event.target.value }))
              }
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
              placeholder="Paste the student's full response here, or leave this blank and upload a PDF/TXT file above."
            />
          </label>

          <button
            type="submit"
            disabled={createMutation.isPending || !manualForm.student_name.trim()}
            className="mt-5 rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-fuchsia-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {createMutation.isPending ? 'Adding...' : 'Add submission'}
          </button>
        </form>

        <form
          className="rounded-[1.75rem] border border-slate-200 bg-slate-50 p-6"
          onSubmit={async (event) => {
            event.preventDefault()
            if (!csvFile) {
              setStatusMessage(null)
              setErrorMessage('Choose a CSV file first.')
              return
            }
            await importMutation.mutateAsync(csvFile)
          }}
        >
          <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">Import CSV</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Use columns `student_name` and either `response_text` or `raw_response_text`.
            `student_identifier` or `student_id` is optional.
          </p>

          <label className="mt-5 block">
            <span className="mb-2 block text-sm font-medium text-slate-700">CSV file</span>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setCsvFile(event.target.files?.[0] ?? null)}
              className="block w-full rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-4 text-sm text-slate-500"
            />
          </label>

          {csvFile ? (
            <div className="mt-4 rounded-2xl bg-white px-4 py-3 text-sm text-slate-600">
              Selected: {csvFile.name}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={importMutation.isPending}
            className="mt-5 rounded-full border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {importMutation.isPending ? 'Importing...' : 'Import submissions'}
          </button>
          {(importsQuery.data?.length ?? 0) > 0 ? (
            <div className="mt-6 border-t border-slate-200 pt-4">
              <h3 className="text-sm font-semibold text-slate-800">Previous imports</h3>
              <ul className="mt-2 space-y-2 text-sm">
                {importsQuery.data?.map((item) => (
                  <li key={item.id}>
                    <a href={item.source_file_url} className="text-fuchsia-700 underline">
                      {item.original_filename}
                    </a>{' '}
                    <span className="text-slate-500">({item.row_count} rows)</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </form>
      </section>

      <section className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold tracking-[0.18em] text-slate-400 uppercase">
              Roster
            </p>
            <h2 className="mt-2 font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
              Submission queue
            </h2>
          </div>
          <div className="flex flex-wrap gap-2 text-xs font-semibold">
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
              {stats.pending} pending
            </span>
            <span className="rounded-full bg-rose-50 px-3 py-1 text-rose-700">
              {stats.failed} failed
            </span>
          </div>
        </div>

        {submissions.length > 0 ? (
          <div className="mt-5 space-y-3">
            {submissions.map((submission) => {
              const isMutatingThisRow =
                gradeMutation.isPending && gradeMutation.variables === submission.id

              return (
                <article
                  key={submission.id}
                  className="rounded-2xl border border-slate-200 bg-slate-50 p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h3 className="text-lg font-semibold text-slate-950">
                        {submission.student_name}
                      </h3>
                      <p className="mt-1 text-sm text-slate-500">
                        {submission.student_identifier
                          ? `ID ${submission.student_identifier}`
                          : 'No identifier'}
                        {' · '}
                        {submission.upload_source === 'csv'
                          ? 'Imported via CSV'
                          : submission.upload_source === 'file'
                            ? 'Uploaded file'
                            : 'Added manually'}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs font-semibold">
                      <span
                        className={`rounded-full px-3 py-1 ${getStatusTone(submission.grading_status)}`}
                      >
                        {submission.grading_status.replace('_', ' ')}
                      </span>
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
                        {submission.total_score ? `${submission.total_score} total` : 'Not graded'}
                      </span>
                    </div>
                  </div>

                  <p className="mt-4 line-clamp-3 text-sm leading-6 text-slate-600">
                    {submission.raw_response_text || 'No raw response text stored yet.'}
                  </p>

                  {submission.response_filename ? (
                    <div className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                      Source file:{' '}
                      <a
                        href={submission.response_file_url ?? undefined}
                        className="text-fuchsia-700 underline"
                      >
                        {submission.response_filename}
                      </a>
                    </div>
                  ) : null}

                  {submission.ingestion_notes ? (
                    <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                      {submission.ingestion_notes}
                    </div>
                  ) : null}

                  {submission.last_error ? (
                    <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                      {submission.last_error}
                    </div>
                  ) : null}

                  <div className="mt-4 flex flex-wrap gap-3">
                    <button
                      type="button"
                      disabled={submission.grading_status === 'grading' || isMutatingThisRow}
                      onClick={() => void gradeMutation.mutateAsync(submission.id)}
                      className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-fuchsia-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isMutatingThisRow
                        ? 'Grading...'
                        : getGradeActionLabel(submission.grading_status)}
                    </button>
                    <Link
                      to={`/assignments/${assignment.id}/review/${submission.id}`}
                      className="rounded-full border border-slate-200 px-4 py-2 text-sm text-slate-500 transition hover:border-slate-950 hover:text-slate-950"
                    >
                      Open review
                    </Link>
                  </div>
                </article>
              )
            })}
          </div>
        ) : (
          <div className="mt-5 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-sm text-slate-600">
            No submissions yet. Add one manually or import a CSV to start grading.
          </div>
        )}
      </section>

      <div className="flex flex-wrap gap-3">
        <Link
          to={`/assignments/${assignment.id}/rubric`}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
        >
          Back to rubric
        </Link>
      </div>
    </div>
  )
}
