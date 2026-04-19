import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { TagSpan, TagSpans, TagSpanUpdate } from 'src/models/tagSpans'
import { SpanType } from 'src/generated/api'
import { useTagSpansRepository } from 'src/repositories/useTagSpansRepository'

export const useTagSpansStore = defineStore('tagSpans', () => {
  const repo = useTagSpansRepository()

  /** All spans keyed by chunkId */
  const spansByChunkId = ref<Record<string, TagSpans>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchSpansForChunk = async (chunkId: string) => {
    try {
      const spans = await repo.getByChunkId(chunkId)
      spansByChunkId.value = {
        ...spansByChunkId.value,
        [chunkId]: spans
      }
    } catch (err) {
      console.error('Failed to fetch spans for chunk', chunkId, err)
      error.value = 'Failed to fetch spans'
    }
  }

  const fetchSpansForChunks = async (chunkIds: string[]) => {
    loading.value = true
    error.value = null
    try {
      const result = await repo.getByChunkIds(chunkIds)
      spansByChunkId.value = { ...spansByChunkId.value, ...result }
    } catch (err) {
      console.error('Failed to fetch spans', err)
      error.value = 'Failed to fetch spans'
    } finally {
      loading.value = false
    }
  }

  const createSpan = async (span: TagSpan) => {
    try {
      await repo.create(span)
      await fetchSpansForChunk(span.chunkId)
    } catch (err) {
      console.error('Failed to create span', err)
      error.value = 'Failed to create span'
      throw err
    }
  }

  const updateSpan = async (spanId: string, chunkId: string, update: TagSpanUpdate) => {
    try {
      await repo.update(spanId, update)
      await fetchSpansForChunk(chunkId)
    } catch (err) {
      console.error('Failed to update span', err)
      error.value = 'Failed to update span'
      throw err
    }
  }

  const deleteSpan = async (spanId: string, chunkId: string) => {
    try {
      await repo.delete(spanId)
      await fetchSpansForChunk(chunkId)
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
    fetchSpansForChunk,
    fetchSpansForChunks,
    createSpan,
    updateSpan,
    deleteSpan,
    clearAll
  }
})
