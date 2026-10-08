import type { SearchResponse, TextChunkWithDocument } from 'src/generated/api'

/**
 * The results of one search, as retrieved: the explicit input of tools working on search
 * results (summary now, search-result chat later). A new search creates a new context
 * with a new `id`; tools drop work started for an older one.
 *
 * Hits keep their source references (chunk `id`, `document`, `startPageId`,
 * `fromPage`/`toPage`). Their `text` is display text, not the canonical text annotation
 * offsets refer to; tools needing canonical text or page geometry resolve it by id.
 */
export interface SearchResultsContext {
  readonly id: number
  readonly response: SearchResponse
}

/**
 * Which results a tool works on. Never more than the retrieved results: there is no
 * re-run of the query and no widening to unselected hits or whole documents.
 */
export type ResultScope =
  | { kind: 'top'; count: number | null } // the first `count` results; null: all of them
  | { kind: 'selected'; ids: readonly string[] } // the results the user selected

export interface ResultSubset {
  results: TextChunkWithDocument[]
  /** 1-based number of each result in the full result list (citations refer to these). */
  numbers: number[]
}

/** The chosen subset of the context's results; null when it is empty. */
export function selectResults (context: SearchResultsContext, scope: ResultScope): ResultSubset | null {
  const all = context.response.results
  const picked: ResultSubset = { results: [], numbers: [] }
  if (scope.kind === 'selected') {
    const ids = new Set(scope.ids)
    all.forEach((result, index) => {
      if (ids.has(result.id)) {
        picked.results.push(result)
        picked.numbers.push(index + 1)
      }
    })
  } else {
    picked.results = scope.count === null ? [...all] : all.slice(0, scope.count)
    picked.numbers = picked.results.map((_, index) => index + 1)
  }
  return picked.results.length ? picked : null
}
