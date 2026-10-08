import { defineStore } from 'pinia'
import { CollectionStats } from 'src/models/collections'
import { useCollectionRepository } from 'src/repositories/useCollectionRepository'
import { ref } from 'vue'
import { createContextGuard } from 'src/shared/api'

export const useCollectionStatsStore = defineStore('collectionStats', () => {
  const collectionRepository = useCollectionRepository()
  const collectionStats = ref<CollectionStats | null>(null)
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)
  // Only the latest load may set the statistics (another collection may be open by now).
  const requests = createContextGuard()

  const fetchCollectionStats = async (collectionId: string) => {
    requests.enter()
    const isCurrent = requests.capture()
    collectionStats.value = null
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.getStats(collectionId)
      if (isCurrent()) collectionStats.value = data
    } catch (err) {
      if (isCurrent()) error.value = 'Failed to fetch collection statistics'
    } finally {
      if (isCurrent()) loading.value = false
    }
  }

  /** Drops the statistics (logout). */
  const clear = () => {
    requests.enter()
    collectionStats.value = null
    error.value = null
    loading.value = false
  }

  return {
    collectionStats,
    error,
    loading,
    fetchCollectionStats,
    clear
  }
})
