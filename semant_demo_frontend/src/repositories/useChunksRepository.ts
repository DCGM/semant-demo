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
    },

    addChunkToCollection: async (chunkId: string, collectionId: string) => {
      return api.addChunk2CollectionApiUserCollectionChunksPost({
        chunk2CollectionReq: { chunkId, collectionId }
      })
    },

    removeChunkFromCollection: async (chunkId: string, collectionId: string) => {
      return api.removeChunkFromCollectionApiUserCollectionChunksDelete({
        chunk2CollectionReq: { chunkId, collectionId }
      })
    },

    getNeighbourChunk: async (
      collectionId: string,
      documentId: string,
      direction: 'prev' | 'next',
      boundaryOrder: number
    ): Promise<Chunk | null> => {
      return api.getNeighbourChunkApiCollectionsCollectionIdDocumentsDocumentIdNeighbourGet({
        collectionId,
        documentId,
        direction,
        boundaryOrder
      })
    },

    countDocumentChunks: async (documentId: string): Promise<number> => {
      return api.countDocumentChunksApiDocumentsDocumentIdChunksCountGet({ documentId })
    },

    getChunksInRange: async (
      collectionId: string,
      documentId: string,
      orderGt?: number | null,
      orderLt?: number | null
    ): Promise<import('src/generated/api').Chunk[]> => {
      return api.getChunksInRangeApiCollectionsCollectionIdDocumentsDocumentIdChunksGet({
        collectionId,
        documentId,
        orderGt,
        orderLt
      })
    }
  }
}
