import { computed } from 'vue'

import { useTagSpansStore } from 'src/stores/tagSpansStore'
import type { PostSpan, PatchSpan, TagSpan } from 'src/models/tagSpans'

const useTagSpans = () => {
  const store = useTagSpansStore()

  const loadSpansForChunkInCollection = (chunkId: string, collectionId: string) =>
    store.fetchSpansForChunkInCollection(chunkId, collectionId)
  const loadSpansForChunksInCollection = (chunkIds: string[], collectionId: string) =>
    store.fetchSpansForChunksInCollection(chunkIds, collectionId)
  const createSpan = (span: PostSpan) => store.createSpan(span)
  const updateSpan = (spanId: string, chunkId: string, update: PatchSpan) =>
    store.updateSpan(spanId, chunkId, update)
  const bulkUpdateSpans = (spanIds: string[], update: PatchSpan) =>
    store.bulkUpdateSpans(spanIds, update)
  const deleteSpan = (spanId: string, chunkId: string) => store.deleteSpan(spanId, chunkId)
  const removeSpansLocally = (predicate: (span: TagSpan, chunkId: string) => boolean) =>
    store.removeSpansLocally(predicate)
  const clearAll = () => store.clearAll()

  const spansByChunkId = computed(() => store.spansByChunkId)
  const loading = computed(() => store.loading)
  const error = computed(() => store.error)

  const findSpanById = (spanId: string): { chunkId: string; span: TagSpan } | null => {
    const byChunk = store.spansByChunkId
    for (const chunkId of Object.keys(byChunk)) {
      const span = (byChunk[chunkId] || []).find((s) => s.id === spanId)
      if (span) return { chunkId, span }
    }
    return null
  }

  return {
    spansByChunkId,
    loading,
    error,
    loadSpansForChunkInCollection,
    loadSpansForChunksInCollection,
    createSpan,
    updateSpan,
    bulkUpdateSpans,
    deleteSpan,
    removeSpansLocally,
    clearAll,
    findSpanById
  }
}

export default useTagSpans
