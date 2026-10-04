import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getAssignment } from '../api/assignments'
import { ApiError } from '../api/client'
import { useAIJobs } from '../hooks/useAIJobs'
import { AIJobNotice } from '../components/AIJobNotice'
import { getApiErrorMessage } from '../api/errors'
import {
  finalizeSubmission,
  getSubmissionGrading,
  saveQuestionReview,
  type CriterionReview,
  type RubricQuestion,
  type GradingResult,
  type SubmissionAnswerPart,
} from '../api/grading'
import { QueryError } from '../components/QueryError'
import { WorkflowBack } from '../components/WorkflowNavigation'
import { useDraft, useDraftSaves } from '../hooks/useDraftSaves'
import { formatStatus } from '../lib/format'

type ReviewPayload = {
  question_part_id: number
  criterion_results: CriterionReview[]
  final_feedback: string
  needs_review: boolean
}

function scoreCents(value: string | null, max: string): number | null {
  if (value === null || !/^\d+(?:\.\d{1,2})?$/.test(value.trim())) return null
  const cents = Math.round(Number(value) * 100)
  return cents >= 0 && cents <= Math.round(Number(max) * 100) ? cents : null
}

function ReviewEditor({
  question,
  referenceAnswer,
  answerPart,
  gradingResult,
  isBusy,
  onSave,
  onTotal,
}: {
  question: RubricQuestion
  referenceAnswer: string
  answerPart?: SubmissionAnswerPart
  gradingResult?: GradingResult
  isBusy: boolean
  onSave: (payload: ReviewPayload) => Promise<unknown>
  onTotal: (questionId: number, total: number | null) => void
}) {
  const criteria = gradingResult?.criterion_results.length
    ? gradingResult.criterion_results
    : question.criteria.map((criterion) => ({
        criterion_id: criterion.id,
        title: criterion.title,
        description: criterion.description,
        max_points: criterion.max_points,
        ai_score: null,
        final_score: null,
        ai_feedback: '',
        final_feedback: '',
      }))
  const saved = JSON.stringify({
    rows: criteria.map((row) => ({
      criterion_id: row.criterion_id,
      final_score: row.final_score,
      final_feedback: row.final_feedback,
    })),
    feedback: gradingResult?.final_feedback ?? '',
    needsReview: gradingResult?.needs_review ?? false,
  })
  const [draft, setDraft] = useState<{
    rows: CriterionReview[]
    feedback: string
    needsReview: boolean
  }>(() => JSON.parse(saved))
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setDraft(JSON.parse(saved))
    setError(null)
  }, [saved])
  const scores = draft.rows.map((row) =>
    scoreCents(
      row.final_score,
      criteria.find((criterion) => criterion.criterion_id === row.criterion_id)?.max_points ?? '0',
    ),
  )
  const entered = scores.filter((score) => score !== null).length
  const partialTotal = scores.reduce<number>((sum, score) => sum + (score ?? 0), 0)
  const total = criteria.length > 0 && entered === criteria.length ? partialTotal : null
  const max = gradingResult?.max_score ?? question.max_marks
  const rubricMax = criteria.reduce((sum, row) => sum + Math.round(Number(row.max_points) * 100), 0)
  const validSetup = Number(max) > 0 && rubricMax === Math.round(Number(max) * 100)
  useEffect(() => {
    onTotal(question.question_part_id, total)
  }, [onTotal, question.question_part_id, total])
  const editRow = (id: number, changes: Partial<CriterionReview>) =>
    setDraft((current) => ({
      ...current,
      rows: current.rows.map((row) => (row.criterion_id === id ? { ...row, ...changes } : row)),
    }))
  const payload = {
    question_part_id: question.question_part_id,
    criterion_results: draft.rows,
    final_feedback: draft.feedback,
    needs_review: draft.needsReview,
  }
  const validate = () => {
    if (!validSetup)
      throw new Error(
        'Set valid question marks and rubric allocations before saving review scores.',
      )
    if (
      draft.rows.some(
        (row) =>
          row.final_score !== null &&
          scoreCents(
            row.final_score,
            criteria.find((criterion) => criterion.criterion_id === row.criterion_id)!.max_points,
          ) === null,
      )
    )
      throw new Error(
        'Each score must be between zero and its criterion maximum, with at most two decimal places.',
      )
  }
  useDraft(`review-${question.question_part_id}`, {
    dirty: JSON.stringify(draft) !== saved,
    validate,
    save: () => onSave(payload),
  })
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        try {
          validate()
          setError(null)
          void onSave(payload).catch(() => {})
        } catch (error) {
          setError(error instanceof Error ? error.message : 'Could not save review.')
        }
      }}
      className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold tracking-[0.18em] text-slate-400 uppercase">
            {question.display_label}
          </p>
          <h2 className="mt-2 font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            {question.question_text}
          </h2>
        </div>
        <p
          className="rounded-full bg-fuchsia-50 px-4 py-2 text-sm font-semibold text-fuchsia-800"
          aria-live="polite"
        >
          Question total: {total === null ? 'Incomplete' : (total / 100).toFixed(2)}
          {Number(max) > 0 ? ` / ${max}` : ' · total not set'}
        </p>
      </div>
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl bg-slate-50 p-4">
          <h3 className="text-sm font-semibold text-slate-700">Student answer</h3>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-600">
            {answerPart
              ? answerPart.extracted_answer_text || 'No answer found for this question.'
              : 'Answers have not been mapped to questions yet. Read the full submission above to enter marks manually.'}
          </p>
        </div>
        <details className="rounded-xl bg-slate-50 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-slate-700">
            Reference answer
          </summary>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-600">
            {referenceAnswer || 'No reference answer has been added yet.'}
          </p>
        </details>
      </div>
      {gradingResult?.ai_score !== null && gradingResult?.ai_score !== undefined ? (
        <p className="mt-4 text-sm text-slate-600">
          AI question total: {gradingResult.ai_score}
          {Number(gradingResult.max_score) > 0
            ? ` / ${gradingResult.max_score}`
            : ' marks · total not set'}{' '}
          · Confidence: {gradingResult.confidence_score ?? 'n/a'}
        </p>
      ) : null}
      {gradingResult && !gradingResult.criterion_results.length ? (
        <p className="mt-3 text-sm text-amber-800">
          This earlier result has no rubric breakdown. Regrade with AI or enter criterion marks
          below; existing totals remain saved until you save a new breakdown.
        </p>
      ) : null}
      {!validSetup ? (
        <p role="alert" className="mt-4 text-sm text-amber-800">
          Set positive question marks and matching rubric allocations before saving criterion
          grades.
        </p>
      ) : null}
      <fieldset disabled={isBusy || !validSetup} className="mt-5 space-y-4">
        <legend className="text-base font-semibold text-slate-900">
          Rubric marks and feedback
        </legend>
        {criteria.map((criterion) => {
          const row = draft.rows.find((item) => item.criterion_id === criterion.criterion_id)
          if (!row) return null
          return (
            <section
              key={criterion.criterion_id}
              className="rounded-xl border border-slate-200 p-4"
            >
              <h3 className="font-semibold text-slate-950">
                {criterion.title}{' '}
                <span className="font-normal text-slate-500">· {criterion.max_points} marks</span>
              </h3>
              <p className="mt-1 text-sm leading-6 text-slate-600">{criterion.description}</p>
              {criterion.ai_score !== null ? (
                <div className="mt-3 rounded-lg bg-fuchsia-50 px-3 py-2 text-sm text-fuchsia-900">
                  <p className="font-medium">
                    AI score: {criterion.ai_score} / {criterion.max_points}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap">{criterion.ai_feedback}</p>
                </div>
              ) : null}
              <div className="mt-3 grid gap-4 md:grid-cols-[10rem_1fr]">
                <label className="block text-sm font-medium text-slate-700">
                  Score for {criterion.title}
                  <input
                    type="number"
                    min="0"
                    max={criterion.max_points}
                    step="0.01"
                    value={row.final_score ?? ''}
                    onChange={(event) =>
                      editRow(criterion.criterion_id, { final_score: event.target.value || null })
                    }
                    className="mt-2 block w-full rounded-xl border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="block text-sm font-medium text-slate-700">
                  Feedback for {criterion.title}
                  <textarea
                    rows={3}
                    value={row.final_feedback}
                    onChange={(event) =>
                      editRow(criterion.criterion_id, { final_feedback: event.target.value })
                    }
                    className="mt-2 block w-full rounded-xl border border-slate-300 px-3 py-2"
                  />
                </label>
              </div>
            </section>
          )
        })}
        {!criteria.length ? (
          <p className="text-sm text-slate-600">
            Add rubric criteria to this question to enter grades.
          </p>
        ) : null}
        <p className="text-sm text-slate-600" aria-live="polite">
          {entered} of {criteria.length} criterion scores entered.{' '}
          {total === null
            ? `Partial total: ${(partialTotal / 100).toFixed(2)} marks.`
            : `Total: ${(total / 100).toFixed(2)} / ${max}.`}
        </p>
        <label className="block text-sm font-medium text-slate-700">
          Overall feedback for {question.display_label}
          <textarea
            rows={3}
            value={draft.feedback}
            onChange={(event) =>
              setDraft((current) => ({ ...current, feedback: event.target.value }))
            }
            className="mt-2 block w-full rounded-xl border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="inline-flex items-center gap-3 text-sm font-medium text-slate-700">
          <input
            type="checkbox"
            checked={draft.needsReview}
            onChange={(event) =>
              setDraft((current) => ({ ...current, needsReview: event.target.checked }))
            }
          />
          Keep this item flagged for review
        </label>
        <div>
          <button
            type="submit"
            className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-fuchsia-700 disabled:opacity-60"
          >
            {isBusy ? 'Saving…' : 'Save review changes'}
          </button>
        </div>
      </fieldset>
      {gradingResult?.ai_feedback ? (
        <details className="mt-4 text-sm text-slate-600">
          <summary className="cursor-pointer font-medium">
            AI overall feedback and reasoning
          </summary>
          <p className="mt-2 whitespace-pre-wrap">{gradingResult.ai_feedback}</p>
          <p className="mt-2 whitespace-pre-wrap">{gradingResult.reasoning_summary}</p>
        </details>
      ) : null}
      {error ? (
        <p role="alert" className="mt-3 text-sm text-rose-700">
          {error}
        </p>
      ) : null}
    </form>
  )
}

export function SubmissionReviewPage() {
  const { assignmentId, submissionId } = useParams()
  const queryClient = useQueryClient()
  const drafts = useDraftSaves()
  const jobs = useAIJobs()
  const job = jobs.latestForSubmission(Number(submissionId))
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)

  const assignmentQuery = useQuery({
    queryKey: ['assignments', assignmentId],
    queryFn: () => getAssignment(assignmentId!),
    enabled: Boolean(assignmentId),
  })

  const gradingQuery = useQuery({
    queryKey: ['submissions', submissionId, 'grading'],
    queryFn: () => getSubmissionGrading(Number(submissionId)),
    enabled: Boolean(submissionId),
    retry: (failures, error) =>
      !(error instanceof ApiError && error.status === 200) && failures < 2,
  })

  const refreshReviewData = async () => {
    await queryClient.invalidateQueries({ queryKey: ['submissions', submissionId, 'grading'] })
    await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'submissions'] })
    await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
    await queryClient.invalidateQueries({ queryKey: ['assignments'] })
  }

  const updateMutation = useMutation({
    mutationFn: (payload: ReviewPayload) => saveQuestionReview(Number(submissionId), payload),
    onSuccess: async () => {
      setErrorMessage(null)
      setStatusMessage('Review changes saved.')
      await refreshReviewData()
    },
    onError: (error) => {
      setStatusMessage(null)
      setErrorMessage(getApiErrorMessage(error))
    },
  })

  const finalizeMutation = useMutation({
    mutationFn: async () => {
      await drafts.saveAll({ dirtyOnly: true })
      return finalizeSubmission(Number(submissionId))
    },
    onSuccess: async () => {
      setErrorMessage(null)
      setStatusMessage('Submission finalized.')
      await refreshReviewData()
    },
    onError: (error) => {
      setStatusMessage(null)
      setErrorMessage(getApiErrorMessage(error))
    },
  })

  const [draftTotals, setDraftTotals] = useState<Record<number, number | null>>({})
  const onTotal = useCallback(
    (id: number, total: number | null) =>
      setDraftTotals((current) => (current[id] === total ? current : { ...current, [id]: total })),
    [],
  )
  const grading = gradingQuery.data
  const answerPartsByQuestionId = useMemo(() => {
    return new Map(
      (grading?.answer_parts ?? []).map((answerPart) => [answerPart.question_part_id, answerPart]),
    )
  }, [grading?.answer_parts])

  if (assignmentQuery.isPending || gradingQuery.isPending) {
    return <div className="text-sm text-slate-600">Loading submission review...</div>
  }

  if (assignmentQuery.isError || gradingQuery.isError) {
    return (
      <div className="space-y-5">
        <h1 className="section-title">Could not load submission review</h1>
        <QueryError
          error={assignmentQuery.error || gradingQuery.error}
          onRetry={() => {
            void assignmentQuery.refetch()
            void gradingQuery.refetch()
          }}
        />
        <WorkflowBack to={`/assignments/${assignmentId}/submissions`}>
          Back to submissions
        </WorkflowBack>
      </div>
    )
  }

  const assignment = assignmentQuery.data
  const submission = grading?.submission

  if (!assignment || !submission) {
    return <div className="text-sm text-rose-700">Submission not found.</div>
  }

  return (
    <div className="space-y-8">
      <AIJobNotice job={job} />
      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[2rem] border border-slate-200 p-6">
          <p className="text-sm font-semibold tracking-[0.18em] text-slate-400 uppercase">
            Student review
          </p>
          <h1 className="mt-3 section-title">{submission.student_name}</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Review AI grades or enter marks manually. Edit scores and feedback for each rubric
            criterion, save your changes, and finalize when the result is ready to export.
          </p>

          <div className="mt-5 flex flex-wrap gap-3 text-xs font-semibold">
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
              {assignment.title}
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
              Status: {formatStatus(submission.grading_status)}
            </span>
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">
              Saved total {submission.total_score ?? 'Incomplete'}
            </span>
          </div>
        </div>

        <div className="rounded-[2rem] bg-slate-950 px-6 py-7 text-white">
          <p className="text-sm font-semibold tracking-[0.18em] text-fuchsia-200/65 uppercase">
            Finalize
          </p>
          <h2 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold">
            Mark this review complete
          </h2>
          <p className="mt-4 text-sm leading-6 text-fuchsia-100/72">
            Save and finalize saves your edits, checks that every question is scored, and marks this
            submission complete. Clear all review flags first. Editing a finalized review reopens
            it.
          </p>
          <button
            type="button"
            disabled={
              finalizeMutation.isPending ||
              updateMutation.isPending ||
              drafts.isSaving ||
              !grading.questions.length ||
              submission.grading_status === 'grading' ||
              Boolean(jobs.forSubmission(submission.id)) ||
              (submission.grading_status === 'finalized' && !drafts.hasChanges)
            }
            onClick={() => finalizeMutation.mutate()}
            className="mt-6 inline-flex rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-fuchsia-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submission.grading_status === 'finalized' && !drafts.hasChanges
              ? 'Finalized'
              : finalizeMutation.isPending
                ? 'Finalizing...'
                : 'Save and finalize'}
          </button>
        </div>
      </section>

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

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap justify-between gap-3 text-sm">
          <p>
            <strong>Student number:</strong> {submission.student_identifier || 'Not provided'}
          </p>
          <p aria-live="polite">
            <strong>Draft assignment total:</strong>{' '}
            {(
              Object.values(draftTotals).reduce<number>((sum, total) => sum + (total ?? 0), 0) / 100
            ).toFixed(2)}{' '}
            /{' '}
            {grading.questions.reduce((sum, question) => sum + Number(question.max_marks ?? 0), 0)}
            {grading.questions.some((question) => draftTotals[question.question_part_id] == null)
              ? ' · incomplete'
              : ''}
          </p>
        </div>
        <details className="mt-4" open={!grading.answer_parts.length}>
          <summary className="cursor-pointer text-sm font-semibold text-slate-700">
            Full student submission
          </summary>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-600">
            {submission.raw_response_text || 'No response text was extracted.'}
          </p>
          {submission.response_file_url ? (
            <a
              href={submission.response_file_url}
              className="mt-3 inline-block text-sm text-fuchsia-700 underline"
            >
              {submission.response_filename || 'Download original submission'}
            </a>
          ) : null}
        </details>
        {submission.ingestion_notes ? (
          <p className="mt-3 text-sm text-amber-800">{submission.ingestion_notes}</p>
        ) : null}
        {submission.last_error ? (
          <p role="alert" className="mt-3 text-sm text-rose-700">
            {submission.last_error}
          </p>
        ) : null}
      </section>
      <section className="space-y-4">
        {grading.questions.map((question) => (
          <ReviewEditor
            key={question.question_part_id}
            question={question}
            referenceAnswer={
              grading.reference_answers.find(
                (answer) => answer.question_part_id === question.question_part_id,
              )?.answer_text ?? ''
            }
            gradingResult={grading.grading_results.find(
              (result) => result.question_part_id === question.question_part_id,
            )}
            isBusy={
              drafts.isSaving ||
              updateMutation.isPending ||
              finalizeMutation.isPending ||
              submission.grading_status === 'grading'
            }
            answerPart={answerPartsByQuestionId.get(question.question_part_id)}
            onSave={(payload) => updateMutation.mutateAsync(payload)}
            onTotal={onTotal}
          />
        ))}
        {!grading.questions.length ? (
          <p className="rounded-2xl bg-slate-50 p-6 text-sm text-slate-600">
            Add scored questions and their rubric to start reviewing this submission.
          </p>
        ) : null}
      </section>

      <div className="flex flex-wrap gap-3">
        <WorkflowBack to={`/assignments/${assignment.id}/review`}>
          Back to review queue
        </WorkflowBack>
        <WorkflowBack to={`/assignments/${assignment.id}/submissions`}>
          Back to submissions
        </WorkflowBack>
      </div>
    </div>
  )
}
