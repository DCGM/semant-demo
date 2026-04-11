import { useApi } from 'src/composables/useApi'
import { Collection, Collections, PostCollection, PatchCollection, CollectionStats } from 'src/models/collections'
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
      return api.getCollectionStatsApiUserCollectionCollectionIdStatsGet({ collectionId })
    },

    create: async (collectionData: PostCollection): Promise<CreateResponse> => {
      return api.createUserCollectionApiUserCollectionsPost({
        postCollection: collectionData
      })
    },

    update: async (collectionId: string, collectionData: PatchCollection): Promise<void> => {
      return api.updateCollectionApiUserCollectionsCollectionIdPatch({
        collectionId,
        patchCollection: collectionData
      })
    },

    remove: async (collectionId: string): Promise<void> => {
      await api.deleteCollectionApiCollectionsCollectionIdDelete({ collectionId })
    }
  }
}
