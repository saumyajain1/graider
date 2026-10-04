import { useEffect, useRef, type PropsWithChildren } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { ApiError } from '../api/client'
import { discoverJobs, setAIActionOwner, type AIJob } from '../api/jobs'
import { activeJobStates, coversQuestion, flattenJobs, pollingDelay } from '../lib/aiJobs'
import { useWorkflowDrafts } from '../hooks/useDraftSaves'

import { AIJobContext, type JobContext } from '../hooks/useAIJobs'

export function AIJobsProvider({ userId, children }: PropsWithChildren<{ userId: number }>) {
  const client = useQueryClient()
  const { hasChanges, isSaving, isDirty } = useWorkflowDrafts()
  const location = useLocation()
  const queryKey = ['aiJobs', userId]
  useEffect(() => {
    setAIActionOwner(userId)
  }, [userId])
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => discoverJobs(signal),
    refetchOnWindowFocus: true,
    refetchInterval: (query) =>
      pollingDelay(
        query.state.data,
        query.state.error ? query.state.errorUpdateCount : 0,
        query.state.error instanceof ApiError && [401, 403].includes(query.state.error.status),
      ),
    refetchIntervalInBackground: false,
  })
  const refresh = () => {
    void query.refetch()
  }
  const seen = useRef(new Set<string>())
  const waiting = useRef(new Map<string, AIJob>())
  useEffect(() => {
    void client.invalidateQueries({ queryKey: ['aiJobs', userId] })
  }, [location.pathname, userId, client])
  useEffect(() => {
    if (query.error instanceof ApiError && [401, 403].includes(query.error.status)) {
      void client.invalidateQueries({ queryKey: ['auth', 'me'] })
    }
  }, [query.error, client])
  useEffect(() => {
    const complete = flattenJobs(query.data ?? []).filter(
      (job) => job.state === 'succeeded' && job.operation !== 'grade_batch',
    )
    for (const job of complete) {
      if (seen.current.has(job.id)) continue
      seen.current.add(job.id)
      waiting.current.set(job.id, job)
      // Roster and dashboard updates never replace editor drafts.
      void client.invalidateQueries({ queryKey: ['assignments'], exact: true })
      void client.invalidateQueries({
        queryKey: ['assignments', String(job.assignment_id), 'submissions'],
        exact: true,
      })
    }
    if (isDirty() || isSaving) return
    for (const job of waiting.current.values()) {
      void client.invalidateQueries({ queryKey: ['assignments', String(job.assignment_id)] })
      if (job.submission_id)
        void client.invalidateQueries({
          queryKey: ['submissions', String(job.submission_id), 'grading'],
        })
    }
    waiting.current.clear()
  }, [query.data, hasChanges, isSaving, isDirty, client])
  const jobs = query.data ?? []
  const active = flattenJobs(jobs).filter((job) => activeJobStates.includes(job.state))
  const value: JobContext = {
    jobs,
    error: query.error,
    isLoading: query.isPending,
    refresh,
    track: (job) => {
      client.setQueryData<AIJob[]>(queryKey, (previous = []) => [
        job,
        ...previous.filter((row) => row.id !== job.id),
      ])
      void client.invalidateQueries({ queryKey })
    },
    find: (operation, assignmentId, questionId) =>
      active.find(
        (job) =>
          job.operation === operation &&
          String(job.assignment_id) === String(assignmentId) &&
          (questionId === undefined
            ? job.question_part_id === null
            : coversQuestion(job, questionId)),
      ),
    forSubmission: (submissionId) =>
      active.find(
        (job) => job.operation === 'grade_submission' && job.submission_id === submissionId,
      ),
    latestForSubmission: (submissionId) =>
      flattenJobs(jobs).find(
        (job) => job.operation === 'grade_submission' && job.submission_id === submissionId,
      ),
    hasOperation: (operation, assignmentId) =>
      active.some(
        (job) => job.operation === operation && String(job.assignment_id) === String(assignmentId),
      ),
  }
  return <AIJobContext.Provider value={value}>{children}</AIJobContext.Provider>
}
