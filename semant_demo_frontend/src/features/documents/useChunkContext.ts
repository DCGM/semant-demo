import { computed, getCurrentScope, onScopeDispose, ref, shallowRef } from 'vue'
import type { Document, DocumentChunkWindow, TextChunk } from 'src/generated/api'
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
  loaded: readonly TextChunk[],
  incoming: readonly TextChunk[],
  direction: ContextDirection,
  max = MAX_CONTEXT_CHUNKS
): { chunks: TextChunk[], trimmed: boolean } {
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
 * A bounded, navigable passage of a document around one chunk (a search hit now, a RAG
 * source later). `open()` starts a new context: earlier requests are aborted and their
 * late answers dropped, so the view never shows another target's text. The passage can
 * be extended in both directions; at most {@link MAX_CONTEXT_CHUNKS} chunks are kept.
 */
export function useChunkContext () {
  const api = useApi().default
  const target = shallowRef<ChunkContextTarget | null>(null)
  const document = shallowRef<Document | null>(null)
  const chunks = shallowRef<TextChunk[]>([])
  const hasBefore = ref(false)
  const hasAfter = ref(false)
  const totalChunks = ref<number | null>(null)
  const loading = ref(false)
  const extending = ref<ContextDirection | null>(null)
  const error = ref<string | null>(null)
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

  async function read (anchorId: string, before: number, after: number,
    signal: AbortSignal): Promise<DocumentChunkWindow> {
    const documentId = target.value?.documentId as string
    return api.readDocumentChunkWindowApiDocumentsDocumentIdChunksChunkIdWindowGet(
      { documentId, chunkId: anchorId, before, after }, { signal })
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
      const window = await read(current.chunkId, CONTEXT_SIDE, CONTEXT_SIDE, controller.signal)
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

  /** Reads up to {@link CONTEXT_STEP} more chunks before or after the shown passage. */
  async function extend (direction: ContextDirection) {
    if (!target.value || loading.value || extending.value || !chunks.value.length) return
    if (direction === 'before' ? !hasBefore.value : !hasAfter.value) return
    const edge = direction === 'before' ? chunks.value[0] : chunks.value[chunks.value.length - 1]
    const isCurrent = guard.capture()
    const controller = new AbortController()
    abort = controller
    extending.value = direction
    error.value = null
    try {
      const window = await read(edge.id, direction === 'before' ? CONTEXT_STEP : 0,
        direction === 'after' ? CONTEXT_STEP : 0, controller.signal)
      if (!isCurrent()) return
      const { chunks: merged, trimmed } = mergeChunks(chunks.value, window.chunks, direction)
      chunks.value = merged
      if (direction === 'before') {
        hasBefore.value = window.hasBefore
        if (trimmed) hasAfter.value = true
      } else {
        hasAfter.value = window.hasAfter
        if (trimmed) hasBefore.value = true
      }
      totalChunks.value = window.totalChunks
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
    containsTarget,
    open,
    load,
    extend,
    clear
  }
}
