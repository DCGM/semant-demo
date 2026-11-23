import { computed, type Ref } from 'vue'
import { useQuery, type QueryClient } from '@tanstack/vue-query'
import { useUserStore } from 'src/features/auth/userStore'
import { queryClient, userScopedKey } from 'src/shared/query'
import { useUserCollectionsRepository } from './useUserCollectionsRepository'

const STATS = 'collection-stats'

/** The query key of one collection's statistics, as the signed-in user may read them. */
export function collectionStatsKey (userId: string, collectionId: string) {
  return userScopedKey(userId, STATS, collectionId)
}

/**
 * A collection's statistics (`GET /api/user_collections/{id}/stats`: documents, chunks,
 * tags and approved annotations), keyed by the collection and the signed-in user.
 *
 * Asked again each time a page showing them mounts (the default `staleTime` of 0), so
 * changes made since then on another page, in another tab or by another member of a
 * shared collection show up; the last known numbers of the same collection are shown
 * meanwhile. The Overview tab and the Collections page's unresolved AI suggestions (#770)
 * show them; no write that changes them can happen there (a deleted collection's are
 * forgotten), so writes need not invalidate them.
 *
 * `enabled` holds the request until the collection itself has loaded, so a collection
 * that is gone or no longer shared shows only its own error. Another collection, or
 * another user, is another key: its answer never shows under the previous one, and a
 * late answer for the previous key stays in that key's cache entry.
 */
export function useCollectionStats (collectionId: Ref<string>, enabled: Ref<boolean>) {
  const userStore = useUserStore()
  const repository = useUserCollectionsRepository()
  return useQuery({
    queryKey: computed(() => collectionStatsKey(userStore.getUserId ?? '', collectionId.value)),
    // The signal lets the cache abort a load nobody waits for any more.
    queryFn: ({ queryKey, signal }) => repository.getStats(queryKey[3] as string, { signal }),
    enabled: computed(() => enabled.value && !!collectionId.value && !!userStore.getUserId)
  })
}

/**
 * Forgets the statistics of deleted collections, for every user they were loaded for, and with them
 * every query whose key extends theirs: the document charts (`useCollectionDocumentCharts`) and the
 * passage charts (`useCollectionPassageCharts`).
 */
export function forgetCollectionStats (collectionIds: readonly string[], client: QueryClient = queryClient): void {
  const ids = new Set(collectionIds)
  client.removeQueries({
    predicate: ({ queryKey }) => queryKey[0] === 'user' && queryKey[2] === STATS && ids.has(queryKey[3] as string)
  })
}
