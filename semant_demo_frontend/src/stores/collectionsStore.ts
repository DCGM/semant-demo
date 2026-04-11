import { ref } from 'vue'
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

  const fetchCollections = async (userId: string) => {
    const notif = ongoingNotification('Loading collections...')
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.getAll(userId)
      collections.value = data
      notif.success('Collections loaded')
    } catch (err) {
      error.value = 'Failed to fetch collections'
      console.error('Error fetching collections:', err)
      notif.error('Failed to load collections')
    } finally {
      loading.value = false
    }
  }
  const fetchCollection = async (collectionId: string) => {
    const notif = ongoingNotification('Loading collection...')
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.getById(collectionId)
      activeCollection.value = data
      notif.success('Collection loaded')
    } catch (err) {
      error.value = 'Failed to fetch collection'
      console.error('Error fetching collection:', err)
      notif.error('Failed to load collection')
    } finally {
      loading.value = false
    }
  }
  const createCollection = async (collectionData: PostCollection) => {
    const notif = ongoingNotification('Creating collection...')
    loading.value = true
    error.value = null
    try {
      await collectionRepository.create(collectionData)
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
      notif.success('Collection deleted')
    } catch (err) {
      error.value = 'Failed to delete collection'
      console.error('Error deleting collection:', err)
      notif.error('Failed to delete collection')
    } finally {
      loading.value = false
    }
  }

  return {
    collections,
    activeCollection,
    error,
    loading,
    fetchCollections,
    fetchCollection,
    createCollection,
    updateCollection,
    deleteCollection
  }
})
