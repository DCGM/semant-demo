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

  return {
    spansByChunkId,
    loading,
    error,
    fetchSpansForChunkInCollection,
    fetchSpansForChunksInCollection,
    createSpan,
    updateSpan,
    deleteSpan,
    clearAll
  }
})
