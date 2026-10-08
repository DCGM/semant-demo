import { useApi } from 'src/shared/api'
import { Chunk, Chunks } from 'src/models/chunks'
import { requireComplete } from 'src/utils/writeOutcome'

export function useChunksRepository() {
  const api = useApi().default

  return {
    getCollectionDocumentChunks: async (collectionId: string, documentId: string): Promise<Chunks> => {
      return api.getCollectionDocumentChunksApiCollectionsCollectionIdDocumentsDocumentIdGet({
        collectionId,
        documentId
      })
    },

    /** Throws IncompleteWriteError when the chunk or its document could not be linked. */
    addChunkToCollection: async (chunkId: string, collectionId: string) => {
      return requireComplete(
        await api.addChunkToCollectionApiUserCollectionCollectionIdChunksChunkIdPost({ chunkId, collectionId }),
        'Adding the chunk'
      )
    },

    removeChunkFromCollection: async (chunkId: string, collectionId: string) => {
      return api.removeChunkFromCollectionApiUserCollectionCollectionIdChunksChunkIdDelete({
        chunkId,
        collectionId
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
      const chunks = (await api.getChunksInRangeApiCollectionsCollectionIdDocumentsDocumentIdChunksGet({
        collectionId,
        documentId,
        orderGt,
        orderLt
      })).filter((chunk) => chunk !== null) // Filter out null values
      return chunks
    }
  }
}
