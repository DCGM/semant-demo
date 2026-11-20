import { useQuery } from '@tanstack/vue-query'
import { useApi } from 'src/shared/api'
import { SHARED_QUERY } from 'src/shared/query'

/** The query key of the configured search filters: the same for every user. */
export const SEARCH_FILTERS_KEY = ['search', 'filters'] as const

/**
 * The configured search filters (`GET /api/search/filters`): their names, targets and value
 * labels, e.g. the chunk classifications a collection's passages are counted by (#807).
 *
 * Server configuration, which changes only with a deployment: one answer serves the tab until it
 * is reloaded, kept across sign-outs (as `useSearchVectors`). A failed load is not kept, so a
 * page that mounts the query anew asks again.
 */
export function useSearchFilters () {
  return useQuery({
    queryKey: SEARCH_FILTERS_KEY,
    // The signal lets the cache abort a load nobody waits for any more.
    queryFn: ({ signal }) => useApi().default.getAvailableSearchFiltersApiSearchFiltersGet({ signal }),
    staleTime: Infinity,
    gcTime: Infinity,
    meta: SHARED_QUERY
  })
}
