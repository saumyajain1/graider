import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getAssignment } from '../api/assignments'
import { getApiErrorMessage } from '../api/errors'
import {
  createRubricCriterion,
  deleteRubricCriterion,
  generateRubric,
  listRubric,
  listReferenceAnswers,
  updateRubricCriterion,
  type RubricCriterion,
  type RubricQuestion,
} from '../api/grading'
import { AIButton } from '../components/AIButton'
import { QueryError } from '../components/QueryError'
import { WorkflowBack, WorkflowContinue } from '../components/WorkflowNavigation'
import { WorkflowDraftProvider, useDraft, useDraftSaves } from '../hooks/useDraftSaves'
import { requireMarks, marksInCents } from '../lib/marks'

function RubricCriterionEditor({
  criterion,
  onSave,
  onDelete,
}: {
  criterion: RubricCriterion
  onSave: (payload: { title: string; description: string; max_points: string }) => Promise<unknown>
  onDelete: () => void
}) {
  const [title, setTitle] = useState(criterion.title)
  const [description, setDescription] = useState(criterion.description)
  const [maxPoints, setMaxPoints] = useState(criterion.max_points)

  useEffect(() => {
    setTitle(criterion.title)
    setDescription(criterion.description)
    setMaxPoints(criterion.max_points)
  }, [criterion.title, criterion.description, criterion.max_points])

  const payload = { title, description, max_points: maxPoints }
  useDraft(`criterion-${criterion.id}`, {
    dirty:
      title !== criterion.title ||
      description !== criterion.description ||
      maxPoints !== criterion.max_points,
    validate: () => {
      if (!title.trim() || !description.trim())
        throw new Error('Each rubric criterion needs a title and a description.')
      requireMarks(maxPoints, title || 'Criterion')
    },
    save: () => onSave(payload),
  })

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="grid gap-3 md:grid-cols-[0.25fr_1fr_0.18fr]">
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          className="rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
          aria-label="Criterion title"
          placeholder="Criterion"
        />
        <input
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
          aria-label="Criterion description"
          placeholder="What earns these points?"
        />
        <input
          type="number"
          min="0.01"
          max="9999.99"
          step="0.01"
          value={maxPoints}
          onChange={(event) => setMaxPoints(event.target.value)}
          className="rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
          aria-label="Maximum points"
          placeholder="Pts"
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => {
            void onSave(payload).catch(() => {})
          }}
          className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-fuchsia-700"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => onDelete()}
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
  isBusy,
  onGenerate,
  isGenerating,
  onCreate,
  onUpdate,
  onDelete,
}: {
  group: RubricQuestion
  isGenerating: boolean
  isBusy: boolean
  onGenerate: () => void
  onCreate: (payload: { title: string; description: string; max_points: string }) => Promise<void>
  onUpdate: (
    criterionId: number,
    payload: { title: string; description: string; max_points: string },
  ) => Promise<unknown>
  onDelete: (criterionId: number) => void
}) {
  const [newCriterion, setNewCriterion] = useState({
    title: '',
    description: '',
    max_points: '',
  })

  const newDirty = Object.values(newCriterion).some((value) => value.trim())
  const create = async () => {
    await onCreate(newCriterion)
    setNewCriterion({ title: '', description: '', max_points: '' })
  }
  useDraft(`new-criterion-${group.question_part_id}`, {
    dirty: newDirty,
    validate: () => {
      if (!newDirty) return
      if (!newCriterion.title.trim() || !newCriterion.description.trim())
        throw new Error(`${group.display_label}: finish the new criterion or clear its draft.`)
      requireMarks(newCriterion.max_points, `${group.display_label} criterion`)
    },
    save: create,
  })

  return (
    <fieldset
      disabled={isBusy}
      className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm"
    >
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
            {group.max_marks ? `${group.max_marks} marks` : 'Marks not set'} · Allocated:{' '}
            {group.criteria.reduce(
              (sum, criterion) => sum + (marksInCents(criterion.max_points) ?? 0),
              0,
            ) / 100}
          </span>
          <AIButton busy={isGenerating} onClick={() => onGenerate()}>
            {isGenerating ? 'Generating…' : 'Generate with AI'}
          </AIButton>
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
            aria-label="Criterion title"
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
            aria-label="Criterion description"
            placeholder="What should be graded?"
          />
          <input
            type="number"
            min="0.01"
            max="9999.99"
            step="0.01"
            value={newCriterion.max_points}
            onChange={(event) =>
              setNewCriterion((current) => ({
                ...current,
                max_points: event.target.value,
              }))
            }
            className="rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-fuchsia-500"
            aria-label="Maximum points"
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
              try {
                await onCreate(newCriterion)
                setNewCriterion({ title: '', description: '', max_points: '' })
              } catch {
                // The parent mutation displays the error; retain the entered criterion.
              }
            }}
            className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-fuchsia-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Add
          </button>
        </div>
      </div>
    </fieldset>
  )
}

export function AssignmentRubricPage() {
  const { assignmentId } = useParams()
  const queryClient = useQueryClient()
  const drafts = useDraftSaves()
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

  if (assignmentQuery.isError || rubricQuery.isError) {
    return (
      <QueryError
        error={assignmentQuery.error || rubricQuery.error}
        onRetry={() => {
          void assignmentQuery.refetch()
          void rubricQuery.refetch()
        }}
      />
    )
  }

  const assignment = assignmentQuery.data
  const rubricGroups = rubricQuery.data ?? []

  if (!assignment) {
    return <div className="text-sm text-rose-700">Assignment not found.</div>
  }

  return (
    <WorkflowDraftProvider value={drafts}>
      <div className="space-y-8">
        <section className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
          <div className="rounded-[2rem] border border-slate-200 p-6">
            <p className="text-sm font-semibold tracking-[0.18em] text-slate-400 uppercase">
              Rubric builder
            </p>
            <h1 className="mt-3 section-title">{assignment.title}</h1>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Generate rubric criteria from each question and its reference answer, or add the
              criteria manually. These point allocations guide grading.
            </p>
          </div>

          <div className="rounded-[2rem] bg-slate-950 px-6 py-7 text-white">
            <p className="text-sm font-semibold tracking-[0.18em] text-fuchsia-200/65 uppercase">
              Workflow step
            </p>
            <h2 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold">
              Set clear grading criteria.
            </h2>
            <p className="mt-4 text-sm leading-6 text-fuchsia-100/72">
              AI generation depends on reference answers. If an answer is missing or generation
              fails, you can still add criteria manually.
            </p>
            <AIButton
              busy={generateMutation.isPending && generateMutation.variables === undefined}
              disabled={
                drafts.isSaving ||
                generateMutation.isPending ||
                createMutation.isPending ||
                updateMutation.isPending ||
                deleteMutation.isPending
              }
              onClick={() => generateMutation.mutate(undefined)}
              className="mt-6"
            >
              {generateMutation.isPending && generateMutation.variables === undefined
                ? 'Generating...'
                : 'Generate all rubric criteria'}
            </AIButton>
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

        {rubricGroups.length > 0 ? (
          <section className="space-y-4">
            {rubricGroups.map((group) => (
              <RubricQuestionSection
                key={group.question_part_id}
                group={group}
                isGenerating={
                  generateMutation.isPending &&
                  generateMutation.variables === group.question_part_id
                }
                isBusy={
                  drafts.isSaving ||
                  generateMutation.isPending ||
                  createMutation.isPending ||
                  updateMutation.isPending ||
                  deleteMutation.isPending
                }
                onGenerate={() => {
                  generateMutation.mutate(group.question_part_id)
                }}
                onCreate={async (payload) => {
                  await createMutation.mutateAsync({
                    question_part_id: group.question_part_id,
                    ...payload,
                  })
                }}
                onUpdate={(criterionId, payload) => {
                  return updateMutation.mutateAsync({ criterionId, payload })
                }}
                onDelete={(criterionId) => {
                  deleteMutation.mutate(criterionId)
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
          <WorkflowBack to={`/assignments/${assignment.id}/reference-answers`}>
            Back to reference answers
          </WorkflowBack>
          <WorkflowContinue
            to={`/assignments/${assignment.id}/submissions`}
            disabled={
              drafts.isSaving ||
              generateMutation.isPending ||
              createMutation.isPending ||
              updateMutation.isPending ||
              deleteMutation.isPending
            }
            validate={async () => {
              const answers = await listReferenceAnswers(assignmentId!)
              const missing = answers.filter((answer) => !answer.answer_text.trim())
              if (missing.length)
                throw new Error(
                  `Add reference answers for ${missing.map((answer) => answer.display_label).join(', ')} before continuing.`,
                )
              const groups = await listRubric(assignmentId!)
              if (!groups.length) throw new Error('Add scored questions before continuing.')
              for (const group of groups) {
                requireMarks(group.max_marks, group.display_label)
                const allocated = group.criteria.reduce(
                  (sum, criterion) => sum + (marksInCents(criterion.max_points) ?? 0),
                  0,
                )
                if (
                  !group.criteria.length ||
                  group.criteria.some((criterion) => marksInCents(criterion.max_points) === null) ||
                  allocated !== marksInCents(group.max_marks)
                )
                  throw new Error(
                    `${group.display_label}: rubric points must total ${group.max_marks} marks. Currently allocated: ${allocated / 100}.`,
                  )
              }
            }}
          >
            submissions
          </WorkflowContinue>
        </div>
      </div>
    </WorkflowDraftProvider>
  )
}
