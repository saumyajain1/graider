import { createContext, useContext } from 'react'
import type { AIJob, JobOperation } from '../api/jobs'

export type JobContext = {
  jobs: AIJob[]
  error: unknown
  isLoading: boolean
  refresh: () => void
  track: (job: AIJob) => void
  find: (
    operation: JobOperation,
    assignmentId: string | number | undefined,
    questionId?: number,
  ) => AIJob | undefined
  forSubmission: (submissionId: number) => AIJob | undefined
  latestForSubmission: (submissionId: number) => AIJob | undefined
  hasOperation: (operation: JobOperation, assignmentId: string | number | undefined) => boolean
}
export const AIJobContext = createContext<JobContext | null>(null)

export function useAIJobs() {
  const context = useContext(AIJobContext)
  if (!context) throw new Error('AI jobs are unavailable outside the signed-in workspace.')
  return context
}
