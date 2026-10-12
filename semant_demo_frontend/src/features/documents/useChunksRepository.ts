import { useApi } from 'src/shared/api'
import { CollectionChunk } from 'src/generated/api'
import { requireComplete } from 'src/shared/writeOutcome'

export function useChunksRepository() {
  const api = useApi().default

  return {
    getCollectionDocumentChunks: async (collectionId: string, documentId: string): Promise<CollectionChunk[]> => {
      return api.getCollectionDocumentChunksApiUserCollectionsCollectionIdDocumentsDocumentIdChunksGet({
        collectionId,
        documentId
      })
    },

    /** Throws IncompleteWriteError when the chunk or its document could not be linked. */
    addChunkToCollection: async (chunkId: string, collectionId: string) => {
      return requireComplete(
        await api.addChunkToCollectionApiUserCollectionsCollectionIdChunksChunkIdPost({ chunkId, collectionId }),
        'Adding the chunk'
      )
    },

    removeChunkFromCollection: async (chunkId: string, collectionId: string) => {
      return api.removeChunkFromCollectionApiUserCollectionsCollectionIdChunksChunkIdDelete({
        chunkId,
        collectionId
      })
    },

    getNeighbourChunk: async (
      collectionId: string,
      documentId: string,
      direction: 'prev' | 'next',
      boundaryOrder: number
    ): Promise<CollectionChunk | null> => {
      return api.getNeighbourChunkApiUserCollectionsCollectionIdDocumentsDocumentIdChunksNeighbourGet({
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
    ): Promise<import('src/generated/api').CollectionChunk[]> => {
      const chunks = (await api.getChunksInRangeApiUserCollectionsCollectionIdDocumentsDocumentIdChunksRangeGet({
        collectionId,
        documentId,
        orderGt,
        orderLt
      })).filter((chunk) => chunk !== null) // Filter out null values
      return chunks
    }
  }
}
