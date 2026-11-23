import { useApi } from 'src/shared/api'
import { Collection, PostCollection, PatchCollection, CollectionStats, CollectionPassages, CollectionPassagesRequestDimensionEnum, CorpusDistributions, UserSearchResult } from 'src/generated/api'

/** A chunk classification the passage counts can be asked for (`TASK_CLASSES`). */
export type PassageDimension = typeof CollectionPassagesRequestDimensionEnum[keyof typeof CollectionPassagesRequestDimensionEnum]

export function useUserCollectionsRepository() {
  const api = useApi().default

  return {
    getAll: async (): Promise<Collection[]> => {
      return api.fetchCollectionsApiUserCollectionsGet()
    },

    getById: async (collectionId: string): Promise<Collection> => {
      return api.fetchCollectionApiUserCollectionsCollectionIdGet({ collectionId })
    },

    getStats: async (collectionId: string, init?: RequestInit): Promise<CollectionStats> => {
      return api.getCollectionStatsApiUserCollectionsCollectionIdStatsGet({ collectionId }, init)
    },

    /** The document charts of the whole collection: its linked documents, no filters (#795, #768). */
    getDocumentDistributions: async (collectionId: string, init?: RequestInit): Promise<CorpusDistributions> => {
      return api.corpusDistributionsApiAnalyticsCorpusDistributionsPost(
        { corpusDistributionsRequest: { filters: {}, userCollectionId: collectionId } }, init)
    },

    /**
     * The passages included in the collection (#807): without `dimension` their total and detected
     * languages, with it their values of that classification (and the total) only.
     */
    getPassageCounts: async (collectionId: string, dimension: PassageDimension | null, init?: RequestInit): Promise<CollectionPassages> => {
      return api.collectionPassagesApiAnalyticsCollectionPassagesPost(
        { collectionPassagesRequest: { userCollectionId: collectionId, dimension } }, init)
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
