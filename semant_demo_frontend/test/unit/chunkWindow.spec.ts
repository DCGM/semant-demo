import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { CollectionChunk } from 'src/generated/api'
import { useChunkWindow } from 'src/features/documents/viewer/useChunkWindow'

interface PendingRangeCall {
  orderGt: number | null | undefined
  orderLt: number | null | undefined
  resolve: (chunks: CollectionChunk[]) => void
}

let rangeCalls: PendingRangeCall[]

vi.mock('src/shared/api', async () => {
  const actual = await vi.importActual<typeof import('src/shared/api')>('src/shared/api')
  return {
    ...actual,
    useApi: () => ({
      default: {
        getChunksInRangeApiUserCollectionsCollectionIdDocumentsDocumentIdChunksRangeGet: (
          requestParameters: { orderGt?: number | null, orderLt?: number | null }
        ) => new Promise<CollectionChunk[]>((resolve) => {
          rangeCalls.push({ orderGt: requestParameters.orderGt, orderLt: requestParameters.orderLt, resolve })
        }),
        getNeighbourChunkApiUserCollectionsCollectionIdDocumentsDocumentIdChunksNeighbourGet: () =>
          Promise.resolve(null)
      }
    })
  }
})

const chunk = (order: number): CollectionChunk => ({
  id: `chunk-${order}`, text: `text ${order}`, startPageId: 'p', fromPage: order, toPage: order, order
})

describe('useChunkWindow.loadUntil', () => {
  it('serializes overlapping calls instead of both reading the same pre-fetch window', async () => {
    rangeCalls = []
    const chunkWindow = useChunkWindow(() => 'c1', () => 'd1', () => undefined)
    chunkWindow.show([chunk(0)])

    // Two citations fired in quick succession (e.g. a double click, or a second citation
    // clicked before the first load settles) before any network call resolves.
    const first = chunkWindow.loadUntil(5)
    const second = chunkWindow.loadUntil(5)
    await flushPromises()

    // The second call is queued behind the first rather than firing its own overlapping
    // request against the same (stale) pre-fetch window (#358 review).
    expect(rangeCalls).toHaveLength(1)

    rangeCalls[0].resolve([chunk(1), chunk(2), chunk(3), chunk(4), chunk(5)])
    await first
    await second

    // No request was ever made for the second call: by the time it ran, order 5 was already
    // in the window, so it only had to discover `loadUntil`'s now-true "already here" case.
    expect(rangeCalls).toHaveLength(1)
    const ids = chunkWindow.displayChunks.value.map((c) => c.id)
    expect(ids).toEqual(['chunk-0', 'chunk-1', 'chunk-2', 'chunk-3', 'chunk-4', 'chunk-5'])
    expect(new Set(ids).size).toBe(ids.length) // no duplicate chunk ids (would break v-for :key)
  })

  it('two calls to different targets still each load, in request order, with no duplicates', async () => {
    rangeCalls = []
    const chunkWindow = useChunkWindow(() => 'c1', () => 'd1', () => undefined)
    chunkWindow.show([chunk(0)])

    const first = chunkWindow.loadUntil(2)
    const second = chunkWindow.loadUntil(5)
    await flushPromises()
    expect(rangeCalls).toHaveLength(1) // the second is queued, not fired yet

    rangeCalls[0].resolve([chunk(1), chunk(2)])
    await first
    await flushPromises()
    expect(rangeCalls).toHaveLength(2) // only now does the queued second call run

    rangeCalls[1].resolve([chunk(3), chunk(4), chunk(5)])
    await second

    const ids = chunkWindow.displayChunks.value.map((c) => c.id)
    expect(ids).toEqual(['chunk-0', 'chunk-1', 'chunk-2', 'chunk-3', 'chunk-4', 'chunk-5'])
  })
})
