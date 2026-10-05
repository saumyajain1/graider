import type { AIJob } from '../api/jobs'
import { jobLabels } from '../lib/aiJobs'

export function AIJobNotice({ job }: { job?: AIJob }) {
  if (!job || job.state === 'succeeded') return null
  return (
    <div
      role="status"
      className="rounded-2xl border border-fuchsia-200 bg-fuchsia-50 p-4 text-sm text-fuchsia-950"
    >
      <p className="font-semibold">
        AI grading: {job.cancel_requested ? 'Cancelling…' : jobLabels[job.state]} ·{' '}
        {job.completed_steps}/{job.total_steps} steps
      </p>
      <p className="mt-1">
        Each student's complete result is published together. Previous grades remain available
        during regrading. Open AI jobs to cancel or resume work.
      </p>
      {job.error_message && <p className="mt-2 text-rose-700">{job.error_message}</p>}
    </div>
  )
}
