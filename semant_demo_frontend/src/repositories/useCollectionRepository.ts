import { useApi } from 'src/composables/useApi'
import { Collection, Collections, PostCollection, PatchCollection, CollectionStats } from 'src/models/collections'
import { UserSearchResult } from 'src/generated/api'

export function useCollectionRepository() {
  const api = useApi().default

  return {
    getAll: async (): Promise<Collections> => {
      return api.fetchCollectionsApiUserCollectionsGet()
    },

    getById: async (collectionId: string): Promise<Collection> => {
      return api.fetchCollectionApiUserCollectionsCollectionIdGet({ collectionId })
    },

    getStats: async (collectionId: string): Promise<CollectionStats> => {
      return api.getCollectionStatsApiUserCollectionCollectionIdStatsGet({ collectionId })
    },

    create: async (collectionData: PostCollection): Promise<Collection> => {
      return api.createUserCollectionApiUserCollectionsPost({
        postCollection: collectionData
      })
    },

    update: async (collectionId: string, collectionData: PatchCollection): Promise<Collection> => {
      return api.updateCollectionApiUserCollectionsCollectionIdPatch({
        collectionId,
        patchCollection: collectionData
      })
    },

    remove: async (collectionId: string): Promise<void> => {
      await api.deleteCollectionApiCollectionsCollectionIdDelete({ collectionId })
    },

    getMembers: async (collectionId: string): Promise<UserSearchResult[]> => {
      return api.getCollectionMembersApiCollectionsCollectionIdMembersGet({ collectionId })
    },

    share: async (collectionId: string, userId: string): Promise<Collection> => {
      return api.shareCollectionApiCollectionsCollectionIdSharePost({
        collectionId,
        shareCollectionRequest: { userId }
      })
    },

    unshare: async (collectionId: string, userId: string): Promise<Collection> => {
      return api.unshareCollectionApiCollectionsCollectionIdShareUserIdDelete({ collectionId, userId })
    }
  }
}
