import { readonly, ref } from 'vue'

export interface RequestedCitation {
  /** The exact document and collection context in which the citation may be shown. */
  documentId: string
  collectionId: string | null
  chunkId: string
  /** The cited chunk's position in the document, when known; lets the reader load it into
   * the displayed window on demand (useChunkWindow.loadUntil) if it isn't shown yet. */
  order: number | null
  /** Bumped on every request, so clicking the same citation again still re-triggers the scroll. */
  token: number
}

// Module-scope singleton: the sidebar panel that cites chunks (AI Chat with its summaries,
// #248/#249) lives in `DocumentViewLayout`, but `DocumentReaderPage` is a sibling
// route with no prop/event path from them. The reader watches `requestedCitation` and
// scrolls to it.
const requested = ref<RequestedCitation | null>(null)
let token = 0

/** The reader's latest citation request, which it scrolls to and highlights. */
export const requestedCitation = readonly(requested)

/** Navigation is scoped to the document/collection: a citation cannot grant read access. */
export function citeInReader (
  chunkId: string, order: number | null, documentId: string, collectionId: string | null
): void {
  requested.value = { documentId, collectionId, chunkId, order, token: ++token }
}

/** Dismiss the highlighted citation without changing the conversation or annotations. */
export function clearReaderCitation (): void {
  requested.value = null
}
