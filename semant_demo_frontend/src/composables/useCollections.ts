import { useCollectionsStore } from 'src/stores/collectionsStore'
import { PostCollection, PatchCollection } from 'src/models/collection'
import { computed } from 'vue'

const useCollections = () => {
  const collectionsStore = useCollectionsStore()

  const loadCollections = (userId: string) => collectionsStore.fetchCollections(userId)
  const loadCollection = (collectionId: string) => collectionsStore.fetchCollection(collectionId)
  const loadCollectionStats = (collectionId: string) => collectionsStore.fetchCollectionStats(collectionId)
  const createCollection = (userId: string, collectionData: PostCollection) => collectionsStore.createCollection(userId, collectionData)
  const updateCollection = (collectionId: string, collectionData: PatchCollection) => collectionsStore.updateCollection(collectionId, collectionData)
  const deleteCollection = (collectionId: string) => collectionsStore.deleteCollection(collectionId)

  const collections = computed(() => collectionsStore.collections)
  const activeCollection = computed(() => collectionsStore.activeCollection)
  const activeCollectionStats = computed(() => collectionsStore.activeCollectionStats)
  const loading = computed(() => collectionsStore.loading)
  const error = computed(() => collectionsStore.error)

  return {
    loadCollections,
    loadCollection,
    loadCollectionStats,
    createCollection,
    updateCollection,
    deleteCollection,

    collections,
    activeCollection,
    activeCollectionStats,
    loading,
    error
  }
}

export default useCollections
