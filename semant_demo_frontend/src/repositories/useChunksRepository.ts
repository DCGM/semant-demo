import { useApi } from 'src/composables/useApi'
import { Chunk, Chunks } from 'src/models/chunks'

export function useChunksRepository() {
  const api = useApi().default

  return {
    getCollectionDocumentChunks: async (collectionId: string, documentId: string): Promise<Chunks> => {
      return api.getCollectionDocumentChunksApiCollectionsCollectionIdDocumentsDocumentIdGet({
        collectionId,
        documentId
      })
    }
  }
}
