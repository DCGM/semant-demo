import { defineStore } from 'pinia'
import { CollectionStats } from 'src/models/collection_stats'
import { useCollectionRepository } from 'src/repositories/useCollectionRepository'
import { ongoingNotification } from 'src/utils/notification'
import { ref } from 'vue'

export const useCollectionStatsStore = defineStore('collectionStats', () => {
  const collectionRepository = useCollectionRepository()
  const collectionStats = ref<CollectionStats | null>(null)
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)

  const fetchCollectionStats = async (collectionId: string) => {
    const notif = ongoingNotification('Loading collection statistics...')
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.getStats(collectionId)
      collectionStats.value = data
      notif.success('Collection statistics loaded')
    } catch (err) {
      error.value = 'Failed to fetch collection statistics'
      notif.error('Failed to load collection statistics')
    } finally {
      loading.value = false
    }
  }

  return {
    collectionStats,
    error,
    loading,
    fetchCollectionStats
  }
})
