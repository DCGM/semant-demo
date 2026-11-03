import { ref, shallowRef } from 'vue'
import type { DocumentChunk } from 'src/generated/api'
import { apiErrorMessage, isAbortError, useApi } from 'src/shared/api'

// The chunks of a public document that the paired text/scan view shows (#544): a bounded,
// growing set read around what the reader opens (a chunk, a page) and extended on request,
// never the whole document. Reads are public corpus data (#541, docs/PAGE_LAYOUT.md); none
// depends on a collection. Gaps between the chunks read are left for the owner to show.

/** A chunk with its place in the document (chunks without an `order` are not shown). */
export type PositionedChunk = DocumentChunk & { order: number }

const WINDOW_BEFORE = 2
const WINDOW_AFTER = 4
const EXTEND = 5
/** Pages tried from the start for the first text of a document opened without a target. */
const START_PAGES = 8

const positioned = (chunks: DocumentChunk[]): PositionedChunk[] =>
  chunks.filter((c): c is PositionedChunk => typeof c.order === 'number')

export function useDocumentText (documentId: () => string) {
  const api = useApi().default
  const chunks = shallowRef<PositionedChunk[]>([])
  /** More chunks follow the last one read (unknown counts as yes). */
  const hasAfter = ref(true)
  const loading = ref(false)
  const error = ref<string | null>(null)
  /** Incremented when the document changes: an older read is not merged. */
  let generation = 0
  const pageReads = new Map<number, Promise<PositionedChunk[]>>()

  function reset () {
    generation++
    chunks.value = []
    hasAfter.value = true
    error.value = null
    pageReads.clear()
  }

  /** Adds chunks (by id) and keeps them in document order. */
  function merge (more: PositionedChunk[]) {
    if (!more.length) return
    const byId = new Map(chunks.value.map(c => [c.id, c]))
    for (const c of more) byId.set(c.id, c)
    chunks.value = [...byId.values()].sort((a, b) => a.order - b.order)
  }

  async function read<T> (work: () => Promise<T>, fallback: string): Promise<T | null> {
    const mine = generation
    loading.value = true
    error.value = null
    try {
      const result = await work()
      return mine === generation ? result : null
    } catch (e) {
      if (mine === generation && !isAbortError(e)) error.value = await apiErrorMessage(e, fallback)
      return null
    } finally {
      if (mine === generation) loading.value = false
    }
  }

  /** Reads a chunk and a few around it; the chunk, or null when it cannot be read. */
  async function openChunk (chunkId: string): Promise<PositionedChunk | null> {
    const known = chunks.value.find(c => c.id === chunkId)
    if (known) return known
    const mine = generation
    const window = await read(() => api.readDocumentChunkWindowApiDocumentsDocumentIdChunksChunkIdWindowGet({
      documentId: documentId(), chunkId, before: WINDOW_BEFORE, after: WINDOW_AFTER
    }), 'The passage could not be loaded.')
    if (!window || mine !== generation) return null
    const read_ = positioned(window.chunks)
    merge(read_)
    const last = read_[read_.length - 1]
    if (last && last.order >= Math.max(...chunks.value.map(c => c.order))) hasAfter.value = window.hasAfter
    return chunks.value.find(c => c.id === chunkId) ?? null
  }

  /**
   * The chunks whose page range includes page `order` (the manifest position), read once per
   * page and merged; their stored page ranges are coarse (one chunk too many, never too few).
   */
  function pageChunks (order: number): Promise<PositionedChunk[]> {
    let pending = pageReads.get(order)
    if (!pending) {
      const mine = generation
      pending = read(() => api.readDocumentPageChunksApiDocumentsDocumentIdChunksByPageGet({ documentId: documentId(), page: order }),
        'The text of this page could not be loaded.').then((result) => {
        const found = result ? positioned(result.chunks) : []
        if (mine === generation) merge(found)
        // A failed read is tried again next time.
        if (!result && pageReads.get(order) === pending) pageReads.delete(order)
        return found
      })
      pageReads.set(order, pending)
    }
    return pending
  }

  /** The first text of the document: the chunks of the first page (of the first few) that has any. */
  async function openStart (): Promise<PositionedChunk[]> {
    const mine = generation
    for (let order = 0; order < START_PAGES; order++) {
      if (mine !== generation) return []
      const found = await pageChunks(order)
      if (found.length || error.value) return found
    }
    return []
  }

  /** Reads up to a few more chunks before the first or after the last one shown. */
  async function extend (direction: 'before' | 'after'): Promise<void> {
    const list = chunks.value
    const edge = direction === 'before' ? list[0] : list[list.length - 1]
    if (!edge) return
    const mine = generation
    const result = await read(() => api.readDocumentAdjacentChunksApiDocumentsDocumentIdChunksChunkIdAdjacentGet({
      documentId: documentId(), chunkId: edge.id, direction, limit: EXTEND
    }), 'More text could not be loaded.')
    if (!result || mine !== generation) return
    merge(positioned(result.chunks))
    if (direction === 'after') hasAfter.value = result.chunks.length === EXTEND
  }

  /** Reads the chunks missing after the chunk at `afterOrder` (at most a few at a time). */
  async function fillGap (afterOrder: number): Promise<void> {
    const edge = chunks.value.find(c => c.order === afterOrder)
    const next = chunks.value.find(c => c.order > afterOrder)
    if (!edge || !next) return
    const mine = generation
    const result = await read(() => api.readDocumentAdjacentChunksApiDocumentsDocumentIdChunksChunkIdAdjacentGet({
      documentId: documentId(), chunkId: edge.id, direction: 'after', limit: Math.min(EXTEND * 2, next.order - afterOrder - 1)
    }), 'More text could not be loaded.')
    if (result && mine === generation) merge(positioned(result.chunks))
  }

  return { chunks, hasAfter, loading, error, reset, merge, openChunk, pageChunks, openStart, extend, fillGap }
}

export type DocumentText = ReturnType<typeof useDocumentText>
