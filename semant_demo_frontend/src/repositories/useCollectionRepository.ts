import { useApi } from 'src/composables/useApi'
import { Collection, Collections, PostCollection, PatchCollection } from 'src/models/collections'
import { CollectionStats } from 'src/models/collection_stats'
import { CreateResponse } from 'src/models/api_responses'

export function useCollectionRepository() {
  const api = useApi().default

  return {
    getAll: async (userId: string): Promise<Collections> => {
      return api.fetchCollectionsApiUserCollectionsGet({ userId })
    },

    getById: async (collectionId: string): Promise<Collection> => {
      return api.fetchCollectionApiUserCollectionsCollectionIdGet({ collectionId })
    },

    getStats: async (collectionId: string): Promise<CollectionStats> => {
      return api.getCollectionStatsApiV1CollectionsCollectionIdStatsGet({ collectionId })
    },

    create: async (collectionData: PostCollection): Promise<CreateResponse> => {
      return api.createUserCollectionApiUserCollectionsPost({
        postCollection: collectionData
      })
    },

    update: async (collectionId: string, collectionData: PatchCollection): Promise<Collection> => {
      return api.updateCollectionApiV1CollectionsCollectionIdPatch({
        collectionId,
        patchCollection: collectionData
      })
    },

    remove: async (collectionId: string): Promise<void> => {
      await api.deleteCollectionApiV1CollectionsCollectionIdDelete({ collectionId })
    }
  }
}
