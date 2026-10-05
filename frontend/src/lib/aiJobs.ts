import type { AIJob } from '../api/jobs'

export function isJobReceipt(value: unknown): value is AIJob {
  if (typeof value !== 'object' || value === null) return false
  const job = value as Record<string, unknown>
  return (
    typeof job.id === 'string' &&
    typeof job.operation === 'string' &&
    job.operation in operationLabels &&
    typeof job.state === 'string' &&
    job.state in jobLabels &&
    typeof job.completed_steps === 'number' &&
    typeof job.total_steps === 'number' &&
    Array.isArray(job.question_part_ids)
  )
}

export const activeJobStates = [
  'queued',
  'running',
  'retry_wait',
  'paused_quota',
  'needs_attention',
]
export const runnableJobStates = ['queued', 'running', 'retry_wait']
export const retryableJobStates = ['failed', 'paused_quota', 'needs_attention']
export const jobLabels = {
  queued: 'Queued',
  running: 'Running',
  retry_wait: 'Waiting to retry',
  paused_quota: 'Paused: AI allowance',
  needs_attention: 'Needs attention',
  succeeded: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  superseded: 'Inputs changed',
}
export const operationLabels = {
  questions: 'Extract questions',
  reference_answers: 'Reference answers',
  rubric: 'Rubric generation',
  grade_submission: 'Grade student',
  grade_batch: 'Grade batch',
}
export function flattenJobs(jobs: AIJob[]) {
  return jobs.flatMap((job) => [job, ...(job.children ?? [])])
}
export function coversQuestion(job: AIJob, questionId: number) {
  return job.operation === 'questions' || job.question_part_ids.includes(questionId)
}
export function pollingDelay(jobs: AIJob[] | undefined, failures: number, unauthorized = false) {
  if (unauthorized) return false
  if (failures) return Math.min(30_000, 3_000 * 2 ** Math.min(failures, 4))
  return jobs?.some((job) => runnableJobStates.includes(job.state)) ? 3_000 : false
}
