import { readonly, ref } from 'vue'

export interface RequestedCitation {
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

/** The reader's latest citation request, which it scrolls to. */
export const requestedCitation = readonly(requested)

/** Asks the document reader to scroll to `chunkId` (loading it first when `order` is known). */
export function citeInReader (chunkId: string, order: number | null): void {
  requested.value = { chunkId, order, token: ++token }
}
