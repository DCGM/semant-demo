import type { ChunkFilters, DocumentFilters } from 'src/generated/api'
import { useCorpusOverview } from 'src/features/analytics/useCorpusOverview'
import { criteriaKey, normalizeCriteria, type Criteria, type ResultsMode } from './criteria'

/**
 * Explore Visualizations, first slice (#618, docs/EXPLORATION.md): charts of the documents the
 * applied filters match, for Documents without a text query.
 *
 * - `documents`: every matching document is counted by `POST /api/analytics/corpus/distributions`
 *   with the same document filters and per-dimension chunk filters as the Documents results
 *   (#606, #529), never from a page of results.
 * - `textQuery`: the charts of a search would describe only its retrieved results (#619/#620);
 *   until then nothing is charted, rather than the filtered corpus shown as if it were the results.
 * - `passages`: Passages need a text query; filter-only passage counts are not available, and
 *   document counts are not shown in their place.
 * - `collection`: the distributions cover the public corpus only, not a collection scope.
 */
export type ChartsAvailability = 'documents' | 'textQuery' | 'passages' | 'collection'

export function chartsAvailability (criteria: Criteria, mode: ResultsMode, userCollectionId: string | null): ChartsAvailability {
  if (criteria.textQuery) return 'textQuery'
  if (mode === 'passages') return 'passages'
  if (userCollectionId) return 'collection'
  return 'documents'
}

/** The request form of the criteria's filters (the text query aside). */
export function chartFilters (criteria: Criteria): { filters: DocumentFilters, chunkFilters: ChunkFilters } {
  const c = normalizeCriteria(criteria)
  return { filters: { ...c.documentFilters }, chunkFilters: { languages: c.chunkFilters.languages, classifications: c.chunkFilters.classifications } }
}

/**
 * The document distributions of the applied criteria. `show` counts them unless the shown (or
 * loading) counts are already those of the same filters, so switching between Results and
 * Visualizations does not count again; `force` counts again anyway (an explicit Search, Retry).
 * A newer request aborts the previous one and its late answer is ignored (`useCorpusOverview`).
 */
export function useExploreCharts () {
  const overview = useCorpusOverview()
  let requestedKey: string | null = null

  function show (criteria: Criteria, { force = false } = {}) {
    const key = criteriaKey({ ...criteria, textQuery: null })
    const current = key === requestedKey && !overview.error.value && (overview.loading.value || overview.distributions.value !== null)
    if (current && !force) return
    requestedKey = key
    const { filters, chunkFilters } = chartFilters(criteria)
    void overview.load(filters, chunkFilters)
  }

  return { ...overview, show }
}
