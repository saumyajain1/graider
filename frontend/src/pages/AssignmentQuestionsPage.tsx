import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  createQuestion,
  deleteQuestion,
  generateQuestions,
  getAssignment,
  listQuestions,
  reorderQuestions,
  updateQuestion,
  type QuestionPart,
} from '../api/assignments'
import { getApiErrorMessage } from '../api/errors'

type QuestionEditorPayload = {
  source_label?: string
  parent_key?: string
  text: string
  max_marks: string | null
  part_type: 'context' | 'question'
}

function QuestionEditor({
  question,
  isFirst,
  isLast,
  onMove,
  onDelete,
  onSave,
}: {
  question: QuestionPart
  isFirst: boolean
  isLast: boolean
  onMove: (direction: 'up' | 'down') => Promise<void>
  onDelete: () => Promise<void>
  onSave: (payload: QuestionEditorPayload) => Promise<void>
}) {
  const [sourceLabel, setSourceLabel] = useState(question.source_label ?? '')
  const [parentKey, setParentKey] = useState(question.parent_key ?? '')
  const [text, setText] = useState(question.text)
  const [maxMarks, setMaxMarks] = useState(question.max_marks ?? '')
  const [partType, setPartType] = useState<'context' | 'question'>(question.part_type)

  useEffect(() => {
    setSourceLabel(question.source_label ?? '')
    setParentKey(question.parent_key ?? '')
    setText(question.text)
    setMaxMarks(question.max_marks ?? '')
    setPartType(question.part_type)
  }, [question])

  return (
    <article className="rounded-[1.75rem] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-[0.18em] text-slate-400 uppercase">
            {question.display_label}
          </p>
          <h3 className="mt-2 font-['Space_Grotesk'] text-xl font-bold text-slate-950">
            Question part
          </h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={isFirst}
            onClick={() => void onMove('up')}
            className="rounded-full border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Move up
          </button>
          <button
            type="button"
            disabled={isLast}
            onClick={() => void onMove('down')}
            className="rounded-full border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Move down
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-slate-700">Source label</span>
          <input
            value={sourceLabel}
            onChange={(event) => setSourceLabel(event.target.value)}
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
            placeholder="1.1"
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-slate-700">Shared group</span>
          <input
            value={parentKey}
            onChange={(event) => setParentKey(event.target.value)}
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
            placeholder="1"
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-slate-700">Part type</span>
          <select
            value={partType}
            onChange={(event) => setPartType(event.target.value as 'context' | 'question')}
            className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
          >
            <option value="question">Question</option>
            <option value="context">Context</option>
          </select>
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-slate-700">Max marks</span>
          <input
            value={maxMarks}
            onChange={(event) => setMaxMarks(event.target.value)}
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
            placeholder="Optional"
          />
        </label>
      </div>

      <label className="mt-4 block">
        <span className="mb-2 block text-sm font-medium text-slate-700">Text</span>
        <textarea
          rows={6}
          value={text}
          onChange={(event) => setText(event.target.value)}
          className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
        />
      </label>

      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() =>
            void onSave({
              source_label: sourceLabel.trim() || undefined,
              parent_key: parentKey.trim() || undefined,
              text,
              max_marks: maxMarks.trim() ? maxMarks : null,
              part_type: partType,
            })
          }
          className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-fuchsia-700"
        >
          Save changes
        </button>
        <button
          type="button"
          onClick={() => void onDelete()}
          className="rounded-full border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-700 transition hover:bg-rose-50"
        >
          Delete
        </button>
      </div>
    </article>
  )
}

export function AssignmentQuestionsPage() {
  const { assignmentId } = useParams()
  const queryClient = useQueryClient()
  const [newQuestion, setNewQuestion] = useState({
    source_label: '',
    parent_key: '',
    text: '',
    max_marks: '',
    part_type: 'question' as 'context' | 'question',
  })

  const assignmentQuery = useQuery({
    queryKey: ['assignments', assignmentId],
    queryFn: () => getAssignment(assignmentId!),
    enabled: Boolean(assignmentId),
  })

  const questionsQuery = useQuery({
    queryKey: ['assignments', assignmentId, 'questions'],
    queryFn: () => listQuestions(assignmentId!),
    enabled: Boolean(assignmentId),
  })

  const createMutation = useMutation({
    mutationFn: (payload: QuestionEditorPayload) => createQuestion(assignmentId!, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'questions'] })
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
      setNewQuestion({
        source_label: '',
        parent_key: '',
        text: '',
        max_marks: '',
        part_type: 'question',
      })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({
      questionId,
      payload,
    }: {
      questionId: number
      payload: QuestionEditorPayload
    }) =>
      updateQuestion(questionId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'questions'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (questionId: number) => deleteQuestion(questionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'questions'] })
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
  })

  const reorderMutation = useMutation({
    mutationFn: (questionIds: number[]) => reorderQuestions(assignmentId!, questionIds),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'questions'] })
    },
  })

  const generateMutation = useMutation({
    mutationFn: () => generateQuestions(assignmentId!, true),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'questions'] })
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
  })

  if (assignmentQuery.isPending || questionsQuery.isPending) {
    return <div className="text-sm text-slate-600">Loading questions...</div>
  }

  const assignment = assignmentQuery.data
  const questions = questionsQuery.data ?? []

  if (!assignment) {
    return <div className="text-sm text-rose-700">Assignment not found.</div>
  }

  return (
    <div className="space-y-8">
      <section className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <div className="rounded-[2rem] border border-slate-200 p-6">
          <p className="text-sm font-semibold tracking-[0.18em] text-slate-400 uppercase">
            Manual question builder
          </p>
          <h1 className="mt-3 section-title">{assignment.title}</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Create the question structure explicitly now. In the next phase, AI will be
            able to generate question parts automatically, but manual editing remains the
            source of truth.
          </p>
          <div className="mt-5 flex flex-wrap gap-3 text-xs font-semibold text-slate-500">
            <span className="rounded-full bg-slate-100 px-3 py-1">
              {questions.length} parts
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1">
              Status: {assignment.status.replace('_', ' ')}
            </span>
          </div>
        </div>

        <div className="rounded-[2rem] bg-slate-950 px-6 py-7 text-white">
          <p className="text-sm font-semibold tracking-[0.18em] text-fuchsia-200/65 uppercase">
            AI generation
          </p>
          <h2 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold">
            Questions become the backbone for answers and rubric generation.
          </h2>
          <p className="mt-4 text-sm leading-6 text-fuchsia-100/72">
            Keep the hierarchy, context blocks, and marks clean. These records directly
            drive the reference answers, rubric, mapping, and review screens.
          </p>
          <Link
            to={`/assignments/${assignment.id}/overview`}
            className="mt-6 inline-flex rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-fuchsia-100"
          >
            Back to overview
          </Link>
          <button
            type="button"
            onClick={() => void generateMutation.mutateAsync()}
            className="mt-3 inline-flex rounded-full border border-white/20 px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/10"
          >
            {generateMutation.isPending
              ? 'Overwriting...'
              : 'Overwrite questions from current assignment text'}
          </button>
        </div>
      </section>

      {generateMutation.isError ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {getApiErrorMessage(generateMutation.error)}
        </div>
      ) : null}

      <section className="rounded-[2rem] border border-slate-200 p-6">
        <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
          Add question part
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          You can add parts manually or use AI generation above. Context rows can carry
          shared setup for a top-level question like 1, while source labels preserve the
          original numbering like 1.1 and 1.2.
        </p>
        <div className="mt-5 grid gap-4 lg:grid-cols-[0.18fr_0.18fr_0.18fr_0.16fr_1fr_auto]">
          <input
            value={newQuestion.source_label}
            onChange={(event) =>
              setNewQuestion((current) => ({
                ...current,
                source_label: event.target.value,
              }))
            }
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
            placeholder="1.1"
          />
          <input
            value={newQuestion.parent_key}
            onChange={(event) =>
              setNewQuestion((current) => ({
                ...current,
                parent_key: event.target.value,
              }))
            }
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
            placeholder="1"
          />
          <select
            value={newQuestion.part_type}
            onChange={(event) =>
              setNewQuestion((current) => ({
                ...current,
                part_type: event.target.value as 'context' | 'question',
              }))
            }
            className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
          >
            <option value="question">Question</option>
            <option value="context">Context</option>
          </select>
          <input
            value={newQuestion.max_marks}
            onChange={(event) =>
              setNewQuestion((current) => ({ ...current, max_marks: event.target.value }))
            }
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
            placeholder="Marks"
          />
          <input
            value={newQuestion.text}
            onChange={(event) =>
              setNewQuestion((current) => ({ ...current, text: event.target.value }))
            }
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
            placeholder="Write the question text or context block..."
          />
          <button
            type="button"
            onClick={() =>
              void createMutation.mutateAsync({
                source_label: newQuestion.source_label.trim() || undefined,
                parent_key: newQuestion.parent_key.trim() || undefined,
                text: newQuestion.text,
                max_marks: newQuestion.max_marks.trim() ? newQuestion.max_marks : null,
                part_type: newQuestion.part_type,
              })
            }
            disabled={!newQuestion.text.trim() || createMutation.isPending}
            className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-fuchsia-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Add part
          </button>
        </div>
      </section>

      {questions.length > 0 ? (
        <section className="space-y-4">
          {questions.map((question, index) => (
            <QuestionEditor
              key={question.id}
              question={question}
              isFirst={index === 0}
              isLast={index === questions.length - 1}
              onMove={async (direction) => {
                const reordered = [...questions]
                const targetIndex = direction === 'up' ? index - 1 : index + 1
                ;[reordered[index], reordered[targetIndex]] = [
                  reordered[targetIndex],
                  reordered[index],
                ]
                await reorderMutation.mutateAsync(reordered.map((item) => item.id))
              }}
              onDelete={async () => {
                await deleteMutation.mutateAsync(question.id)
              }}
              onSave={async (payload) => {
                await updateMutation.mutateAsync({ questionId: question.id, payload })
              }}
            />
          ))}
        </section>
      ) : (
        <section className="rounded-[2rem] border border-dashed border-slate-300 bg-slate-50 p-8">
          <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            No question parts yet
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
            Start by adding one part for each question or context block in the
            assignment. You can reorder them anytime.
          </p>
        </section>
      )}

      <div className="flex flex-wrap gap-3">
        <Link
          to={`/assignments/${assignment.id}/overview`}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
        >
          Back to overview
        </Link>
        <Link
          to={`/assignments/${assignment.id}/reference-answers`}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
        >
          Continue to reference answers
        </Link>
      </div>
    </div>
  )
}
