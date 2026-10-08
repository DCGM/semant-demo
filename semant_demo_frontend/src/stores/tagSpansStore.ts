import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { PostSpan, TagSpans, PatchSpan } from 'src/models/tagSpans'
import { useTagSpansRepository } from 'src/repositories/useTagSpansRepository'
import { requireComplete, searchTagWarning, spanOf } from 'src/utils/writeOutcome'
import { warningNotification } from 'src/utils/notification'
import { createScope } from 'src/shared/api'

/**
 * Spans of the document view, keyed by chunk id. They belong to one collection (a chunk
 * can be in several collections, each with its own annotations): loading spans for
 * another collection, or `clearAll()` (document change, logout), starts a new scope.
 * Responses and write results of the old scope do not change the new one; the writes
 * themselves are kept by the backend.
 */
export const useTagSpansStore = defineStore('tagSpans', () => {
  const repo = useTagSpansRepository()
  const scope = createScope()

  /** All spans keyed by chunkId */
  const spansByChunkId = ref<Record<string, TagSpans>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)
  /**
   * Bumped on every span mutation (create/update/bulkUpdate/delete). The
   * chunk-keyed mutations below don't change `spansByChunkId`'s top-level
   * identity, so a non-deep watcher can't see them directly — this counter
   * gives callers a lightweight, non-deep-watchable signal instead.
   */
  const spansVersion = ref(0)

  /** Switches to `collectionId`, dropping the spans of another collection. */
  const enterCollection = (collectionId: string) => {
    if (scope.enter(collectionId)) {
      spansByChunkId.value = {}
      error.value = null
      loading.value = false
    }
    return scope.capture()
  }

  const fetchSpansForChunkInCollection = async (chunkId: string, collectionId: string) => {
    const isCurrent = enterCollection(collectionId)
    try {
      const spans = await repo.getByChunkIdInCollection(chunkId, collectionId)
      if (!isCurrent()) return
      spansByChunkId.value = {
        ...spansByChunkId.value,
        [chunkId]: spans
      }
    } catch (err) {
      if (!isCurrent()) return
      console.error('Failed to fetch spans for chunk', chunkId, err)
      error.value = 'Failed to fetch spans'
    }
  }

  const fetchSpansForChunksInCollection = async (chunkIds: string[], collectionId: string) => {
    const isCurrent = enterCollection(collectionId)
    loading.value = true
    error.value = null
    try {
      const result = await repo.getByChunkIdsInCollection(chunkIds, collectionId)
      if (!isCurrent()) return
      spansByChunkId.value = { ...spansByChunkId.value, ...result }
    } catch (err) {
      if (!isCurrent()) return
      console.error('Failed to fetch spans', err)
      error.value = 'Failed to fetch spans'
    } finally {
      if (isCurrent()) loading.value = false
    }
  }

  /** Show a warning when a span write was kept but its search tag update failed. */
  const warnIfSearchTagFailed = (warning: string | null) => {
    if (warning) warningNotification(warning)
  }

  const createSpan = async (span: PostSpan) => {
    const isCurrent = scope.capture()
    try {
      const result = await repo.create(span)
      warnIfSearchTagFailed(searchTagWarning(result, 'saved'))
      if (!isCurrent()) return
      spansByChunkId.value[span.chunkId] = [...(spansByChunkId.value[span.chunkId] || []), spanOf(result)]
      spansVersion.value++
    } catch (err) {
      if (!isCurrent()) throw err
      console.error('Failed to create span', err)
      error.value = 'Failed to create span'
      throw err
    }
  }

  const updateSpan = async (spanId: string, chunkId: string, update: PatchSpan) => {
    const isCurrent = scope.capture()
    try {
      const result = await repo.update(spanId, update)
      warnIfSearchTagFailed(searchTagWarning(result, 'saved'))
      if (!isCurrent()) return
      const updatedSpan = spanOf(result)
      spansByChunkId.value[chunkId] = (spansByChunkId.value[chunkId] ?? []).map((s) => (s.id === spanId ? updatedSpan : s))
      spansVersion.value++
    } catch (err) {
      if (!isCurrent()) throw err
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
    const isCurrent = scope.capture()
    try {
      const result = await repo.bulkUpdate(spanIds, update)
      if (!isCurrent()) {
        requireComplete(result, 'Updating the selected suggestions')
        return
      }
      // Apply the spans that were updated, then report any that were not.
      const byId = new Map(result.spans.map((s) => [s.id, s] as const))

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
      spansVersion.value++
      requireComplete(result, 'Updating the selected suggestions')
    } catch (err) {
      if (!isCurrent()) throw err
      console.error('Failed to bulk-update spans', err)
      error.value = 'Failed to bulk-update spans'
      throw err
    }
  }

  const deleteSpan = async (spanId: string, chunkId: string) => {
    const isCurrent = scope.capture()
    try {
      const result = await repo.delete(spanId)
      warnIfSearchTagFailed(searchTagWarning(result, 'deleted'))
      if (!isCurrent()) return
      spansByChunkId.value[chunkId] = (spansByChunkId.value[chunkId] ?? []).filter((s) => s.id !== spanId)
      spansVersion.value++
    } catch (err) {
      if (!isCurrent()) throw err
      console.error('Failed to delete span', err)
      error.value = 'Failed to delete span'
      throw err
    }
  }

  /** Drops all spans and starts a new scope (document change, logout). */
  const clearAll = () => {
    scope.reset()
    spansByChunkId.value = {}
    error.value = null
    loading.value = false
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
    spansVersion.value++
  }

  return {
    spansByChunkId,
    spansVersion,
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
