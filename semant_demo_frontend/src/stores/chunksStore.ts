import { defineStore } from 'pinia'
import { ref } from 'vue'
import { Chunks } from 'src/models/chunks'
import { ongoingNotification } from 'src/utils/notification'
import { useChunksRepository } from 'src/repositories/useChunksRepository'

export const useChunksStore = defineStore('chunks', () => {
  const chunksRepository = useChunksRepository()
  const chunks = ref<Chunks>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchChunksInCollectionDocument = async (collectionId: string, documentId: string) => {
    // const notif = ongoingNotification('Loading chunks...')
    loading.value = true
    error.value = null
    try {
      const data = await chunksRepository.getCollectionDocumentChunks(collectionId, documentId)
      chunks.value = data
      // notif.success('Chunks loaded')
    } catch (err) {
      error.value = 'Failed to fetch chunks'
      console.error('Error fetching chunks:', err)
      // notif.error('Failed to load chunks')
      chunks.value = []
    } finally {
      loading.value = false
    }
  }

  return {
    chunks,
    loading,
    error,
    fetchChunksInCollectionDocument
  }
})
