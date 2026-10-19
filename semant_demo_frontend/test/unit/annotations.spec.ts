import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useTagSpansStore } from 'src/features/annotations/tagSpansStore'
import { SpanMoveLostError, useAnnotations } from 'src/features/annotations/useAnnotations'
import type { CollectionChunk } from 'src/generated/api'

// Two consecutive chunks; the span starts in the first one.
const chunks = [
  { id: 'c1', order: 0, text: 'First chunk.' },
  { id: 'c2', order: 1, text: 'Second chunk.' }
] as CollectionChunk[]
const span = { id: 's1', chunkId: 'c1', tagId: 't', start: 0, end: 5, type: 'pos' as const }

describe('saving a span position', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('reports a span moved to another chunk as lost when it is removed but not saved again', async () => {
    const store = useTagSpansStore()
    store.spansByChunkId = { c1: [span] }
    const deleteSpan = vi.spyOn(store, 'deleteSpan').mockResolvedValue(undefined)
    vi.spyOn(store, 'createSpan').mockRejectedValue(new Error('500'))
    const annotations = useAnnotations(() => chunks)

    annotations.editSpan(span)
    // Drag the span into the second chunk.
    const length = chunks[0].text.length
    annotations.selection.value = { ...annotations.selection.value!, start: length + 1, end: length + 7 }

    await expect(annotations.updateSpanPosition()).rejects.toBeInstanceOf(SpanMoveLostError)
    expect(deleteSpan).toHaveBeenCalledWith('s1', 'c1')
    // The selection edited the deleted span, so it is closed rather than left to retry.
    expect(annotations.selection.value).toBeNull()
    expect(annotations.saving.value).toBe(false)
  })
})
