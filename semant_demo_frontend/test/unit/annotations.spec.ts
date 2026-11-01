import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

import { useTagSpansStore } from 'src/features/annotations/tagSpansStore'
import { useAnnotations } from 'src/features/annotations/useAnnotations'
import { memoizeVisibleSpansByChunkId } from 'src/features/documents/viewer/readerOffsets'
import { useReaderGutters } from 'src/features/documents/viewer/useReaderGutters'
import type { CollectionChunk, TagSpan } from 'src/generated/api'

// Two consecutive chunks; the span starts in the first one.
const chunks = [
  { id: 'c1', order: 0, text: 'First chunk.' },
  { id: 'c2', order: 1, text: 'Second chunk.' }
] as CollectionChunk[]
const length = chunks[0].text.length
const span: TagSpan = { id: 's1', chunkId: 'c1', tagId: 't', start: 0, end: 5, type: 'auto', reason: 'A place.', confidence: 0.8 }

function setup () {
  const store = useTagSpansStore()
  store.spansByChunkId = { c1: [span] }
  const createSpan = vi.spyOn(store, 'createSpan').mockResolvedValue(undefined)
  const deleteSpan = vi.spyOn(store, 'deleteSpan').mockResolvedValue(undefined)
  const updateSpan = vi.spyOn(store, 'updateSpan').mockResolvedValue(undefined)
  const annotations = useAnnotations(() => chunks)
  annotations.editSpan(span)
  return { annotations, createSpan, deleteSpan, updateSpan }
}

/** Drag the edited span's start into the second chunk. */
function dragIntoSecondChunk (annotations: ReturnType<typeof useAnnotations>) {
  annotations.selection.value = { ...annotations.selection.value!, start: length + 1, end: length + 7 }
}

describe('moving a span to another chunk', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('moves it in one update that keeps its id, then closes the selection', async () => {
    const { annotations, createSpan, deleteSpan, updateSpan } = setup()
    dragIntoSecondChunk(annotations)

    await annotations.updateSpanPosition()

    expect(updateSpan).toHaveBeenCalledWith('s1', 'c1', { start: 1, end: 7, chunkId: 'c2' })
    expect(createSpan).not.toHaveBeenCalled()
    expect(deleteSpan).not.toHaveBeenCalled()
    expect(annotations.selection.value).toBeNull()
  })

  it('sends no chunk when the start stays in the span\'s chunk', async () => {
    const { annotations, updateSpan } = setup()
    annotations.adjustSelectionBoundary('end', 'c2', 3)

    await annotations.updateSpanPosition()

    expect(updateSpan).toHaveBeenCalledWith('s1', 'c1', { start: 0, end: length + 3 })
  })

  it('keeps the span and the selection when the move fails', async () => {
    const { annotations, updateSpan } = setup()
    updateSpan.mockRejectedValue(new Error('500'))
    dragIntoSecondChunk(annotations)

    await expect(annotations.updateSpanPosition()).rejects.toThrow('500')
    expect(annotations.selection.value).toMatchObject({ editingSpanId: 's1', spanChunkId: 'c1', chunkId: 'c2' })
    expect(annotations.saving.value).toBe(false)
  })
})

describe('retagging a span', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('addresses the chunk that holds the span after its start was dragged into another chunk', async () => {
    const { annotations, updateSpan } = setup()
    dragIntoSecondChunk(annotations)
    annotations.adjustSelectionBoundary('end', 'c2', 8)

    await annotations.updateSpanTag('t2')

    expect(updateSpan).toHaveBeenCalledWith('s1', 'c1', { tagId: 't2' })
  })
})

describe('span projection', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('keeps unaffected chunk arrays stable in a long document', () => {
    const longChunks = Array.from({ length: 2000 }, (_, order) => ({
      id: `c${order}`,
      order,
      text: 'abcd'
    })) as CollectionChunk[]

    const changedSpan: TagSpan = {
      id: 'changed',
      chunkId: 'c0',
      tagId: 't1',
      start: 0,
      end: 2,
      type: 'pos'
    }

    const untouchedSpan: TagSpan = {
      id: 'untouched',
      chunkId: 'c1999',
      tagId: 't1',
      start: 0,
      end: 2,
      type: 'pos'
    }

    const store = useTagSpansStore()

    store.spansByChunkId = {
      c0: [changedSpan],
      c1999: [untouchedSpan]
    }

    const annotations = useAnnotations(() => longChunks)

    const changedBefore = annotations.getProjectedSpans('c0')
    const untouchedBefore = annotations.getProjectedSpans('c1999')

    // Test the final reader-visible arrays, not just the annotation projection.
    const visibleBefore = memoizeVisibleSpansByChunkId(
      longChunks,
      (chunkId) => annotations.getProjectedSpans(chunkId),
      (span) => span.tagId === 't1',
      {}
    )

    // Simulate a store update of one span.
    store.spansByChunkId.c0 = [
      {
        ...changedSpan,
        tagId: 't2'
      }
    ]

    const changedAfter = annotations.getProjectedSpans('c0')
    const untouchedAfter = annotations.getProjectedSpans('c1999')

    const visibleAfter = memoizeVisibleSpansByChunkId(
      longChunks,
      (chunkId) => annotations.getProjectedSpans(chunkId),
      (span) => span.tagId === 't1',
      visibleBefore
    )

    expect(changedAfter).not.toBe(changedBefore)

    // Critical for #492: an unrelated ChunkAnnotator must receive the same
    // spans array instance and therefore does not need to rerender.
    expect(untouchedAfter).toBe(untouchedBefore)

    // Retagging c0 hides its span, so that reader array must change.
    expect(visibleBefore.c0).toHaveLength(1)
    expect(visibleAfter.c0).toHaveLength(0)
    expect(visibleAfter.c0).not.toBe(visibleBefore.c0)

    // All unaffected ChunkAnnotators must retain their original arrays.
    expect(visibleAfter.c1000).toBe(visibleBefore.c1000)
    expect(visibleAfter.c1999).toBe(visibleBefore.c1999)
  })

  it('preserves anchor entries for legacy spans with invalid offsets', () => {
    const chunks = [
      { id: 'c0', order: 0, text: 'abc' },
      { id: 'c1', order: 1, text: 'def' }
    ] as CollectionChunk[]

    const atBoundary: TagSpan = {
      id: 'boundary',
      chunkId: 'c0',
      tagId: 't1',
      start: 3,
      end: 5,
      type: 'pos'
    }

    const empty: TagSpan = {
      id: 'empty',
      chunkId: 'c0',
      tagId: 't1',
      start: 2,
      end: 2,
      type: 'pos'
    }

    const store = useTagSpansStore()
    store.spansByChunkId = {
      c0: [atBoundary, empty]
    }

    const annotations = useAnnotations(() => chunks)

    // Both legacy spans must remain accessible through their anchor chunk.
    expect(annotations.getProjectedSpans('c0')).toEqual([
      atBoundary,
      empty
    ])

    // Only the boundary span overlaps the following chunk.
    expect(annotations.getProjectedSpans('c1')).toEqual([
      { ...atBoundary, start: 0, end: 2 }
    ])
  })

  it('projects a sparse long document in linear work', () => {
    let textReads = 0

    const longChunks = Array.from({ length: 2000 }, (_, order) => ({
      id: `c${order}`,
      order,
      get text () {
        textReads++
        return 'abcd'
      }
    })) as CollectionChunk[]

    const store = useTagSpansStore()

    store.spansByChunkId = {
      c0: [{
        id: 'start',
        chunkId: 'c0',
        tagId: 't1',
        start: 0,
        end: 2,
        type: 'pos'
      }],
      c1999: [{
        id: 'end',
        chunkId: 'c1999',
        tagId: 't1',
        start: 0,
        end: 2,
        type: 'pos'
      }]
    }

    const annotations = useAnnotations(() => longChunks)

    expect(annotations.getProjectedSpans('c1999')).toHaveLength(1)

    // Prefix positions inspect the document once. Sparse span projection must
    // not turn that into an all-pairs traversal.
    expect(textReads).toBeLessThan(5000)
  })
})

describe('reader gutter layout', () => {
  const originalRaf = Object.getOwnPropertyDescriptor(
    globalThis, 'requestAnimationFrame'
  )

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('requestAnimationFrame', vi.fn())
  })

  afterEach(() => {
    document.body.innerHTML = ''

    // Restore the original global without relying on newer Vitest APIs.
    if (originalRaf) {
      Object.defineProperty(globalThis, 'requestAnimationFrame', originalRaf)
    } else {
      Reflect.deleteProperty(globalThis, 'requestAnimationFrame')
    }
  })

  it('reuses projected spans across hidden chunks and clears hidden gutter rows', async () => {
    const first = {
      id: 'c0', order: 0, text: 'abcd'
    } as CollectionChunk

    const hidden = {
      id: 'c1', order: 1, text: 'WXYZ'
    } as CollectionChunk

    const last = {
      id: 'c2', order: 2, text: 'efgh'
    } as CollectionChunk

    const displayed = ref([first, last])

    const store = useTagSpansStore()

    // The span starts in c0, crosses hidden c1 and ends in c2.
    store.spansByChunkId = {
      c0: [
        {
          id: 'cross',
          chunkId: 'c0',
          tagId: 't1',
          start: 2,
          end: 10,
          type: 'pos'
        },
        {
          id: 'declined',
          chunkId: 'c0',
          tagId: 't1',
          start: 0,
          end: 1,
          type: 'neg'
        }
      ]
    }

    const annotations = useAnnotations(
      () => displayed.value,
      () => [hidden]
    )

    document.body.innerHTML = `
      <div class="paper-card">
        <div class="document-text">
          <div data-chunk-id="c0">
            <span class="text-segment" data-start="0" data-end="2">ab</span>
            <span class="text-segment" data-start="2" data-end="4">cd</span>
          </div>
          <div data-chunk-id="c2">
            <span class="text-segment" data-start="0" data-end="2">ef</span>
            <span class="text-segment" data-start="2" data-end="4">gh</span>
          </div>
        </div>
      </div>
    `

    // jsdom has no actual layout, so provide known element positions.
    const setRect = (selector: string, top: number, height: number) => {
      const element = document.querySelector<HTMLElement>(selector)!

      vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({
        top,
        bottom: top + height,
        height
      } as DOMRect)
    }

    setRect('.paper-card', 100, 200)
    setRect('[data-chunk-id="c0"]', 108, 28)
    setRect('[data-chunk-id="c2"]', 178, 30)

    setRect('[data-chunk-id="c0"] [data-start="0"]', 110, 8)
    setRect('[data-chunk-id="c0"] [data-start="2"]', 120, 16)
    setRect('[data-chunk-id="c2"] [data-start="0"]', 180, 22)
    setRect('[data-chunk-id="c2"] [data-start="2"]', 204, 8)

    const textEl = ref<HTMLElement | null>(
      document.querySelector<HTMLElement>('.document-text')
    )

    const linkedSpanId = ref<string | null>(null)
    const showChunkRows = ref(true)

    const gutters = useReaderGutters(
      textEl,
      displayed,
      (chunkId) => annotations.getAllProjectedSpans(chunkId),
      (span) => span.type !== 'neg' || span.id === linkedSpanId.value,
      () => showChunkRows.value
    )

    gutters.relayout()

    // Cross-chunk span produces a single marker with original offsets.
    expect(gutters.spanMarkers.value).toHaveLength(1)

    expect(gutters.spanMarkers.value[0]).toMatchObject({
      spanId: 'cross',
      chunkId: 'c0',
      tagId: 't1',
      start: 2,
      end: 10,
      top: 20,
      height: 82
    })

    // Only displayed chunks have gutter rows.
    expect(gutters.chunkRows.value.map((row) => row.chunkId))
      .toEqual(['c0', 'c2'])

    // A declined span is shown when directly linked.
    linkedSpanId.value = 'declined'
    gutters.relayout()

    expect(gutters.spanMarkers.value.map((marker) => marker.spanId))
      .toContain('declined')

    expect(gutters.spanMarkers.value).toHaveLength(2)

    // Hiding the chunk gutter must clear previously measured rows.
    showChunkRows.value = false
    gutters.relayoutChunkRows()

    expect(gutters.chunkRows.value).toEqual([])

    await nextTick()
  })
})
