import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getAssignment } from '../api/assignments'
import {
  createReferenceAnswer,
  generateReferenceAnswers,
  listReferenceAnswers,
  updateReferenceAnswer,
  type ReferenceAnswerItem,
} from '../api/grading'
import { getApiErrorMessage } from '../api/errors'

function ReferenceAnswerEditor({
  item,
  onGenerate,
  onSave,
}: {
  item: ReferenceAnswerItem
  onGenerate: () => Promise<void>
  onSave: (answerText: string) => Promise<void>
}) {
  const [answerText, setAnswerText] = useState(item.answer_text)

  useEffect(() => {
    setAnswerText(item.answer_text)
  }, [item])

  return (
    <article className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold tracking-[0.18em] text-slate-400 uppercase">
            {item.display_label}
          </p>
          <h2 className="mt-2 font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            {item.question_text}
          </h2>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-semibold">
          <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
            {item.max_marks ? `${item.max_marks} marks` : 'Marks not set'}
          </span>
          <span className="rounded-full bg-fuchsia-50 px-3 py-1 text-fuchsia-700">
            {item.source ? `Source: ${item.source}` : 'Manual draft'}
          </span>
        </div>
      </div>

      <textarea
        rows={8}
        value={answerText}
        onChange={(event) => setAnswerText(event.target.value)}
        className="mt-5 w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
        placeholder="Write or generate the reference answer for this question."
      />

      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => void onSave(answerText)}
          className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-fuchsia-700"
        >
          Save answer
        </button>
        <button
          type="button"
          onClick={() => void onGenerate()}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
        >
          Generate with AI
        </button>
      </div>
    </article>
  )
}

export function AssignmentReferenceAnswersPage() {
  const { assignmentId } = useParams()
  const queryClient = useQueryClient()
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const assignmentQuery = useQuery({
    queryKey: ['assignments', assignmentId],
    queryFn: () => getAssignment(assignmentId!),
    enabled: Boolean(assignmentId),
  })

  const answersQuery = useQuery({
    queryKey: ['assignments', assignmentId, 'reference-answers'],
    queryFn: () => listReferenceAnswers(assignmentId!),
    enabled: Boolean(assignmentId),
  })

  const saveMutation = useMutation({
    mutationFn: async (payload: { item: ReferenceAnswerItem; answer_text: string }) => {
      if (payload.item.id) {
        return updateReferenceAnswer(payload.item.id, {
          answer_text: payload.answer_text,
          source: 'teacher',
        })
      }

      return createReferenceAnswer(assignmentId!, {
        question_part_id: payload.item.question_part_id,
        answer_text: payload.answer_text,
      })
    },
    onSuccess: async () => {
      setErrorMessage(null)
      await queryClient.invalidateQueries({
        queryKey: ['assignments', assignmentId, 'reference-answers'],
      })
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
    onError: (error) => setErrorMessage(getApiErrorMessage(error)),
  })

  const generateMutation = useMutation({
    mutationFn: (questionPartId?: number) =>
      generateReferenceAnswers(
        assignmentId!,
        questionPartId ? { question_part_id: questionPartId } : undefined,
      ),
    onSuccess: async () => {
      setErrorMessage(null)
      await queryClient.invalidateQueries({
        queryKey: ['assignments', assignmentId, 'reference-answers'],
      })
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
    onError: (error) => setErrorMessage(getApiErrorMessage(error)),
  })

  if (assignmentQuery.isPending || answersQuery.isPending) {
    return <div className="text-sm text-slate-600">Loading reference answers...</div>
  }

  const assignment = assignmentQuery.data
  const answers = answersQuery.data ?? []

  if (!assignment) {
    return <div className="text-sm text-rose-700">Assignment not found.</div>
  }

  return (
    <div className="space-y-8">
      <section className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <div className="rounded-[2rem] border border-slate-200 p-6">
          <p className="text-sm font-semibold tracking-[0.18em] text-slate-400 uppercase">
            Reference answers
          </p>
          <h1 className="mt-3 section-title">{assignment.title}</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Generate model answers with AI or draft them manually. These answers feed the rubric
            builder and later guide grading.
          </p>
        </div>

        <div className="rounded-[2rem] bg-slate-950 px-6 py-7 text-white">
          <p className="text-sm font-semibold tracking-[0.18em] text-fuchsia-200/65 uppercase">
            Workflow step
          </p>
          <h2 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold">
            Reference answers should be clear, compact, and editable.
          </h2>
          <p className="mt-4 text-sm leading-6 text-fuchsia-100/72">
            If AI generation is unavailable, you can still write every answer manually and continue
            the workflow.
          </p>
          <button
            type="button"
            onClick={() => void generateMutation.mutateAsync(undefined)}
            className="mt-6 inline-flex rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-fuchsia-100"
          >
            {generateMutation.isPending ? 'Generating...' : 'Generate all answers'}
          </button>
        </div>
      </section>

      {errorMessage ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {errorMessage}
        </div>
      ) : null}

      {answers.length > 0 ? (
        <section className="space-y-4">
          {answers.map((item) => (
            <ReferenceAnswerEditor
              key={item.question_part_id}
              item={item}
              onGenerate={async () => {
                await generateMutation.mutateAsync(item.question_part_id)
              }}
              onSave={async (answerText) => {
                await saveMutation.mutateAsync({ item, answer_text: answerText })
              }}
            />
          ))}
        </section>
      ) : (
        <section className="rounded-[2rem] border border-dashed border-slate-300 bg-slate-50 p-8">
          <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            No question parts available
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
            Add or generate question parts before working on reference answers.
          </p>
        </section>
      )}

      <div className="flex flex-wrap gap-3">
        <Link
          to={`/assignments/${assignment.id}/questions`}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
        >
          Back to questions
        </Link>
        <Link
          to={`/assignments/${assignment.id}/rubric`}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
        >
          Continue to rubric
        </Link>
      </div>
    </div>
  )
}
