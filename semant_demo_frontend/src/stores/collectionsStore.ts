import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { Collection, Collections, PostCollection, PatchCollection } from 'src/models/collections'
import { useCollectionRepository } from 'src/repositories/useCollectionRepository'
import { ongoingNotification } from 'src/utils/notification'

export const useCollectionsStore = defineStore('userCollections', () => {
  const collectionRepository = useCollectionRepository()
  const collections = ref<Collections>([])
  const activeCollection = ref<Collection | null>(null)
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)
  const pendingDeleteIds = ref<Set<string>>(new Set())

  // Collections visible in UI — excludes any IDs currently being deleted
  const visibleCollections = computed(() =>
    collections.value.filter((c) => !pendingDeleteIds.value.has(c.id))
  )

  const fetchCollections = async () => {
    // const notif = ongoingNotification('Loading collections...')
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.getAll()
      collections.value = data
      // notif.success('Collections loaded')
    } catch (err) {
      error.value = 'Failed to fetch collections'
      console.error('Error fetching collections:', err)
      // notif.error('Failed to load collections')
    } finally {
      loading.value = false
    }
  }
  const fetchCollection = async (collectionId: string) => {
    // const notif = ongoingNotification('Loading collection...')
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.getById(collectionId)
      activeCollection.value = data
      // notif.success('Collection loaded')
    } catch (err) {
      error.value = 'Failed to fetch collection'
      console.error('Error fetching collection:', err)
      // notif.error('Failed to load collection')
    } finally {
      loading.value = false
    }
  }
  const createCollection = async (collectionData: PostCollection) => {
    const notif = ongoingNotification('Creating collection...')
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.create(collectionData)
      collections.value.push(data)
      notif.success('Collection created')
    } catch (err) {
      error.value = 'Failed to create collection'
      console.error('Error creating collection:', err)
      notif.error('Failed to create collection')
    } finally {
      loading.value = false
    }
  }
  const updateCollection = async (collectionId: string, collectionData: PatchCollection) => {
    const notif = ongoingNotification('Updating collection...')
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.update(collectionId, collectionData)
      const index = collections.value.findIndex((c) => c.id === collectionId)
      if (index !== -1) {
        collections.value[index] = data
      }
      if (activeCollection.value?.id === collectionId) {
        activeCollection.value = data
      }
      notif.success('Collection updated')
    } catch (err) {
      error.value = 'Failed to update collection'
      console.error('Error updating collection:', err)
      notif.error('Failed to update collection')
    } finally {
      loading.value = false
    }
  }
  const deleteCollection = async (collectionId: string) => {
    const notif = ongoingNotification('Deleting collection...')
    loading.value = true
    error.value = null
    try {
      await collectionRepository.remove(collectionId)
      collections.value = collections.value.filter((c) => c.id !== collectionId)
      if (activeCollection.value?.id === collectionId) {
        activeCollection.value = null
      }
      notif.success('Collection deleted')
    } catch (err) {
      error.value = 'Failed to delete collection'
      console.error('Error deleting collection:', err)
      notif.error('Failed to delete collection')
    } finally {
      loading.value = false
    }
  }

  const deleteManyCollections = async (collectionIds: string[]) => {
    if (collectionIds.length === 0) return
    const notif = ongoingNotification(`Deleting ${collectionIds.length} collections...`)
    // Track pending deletes so fetchCollections can't bring them back
    collectionIds.forEach((id) => pendingDeleteIds.value.add(id))
    collections.value = collections.value.filter((c) => !collectionIds.includes(c.id))
    error.value = null
    let hadError = false
    try {
      await Promise.all(collectionIds.map((id) => collectionRepository.remove(id)))
      notif.success(`${collectionIds.length} collection${collectionIds.length === 1 ? '' : 's'} deleted`)
    } catch (err) {
      hadError = true
      error.value = 'Failed to delete some collections'
      console.error('Error deleting collections:', err)
      notif.error('Failed to delete some collections')
      // On error, restore via fresh fetch so non-deleted items reappear
      await fetchCollections()
    } finally {
      if (!hadError) {
        // Re-filter in case a mid-deletion refresh restored items into collections.value
        collections.value = collections.value.filter((c) => !collectionIds.includes(c.id))
      }
      collectionIds.forEach((id) => pendingDeleteIds.value.delete(id))
    }
  }

  return {
    collections: visibleCollections,
    activeCollection,
    error,
    loading,
    fetchCollections,
    fetchCollection,
    createCollection,
    updateCollection,
    deleteCollection,
    deleteManyCollections
  }
})
