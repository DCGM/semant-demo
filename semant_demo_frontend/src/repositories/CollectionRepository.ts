import { Collection, CollectionStats, Collections, PostCollection, PatchCollection } from 'src/models/collections'
import { CollectionsSchema, CollectionSchema, CollectionStatsSchema } from 'src/schemas/collection'
import CollectionsService from 'src/services/CollectionsService'

const CollectionRepository = {
  getAll: async (userId: string): Promise<Collections> => {
    const response = await CollectionsService.getCollections(userId)
    const data = response.data

    const parsedData = CollectionsSchema.safeParse(data)

    if (!parsedData.success) {
      throw new Error('Failed to parse collections data from API')
    }

    return parsedData.data
  },

  getById: async (collectionId: string): Promise<Collection> => {
    const response = await CollectionsService.getCollectionById(collectionId)
    const data = response.data

    const parsedData = CollectionSchema.safeParse(data)

    if (!parsedData.success) {
      throw new Error('Failed to parse collection data from API')
    }

    return parsedData.data
  },

  getStats: async (collectionId: string): Promise<CollectionStats> => {
    const response = await CollectionsService.getCollectionStats(collectionId)
    const data = response.data

    const parsedData = CollectionStatsSchema.safeParse(data)

    if (!parsedData.success) {
      throw new Error('Failed to parse collection stats data from API')
    }

    return parsedData.data
  },

  create: async (userId: string, collectionData: PostCollection): Promise<Collection> => {
    const response = await CollectionsService.postCollection(userId, collectionData)
    const data = response.data

    const parsedData = CollectionSchema.safeParse(data)

    if (!parsedData.success) {
      throw new Error('Failed to parse created collection data from API')
    }

    return parsedData.data
  },

  update: async (collectionId: string, collectionData: PatchCollection): Promise<Collection> => {
    const response = await CollectionsService.patchCollection(collectionId, collectionData)
    const data = response.data

    const parsedData = CollectionSchema.safeParse(data)

    if (!parsedData.success) {
      throw new Error('Failed to parse updated collection data from API')
    }

    return parsedData.data
  },

  remove: async (collectionId: string): Promise<void> => {
    const response = await CollectionsService.deleteCollection(collectionId)

    if (response.status !== 204 && response.status !== 200) {
      throw new Error('Failed to delete collection')
    }
  }
}

export default CollectionRepository
