import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useTagSpansStore } from 'src/features/annotations/tagSpansStore'
import { ResponseError, WriteOutcome } from 'src/generated/api'

// The document view's span writes carry the version the view loaded (#460): a span someone
// else changed meanwhile is refused, and the view then shows it as it is now.

const repo = {
  getByChunkIdsInCollection: vi.fn(),
  update: vi.fn(),
  bulkUpdate: vi.fn(),
  delete: vi.fn()
}
vi.mock('src/features/annotations/useTagSpansRepository', () => ({ useTagSpansRepository: () => repo }))
vi.mock('src/shared/notification', () => ({ warningNotification: vi.fn() }))

const span = (id: string, editVersion: number, type = 'auto') =>
  ({ id, chunkId: 'c1', tagId: 't', start: 0, end: 3, type, editVersion })
const complete = { outcome: WriteOutcome.complete, succeeded: [], failed: [], unattempted: [] }
const refused = (status: number, body: unknown) =>
  new ResponseError(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

async function loaded () {
  const store = useTagSpansStore()
  repo.getByChunkIdsInCollection.mockResolvedValue({ c1: [span('s1', 2), span('s2', 0)] })
  await store.fetchSpansForChunksInCollection(['c1'], 'col')
  return store
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
})

describe('span writes in the document view', () => {
  it('send the version of the loaded span and keep the saved one', async () => {
    const store = await loaded()
    repo.update.mockResolvedValue({ ...span('s1', 3, 'pos'), ...complete })

    await store.updateSpan('s1', 'c1', { type: 'pos' })
    expect(repo.update).toHaveBeenCalledWith('s1', 'col', { type: 'pos' }, 2)
    repo.delete.mockResolvedValue(complete)
    await store.deleteSpan('s1', 'c1')
    expect(repo.delete).toHaveBeenCalledWith('s1', 'col', 3)
  })

  it('show the current span when someone else changed it meanwhile, and say nothing was saved', async () => {
    const store = await loaded()
    repo.update.mockRejectedValue(refused(409, { detail: 'conflict', current: span('s1', 3, 'neg') }))

    await expect(store.updateSpan('s1', 'c1', { type: 'pos' })).rejects.toMatchObject({
      status: 409, detail: expect.stringContaining('nothing was saved')
    })
    expect(store.spansByChunkId.c1.find(s => s.id === 's1')).toMatchObject({ type: 'neg', editVersion: 3 })
  })

  it('remove a span someone else deleted meanwhile', async () => {
    const store = await loaded()
    repo.delete.mockRejectedValue(refused(404, { detail: 'Span not found' }))

    await expect(store.deleteSpan('s1', 'c1')).rejects.toMatchObject({ status: 404, detail: expect.stringContaining('deleted') })
    expect(store.spansByChunkId.c1.map(s => s.id)).toEqual(['s2'])
  })

  it('approve or reject many with their versions and show the ones changed meanwhile as they are', async () => {
    const store = await loaded()
    repo.bulkUpdate.mockResolvedValue({
      ...complete,
      outcome: WriteOutcome.partial,
      succeeded: ['s2'],
      failed: [{ itemId: 's1', step: 'edit_conflict', message: 'x' }],
      spans: [span('s2', 1, 'pos')],
      conflicts: [span('s1', 3, 'neg')]
    })

    await expect(store.bulkUpdateSpans(['s1', 's2'], { type: 'pos' })).rejects.toThrow('changed by someone else')
    expect(repo.bulkUpdate).toHaveBeenCalledWith(['s1', 's2'], 'col', { type: 'pos' }, { s1: 2, s2: 0 })
    expect(store.spansByChunkId.c1.map(s => [s.id, s.type, s.editVersion])).toEqual([['s1', 'neg', 3], ['s2', 'pos', 1]])
  })
})
