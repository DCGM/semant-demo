import { useCollectionsStore } from 'src/stores/collectionsStore'
import { PostCollection, PatchCollection } from 'src/models/collections'
import { computed } from 'vue'

const useCollections = () => {
  const collectionsStore = useCollectionsStore()

  const loadCollections = () => collectionsStore.fetchCollections()
  const loadCollection = (collectionId: string) => collectionsStore.fetchCollection(collectionId)
  const createCollection = (collectionData: PostCollection) => collectionsStore.createCollection(collectionData)
  const updateCollection = (collectionId: string, collectionData: PatchCollection) => collectionsStore.updateCollection(collectionId, collectionData)
  const deleteCollection = (collectionId: string) => collectionsStore.deleteCollection(collectionId)
  const deleteManyCollections = (collectionIds: string[]) => collectionsStore.deleteManyCollections(collectionIds)

  const collections = computed(() => collectionsStore.collections)
  const activeCollection = computed(() => collectionsStore.activeCollection)
  const loading = computed(() => collectionsStore.loading)
  const error = computed(() => collectionsStore.error)

  return {
    loadCollections,
    loadCollection,
    createCollection,
    updateCollection,
    deleteCollection,
    deleteManyCollections,

    collections,
    activeCollection,
    loading,
    error
  }
}

export default useCollections
