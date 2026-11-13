import { useQuery } from '@tanstack/vue-query'
import { useApi } from 'src/shared/api'
import { SHARED_QUERY } from 'src/shared/query'

/** The query key of the configured search vectors: the same for every user. */
export const SEARCH_VECTORS_KEY = ['search', 'vectors'] as const

/**
 * The configured search vectors (`GET /api/search/vectors`) and the server's default.
 *
 * Server configuration, which changes only with a deployment: one answer serves the tab
 * until it is reloaded, kept across sign-outs. The Search page stays alive (`meta.keepAlive`),
 * so it asks once per tab, as before; a failed load is not kept, so a page that mounts the
 * query anew asks again.
 */
export function useSearchVectors () {
  return useQuery({
    queryKey: SEARCH_VECTORS_KEY,
    // The signal lets the cache abort a load nobody waits for any more.
    queryFn: ({ signal }) => useApi().default.getAvailableSearchVectorsApiSearchVectorsGet({ signal }),
    staleTime: Infinity,
    gcTime: Infinity,
    meta: SHARED_QUERY
  })
}
