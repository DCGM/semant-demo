import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useTagSpansStore } from 'src/features/annotations/tagSpansStore'
import { cutAtGap } from 'src/features/annotations/spanOffsets'
import { useAnnotations } from 'src/features/annotations/useAnnotations'
import { GAP_PRELOAD_LIMIT, useChunkWindow } from 'src/features/documents/viewer/useChunkWindow'
import type { CollectionChunk, TagSpan } from 'src/generated/api'

// Annotations crossing the gap that a distant page of the scan opens in the collection reader
// (#545 review): a bounded gap is read as on the initial load, so the annotation is shown across
// it; a larger one is not read, and the annotation running into it is reported, not cut silently.

const chunk = (order: number): CollectionChunk => ({
  id: `chunk-${order}`, text: `text ${String(order).padStart(3, '0')} `, startPageId: 'p', fromPage: order, toPage: order, order
})
/** Every chunk text has this length. */
const LENGTH = chunk(0).text.length

vi.mock('src/shared/api', async () => {
  const actual = await vi.importActual<typeof import('src/shared/api')>('src/shared/api')
  return {
    ...actual,
    useApi: () => ({
      default: {
        // The document's chunks, every order: those strictly between the bounds.
        getChunksInRangeApiUserCollectionsCollectionIdDocumentsDocumentIdChunksRangeGet: (
          { orderGt, orderLt }: { orderGt?: number | null, orderLt?: number | null }
        ) => {
          const from = (orderGt ?? -1) + 1
          const to = (orderLt ?? 1000) - 1
          return Promise.resolve(Array.from({ length: Math.max(0, to - from + 1) }, (_, i) => chunk(from + i)))
        },
        getNeighbourChunkApiUserCollectionsCollectionIdDocumentsDocumentIdChunksNeighbourGet: () => Promise.resolve(null)
      }
    })
  }
})

/** A collection of chunks 0 and 10 (the gap between them read, as on the initial load) and a span from chunk 10 on. */
function reader (spanEnd: number) {
  const chunkWindow = useChunkWindow(() => 'c1', () => 'd1', () => undefined)
  chunkWindow.show([{ ...chunk(0), inCollection: true }, { ...chunk(10), inCollection: true }])
  chunkWindow.hiddenPreviewChunks.value = Array.from({ length: 9 }, (_, i) => chunk(i + 1))
  const span: TagSpan = { id: 's1', chunkId: 'chunk-10', tagId: 't', start: 2, end: spanEnd, type: 'pos' }
  useTagSpansStore().spansByChunkId = { 'chunk-10': [span] }
  const annotations = useAnnotations(() => chunkWindow.displayChunks.value, () => chunkWindow.hiddenPreviewChunks.value)
  return { chunkWindow, annotations }
}

describe('annotations across the gap a distant page opens', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('shows an annotation across a bounded gap on the page shown', async () => {
    // The span runs from chunk 10 into chunk 40, the page shown: 30 chunks and 4 characters.
    const { chunkWindow, annotations } = reader(30 * LENGTH + 4)
    expect(annotations.cutAtGapOrders.value.size).toBe(0)

    await chunkWindow.showRange(40, 41)
    await flushPromises()

    expect(chunkWindow.displayChunks.value.map(c => c.order)).toEqual([0, 10, 40, 41])
    expect(annotations.getProjectedSpans('chunk-10').map(s => [s.id, s.start, s.end])).toEqual([['s1', 2, 30 * LENGTH + 4]])
    expect(annotations.getProjectedSpans('chunk-40').map(s => [s.id, s.start, s.end])).toEqual([['s1', 0, 4]])
    expect(annotations.getProjectedSpans('chunk-41')).toEqual([])
    expect(annotations.cutAtGapOrders.value.size).toBe(0)
  })

  it('reports an annotation running into a gap too large to read, instead of cutting it silently', async () => {
    const far = 10 + GAP_PRELOAD_LIMIT + 5
    const { chunkWindow, annotations } = reader(3 * LENGTH)
    // Before: the span runs past the last chunk shown, the end of the known text, not into a gap.
    expect(annotations.cutAtGapOrders.value.size).toBe(0)

    await chunkWindow.showRange(far, far)
    await flushPromises()

    expect(chunkWindow.hiddenPreviewChunks.value.every(c => c.order < 10)).toBe(true)
    expect(annotations.getProjectedSpans('chunk-10').map(s => s.id)).toEqual(['s1'])
    expect([...annotations.cutAtGapOrders.value]).toEqual([10])
  })
})

describe('cutAtGap', () => {
  const chunks = [{ order: 0, text: 'abcd' }, { order: 1, text: 'efgh' }, { order: 5, text: 'ijkl' }]

  it('finds the chunk before the gap a span runs into', () => {
    expect(cutAtGap(chunks, 0, 9)).toBe(1)
    expect(cutAtGap(chunks, 1, 5)).toBe(1)
  })

  it('is null for a span ending before the gap, or at the end of the known text', () => {
    expect(cutAtGap(chunks, 0, 8)).toBeNull()
    expect(cutAtGap(chunks, 0, 3)).toBeNull()
    expect(cutAtGap(chunks, 2, 9)).toBeNull()
  })
})
