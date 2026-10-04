import assert from 'node:assert/strict'
import test from 'node:test'
import { DraftStore } from '../src/lib/draftStore.ts'

const draft = (save, validate = () => {}, dirty = true) => ({ dirty, save, validate })

test('validates every selected editor before saving any of them', async () => {
  const store = new DraftStore()
  let writes = 0
  store.register(
    'one',
    draft(async () => writes++),
  )
  store.register(
    'two',
    draft(
      async () => writes++,
      () => {
        throw new Error('Invalid second editor')
      },
    ),
  )
  await assert.rejects(store.saveAll(), /Invalid second editor/)
  assert.equal(writes, 0)
  assert.equal(store.isDirty(), true)
})

test('saving before leaving permits incomplete unchanged setup but validates edited work', async () => {
  const store = new DraftStore()
  let saved = false
  store.register(
    'edited',
    draft(async () => {
      saved = true
    }),
  )
  store.register(
    'empty',
    draft(
      async () => {},
      () => {
        throw new Error('Incomplete answer')
      },
      false,
    ),
  )
  await store.saveAll({ dirtyOnly: true })
  assert.equal(saved, true)
  assert.equal(store.isDirty(), false)
  await assert.rejects(store.saveAll(), /Incomplete answer/)
})

test('failed later save keeps the remaining editor dirty and retries only unsaved work', async () => {
  const store = new DraftStore()
  let first = 0,
    second = 0
  store.register(
    'first',
    draft(async () => first++),
  )
  store.register(
    'second',
    draft(async () => {
      if (++second === 1) throw new Error('Network failed')
    }),
  )
  await assert.rejects(store.saveAll({ dirtyOnly: true }), /Network failed/)
  assert.equal(store.isDirty('first'), false)
  assert.equal(store.isDirty('second'), true)
  await store.saveAll({ dirtyOnly: true })
  assert.equal(first, 1)
  assert.equal(second, 2)
  assert.equal(store.isDirty(), false)
})

test('query refreshes do not drop remaining edits from the save snapshot', async () => {
  const store = new DraftStore()
  let writes = 0
  store.register(
    'first',
    draft(async () => {
      writes++
      store.register(
        'first',
        draft(
          async () => {},
          () => {},
          false,
        ),
      )
      store.register(
        'second',
        draft(async () => {
          throw new Error('Must use captured draft')
        }),
      )
    }),
  )
  store.register(
    'second',
    draft(async () => writes++),
  )
  await store.saveAll()
  assert.equal(writes, 2)
  assert.equal(store.isDirty(), false)
})

test('discard clears navigation guard and old effect cleanup cannot unregister a replacement', () => {
  const store = new DraftStore()
  const removeOld = store.register(
    'editor',
    draft(async () => {}),
  )
  store.register(
    'editor',
    draft(async () => {}),
  )
  removeOld()
  assert.equal(store.isDirty(), true)
  store.discard()
  assert.equal(store.isDirty(), false)
})

test('concurrent save attempts are rejected without duplicate writes', async () => {
  const store = new DraftStore()
  let release,
    writes = 0
  store.register(
    'editor',
    draft(() => {
      writes++
      return new Promise((resolve) => {
        release = resolve
      })
    }),
  )
  const pending = store.saveAll()
  await assert.rejects(store.saveAll(), /wait for saving/)
  release()
  await pending
  assert.equal(writes, 1)
})
