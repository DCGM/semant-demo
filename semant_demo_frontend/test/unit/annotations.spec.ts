import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useTagSpansStore } from 'src/features/annotations/tagSpansStore'
import { useAnnotations } from 'src/features/annotations/useAnnotations'
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

    // Simulate a store update of one span.
    store.spansByChunkId.c0 = [
      {
        ...changedSpan,
        tagId: 't2'
      }
    ]

    const changedAfter = annotations.getProjectedSpans('c0')
    const untouchedAfter = annotations.getProjectedSpans('c1999')

    expect(changedAfter).not.toBe(changedBefore)

    // Critical for #492: an unrelated ChunkAnnotator must receive the same
    // spans array instance and therefore does not need to rerender.
    expect(untouchedAfter).toBe(untouchedBefore)
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
