import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { CollectionChunk } from 'src/generated/api'
import { GAP_PRELOAD_LIMIT, useChunkWindow } from 'src/features/documents/viewer/useChunkWindow'

interface PendingRangeCall {
  orderGt: number | null | undefined
  orderLt: number | null | undefined
  resolve: (chunks: CollectionChunk[]) => void
  reject: (error: Error) => void
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
        ) => new Promise<CollectionChunk[]>((resolve, reject) => {
          rangeCalls.push({ orderGt: requestParameters.orderGt, orderLt: requestParameters.orderLt, resolve, reject })
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

describe('useChunkWindow.showRange', () => {
  it('reads only the orders asked for and leaves a gap to the text shown (#545)', async () => {
    rangeCalls = []
    const chunkWindow = useChunkWindow(() => 'c1', () => 'd1', () => undefined)
    chunkWindow.show([chunk(0), chunk(1)])

    // A gap of more than GAP_PRELOAD_LIMIT chunks: not read.
    const far = GAP_PRELOAD_LIMIT + 10
    const shown = chunkWindow.showRange(far, far + 1)
    await flushPromises()
    expect(rangeCalls.map(c => [c.orderGt, c.orderLt])).toEqual([[far - 1, far + 2]])
    rangeCalls[0].resolve([chunk(far), chunk(far + 1)])
    const result = await shown

    expect(result.shown.map(c => c.order)).toEqual([far, far + 1])
    expect(result.fresh.map(c => c.order)).toEqual([far, far + 1])
    expect(chunkWindow.displayChunks.value.map(c => c.order)).toEqual([0, 1, far, far + 1])
    expect(chunkWindow.hiddenPreviewChunks.value).toEqual([])

    // Shown already: nothing is read again.
    const again = await chunkWindow.showRange(far + 1, far + 1)
    expect(again).toEqual({ shown: [chunk(far + 1)], fresh: [] })
    expect(rangeCalls).toHaveLength(1)
  })

  it('reads a bounded gap it opens as hidden chunks, as the initial load does (#545 review)', async () => {
    rangeCalls = []
    const chunkWindow = useChunkWindow(() => 'c1', () => 'd1', () => undefined)
    // The collection's chunks 0 and 10 (their gap read on the initial load), then a page at 40-41.
    chunkWindow.show([chunk(0), chunk(10)])
    chunkWindow.hiddenPreviewChunks.value = Array.from({ length: 9 }, (_, i) => chunk(i + 1))

    const shown = chunkWindow.showRange(40, 41)
    await flushPromises()
    // The page, and the gap it opens after chunk 10; the known gap 1-9 is not read again.
    expect(rangeCalls.map(c => [c.orderGt, c.orderLt])).toEqual([[39, 42], [10, 40]])
    rangeCalls[0].resolve([chunk(40), chunk(41)])
    rangeCalls[1].resolve(Array.from({ length: 29 }, (_, i) => chunk(i + 11)))
    await shown

    expect(chunkWindow.displayChunks.value.map(c => c.order)).toEqual([0, 10, 40, 41])
    expect(chunkWindow.hiddenPreviewChunks.value.map(c => c.order))
      .toEqual([...Array.from({ length: 9 }, (_, i) => i + 1), ...Array.from({ length: 29 }, (_, i) => i + 11)])
  })

  it('shows the page when reading its gap fails', async () => {
    rangeCalls = []
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const chunkWindow = useChunkWindow(() => 'c1', () => 'd1', () => undefined)
    chunkWindow.show([chunk(0)])
    const shown = chunkWindow.showRange(5, 5)
    await flushPromises()
    expect(rangeCalls).toHaveLength(2)
    rangeCalls[0].resolve([chunk(5)])
    rangeCalls[1].reject(new Error('offline'))
    expect((await shown).fresh.map(c => c.order)).toEqual([5])
    expect(chunkWindow.hiddenPreviewChunks.value).toEqual([])
    warn.mockRestore()
  })

  it('waits for a load still under way, so no chunk is shown twice', async () => {
    rangeCalls = []
    const chunkWindow = useChunkWindow(() => 'c1', () => 'd1', () => undefined)
    chunkWindow.show([chunk(0)])
    const loading = chunkWindow.loadUntil(3)
    const showing = chunkWindow.showRange(2, 4)
    await flushPromises()
    expect(rangeCalls).toHaveLength(1)
    rangeCalls[0].resolve([chunk(1), chunk(2), chunk(3)])
    await loading
    await flushPromises()
    expect(rangeCalls.map(c => [c.orderGt, c.orderLt])).toEqual([[0, 4], [1, 5]])
    rangeCalls[1].resolve([chunk(2), chunk(3), chunk(4)])
    expect((await showing).fresh.map(c => c.order)).toEqual([4])
    expect(chunkWindow.displayChunks.value.map(c => c.order)).toEqual([0, 1, 2, 3, 4])
  })
})
