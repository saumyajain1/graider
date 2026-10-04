import assert from 'node:assert/strict'
import test from 'node:test'
import { build } from 'esbuild'

const compiled = await build({
  entryPoints: ['src/api/jobs.ts'],
  bundle: true,
  write: false,
  format: 'esm',
  platform: 'node',
})
const source = `data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`
const { aiAction, setAIActionOwner, discoverJobs } = await import(source)
const stored = new Map()
globalThis.sessionStorage = {
  getItem: (key) => stored.get(key) ?? null,
  setItem: (key, value) => stored.set(key, value),
  removeItem: (key) => stored.delete(key),
}
globalThis.document = { cookie: 'csrftoken=test-csrf' }
globalThis.window = { location: { origin: 'http://localhost' }, setTimeout, clearTimeout }
const response = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

test('lost response retries preserve the action key across navigation and reload, then clear it on success', async () => {
  setAIActionOwner(1)
  const keys = []
  let count = 0
  globalThis.fetch = async (_, options) => {
    keys.push(options.headers.get('Idempotency-Key'))
    assert.equal(options.headers.get('X-CSRFToken'), 'test-csrf')
    if (++count === 1) throw new TypeError('Lost response')
    return response({ id: 'accepted' })
  }
  await assert.rejects(aiAction('/action', { regrade: false }))
  // Reload creates a fresh module; the session-stored key must still replay admission.
  const reloaded = await import(source + '#reload')
  reloaded.setAIActionOwner(1)
  await reloaded.aiAction('/action', { regrade: false })
  await reloaded.aiAction('/action', { regrade: false })
  assert.equal(keys[0], keys[1])
  assert.notEqual(keys[1], keys[2])
  assert.equal(stored.size, 0)
})

test('owner scope prevents one user reusing another user’s pending action key', async () => {
  const keys = []
  globalThis.fetch = async (_, options) => {
    keys.push(options.headers.get('Idempotency-Key'))
    throw new TypeError('Lost response')
  }
  setAIActionOwner(10)
  await assert.rejects(aiAction('/scope', {}))
  setAIActionOwner(11)
  await assert.rejects(aiAction('/scope', {}))
  assert.notEqual(keys[0], keys[1])
})

test('server errors preserve an uncertain admission key; explicit rejection releases it', async () => {
  setAIActionOwner(20)
  const keys = []
  const statuses = [500, 409, 200]
  globalThis.fetch = async (_, options) => {
    keys.push(options.headers.get('Idempotency-Key'))
    return response({ detail: 'test' }, statuses.shift())
  }
  await assert.rejects(aiAction('/uncertain', {}))
  await assert.rejects(aiAction('/uncertain', {}))
  await aiAction('/uncertain', {})
  assert.equal(keys[0], keys[1])
  assert.notEqual(keys[1], keys[2])
})

test('discovers active jobs beyond the recent page and expands child progress', async () => {
  const seen = []
  globalThis.fetch = async (path) => {
    seen.push(path)
    if (path === '/api/ai/jobs/')
      return response({
        results: [{ id: 'recent', operation: 'questions', created_at: '2026-10-03' }],
        next: null,
      })
    if (path === '/api/ai/jobs/?active_only=true')
      return response({
        results: [{ id: 'older-batch', operation: 'grade_batch', created_at: '2026-10-01' }],
        next: 'http://localhost/api/ai/jobs/?active_only=true&page=2',
      })
    if (path.includes('page=2'))
      return response({
        results: [{ id: 'older-single', operation: 'rubric', created_at: '2026-10-02' }],
        next: null,
      })
    return response({
      id: 'older-batch',
      operation: 'grade_batch',
      created_at: '2026-10-01',
      children: [
        { id: 'first', state: 'succeeded' },
        { id: 'second', state: 'running' },
      ],
    })
  }
  const jobs = await discoverJobs()
  assert.deepEqual(
    jobs.map((job) => job.id),
    ['recent', 'older-single', 'older-batch'],
  )
  assert.equal(jobs[2].children[0].state, 'succeeded')
  assert.ok(seen.includes('/api/ai/jobs/?active_only=true&page=2'))
})
