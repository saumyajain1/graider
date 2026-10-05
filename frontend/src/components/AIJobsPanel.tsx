import { useState } from 'react'
import { Link } from 'react-router-dom'
import { cancelJob, getJob, retryJob, type AIJob } from '../api/jobs'
import { getApiErrorMessage } from '../api/errors'
import { useAIJobs } from '../hooks/useAIJobs'
import { useWorkflowDrafts } from '../hooks/useDraftSaves'
import { useConfirmation } from '../hooks/useConfirmation'
import {
  activeJobStates,
  jobLabels,
  operationLabels,
  retryableJobStates,
  runnableJobStates,
} from '../lib/aiJobs'
import { Icon } from './Icon'
import { ReplacementConfirmation } from './ReplacementConfirmation'

export function AIJobsPanel() {
  const jobs = useAIJobs()
  const drafts = useWorkflowDrafts()
  const confirmation = useConfirmation()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const active = jobs.jobs.filter((job) => activeJobStates.includes(job.state))
  const running = active.some((job) => runnableJobStates.includes(job.state))
  const act = async (job: AIJob, retry: boolean) => {
    setBusy(job.id)
    setError(null)
    try {
      if (retry) {
        const latest = await getJob(job.id)
        if (
          latest.possible_duplicate_charge &&
          !(await confirmation.ask(
            'A previous AI request may already have been billed. Retrying can incur an additional charge. Resume this unfinished work?',
          ))
        )
          return
        jobs.track(await retryJob(job.id, Boolean(latest.possible_duplicate_charge)))
      } else jobs.track(await cancelJob(job.id))
    } catch (error) {
      setError(getApiErrorMessage(error))
    } finally {
      setBusy(null)
      jobs.refresh()
    }
  }
  const row = (job: AIJob, child = false) => (
    <div
      key={job.id}
      className={`space-y-2 border-t border-slate-200 py-3 ${child ? 'pl-3 text-xs' : 'text-sm'}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-slate-950">
            {child ? job.student_name : operationLabels[job.operation]}
          </p>
          {!child && (
            <p className="break-words text-xs text-slate-500">
              {job.assignment_title}
              {job.student_name ? ` · ${job.student_name}` : ''}
            </p>
          )}
          <p className="mt-1 text-fuchsia-800">
            {job.cancel_requested && activeJobStates.includes(job.state)
              ? 'Cancelling…'
              : jobLabels[job.state]}{' '}
            · {job.completed_steps}/{job.total_steps} steps
          </p>
        </div>
        {job.assignment_id && (
          <Link
            className="shrink-0 font-semibold text-fuchsia-700 underline"
            to={`/assignments/${job.assignment_id}/${job.submission_id ? `review/${job.submission_id}` : job.operation === 'questions' ? 'questions' : job.operation === 'reference_answers' ? 'reference-answers' : job.operation === 'rubric' ? 'rubric' : 'submissions'}`}
          >
            {job.state === 'succeeded' ? 'View result' : 'Open'}
          </Link>
        )}
      </div>
      <progress
        className="h-2 w-full accent-fuchsia-700"
        max={Math.max(1, job.total_steps)}
        value={job.completed_steps}
        aria-label={`Progress: ${job.student_name || operationLabels[job.operation]}`}
      />
      {job.error_message && <p className="break-words text-rose-700">{job.error_message}</p>}
      <div className="flex gap-2">
        {activeJobStates.includes(job.state) && !job.cancel_requested && (
          <button
            type="button"
            className="rounded-full border border-slate-300 px-3 py-1 text-slate-700"
            disabled={busy !== null}
            onClick={() => {
              void act(job, false)
            }}
          >
            Cancel
          </button>
        )}
        {retryableJobStates.includes(job.state) && !job.cancel_requested && (
          <button
            type="button"
            className="rounded-full border border-fuchsia-300 px-3 py-1 text-fuchsia-800"
            disabled={busy !== null}
            onClick={() => {
              void act(job, true)
            }}
          >
            {busy === job.id ? 'Resuming…' : 'Retry / resume'}
          </button>
        )}
      </div>
      {job.children?.map((child) => row(child, true))}
    </div>
  )
  return (
    <div className="relative">
      <ReplacementConfirmation
        confirmation={confirmation}
        titleText="Resume AI job?"
        confirmLabel="Confirm and resume"
        cancelLabel="Keep paused"
      />
      <details
        onToggle={(event) => {
          if (event.currentTarget.open) jobs.refresh()
        }}
      >
        <summary
          className="flex cursor-pointer list-none items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm font-semibold"
          aria-label="AI job progress"
        >
          <Icon name={running ? 'spinner' : 'sparkles'} /> AI jobs
          {active.length ? ` (${active.length})` : ''}
        </summary>
        <div className="absolute right-0 z-50 mt-3 max-h-[70vh] w-[min(28rem,85vw)] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-5 text-slate-700 shadow-xl">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-semibold text-slate-950">AI jobs</h3>
            <button
              type="button"
              className="text-sm font-semibold text-fuchsia-700"
              onClick={jobs.refresh}
            >
              Refresh
            </button>
          </div>
          <p className="my-3 text-xs text-slate-500">
            You can navigate while jobs run. Each student's results appear when their grading
            finishes. Cancel stops future work; a request already sent may still be charged.
          </p>
          {drafts.hasChanges && (
            <p className="mb-3 rounded-xl bg-amber-50 p-3 text-xs text-amber-900">
              Your unsaved edits are kept. Save them or leave this page to load updated editor
              results.
            </p>
          )}
          {Boolean(error || jobs.error) && (
            <p role="alert" className="mb-3 text-sm text-rose-700">
              {error || getApiErrorMessage(jobs.error)}
            </p>
          )}
          {jobs.isLoading && <p className="text-sm">Loading jobs…</p>}
          {!jobs.isLoading && !jobs.jobs.length && (
            <p className="text-sm text-slate-500">No recent AI jobs.</p>
          )}
          {jobs.jobs.map((job) => row(job))}
        </div>
      </details>
      <span className="sr-only" role="status">
        {active.length} active AI jobs.
      </span>
    </div>
  )
}
