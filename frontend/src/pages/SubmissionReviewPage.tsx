import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { QueryError } from '../components/QueryError'
import { formatStatus } from '../lib/format'

import { getAssignment } from '../api/assignments'
import { getApiErrorMessage } from '../api/errors'
import {
  finalizeSubmission,
  getSubmissionGrading,
  updateGradingResult,
  type GradingResult,
  type SubmissionAnswerPart,
} from '../api/grading'

function ReviewEditor({
  answerPart,
  gradingResult,
  isBusy,
  onSave,
}: {
  answerPart?: SubmissionAnswerPart
  gradingResult: GradingResult
  isBusy: boolean
  onSave: (payload: {
    final_score: string | null
    final_feedback: string
    needs_review: boolean
  }) => void
}) {
  const [finalScore, setFinalScore] = useState(gradingResult.final_score ?? '')
  const [finalFeedback, setFinalFeedback] = useState(
    gradingResult.final_feedback || gradingResult.ai_feedback,
  )
  const [needsReview, setNeedsReview] = useState(gradingResult.needs_review)

  useEffect(() => {
    setFinalScore(gradingResult.final_score ?? '')
    setFinalFeedback(gradingResult.final_feedback || gradingResult.ai_feedback)
    setNeedsReview(gradingResult.needs_review)
  }, [gradingResult])

  return (
    <fieldset
      disabled={isBusy}
      className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold tracking-[0.18em] text-slate-400 uppercase">
            {gradingResult.display_label}
          </p>
          <h2 className="mt-2 font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            {gradingResult.question_text}
          </h2>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-semibold">
          <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
            AI score {gradingResult.ai_score ?? '0'} / {gradingResult.max_score}
          </span>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
            Confidence {gradingResult.confidence_score ?? 'n/a'}
          </span>
        </div>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-semibold text-slate-700">Extracted answer</p>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            {answerPart?.extracted_answer_text || 'No mapped answer was found for this question.'}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm font-semibold text-slate-700">AI reasoning</p>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            {gradingResult.reasoning_summary || 'No reasoning summary provided.'}
          </p>
          <p className="mt-4 text-sm font-semibold text-slate-700">AI feedback</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {gradingResult.ai_feedback || 'No AI feedback provided.'}
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-[0.25fr_1fr]">
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-slate-700">Final score</span>
          <input
            value={finalScore}
            onChange={(event) => setFinalScore(event.target.value)}
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
            placeholder={gradingResult.ai_score ?? '0'}
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-slate-700">Final feedback</span>
          <textarea
            rows={5}
            value={finalFeedback}
            onChange={(event) => setFinalFeedback(event.target.value)}
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
          />
        </label>
      </div>

      <label className="mt-4 inline-flex items-center gap-3 text-sm font-medium text-slate-700">
        <input
          type="checkbox"
          checked={needsReview}
          onChange={(event) => setNeedsReview(event.target.checked)}
          className="h-4 w-4 rounded border-slate-300 text-fuchsia-600 focus:ring-fuchsia-500"
        />
        Keep this item flagged for review
      </label>

      <div className="mt-5">
        <button
          type="button"
          onClick={() =>
            onSave({
              final_score: finalScore.trim() ? finalScore : null,
              final_feedback: finalFeedback,
              needs_review: needsReview,
            })
          }
          className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-fuchsia-700"
        >
          Save review changes
        </button>
      </div>
    </fieldset>
  )
}

export function SubmissionReviewPage() {
  const { assignmentId, submissionId } = useParams()
  const queryClient = useQueryClient()
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
  })

  const refreshReviewData = async () => {
    await queryClient.invalidateQueries({ queryKey: ['submissions', submissionId, 'grading'] })
    await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'submissions'] })
    await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
    await queryClient.invalidateQueries({ queryKey: ['assignments'] })
  }

  const updateMutation = useMutation({
    mutationFn: ({
      gradingResultId,
      payload,
    }: {
      gradingResultId: number
      payload: {
        final_score: string | null
        final_feedback: string
        needs_review: boolean
      }
    }) => updateGradingResult(gradingResultId, payload),
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
    mutationFn: () => finalizeSubmission(Number(submissionId)),
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
      <QueryError
        error={assignmentQuery.error || gradingQuery.error}
        onRetry={() => {
          void assignmentQuery.refetch()
          void gradingQuery.refetch()
        }}
      />
    )
  }

  const assignment = assignmentQuery.data
  const submission = grading?.submission

  if (!assignment || !submission) {
    return <div className="text-sm text-rose-700">Submission not found.</div>
  }

  return (
    <div className="space-y-8">
      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[2rem] border border-slate-200 p-6">
          <p className="text-sm font-semibold tracking-[0.18em] text-slate-400 uppercase">
            Student review
          </p>
          <h1 className="mt-3 section-title">{submission.student_name}</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Review the AI pass question by question, edit marks or feedback, and finalize when the
            result is ready to export.
          </p>

          <div className="mt-5 flex flex-wrap gap-3 text-xs font-semibold">
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
              {assignment.title}
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
              Status: {formatStatus(submission.grading_status)}
            </span>
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">
              Total {submission.total_score ?? 'n/a'}
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
            Finalizing saves the reviewed total and marks this submission complete. You can return
            to edit the scores and feedback later.
          </p>
          <button
            type="button"
            disabled={
              finalizeMutation.isPending ||
              updateMutation.isPending ||
              grading.grading_results.length === 0 ||
              submission.grading_status === 'finalized'
            }
            onClick={() => finalizeMutation.mutate()}
            className="mt-6 inline-flex rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-fuchsia-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submission.grading_status === 'finalized'
              ? 'Finalized'
              : finalizeMutation.isPending
                ? 'Finalizing...'
                : 'Finalize submission'}
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

      {grading.grading_results.length > 0 ? (
        <section className="space-y-4">
          {grading.grading_results.map((gradingResult) => (
            <ReviewEditor
              key={gradingResult.id}
              gradingResult={gradingResult}
              isBusy={updateMutation.isPending || finalizeMutation.isPending}
              answerPart={answerPartsByQuestionId.get(gradingResult.question_part_id)}
              onSave={(payload) => {
                updateMutation.mutate({
                  gradingResultId: gradingResult.id,
                  payload,
                })
              }}
            />
          ))}
        </section>
      ) : (
        <section className="rounded-[2rem] border border-dashed border-slate-300 bg-slate-50 p-8">
          <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            No grading results yet
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
            This submission needs to be graded from the Submissions page before there is anything to
            review here.
          </p>
        </section>
      )}

      <div className="flex flex-wrap gap-3">
        <Link
          to={`/assignments/${assignment.id}/review`}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
        >
          Back to review queue
        </Link>
        <Link
          to={`/assignments/${assignment.id}/submissions`}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
        >
          Back to submissions
        </Link>
      </div>
    </div>
  )
}
