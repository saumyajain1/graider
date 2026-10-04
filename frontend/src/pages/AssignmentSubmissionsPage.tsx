import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getAssignment, listQuestions } from '../api/assignments'
import { getApiErrorMessage } from '../api/errors'
import {
  createSubmission,
  gradeAllSubmissions,
  gradeSubmission,
  importSubmissionsCsv,
  listSubmissionImports,
  listSubmissions,
  listReferenceAnswers,
  listRubric,
  type StudentSubmission,
} from '../api/grading'
import { AIButton } from '../components/AIButton'
import { QueryError } from '../components/QueryError'
import { WorkflowBack, WorkflowContinue } from '../components/WorkflowNavigation'
import { WorkflowDraftProvider, useDraft, useDraftSaves } from '../hooks/useDraftSaves'
import { SubmissionTable } from '../components/SubmissionTable'
import { marksInCents } from '../lib/marks'

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
  const drafts = useDraftSaves()
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

  const questionsQuery = useQuery({
    queryKey: ['assignments', assignmentId, 'questions'],
    queryFn: () => listQuestions(assignmentId!),
    enabled: Boolean(assignmentId),
  })
  const answersQuery = useQuery({
    queryKey: ['assignments', assignmentId, 'reference-answers'],
    queryFn: () => listReferenceAnswers(assignmentId!),
    enabled: Boolean(assignmentId),
  })
  const rubricQuery = useQuery({
    queryKey: ['assignments', assignmentId, 'rubric'],
    queryFn: () => listRubric(assignmentId!),
    enabled: Boolean(assignmentId),
  })
  const setupPending = questionsQuery.isPending || answersQuery.isPending || rubricQuery.isPending
  const setupError = questionsQuery.isError || answersQuery.isError || rubricQuery.isError
  const questions = (questionsQuery.data ?? []).filter(
    (question) => question.part_type === 'question',
  )
  const setupIssues = questions.length
    ? questions.flatMap((question) => {
        const issues: string[] = []
        if (marksInCents(question.max_marks) === null)
          issues.push(`${question.display_label}: set positive total marks.`)
        if (
          !answersQuery.data
            ?.find((answer) => answer.question_part_id === question.id)
            ?.answer_text.trim()
        )
          issues.push(`${question.display_label}: add a reference answer.`)
        const criteria =
          rubricQuery.data?.find((group) => group.question_part_id === question.id)?.criteria ?? []
        if (
          !criteria.length ||
          criteria.some((criterion) => marksInCents(criterion.max_points) === null) ||
          criteria.reduce(
            (sum, criterion) => sum + (marksInCents(criterion.max_points) ?? 0),
            0,
          ) !== marksInCents(question.max_marks)
        )
          issues.push(`${question.display_label}: rubric points must add up to its total marks.`)
        return issues
      })
    : ['Add at least one scored question.']
  const gradingReady = !setupPending && !setupError && setupIssues.length === 0

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

  const manualDirty = Boolean(
    manualForm.student_name.trim() ||
    manualForm.student_identifier.trim() ||
    manualForm.raw_response_text.trim() ||
    manualForm.response_file,
  )
  useDraft(
    'new-submission',
    {
      dirty: manualDirty,
      validate: () => {
        if (!manualDirty) return
        if (!manualForm.student_name.trim())
          throw new Error('Enter the student name or clear the new submission draft.')
        if (!manualForm.raw_response_text.trim() && !manualForm.response_file)
          throw new Error('Provide response text or a submission file before continuing.')
      },
      save: () => createMutation.mutateAsync(manualForm),
    },
    drafts,
  )
  useDraft(
    'csv-import',
    {
      dirty: Boolean(csvFile),
      validate: () => {},
      save: () => importMutation.mutateAsync(csvFile!),
    },
    drafts,
  )
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
  if (!assignment) {
    return <div className="text-sm text-rose-700">Assignment not found.</div>
  }

  return (
    <WorkflowDraftProvider value={drafts}>
      <div className="space-y-8">
        <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-[2rem] border border-slate-200 p-6">
            <p className="text-sm font-semibold tracking-[0.18em] text-slate-400 uppercase">
              Submissions intake
            </p>
            <h1 className="mt-3 section-title">{assignment.title}</h1>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Add a single student response manually, upload a PDF/TXT submission, or import a
              simple CSV. Once responses are in, trigger grading per student or across the full
              roster.
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
              Grade submitted responses
            </h2>
            <p className="mt-4 text-sm leading-6 text-fuchsia-100/72">
              Prepare reference answers and rubric criteria for every question before grading.
              Review the results and retry any submissions that need attention.
            </p>
            <AIButton
              busy={gradeAllMutation.isPending}
              disabled={
                drafts.isSaving ||
                createMutation.isPending ||
                importMutation.isPending ||
                !gradingReady ||
                submissions.length === 0 ||
                gradeAllMutation.isPending ||
                gradeMutation.isPending
              }
              onClick={() => gradeAllMutation.mutate()}
              className="mt-6"
            >
              {gradeAllMutation.isPending ? 'Grading roster...' : 'Grade all submissions'}
            </AIButton>
          </div>
        </section>

        {!gradingReady ? (
          <section
            className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900"
            aria-live="polite"
          >
            <h2 className="font-semibold">
              {setupPending
                ? 'Checking grading setup…'
                : setupError
                  ? 'Could not check grading setup'
                  : 'Complete grading setup'}
            </h2>
            {!setupPending && !setupError ? (
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {setupIssues.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            ) : null}
            {setupError ? (
              <button
                type="button"
                className="mt-3 underline"
                onClick={() => {
                  void questionsQuery.refetch()
                  void answersQuery.refetch()
                  void rubricQuery.refetch()
                }}
              >
                Retry setup check
              </button>
            ) : null}
            {!setupPending ? (
              <p className="mt-3">
                Review{' '}
                <Link className="underline" to={`/assignments/${assignment.id}/questions`}>
                  questions
                </Link>
                ,{' '}
                <Link className="underline" to={`/assignments/${assignment.id}/reference-answers`}>
                  reference answers
                </Link>
                , and{' '}
                <Link className="underline" to={`/assignments/${assignment.id}/rubric`}>
                  rubrics
                </Link>{' '}
                before grading. You can add submissions now.
              </p>
            ) : null}
          </section>
        ) : null}

        {errorMessage ? (
          <div
            role="alert"
            className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
          >
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
            onSubmit={(event) => {
              event.preventDefault()
              createMutation.mutate(manualForm)
            }}
          >
            <fieldset
              disabled={drafts.isSaving || createMutation.isPending || importMutation.isPending}
              className="contents"
            >
              <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
                Add one submission
              </h2>
              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate-700">
                    Student name
                  </span>
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
                <span className="mb-2 block text-sm font-medium text-slate-700">
                  Submission file
                </span>
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
                <span className="mb-2 block text-sm font-medium text-slate-700">
                  Raw response text
                </span>
                <textarea
                  rows={9}
                  value={manualForm.raw_response_text}
                  onChange={(event) =>
                    setManualForm((current) => ({
                      ...current,
                      raw_response_text: event.target.value,
                    }))
                  }
                  className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
                  placeholder="Paste the student's full response here, or leave this blank and upload a PDF/TXT file above."
                />
              </label>

              <button
                type="submit"
                disabled={
                  drafts.isSaving ||
                  createMutation.isPending ||
                  !manualForm.student_name.trim() ||
                  (!manualForm.raw_response_text.trim() && !manualForm.response_file)
                }
                className="mt-5 rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-fuchsia-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {createMutation.isPending ? 'Adding...' : 'Add submission'}
              </button>
            </fieldset>
          </form>

          <form
            className="rounded-[1.75rem] border border-slate-200 bg-slate-50 p-6"
            onSubmit={(event) => {
              event.preventDefault()
              if (!csvFile) {
                setStatusMessage(null)
                setErrorMessage('Choose a CSV file first.')
                return
              }
              importMutation.mutate(csvFile)
            }}
          >
            <fieldset
              disabled={drafts.isSaving || createMutation.isPending || importMutation.isPending}
              className="contents"
            >
              <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
                Import CSV
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Use columns <code>student_name</code> and either <code>response_text</code> or{' '}
                <code>raw_response_text</code>. <code>student_identifier</code> or{' '}
                <code>student_id</code> is optional.
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
                disabled={!csvFile || importMutation.isPending}
                className="mt-5 rounded-full border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {importMutation.isPending ? 'Importing...' : 'Import submissions'}
              </button>
              {importsQuery.isError ? (
                <div className="mt-5">
                  <QueryError
                    error={importsQuery.error}
                    onRetry={() => {
                      void importsQuery.refetch()
                    }}
                  />
                </div>
              ) : null}
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
            </fieldset>
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

          <div className="mt-5">
            <SubmissionTable
              submissions={submissions}
              assignmentId={assignment.id}
              gradeAction={(submission) => {
                const busy =
                  (gradeMutation.isPending && gradeMutation.variables === submission.id) ||
                  submission.grading_status === 'grading'
                return (
                  <AIButton
                    busy={busy}
                    disabled={
                      drafts.isSaving ||
                      createMutation.isPending ||
                      importMutation.isPending ||
                      !gradingReady ||
                      gradeMutation.isPending ||
                      gradeAllMutation.isPending ||
                      submission.grading_status === 'grading'
                    }
                    onClick={() => gradeMutation.mutate(submission.id)}
                  >
                    {busy ? 'Grading…' : getGradeActionLabel(submission.grading_status)}
                  </AIButton>
                )
              }}
            />
          </div>
        </section>

        <div className="flex flex-wrap gap-3">
          <WorkflowBack to={`/assignments/${assignment.id}/rubric`}>Back to rubric</WorkflowBack>
          <WorkflowContinue
            to={`/assignments/${assignment.id}/review`}
            disabled={
              drafts.isSaving ||
              createMutation.isPending ||
              importMutation.isPending ||
              gradeMutation.isPending ||
              gradeAllMutation.isPending
            }
          >
            review
          </WorkflowContinue>
        </div>
      </div>
    </WorkflowDraftProvider>
  )
}
