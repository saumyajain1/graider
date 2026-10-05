import { ApiError, apiRequest } from './client'
import { isJobReceipt } from '../lib/aiJobs'

export type JobState =
  | 'queued'
  | 'running'
  | 'retry_wait'
  | 'paused_quota'
  | 'needs_attention'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'superseded'
export type JobOperation =
  'questions' | 'reference_answers' | 'rubric' | 'grade_submission' | 'grade_batch'
export type AIJob = {
  id: string
  operation: JobOperation
  state: JobState
  assignment_id: number | null
  assignment_title: string
  submission_id: number | null
  student_name: string
  parent_id: string | null
  question_part_id: number | null
  question_part_ids: number[]
  replace_existing: boolean
  completed_steps: number
  total_steps: number
  cancel_requested: boolean
  error_code: string
  error_message: string
  result_reference: Record<string, unknown>
  retry_after: string | null
  created_at: string
  updated_at: string
  finished_at: string | null
  children?: AIJob[]
  possible_duplicate_charge?: boolean
}
type JobPage = { results: AIJob[]; next: string | null }

export function getJob(id: string, signal?: AbortSignal) {
  return apiRequest<AIJob>(`/api/ai/jobs/${id}/`, { signal })
}

export async function discoverJobs(signal?: AbortSignal) {
  const recent = await apiRequest<JobPage>('/api/ai/jobs/', { signal })
  const all = new Map(recent.results.map((job) => [job.id, job]))
  let path: string | null = '/api/ai/jobs/?active_only=true'
  while (path) {
    const page: JobPage = await apiRequest<JobPage>(path, { signal })
    page.results.forEach((job) => all.set(job.id, job))
    path = page.next
      ? new URL(page.next, window.location.origin).pathname +
        new URL(page.next, window.location.origin).search
      : null
  }
  const jobs = await Promise.all(
    [...all.values()].map((job) =>
      job.operation === 'grade_batch' ? getJob(job.id, signal) : job,
    ),
  )
  return jobs.sort((a, b) => b.created_at.localeCompare(a.created_at))
}

export function cancelJob(id: string) {
  return apiRequest<AIJob>(`/api/ai/jobs/${id}/cancel/`, { method: 'POST', body: '{}' })
}
export function retryJob(id: string, confirmPossibleCharge: boolean) {
  return apiRequest<AIJob>(`/api/ai/jobs/${id}/retry/`, {
    method: 'POST',
    body: JSON.stringify({ confirm_possible_charge: confirmPossibleCharge }),
  })
}

let actionOwner: number | null = null
const pendingKeys = new Map<string, string>()
export function setAIActionOwner(owner: number) {
  actionOwner = owner
}

export async function aiAction(path: string, payload: unknown) {
  const intent = `graider-ai-request:${actionOwner}:${path}:${JSON.stringify(payload)}`
  let key = pendingKeys.get(intent)
  try {
    key ??= sessionStorage.getItem(intent) ?? undefined
  } catch {
    /* Storage may be disabled. */
  }
  key ??= crypto.randomUUID()
  pendingKeys.set(intent, key)
  try {
    sessionStorage.setItem(intent, key)
  } catch {
    /* The in-memory key still protects retries. */
  }
  const clear = () => {
    pendingKeys.delete(intent)
    try {
      sessionStorage.removeItem(intent)
    } catch {
      /* Storage may be disabled. */
    }
  }
  try {
    const result = await apiRequest<unknown>(path, {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Idempotency-Key': key },
    })
    if (!isJobReceipt(result)) {
      throw new ApiError(
        'Could not confirm the AI job. Retry to check whether it was accepted.',
        502,
        null,
      )
    }
    clear()
    return result
  } catch (error) {
    // Preserve the action key when the server may have accepted a lost response.
    if (error instanceof ApiError && error.status >= 400 && error.status < 500) clear()
    throw error
  }
}
