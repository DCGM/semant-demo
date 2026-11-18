import { computed, type Ref } from 'vue'
import { useQuery, type QueryClient } from '@tanstack/vue-query'
import { useUserStore } from 'src/features/auth/userStore'
import { queryClient, userScopedKey } from 'src/shared/query'
import { countAnnotations } from 'src/features/annotations/annotationCounts'

const COUNTS = 'collection-annotation-counts'

/**
 * How many AI suggestions in a collection are still unresolved (#770), from
 * `GET /api/user_collections/{id}/annotations/counts`, keyed by the collection and the
 * signed-in user. Only the collections a page shows ask for it (the rows of the table's
 * current page, the tiles of the current page): the server counts one collection at a time.
 * Asked again whenever a row or tile showing it mounts; the last known number is shown meanwhile.
 */
export function usePendingSuggestions (collectionId: Ref<string>) {
  const userStore = useUserStore()
  const query = useQuery({
    queryKey: computed(() => userScopedKey(userStore.getUserId ?? '', COUNTS, collectionId.value)),
    queryFn: async ({ queryKey }) => (await countAnnotations(queryKey[3] as string)).suggestions,
    enabled: computed(() => !!collectionId.value && !!userStore.getUserId),
    retry: false
  })
  return { count: query.data, failed: query.isError }
}

/** Forgets the counts of deleted collections, for every user they were loaded for. */
export function forgetPendingSuggestions (collectionIds: readonly string[], client: QueryClient = queryClient): void {
  const ids = new Set(collectionIds)
  client.removeQueries({
    predicate: ({ queryKey }) => queryKey[0] === 'user' && queryKey[2] === COUNTS && ids.has(queryKey[3] as string)
  })
}
