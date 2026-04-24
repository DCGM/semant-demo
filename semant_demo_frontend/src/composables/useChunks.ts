import { computed } from 'vue'
import { useChunksStore } from 'src/stores/chunksStore'
import { useChunksRepository } from 'src/repositories/useChunksRepository'

const useChunks = () => {
  const chunksStore = useChunksStore()
  const chunksRepository = useChunksRepository()

  const chunks = computed(() => chunksStore.chunks)
  const loading = computed(() => chunksStore.loading)
  const error = computed(() => chunksStore.error)

  const loadChunksInCollectionDocument = (collectionId: string, documentId: string) => {
    chunksStore.fetchChunksInCollectionDocument(collectionId, documentId)
  }

  const addChunkToCollection = (chunkId: string, collectionId: string) =>
    chunksRepository.addChunkToCollection(chunkId, collectionId)

  const removeChunkFromCollection = (chunkId: string, collectionId: string) =>
    chunksRepository.removeChunkFromCollection(chunkId, collectionId)

  const getNeighbourChunk = (
    collectionId: string,
    documentId: string,
    direction: 'prev' | 'next',
    boundaryOrder: number
  ) => chunksRepository.getNeighbourChunk(collectionId, documentId, direction, boundaryOrder)

  const countDocumentChunks = (documentId: string) =>
    chunksRepository.countDocumentChunks(documentId)

  const getChunksInRange = (
    collectionId: string,
    documentId: string,
    orderGt?: number | null,
    orderLt?: number | null
  ) => chunksRepository.getChunksInRange(collectionId, documentId, orderGt, orderLt)

  return {
    chunks,
    loading,
    error,
    loadChunksInCollectionDocument,
    addChunkToCollection,
    removeChunkFromCollection,
    getNeighbourChunk,
    countDocumentChunks,
    getChunksInRange
  }
}

export default useChunks
