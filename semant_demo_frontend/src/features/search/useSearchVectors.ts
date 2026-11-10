import { useQuery } from '@tanstack/vue-query'
import { useApi } from 'src/shared/api'

/** The query key of the configured search vectors: the same for every user. */
export const SEARCH_VECTORS_KEY = ['search', 'vectors'] as const

/**
 * Search vectors are server configuration, which changes only with a deployment. One
 * answer serves every Search page in the tab for this long, also after the page is left;
 * a reload asks again. A failed load is not kept: the next mount asks again.
 */
export const SEARCH_VECTORS_FRESH_MS = 60 * 60 * 1000

/** The configured search vectors (`GET /api/search/vectors`) and the server's default. */
export function useSearchVectors () {
  return useQuery({
    queryKey: SEARCH_VECTORS_KEY,
    // The signal lets the cache abort a load nobody waits for any more.
    queryFn: ({ signal }) => useApi().default.getAvailableSearchVectorsApiSearchVectorsGet({ signal }),
    staleTime: SEARCH_VECTORS_FRESH_MS,
    gcTime: SEARCH_VECTORS_FRESH_MS
  })
}
