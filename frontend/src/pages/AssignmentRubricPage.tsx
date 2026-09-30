import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getAssignment } from '../api/assignments'
import {
  createRubricCriterion,
  deleteRubricCriterion,
  generateRubric,
  listRubric,
  updateRubricCriterion,
  type RubricCriterion,
  type RubricQuestion,
} from '../api/grading'
import { getApiErrorMessage } from '../api/errors'

function RubricCriterionEditor({
  criterion,
  onSave,
  onDelete,
}: {
  criterion: RubricCriterion
  onSave: (payload: { title: string; description: string; max_points: string }) => Promise<void>
  onDelete: () => Promise<void>
}) {
  const [title, setTitle] = useState(criterion.title)
  const [description, setDescription] = useState(criterion.description)
  const [maxPoints, setMaxPoints] = useState(criterion.max_points)

  useEffect(() => {
    setTitle(criterion.title)
    setDescription(criterion.description)
    setMaxPoints(criterion.max_points)
  }, [criterion])

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="grid gap-3 md:grid-cols-[0.25fr_1fr_0.18fr]">
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          className="rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
          placeholder="Criterion"
        />
        <input
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
          placeholder="What earns these points?"
        />
        <input
          value={maxPoints}
          onChange={(event) => setMaxPoints(event.target.value)}
          className="rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
          placeholder="Pts"
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => void onSave({ title, description, max_points: maxPoints })}
          className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-fuchsia-700"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => void onDelete()}
          className="rounded-full border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-700 transition hover:bg-rose-50"
        >
          Delete
        </button>
      </div>
    </div>
  )
}

function RubricQuestionSection({
  group,
  onGenerate,
  onCreate,
  onUpdate,
  onDelete,
}: {
  group: RubricQuestion
  onGenerate: () => Promise<void>
  onCreate: (payload: { title: string; description: string; max_points: string }) => Promise<void>
  onUpdate: (
    criterionId: number,
    payload: { title: string; description: string; max_points: string },
  ) => Promise<void>
  onDelete: (criterionId: number) => Promise<void>
}) {
  const [newCriterion, setNewCriterion] = useState({
    title: '',
    description: '',
    max_points: '',
  })

  return (
    <article className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold tracking-[0.18em] text-slate-400 uppercase">
            {group.display_label}
          </p>
          <h2 className="mt-2 font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            {group.question_text}
          </h2>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-semibold">
          <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
            {group.max_marks ? `${group.max_marks} marks` : 'Marks not set'}
          </span>
          <button
            type="button"
            onClick={() => void onGenerate()}
            className="rounded-full border border-slate-300 px-3 py-1 text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
          >
            Generate with AI
          </button>
        </div>
      </div>

      <div className="mt-5 space-y-3">
        {group.criteria.length > 0 ? (
          group.criteria.map((criterion) => (
            <RubricCriterionEditor
              key={criterion.id}
              criterion={criterion}
              onSave={(payload) => onUpdate(criterion.id, payload)}
              onDelete={() => onDelete(criterion.id)}
            />
          ))
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-5 text-sm text-slate-600">
            No rubric criteria yet. Add them manually or generate them with AI.
          </div>
        )}
      </div>

      <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <p className="text-sm font-semibold text-slate-700">Add criterion manually</p>
        <div className="mt-3 grid gap-3 md:grid-cols-[0.25fr_1fr_0.18fr_auto]">
          <input
            value={newCriterion.title}
            onChange={(event) =>
              setNewCriterion((current) => ({ ...current, title: event.target.value }))
            }
            className="rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
            placeholder="Criterion"
          />
          <input
            value={newCriterion.description}
            onChange={(event) =>
              setNewCriterion((current) => ({
                ...current,
                description: event.target.value,
              }))
            }
            className="rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
            placeholder="What should be graded?"
          />
          <input
            value={newCriterion.max_points}
            onChange={(event) =>
              setNewCriterion((current) => ({
                ...current,
                max_points: event.target.value,
              }))
            }
            className="rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
            placeholder="Pts"
          />
          <button
            type="button"
            disabled={
              !newCriterion.title.trim() ||
              !newCriterion.description.trim() ||
              !newCriterion.max_points.trim()
            }
            onClick={async () => {
              await onCreate(newCriterion)
              setNewCriterion({ title: '', description: '', max_points: '' })
            }}
            className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-fuchsia-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Add
          </button>
        </div>
      </div>
    </article>
  )
}

export function AssignmentRubricPage() {
  const { assignmentId } = useParams()
  const queryClient = useQueryClient()
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const assignmentQuery = useQuery({
    queryKey: ['assignments', assignmentId],
    queryFn: () => getAssignment(assignmentId!),
    enabled: Boolean(assignmentId),
  })

  const rubricQuery = useQuery({
    queryKey: ['assignments', assignmentId, 'rubric'],
    queryFn: () => listRubric(assignmentId!),
    enabled: Boolean(assignmentId),
  })

  const createMutation = useMutation({
    mutationFn: (payload: {
      question_part_id: number
      title: string
      description: string
      max_points: string
    }) => createRubricCriterion(assignmentId!, payload),
    onSuccess: async () => {
      setErrorMessage(null)
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'rubric'] })
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
    onError: (error) => setErrorMessage(getApiErrorMessage(error)),
  })

  const updateMutation = useMutation({
    mutationFn: ({
      criterionId,
      payload,
    }: {
      criterionId: number
      payload: { title: string; description: string; max_points: string }
    }) => updateRubricCriterion(criterionId, payload),
    onSuccess: async () => {
      setErrorMessage(null)
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'rubric'] })
    },
    onError: (error) => setErrorMessage(getApiErrorMessage(error)),
  })

  const deleteMutation = useMutation({
    mutationFn: (criterionId: number) => deleteRubricCriterion(criterionId),
    onSuccess: async () => {
      setErrorMessage(null)
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'rubric'] })
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
    onError: (error) => setErrorMessage(getApiErrorMessage(error)),
  })

  const generateMutation = useMutation({
    mutationFn: (questionPartId?: number) =>
      generateRubric(
        assignmentId!,
        questionPartId ? { question_part_id: questionPartId } : undefined,
      ),
    onSuccess: async () => {
      setErrorMessage(null)
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'rubric'] })
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
    onError: (error) => setErrorMessage(getApiErrorMessage(error)),
  })

  if (assignmentQuery.isPending || rubricQuery.isPending) {
    return <div className="text-sm text-slate-600">Loading rubric...</div>
  }

  const assignment = assignmentQuery.data
  const rubricGroups = rubricQuery.data ?? []

  if (!assignment) {
    return <div className="text-sm text-rose-700">Assignment not found.</div>
  }

  return (
    <div className="space-y-8">
      <section className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <div className="rounded-[2rem] border border-slate-200 p-6">
          <p className="text-sm font-semibold tracking-[0.18em] text-slate-400 uppercase">
            Rubric builder
          </p>
          <h1 className="mt-3 section-title">{assignment.title}</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Generate rubric criteria from each question and its reference answer, or add the
            criteria manually. These point allocations will later drive grading.
          </p>
        </div>

        <div className="rounded-[2rem] bg-slate-950 px-6 py-7 text-white">
          <p className="text-sm font-semibold tracking-[0.18em] text-fuchsia-200/65 uppercase">
            Workflow step
          </p>
          <h2 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold">
            Rubrics are generated per question part and stay fully editable.
          </h2>
          <p className="mt-4 text-sm leading-6 text-fuchsia-100/72">
            AI generation depends on reference answers. If the key is missing or generation fails,
            you can still add criteria manually.
          </p>
          <button
            type="button"
            onClick={() => void generateMutation.mutateAsync(undefined)}
            className="mt-6 inline-flex rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-fuchsia-100"
          >
            {generateMutation.isPending ? 'Generating...' : 'Generate all rubric criteria'}
          </button>
        </div>
      </section>

      {errorMessage ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {errorMessage}
        </div>
      ) : null}

      {rubricGroups.length > 0 ? (
        <section className="space-y-4">
          {rubricGroups.map((group) => (
            <RubricQuestionSection
              key={group.question_part_id}
              group={group}
              onGenerate={async () => {
                await generateMutation.mutateAsync(group.question_part_id)
              }}
              onCreate={async (payload) => {
                await createMutation.mutateAsync({
                  question_part_id: group.question_part_id,
                  ...payload,
                })
              }}
              onUpdate={async (criterionId, payload) => {
                await updateMutation.mutateAsync({ criterionId, payload })
              }}
              onDelete={async (criterionId) => {
                await deleteMutation.mutateAsync(criterionId)
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
            Add or generate question parts before building the rubric.
          </p>
        </section>
      )}

      <div className="flex flex-wrap gap-3">
        <Link
          to={`/assignments/${assignment.id}/reference-answers`}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
        >
          Back to reference answers
        </Link>
      </div>
    </div>
  )
}
