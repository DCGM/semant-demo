import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { PostSpan, TagSpans, PatchSpan } from 'src/models/tagSpans'
import { useTagSpansRepository } from 'src/repositories/useTagSpansRepository'

export const useTagSpansStore = defineStore('tagSpans', () => {
  const repo = useTagSpansRepository()

  /** All spans keyed by chunkId */
  const spansByChunkId = ref<Record<string, TagSpans>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchSpansForChunkInCollection = async (chunkId: string, collectionId: string) => {
    try {
      const spans = await repo.getByChunkIdInCollection(chunkId, collectionId)
      spansByChunkId.value = {
        ...spansByChunkId.value,
        [chunkId]: spans
      }
    } catch (err) {
      console.error('Failed to fetch spans for chunk', chunkId, err)
      error.value = 'Failed to fetch spans'
    }
  }

  const fetchSpansForChunksInCollection = async (chunkIds: string[], collectionId: string) => {
    loading.value = true
    error.value = null
    try {
      const result = await repo.getByChunkIdsInCollection(chunkIds, collectionId)
      spansByChunkId.value = { ...spansByChunkId.value, ...result }
    } catch (err) {
      console.error('Failed to fetch spans', err)
      error.value = 'Failed to fetch spans'
    } finally {
      loading.value = false
    }
  }

  const createSpan = async (span: PostSpan) => {
    try {
      const newSpan = await repo.create(span)
      spansByChunkId.value[span.chunkId] = [...(spansByChunkId.value[span.chunkId] || []), newSpan]
    } catch (err) {
      console.error('Failed to create span', err)
      error.value = 'Failed to create span'
      throw err
    }
  }

  const updateSpan = async (spanId: string, chunkId: string, update: PatchSpan) => {
    try {
      const updatedSpan = await repo.update(spanId, update)
      spansByChunkId.value[chunkId] = spansByChunkId.value[chunkId].map((s) => (s.id === spanId ? updatedSpan : s))
    } catch (err) {
      console.error('Failed to update span', err)
      error.value = 'Failed to update span'
      throw err
    }
  }

  /**
   * Apply the same patch to many spans in one round-trip and commit the
   * results with a SINGLE reactive write to `spansByChunkId`.
   *
   * The previous approach (`Promise.all(updateSpan(...))`) caused N
   * independent reactive mutations, each triggering recomputes of derived
   * `pendingAutoSpans` / `autoSpansByTag` and a document re-render. For
   * large bulk approve/reject actions that stalled the main thread.
   */
  const bulkUpdateSpans = async (spanIds: string[], update: PatchSpan) => {
    if (spanIds.length === 0) return
    try {
      const updated = await repo.bulkUpdate(spanIds, update)
      const byId = new Map(updated.map((s) => [s.id, s] as const))

      const next: Record<string, TagSpans> = { ...spansByChunkId.value }
      for (const chunkId of Object.keys(next)) {
        const list = next[chunkId]
        if (!list) continue
        let copy: TagSpans | null = null
        for (let i = 0; i < list.length; i++) {
          const id = list[i]?.id
          if (!id) continue
          const replacement = byId.get(id)
          if (!replacement) continue
          if (!copy) copy = list.slice()
          copy[i] = replacement
        }
        if (copy) next[chunkId] = copy
      }

      spansByChunkId.value = next
    } catch (err) {
      console.error('Failed to bulk-update spans', err)
      error.value = 'Failed to bulk-update spans'
      throw err
    }
  }

  const deleteSpan = async (spanId: string, chunkId: string) => {
    try {
      await repo.delete(spanId)
      spansByChunkId.value[chunkId] = spansByChunkId.value[chunkId].filter((s) => s.id !== spanId)
    } catch (err) {
      console.error('Failed to delete span', err)
      error.value = 'Failed to delete span'
      throw err
    }
  }

  const clearAll = () => {
    spansByChunkId.value = {}
    error.value = null
  }

  /**
   * Drop spans from the in-memory cache without hitting the API.
   * Useful when the backend has already deleted spans in bulk and we only
   * need to mirror the change locally.
   */
  const removeSpansLocally = (predicate: (span: TagSpans[number], chunkId: string) => boolean) => {
    const next: Record<string, TagSpans> = {}
    for (const chunkId of Object.keys(spansByChunkId.value)) {
      const list = spansByChunkId.value[chunkId] || []
      next[chunkId] = list.filter((s) => !predicate(s, chunkId))
    }
    spansByChunkId.value = next
  }

  return {
    spansByChunkId,
    loading,
    error,
    fetchSpansForChunkInCollection,
    fetchSpansForChunksInCollection,
    createSpan,
    updateSpan,
    bulkUpdateSpans,
    deleteSpan,
    removeSpansLocally,
    clearAll
  }
})
