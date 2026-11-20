import { computed, type Ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useUserStore } from 'src/features/auth/userStore'
import { collectionStatsKey } from './useCollectionStats'
import { useUserCollectionsRepository } from './useUserCollectionsRepository'

/**
 * The query key of a collection's document charts. It extends the statistics' key, so the
 * charts are forgotten (and would be invalidated) together with the statistics.
 */
export function collectionDocumentChartsKey (userId: string, collectionId: string) {
  return [...collectionStatsKey(userId, collectionId), 'document-charts']
}

/**
 * The document charts of a whole collection on its Overview tab (#795, #622): the unfiltered
 * `POST /api/analytics/corpus/distributions` with `user_collection_id` (#768), loaded as the
 * statistics are (`useCollectionStats`): asked again on every visit, held until the collection
 * itself has loaded (`enabled`), keyed by the collection and the signed-in user, never retried
 * behind the user's back.
 */
export function useCollectionDocumentCharts (collectionId: Ref<string>, enabled: Ref<boolean>) {
  const userStore = useUserStore()
  const repository = useUserCollectionsRepository()
  return useQuery({
    queryKey: computed(() => collectionDocumentChartsKey(userStore.getUserId ?? '', collectionId.value)),
    queryFn: ({ queryKey, signal }) => repository.getDocumentDistributions(queryKey[3] as string, { signal }),
    enabled: computed(() => enabled.value && !!collectionId.value && !!userStore.getUserId)
  })
}
