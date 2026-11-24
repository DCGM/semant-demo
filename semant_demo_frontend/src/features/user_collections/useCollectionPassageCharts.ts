import { computed, type Ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useUserStore } from 'src/features/auth/userStore'
import { collectionStatsKey } from './useCollectionStats'
import { useUserCollectionsRepository, type PassageDimension } from './useUserCollectionsRepository'

// The two reads of a collection's included-passage charts (#807): the total and the detected
// languages once per visit, and one classification when it is picked, so choosing another
// classification asks for that classification alone. Both keys extend the statistics' key, so
// they are forgotten together with the statistics (`forgetCollectionStats`). Loaded as the
// statistics and the document charts are: asked again on every visit, held until the collection
// itself has loaded (`enabled`), keyed by the collection and the signed-in user, never retried
// behind the user's back.

export function collectionPassageLanguagesKey (userId: string, collectionId: string) {
  return [...collectionStatsKey(userId, collectionId), 'passage-languages']
}

export function collectionPassageClassificationKey (userId: string, collectionId: string, dimension: string) {
  return [...collectionStatsKey(userId, collectionId), 'passage-classification', dimension]
}

/** The collection's included passages: their total and detected languages. */
export function useCollectionPassageLanguages (collectionId: Ref<string>, enabled: Ref<boolean>) {
  const userStore = useUserStore()
  const repository = useUserCollectionsRepository()
  return useQuery({
    queryKey: computed(() => collectionPassageLanguagesKey(userStore.getUserId ?? '', collectionId.value)),
    queryFn: ({ queryKey, signal }) => repository.getPassageCounts(queryKey[3] as string, null, { signal }),
    enabled: computed(() => enabled.value && !!collectionId.value && !!userStore.getUserId)
  })
}

/** The collection's included passages per value of `dimension` (none: nothing is asked). */
export function useCollectionPassageClassification (collectionId: Ref<string>, dimension: Ref<PassageDimension | null>,
  enabled: Ref<boolean>) {
  const userStore = useUserStore()
  const repository = useUserCollectionsRepository()
  return useQuery({
    queryKey: computed(() => collectionPassageClassificationKey(userStore.getUserId ?? '', collectionId.value,
      dimension.value ?? '')),
    queryFn: ({ queryKey, signal }) =>
      repository.getPassageCounts(queryKey[3] as string, queryKey[5] as PassageDimension, { signal }),
    enabled: computed(() => enabled.value && !!collectionId.value && !!dimension.value && !!userStore.getUserId)
  })
}
