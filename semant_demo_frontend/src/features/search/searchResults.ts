import type { SearchResponse, SearchResultChunk } from 'src/generated/api'

/**
 * The results of one search, as retrieved so far: the explicit input of tools working on
 * search results (the AI Chat panel's summaries and questions, #245). A new search creates a new context
 * with a new `id`; tools drop work started for an older one. Loading more results of the same
 * search keeps the `id` and adds to `results`, so earlier result numbers stay valid.
 *
 * Hits keep their source references (chunk `id`, `document`, `startPageId`,
 * `fromPage`/`toPage`). Their `text` is display text, not the canonical text annotation
 * offsets refer to; tools needing canonical text or page geometry resolve it by id.
 */
export interface SearchResultsContext {
  readonly id: number
  /** The text query the results were retrieved for. */
  readonly query: string
  readonly results: readonly SearchResultChunk[]
  /** Retrieval time in seconds. */
  readonly timeSpent: number
}

/** The context as the summary endpoint reads it (`/api/summarize`: a search response). */
export function asSearchResponse (context: SearchResultsContext, results: SearchResultChunk[]): SearchResponse {
  return {
    results,
    searchRequest: { query: context.query, tagUuids: [], positive: false, automatic: false },
    timeSpent: context.timeSpent,
    searchLog: []
  }
}
