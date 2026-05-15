import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { createAssignment, type AssignmentPayload } from '../api/assignments'
import { getApiErrorMessage } from '../api/errors'

export function AssignmentCreatePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<AssignmentPayload>({
    title: '',
    course_name: '',
    description: '',
    raw_assignment_text: '',
    source_file: null,
  })

  const createMutation = useMutation({
    mutationFn: createAssignment,
    onSuccess: async (assignment) => {
      await queryClient.invalidateQueries({ queryKey: ['assignments'] })
      navigate(`/assignments/${assignment.id}/overview`)
    },
  })

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold tracking-[0.18em] text-slate-400 uppercase">
          Assignment creation
        </p>
        <h1 className="mt-3 section-title">Start a new grading project</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
          Paste the assignment prompt, upload a .txt file, or try a PDF extraction. You
          can edit the resulting text immediately after creation.
        </p>
      </div>

      <form
        className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]"
        onSubmit={async (event) => {
          event.preventDefault()
          await createMutation.mutateAsync(form)
        }}
      >
        <section className="rounded-[2rem] border border-slate-200 p-6">
          <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            Core details
          </h2>
          <div className="mt-5 space-y-4">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">Title</span>
              <input
                required
                value={form.title}
                onChange={(event) =>
                  setForm((current) => ({ ...current, title: event.target.value }))
                }
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
                placeholder="Midterm short answer set"
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">
                Course name
              </span>
              <input
                value={form.course_name}
                onChange={(event) =>
                  setForm((current) => ({ ...current, course_name: event.target.value }))
                }
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
                placeholder="History 201"
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">
                Description
              </span>
              <textarea
                rows={4}
                value={form.description}
                onChange={(event) =>
                  setForm((current) => ({ ...current, description: event.target.value }))
                }
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-fuchsia-500"
                placeholder="Optional assignment summary or grading context."
              />
            </label>
          </div>
        </section>

        <section className="rounded-[2rem] border border-slate-200 p-6">
          <h2 className="font-['Space_Grotesk'] text-2xl font-bold text-slate-950">
            Source text
          </h2>
          <div className="mt-5 space-y-4">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">
                Upload source file
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
              <span className="mb-2 block text-sm font-medium text-slate-700">
                Assignment text
              </span>
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
                placeholder="Paste the assignment prompt here, or leave this blank and let a file populate it."
              />
            </label>

            {createMutation.isError ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {getApiErrorMessage(
                  createMutation.error,
                  'Something went wrong while saving the assignment.',
                )}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={createMutation.isPending}
              className="w-full rounded-2xl bg-slate-950 px-4 py-3 font-semibold text-white transition hover:bg-fuchsia-700 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {createMutation.isPending ? 'Creating assignment...' : 'Create assignment'}
            </button>
          </div>
        </section>
      </form>
    </div>
  )
}
