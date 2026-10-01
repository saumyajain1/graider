import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { QueryError } from '../components/QueryError'
import { formatStatus } from '../lib/format'

import {
  deleteAssignment,
  generateQuestions,
  getAssignment,
  updateAssignment,
  type AssignmentPayload,
} from '../api/assignments'
import { getApiErrorMessage } from '../api/errors'

export function AssignmentOverviewPage() {
  const { assignmentId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<AssignmentPayload>({
    title: '',
    course_name: '',
    description: '',
    raw_assignment_text: '',
    source_file: null,
  })

  const assignmentQuery = useQuery({
    queryKey: ['assignments', assignmentId],
    queryFn: () => getAssignment(assignmentId!),
    enabled: Boolean(assignmentId),
  })

  useEffect(() => {
    if (!assignmentQuery.data) {
      return
    }

    setForm({
      title: assignmentQuery.data.title,
      course_name: assignmentQuery.data.course_name,
      description: assignmentQuery.data.description,
      raw_assignment_text: assignmentQuery.data.raw_assignment_text,
      source_file: null,
    })
  }, [assignmentQuery.data])

  const updateMutation = useMutation({
    mutationFn: (payload: AssignmentPayload) => updateAssignment(assignmentId!, payload),
    onSuccess: async (assignment) => {
      queryClient.setQueryData(['assignments', assignmentId], assignment)
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
  })

  const regenerateMutation = useMutation({
    mutationFn: async (payload: AssignmentPayload) => {
      await updateAssignment(assignmentId!, payload)
      return generateQuestions(assignmentId!, true)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId] })
      await queryClient.invalidateQueries({ queryKey: ['assignments', assignmentId, 'questions'] })
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteAssignment(assignmentId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
      navigate('/', { replace: true })
    },
  })

  if (assignmentQuery.isPending) {
    return <div className="text-sm text-slate-600">Loading assignment...</div>
  }

  if (assignmentQuery.isError) {
    return (
      <QueryError
        error={assignmentQuery.error}
        onRetry={() => {
          void assignmentQuery.refetch()
        }}
      />
    )
  }

  if (!assignmentQuery.data) {
    return <div className="text-sm text-rose-700">Assignment not found.</div>
  }

  const assignment = assignmentQuery.data

  return (
    <div className="space-y-8">
      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[2rem] border border-slate-200 p-6">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-fuchsia-50 px-3 py-1 text-xs font-semibold text-fuchsia-700">
              {formatStatus(assignment.status)}
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
              {assignment.question_count} questions
            </span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
              {assignment.submission_count} submissions
            </span>
          </div>

          <h1 className="mt-4 section-title">{assignment.title}</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Keep the raw assignment text clean here before you decompose it into question parts. If
            file extraction was messy, correct it directly in the editor below.
          </p>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            If you replace the uploaded file, save here and then regenerate questions to overwrite
            the existing structure from the current file/text.
          </p>

          {assignment.ingestion_notes ? (
            <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              {assignment.ingestion_notes}
            </div>
          ) : null}

          {assignment.source_filename ? (
            <div className="mt-4 rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
              Uploaded file:{' '}
              <a
                href={assignment.source_file_url ?? undefined}
                className="font-medium text-fuchsia-700 underline"
              >
                {assignment.source_filename}
              </a>
            </div>
          ) : null}
        </div>

        <div className="rounded-[2rem] bg-slate-950 px-6 py-7 text-white">
          <p className="text-sm font-semibold tracking-[0.18em] text-fuchsia-200/65 uppercase">
            Next step
          </p>
          <h2 className="mt-3 font-['Space_Grotesk'] text-3xl font-bold">Set up your questions.</h2>
          <p className="mt-4 text-sm leading-6 text-fuchsia-100/72">
            Generate questions from your assignment text or add them manually. Check their order and
            marks, then build the reference answers and rubric.
          </p>
          <Link
            to={`/assignments/${assignment.id}/questions`}
            className="mt-6 inline-flex rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-fuchsia-100"
          >
            Open question editor
          </Link>
        </div>
      </section>

      <form
        className="rounded-[2rem] border border-slate-200 p-6"
        onSubmit={(event) => {
          event.preventDefault()
          updateMutation.mutate(form)
        }}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate-700">Title</span>
            <input
              required
              value={form.title}
              onChange={(event) =>
                setForm((current) => ({ ...current, title: event.target.value }))
              }
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate-700">Course name</span>
            <input
              value={form.course_name}
              onChange={(event) =>
                setForm((current) => ({ ...current, course_name: event.target.value }))
              }
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
            />
          </label>
        </div>

        <label className="mt-4 block">
          <span className="mb-2 block text-sm font-medium text-slate-700">Description</span>
          <textarea
            rows={4}
            value={form.description}
            onChange={(event) =>
              setForm((current) => ({ ...current, description: event.target.value }))
            }
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
          />
        </label>

        <div className="mt-4 grid gap-4 md:grid-cols-[0.8fr_1.2fr]">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate-700">
              Replace source file
            </span>
            <input
              type="file"
              accept=".txt,.pdf"
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  source_file: event.target.files?.[0] ?? null,
                }))
              }
              className="block w-full rounded-2xl border border-dashed border-slate-300 px-4 py-4 text-sm text-slate-500"
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate-700">Assignment text</span>
            <textarea
              rows={14}
              value={form.raw_assignment_text}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  raw_assignment_text: event.target.value,
                }))
              }
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
            />
          </label>
        </div>

        {updateMutation.isError ? (
          <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {getApiErrorMessage(
              updateMutation.error,
              'Something went wrong while updating the assignment.',
            )}
          </div>
        ) : null}

        {regenerateMutation.isError ? (
          <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {getApiErrorMessage(
              regenerateMutation.error,
              'Something went wrong while updating the assignment.',
            )}
          </div>
        ) : null}

        {deleteMutation.isError ? (
          <div
            role="alert"
            className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
          >
            {getApiErrorMessage(deleteMutation.error)}
          </div>
        ) : null}
        {updateMutation.isSuccess ? (
          <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            Assignment saved.
          </div>
        ) : null}

        <div className="mt-5 flex flex-wrap gap-3">
          <button
            type="submit"
            disabled={
              updateMutation.isPending || regenerateMutation.isPending || deleteMutation.isPending
            }
            className="rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-fuchsia-700 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {updateMutation.isPending ? 'Saving...' : 'Save assignment'}
          </button>
          <button
            type="button"
            disabled={
              updateMutation.isPending || regenerateMutation.isPending || deleteMutation.isPending
            }
            onClick={() => {
              if (
                assignment.question_count > 0 &&
                !window.confirm(
                  'Replace all questions? Existing reference answers, rubrics, and per-question grading results will also be removed.',
                )
              )
                return
              regenerateMutation.mutate(form)
            }}
            className="rounded-full border border-fuchsia-300 px-5 py-3 text-sm font-semibold text-fuchsia-700 transition hover:bg-fuchsia-50 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {regenerateMutation.isPending
              ? 'Saving and regenerating...'
              : 'Overwrite questions from current file/text'}
          </button>
          <Link
            to={`/assignments/${assignment.id}/questions`}
            className="rounded-full border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
          >
            Continue to questions
          </Link>
          <button
            type="button"
            disabled={
              updateMutation.isPending || regenerateMutation.isPending || deleteMutation.isPending
            }
            onClick={() => {
              if (
                window.confirm(
                  `Delete "${assignment.title}" and all of its generated answers, rubric, submissions, and grading data?`,
                )
              ) {
                deleteMutation.mutate()
              }
            }}
            className="rounded-full border border-rose-200 px-5 py-3 text-sm font-semibold text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {deleteMutation.isPending ? 'Deleting...' : 'Delete assignment'}
          </button>
        </div>
      </form>
    </div>
  )
}
