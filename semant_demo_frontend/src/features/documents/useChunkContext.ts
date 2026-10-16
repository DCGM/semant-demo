import { computed, getCurrentScope, onScopeDispose, ref, shallowRef } from 'vue'
import type { Document, DocumentChunk } from 'src/generated/api'
import { createContextGuard, errorStatus, isAbortError, useApi } from 'src/shared/api'

/** The chunk a context view is about; documents and chunks are public corpus data. */
export interface ChunkContextTarget {
  documentId: string
  chunkId: string
}

/** Chunks read on each side of the target when it is opened. */
export const CONTEXT_SIDE = 3
/** Chunks added by one "earlier"/"later" step. */
export const CONTEXT_STEP = 5
/** Most chunks kept at once; extending past it drops chunks from the other end. */
export const MAX_CONTEXT_CHUNKS = 60

export type ContextDirection = 'before' | 'after'

/**
 * Adds the newly read `incoming` chunks (in document order) on the `direction` side of
 * `loaded`, skipping ones already there, and keeps at most `max` chunks by dropping from
 * the other end. Reports whether that end was trimmed.
 */
export function mergeChunks (
  loaded: readonly DocumentChunk[],
  incoming: readonly DocumentChunk[],
  direction: ContextDirection,
  max = MAX_CONTEXT_CHUNKS
): { chunks: DocumentChunk[], trimmed: boolean } {
  const known = new Set(loaded.map(c => c.id))
  const added = incoming.filter(c => !known.has(c.id))
  const merged = direction === 'before' ? [...added, ...loaded] : [...loaded, ...added]
  if (merged.length <= max) return { chunks: merged, trimmed: false }
  return {
    chunks: direction === 'before' ? merged.slice(0, max) : merged.slice(merged.length - max),
    trimmed: true
  }
}

/**
 * A bounded, navigable passage of a document around one chunk (a search hit or a chat
 * assistant's source). `open()` starts a new context: earlier requests are aborted and their
 * late answers dropped, so the view never shows another target's text. The passage can
 * be extended in both directions (reading only the neighbouring chunks, not the document
 * again); at most {@link MAX_CONTEXT_CHUNKS} chunks are kept. Every `open()`, also of the
 * same target, increases `focusRequest`, so a view brings the target into view again.
 */
export function useChunkContext () {
  const api = useApi().default
  const target = shallowRef<ChunkContextTarget | null>(null)
  const document = shallowRef<Document | null>(null)
  const chunks = shallowRef<DocumentChunk[]>([])
  const hasBefore = ref(false)
  const hasAfter = ref(false)
  const totalChunks = ref<number | null>(null)
  const loading = ref(false)
  const extending = ref<ContextDirection | null>(null)
  const error = ref<string | null>(null)
  const focusRequest = ref(0)
  const guard = createContextGuard()
  let abort: AbortController | null = null

  /** Whether the target chunk is among the loaded ones (it can be dropped by extending). */
  const containsTarget = computed(() => !!target.value && chunks.value.some(c => c.id === target.value?.chunkId))

  function stop () {
    abort?.abort()
    abort = null
    guard.enter()
    loading.value = false
    extending.value = null
  }

  /** Forgets the target and everything loaded for it. */
  function clear () {
    stop()
    target.value = null
    document.value = null
    chunks.value = []
    hasBefore.value = false
    hasAfter.value = false
    totalChunks.value = null
    error.value = null
  }

  function failure (e: unknown): string {
    const status = errorStatus(e)
    if (status === 404) return 'This passage or its document is no longer available.'
    console.error('Loading the document context failed', e)
    return 'Failed to load the document context.'
  }

  /** Shows the passage around `next`, replacing whatever was shown. */
  async function open (next: ChunkContextTarget) {
    clear()
    target.value = next
    focusRequest.value++
    await load()
  }

  /** Reloads the passage around the current target (retry, or back to a dropped target). */
  async function load () {
    const current = target.value
    if (!current) return
    stop()
    error.value = null
    const isCurrent = guard.capture()
    const controller = new AbortController()
    abort = controller
    loading.value = true
    try {
      const window = await api.readDocumentChunkWindowApiDocumentsDocumentIdChunksChunkIdWindowGet(
        { documentId: current.documentId, chunkId: current.chunkId, before: CONTEXT_SIDE, after: CONTEXT_SIDE },
        { signal: controller.signal })
      if (!isCurrent()) return
      document.value = window.document
      chunks.value = window.chunks
      hasBefore.value = window.hasBefore
      hasAfter.value = window.hasAfter
      totalChunks.value = window.totalChunks
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return
      document.value = null
      chunks.value = []
      error.value = failure(e)
    } finally {
      if (isCurrent()) {
        loading.value = false
        abort = null
      }
    }
  }

  /**
   * Brings the target into view again (after the user scrolled the passage): reloads the
   * passage around it when extending has dropped it, otherwise only scrolls to it.
   */
  async function focus () {
    if (!target.value) return
    focusRequest.value++
    if (!containsTarget.value && !loading.value) await load()
  }

  /**
   * Reads up to {@link CONTEXT_STEP} more chunks before or after the shown passage: only
   * the neighbours of its edge chunk, not the document metadata or chunk count again.
   */
  async function extend (direction: ContextDirection) {
    if (!target.value || loading.value || extending.value || !chunks.value.length) return
    if (direction === 'before' ? !hasBefore.value : !hasAfter.value) return
    const documentId = target.value.documentId
    const edge = direction === 'before' ? chunks.value[0] : chunks.value[chunks.value.length - 1]
    const isCurrent = guard.capture()
    const controller = new AbortController()
    abort = controller
    extending.value = direction
    error.value = null
    try {
      const adjacent = await api.readDocumentAdjacentChunksApiDocumentsDocumentIdChunksChunkIdAdjacentGet(
        { documentId, chunkId: edge.id, direction, limit: CONTEXT_STEP }, { signal: controller.signal })
      if (!isCurrent()) return
      const { chunks: merged, trimmed } = mergeChunks(chunks.value, adjacent.chunks, direction)
      chunks.value = merged
      if (direction === 'before') {
        hasBefore.value = adjacent.hasMore
        if (trimmed) hasAfter.value = true
      } else {
        hasAfter.value = adjacent.hasMore
        if (trimmed) hasBefore.value = true
      }
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return
      // The shown passage stays; only the extension failed.
      error.value = failure(e)
    } finally {
      if (isCurrent()) {
        extending.value = null
        abort = null
      }
    }
  }

  if (getCurrentScope()) onScopeDispose(stop)

  return {
    target,
    document,
    chunks,
    hasBefore,
    hasAfter,
    totalChunks,
    loading,
    extending,
    error,
    focusRequest,
    containsTarget,
    open,
    load,
    focus,
    extend,
    clear
  }
}
