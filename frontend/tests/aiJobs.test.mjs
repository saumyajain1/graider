import assert from 'node:assert/strict'
import test from 'node:test'
import { coversQuestion, flattenJobs, isJobReceipt, pollingDelay } from '../src/lib/aiJobs.ts'

test('polls runnable work and backs off outages, without polling paused or finished jobs', () => {
  assert.equal(pollingDelay([{ state: 'queued' }], 0), 3000)
  assert.equal(pollingDelay([{ state: 'running' }], 1), 6000)
  assert.equal(pollingDelay([{ state: 'running' }], 8), 30000)
  assert.equal(pollingDelay([{ state: 'running' }], 0, true), false)
  for (const state of ['succeeded', 'paused_quota', 'needs_attention', 'failed', 'cancelled'])
    assert.equal(pollingDelay([{ state }], 0), false)
  assert.equal(pollingDelay([], 0), false)
})

test('tracks child completion independently of a running batch and scopes generation targets', () => {
  const children = [
    { id: 'done', state: 'succeeded' },
    { id: 'slow', state: 'running' },
  ]
  const jobs = flattenJobs([{ id: 'batch', state: 'running', children }])
  assert.equal(jobs.find((job) => job.id === 'done').state, 'succeeded')
  assert.equal(jobs.find((job) => job.id === 'batch').state, 'running')
  assert.equal(coversQuestion({ operation: 'reference_answers', question_part_ids: [2] }, 1), false)
  assert.equal(coversQuestion({ operation: 'reference_answers', question_part_ids: [2] }, 2), true)
  assert.equal(coversQuestion({ operation: 'questions', question_part_ids: [] }, 1), true)
})

test('distinguishes complete job metadata from legacy responses and malformed receipts', () => {
  const job = {
    id: 'uuid',
    operation: 'rubric',
    state: 'queued',
    completed_steps: 0,
    total_steps: 1,
    question_part_ids: [1],
  }
  assert.equal(isJobReceipt(job), true)
  for (const data of [
    null,
    [],
    { id: 1, student_name: 'Student' },
    { ...job, state: 'unknown' },
    { ...job, question_part_ids: undefined },
  ])
    assert.equal(isJobReceipt(data), false)
})
