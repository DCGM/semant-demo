import { useApi } from 'src/shared/api'
import { Collection, PostCollection, PatchCollection, CollectionStats, UserSearchResult } from 'src/generated/api'

export function useUserCollectionsRepository() {
  const api = useApi().default

  return {
    getAll: async (): Promise<Collection[]> => {
      return api.fetchCollectionsApiUserCollectionsGet()
    },

    getById: async (collectionId: string): Promise<Collection> => {
      return api.fetchCollectionApiUserCollectionsCollectionIdGet({ collectionId })
    },

    getStats: async (collectionId: string): Promise<CollectionStats> => {
      return api.getCollectionStatsApiUserCollectionsCollectionIdStatsGet({ collectionId })
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
      await api.deleteCollectionApiUserCollectionsCollectionIdDelete({ collectionId })
    },

    getMembers: async (collectionId: string): Promise<UserSearchResult[]> => {
      return api.getCollectionMembersApiUserCollectionsCollectionIdMembersGet({ collectionId })
    },

    share: async (collectionId: string, userId: string): Promise<Collection> => {
      return api.shareCollectionApiUserCollectionsCollectionIdSharePost({
        collectionId,
        shareCollectionRequest: { userId }
      })
    },

    unshare: async (collectionId: string, userId: string): Promise<Collection> => {
      return api.unshareCollectionApiUserCollectionsCollectionIdShareUserIdDelete({ collectionId, userId })
    }
  }
}
