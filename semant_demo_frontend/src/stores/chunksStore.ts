import { defineStore } from 'pinia'
import { ref } from 'vue'
import { Chunks } from 'src/models/chunks'
import { useChunksRepository } from 'src/repositories/useChunksRepository'
import { createContextGuard } from 'src/shared/api'

export const useChunksStore = defineStore('chunks', () => {
  const chunksRepository = useChunksRepository()
  const chunks = ref<Chunks>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  // Only the latest load (collection + document) may set the chunks.
  const requests = createContextGuard()

  const fetchChunksInCollectionDocument = async (collectionId: string, documentId: string) => {
    requests.enter()
    const isCurrent = requests.capture()
    chunks.value = []
    loading.value = true
    error.value = null
    try {
      const data = await chunksRepository.getCollectionDocumentChunks(collectionId, documentId)
      if (isCurrent()) chunks.value = data
    } catch (err) {
      if (!isCurrent()) return
      error.value = 'Failed to fetch chunks'
      console.error('Error fetching chunks:', err)
      chunks.value = []
    } finally {
      if (isCurrent()) loading.value = false
    }
  }

  /** Drops the chunks (logout). */
  const clear = () => {
    requests.enter()
    chunks.value = []
    error.value = null
    loading.value = false
  }

  return {
    chunks,
    loading,
    error,
    fetchChunksInCollectionDocument,
    clear
  }
})
