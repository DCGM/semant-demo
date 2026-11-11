import type { SearchResponse, SearchResultChunk } from 'src/generated/api'

/** A search's results as the summary endpoint reads them (`/api/summarize`: a search response). */
export function asSearchResponse (query: string, timeSpent: number, results: SearchResultChunk[]): SearchResponse {
  return {
    results,
    searchRequest: { query, tagUuids: [], positive: false, automatic: false },
    timeSpent,
    searchLog: []
  }
}
