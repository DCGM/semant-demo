import { api } from 'src/boot/axios'
import { ENDPOINTS } from 'src/constants/endpoints'
import { Collection, CollectionStats, Collections, PostCollection, PatchCollection } from 'src/models/collections'

const CollectionsService = {
  getCollections: async (userId: string) => await api.get<Collections>(ENDPOINTS.COLLECTIONS, { params: { user_id: userId } }),
  getCollectionById: async (collectionId: string) => await api.get<Collection>(`${ENDPOINTS.COLLECTIONS}/${collectionId}`),
  getCollectionStats: async (collectionId: string) => await api.get<CollectionStats>(`${ENDPOINTS.COLLECTIONS}/${collectionId}/stats`),
  postCollection: async (userId: string, data: PostCollection) => await api.post<Collection>(ENDPOINTS.COLLECTIONS, { userId, ...data }),
  // putCollection: async (collectionId: string, data: PatchCollection) => await api.put<Collection>(`${ENDPOINTS.COLLECTIONS}/${collectionId}`, data),
  patchCollection: async (collectionId: string, data: PatchCollection) => await api.patch<Collection>(`${ENDPOINTS.COLLECTIONS}/${collectionId}`, data),
  deleteCollection: async (collectionId: string) => await api.delete(`${ENDPOINTS.COLLECTIONS}/${collectionId}`)
}

export default CollectionsService
