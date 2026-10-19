import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useTagSpansStore } from 'src/features/annotations/tagSpansStore'
import { SpanMoveIncompleteError, useAnnotations } from 'src/features/annotations/useAnnotations'
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

  it('saves it in the new chunk with its type, reason and confidence, then removes the old one', async () => {
    const { annotations, createSpan, deleteSpan } = setup()
    dragIntoSecondChunk(annotations)

    await annotations.updateSpanPosition()

    expect(createSpan).toHaveBeenCalledWith({
      chunkId: 'c2', tagId: 't', start: 1, end: 7, type: 'auto', reason: 'A place.', confidence: 0.8
    })
    expect(deleteSpan).toHaveBeenCalledWith('s1', 'c1')
    expect(createSpan.mock.invocationCallOrder[0]).toBeLessThan(deleteSpan.mock.invocationCallOrder[0])
    expect(annotations.selection.value).toBeNull()
  })

  it('keeps the old span and the selection when saving in the new chunk fails', async () => {
    const { annotations, createSpan, deleteSpan } = setup()
    createSpan.mockRejectedValue(new Error('500'))
    dragIntoSecondChunk(annotations)

    await expect(annotations.updateSpanPosition()).rejects.toThrow('500')
    expect(deleteSpan).not.toHaveBeenCalled()
    expect(annotations.selection.value?.editingSpanId).toBe('s1')
    expect(annotations.saving.value).toBe(false)
  })

  it('reports a span left at both positions when removing the old one fails', async () => {
    const { annotations, deleteSpan } = setup()
    deleteSpan.mockRejectedValue(new Error('500'))
    dragIntoSecondChunk(annotations)

    await expect(annotations.updateSpanPosition()).rejects.toBeInstanceOf(SpanMoveIncompleteError)
    // The selection edited the old span, which no longer matches the saved position.
    expect(annotations.selection.value).toBeNull()
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
