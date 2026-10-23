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
