import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { PostSpan, TagSpan, PatchSpan } from 'src/generated/api'
import { useTagSpansRepository } from './useTagSpansRepository'
import { requireComplete, spanWriteWarning, spanOf } from 'src/shared/writeOutcome'
import { warningNotification } from 'src/shared/notification'
import { ApiError, createScope, errorStatus } from 'src/shared/api'

/** The span a 409 answer carries: the span as someone else saved it meanwhile (#460). */
async function currentOfConflict (err: unknown): Promise<TagSpan | null> {
  if (errorStatus(err) !== 409) return null
  const response = (err as { response?: Response } | null)?.response
  try {
    const body = await response?.clone().json() as { current?: TagSpan } | undefined
    return body?.current ?? null
  } catch {
    return null
  }
}

const CHANGED = 'Someone else changed this annotation meanwhile; nothing was saved. The view now shows its current version.'
const DELETED = 'Someone else deleted this annotation meanwhile; it was removed from the view.'

/**
 * Spans of the document view, keyed by chunk id. They belong to one collection (a chunk
 * can be in several collections, each with its own annotations): loading spans for
 * another collection, or `clearAll()` (document change, logout), starts a new scope.
 * Responses and write results of the old scope do not change the new one; the writes
 * themselves are kept by the backend. Span updates and deletions name the scope's
 * collection, since the backend finds a span only within its own collection.
 *
 * Updates and deletions send the span's `editVersion` as loaded (#460): when someone else
 * changed the span meanwhile, nothing is saved, the span is replaced by its current version
 * (or removed, when it was deleted) and the write fails with a message saying so.
 */
export const useTagSpansStore = defineStore('tagSpans', () => {
  const repo = useTagSpansRepository()
  const scope = createScope()

  /** All spans keyed by chunkId */
  const spansByChunkId = ref<Record<string, TagSpan[]>>({})
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

  /** The collection of the loaded spans, which span updates and deletions address. */
  const currentCollection = (): string => {
    const collectionId = scope.key
    if (!collectionId) throw new Error('No collection is loaded for the spans')
    return collectionId
  }

  /** Show a warning when a span write was kept but its search tag update failed. */
  const warnIfIncomplete = (warning: string | null) => {
    if (warning) warningNotification(warning)
  }

  const createSpan = async (span: PostSpan) => {
    const isCurrent = scope.capture()
    try {
      const result = await repo.create(span)
      warnIfIncomplete(spanWriteWarning(result, 'saved'))
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

  const findSpan = (spanId: string, chunkId: string) =>
    spansByChunkId.value[chunkId]?.find((s) => s.id === spanId)

  /** After a refused write: shows the span as it is now, and the error to report. */
  const reconcileRefused = async (err: unknown, spanId: string, chunkId: string): Promise<unknown> => {
    const current = await currentOfConflict(err)
    if (current) {
      spansByChunkId.value[chunkId] = (spansByChunkId.value[chunkId] ?? []).map((s) => (s.id === spanId ? current : s))
      spansVersion.value++
      return new ApiError(409, CHANGED)
    }
    if (errorStatus(err) === 404 && findSpan(spanId, chunkId)) {
      spansByChunkId.value[chunkId] = (spansByChunkId.value[chunkId] ?? []).filter((s) => s.id !== spanId)
      spansVersion.value++
      return new ApiError(404, DELETED)
    }
    return err
  }

  const updateSpan = async (spanId: string, chunkId: string, update: PatchSpan) => {
    const isCurrent = scope.capture()
    try {
      const result = await repo.update(spanId, currentCollection(), update, findSpan(spanId, chunkId)?.editVersion)
      warnIfIncomplete(spanWriteWarning(result, 'saved'))
      if (!isCurrent()) return
      const updatedSpan = spanOf(result)
      spansByChunkId.value[chunkId] = (spansByChunkId.value[chunkId] ?? []).map((s) => (s.id === spanId ? updatedSpan : s))
      spansVersion.value++
    } catch (err) {
      if (!isCurrent()) throw err
      console.error('Failed to update span', err)
      error.value = 'Failed to update span'
      throw await reconcileRefused(err, spanId, chunkId)
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
      const known = new Map(Object.values(spansByChunkId.value).flat().map((s) => [s.id, s.editVersion] as const))
      const expected = Object.fromEntries(spanIds.flatMap((id) => {
        const version = known.get(id)
        return version === undefined ? [] : [[id, version]]
      }))
      const result = await repo.bulkUpdate(spanIds, currentCollection(), update, expected)
      if (!isCurrent()) {
        requireComplete(result, 'Updating the selected suggestions')
        return
      }
      // Apply the spans that were updated and the current state of those changed by
      // someone else meanwhile, then report any that were not updated.
      const byId = new Map([...(result.conflicts ?? []), ...result.spans].map((s) => [s.id, s] as const))

      const next: Record<string, TagSpan[]> = { ...spansByChunkId.value }
      for (const chunkId of Object.keys(next)) {
        const list = next[chunkId]
        if (!list) continue
        let copy: TagSpan[] | null = null
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
      const changed = result.conflicts?.length ?? 0
      if (changed && changed === (result.failed ?? []).length) {
        throw new Error(`${changed} of the selected suggestions ${changed === 1 ? 'was' : 'were'} changed by someone else meanwhile and ${changed === 1 ? 'was' : 'were'} not updated; the view now shows ${changed === 1 ? 'it' : 'them'} as ${changed === 1 ? 'it is' : 'they are'}.`)
      }
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
      const result = await repo.delete(spanId, currentCollection(), findSpan(spanId, chunkId)?.editVersion)
      warnIfIncomplete(spanWriteWarning(result, 'deleted'))
      if (!isCurrent()) return
      spansByChunkId.value[chunkId] = (spansByChunkId.value[chunkId] ?? []).filter((s) => s.id !== spanId)
      spansVersion.value++
    } catch (err) {
      if (!isCurrent()) throw err
      console.error('Failed to delete span', err)
      error.value = 'Failed to delete span'
      throw await reconcileRefused(err, spanId, chunkId)
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
  const removeSpansLocally = (predicate: (span: TagSpan, chunkId: string) => boolean) => {
    const next: Record<string, TagSpan[]> = {}
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
