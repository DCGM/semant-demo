import { useCollectionStatsStore } from 'src/stores/collectionStatsStore'
import { computed } from 'vue'

const useCollectionStats = () => {
  const collectionStatsStore = useCollectionStatsStore()

  const loadCollectionStats = (collectionId: string) => collectionStatsStore.fetchCollectionStats(collectionId)

  const collectionStats = computed(() => collectionStatsStore.collectionStats)
  const loading = computed(() => collectionStatsStore.loading)
  const error = computed(() => collectionStatsStore.error)

  return {
    loadCollectionStats,
    collectionStats,
    loading,
    error
  }
}

export default useCollectionStats
