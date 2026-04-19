import { computed } from 'vue'
import { useChunksStore } from 'src/stores/chunksStore'

const useChunks = () => {
  const chunksStore = useChunksStore()

  const chunks = computed(() => chunksStore.chunks)
  const loading = computed(() => chunksStore.loading)
  const error = computed(() => chunksStore.error)

  const loadChunksInCollectionDocument = (collectionId: string, documentId: string) => {
    chunksStore.fetchChunksInCollectionDocument(collectionId, documentId)
  }

  return {
    chunks,
    loading,
    error,
    loadChunksInCollectionDocument
  }
}

export default useChunks
