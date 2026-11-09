import type { DefaultApi, DocumentChunk } from 'src/generated/api'

// The chunks of one page of a public document (#544, #545): the stored page ranges
// (`from_page`..`to_page`) are coarse locators (one chunk too many, never too few), read with
// the bounded `/chunks/by_page` and, for a page with more chunks than one read returns,
// continued with `/adjacent`. Never the chunks of the earlier pages.

/** A chunk with its place in the document (chunks without an `order` are not shown). */
export type PositionedChunk = DocumentChunk & { order: number }

/** Chunks per page read (the API's maximum), and further reads for a page with more. */
export const PAGE_LIMIT = 50
export const PAGE_FOLLOW_READS = 3

export const positioned = (chunks: DocumentChunk[]): PositionedChunk[] =>
  chunks.filter((c): c is PositionedChunk => typeof c.order === 'number')

/**
 * The chunks whose page range includes page `order` (the manifest position), in document
 * order; `complete` is false when chunks of the page may remain unread (after
 * `PAGE_FOLLOW_READS` further reads). Rejects when a read fails.
 */
export async function readPageChunks (
  api: DefaultApi, documentId: string, order: number
): Promise<{ chunks: PositionedChunk[], complete: boolean }> {
  const covers = (c: PositionedChunk) => c.fromPage <= order && order <= c.toPage
  const first = await api.readDocumentPageChunksApiDocumentsDocumentIdChunksByPageGet({
    documentId, page: order, limit: PAGE_LIMIT
  })
  const found = positioned(first.chunks)
  let complete = !first.hasMore
  for (let i = 0; !complete && i < PAGE_FOLLOW_READS && found.length; i++) {
    const more = await api.readDocumentAdjacentChunksApiDocumentsDocumentIdChunksChunkIdAdjacentGet({
      documentId, chunkId: found[found.length - 1].id, direction: 'after', limit: PAGE_LIMIT
    })
    const next = positioned(more.chunks)
    found.push(...next.filter(covers))
    // Chunks are in document order: one starting after the page, or the end of the
    // document, ends the page's chunks.
    complete = next.length < PAGE_LIMIT || next.some(c => c.fromPage > order)
  }
  return { chunks: found, complete }
}
