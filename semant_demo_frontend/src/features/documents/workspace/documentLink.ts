import type { RouteLocationRaw } from 'vue-router'
import { keptLocation } from 'src/router/keptPages'

// Links to the public document view (#545, `/documents/:documentId`) and back to the page a
// reader came from. The page that opens a document (Search, Chat) keeps its state while the
// document is open (MainLayout keeps it alive), so going back finds the results and the
// conversation as they were; the link to Search carries the search's URL (`keptLocation`,
// #605). After a reload of the document the link still leads there, to an empty page.

export type ReturnSource = 'search' | 'chat'

export interface DocumentTarget {
  /** A passage: the chunk, and optionally a range in it (UTF-16 offsets). */
  chunkId?: string | null
  start?: number | null
  end?: number | null
  /** A page (manifest page id); used when no chunk is given. */
  pageId?: string | null
  from?: ReturnSource | null
}

/** The public document view at a target. */
export function documentLink (documentId: string, target: DocumentTarget = {}): RouteLocationRaw {
  const query: Record<string, string> = {}
  if (target.chunkId) {
    query.chunk = target.chunkId
    if (target.start != null) query.start = String(target.start)
    if (target.end != null) query.end = String(target.end)
  } else if (target.pageId) {
    query.page = target.pageId
  }
  if (target.from) query.from = target.from
  return { name: 'document', params: { documentId }, query }
}

export interface ReturnLink {
  to: RouteLocationRaw
  label: string
  ariaLabel: string
}

/** Where the document view's back link leads, from its `?from=`; null without one. */
export function returnLink (from: unknown): ReturnLink | null {
  if (from === 'search') return { to: keptLocation('search'), label: 'Search', ariaLabel: 'Back to search results' }
  if (from === 'chat') return { to: { name: 'rag' }, label: 'Chat', ariaLabel: 'Back to the conversation' }
  return null
}
