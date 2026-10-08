import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { Collection, Collections, PostCollection, PatchCollection } from 'src/models/collections'
import { useCollectionRepository } from 'src/repositories/useCollectionRepository'
import { ongoingNotification } from 'src/utils/notification'
import { incompleteWriteMessage } from 'src/utils/writeOutcome'
import { captureSession, createContextGuard } from 'src/shared/api'

export const useCollectionsStore = defineStore('userCollections', () => {
  const collectionRepository = useCollectionRepository()
  const collections = ref<Collections>([])
  const activeCollection = ref<Collection | null>(null)
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)
  const pendingDeleteIds = ref<Set<string>>(new Set())
  // Only the latest load sets the list / the open collection (another one may be open by
  // now, or another user signed in).
  const listRequests = createContextGuard()
  const activeRequests = createContextGuard()
  // Deletions the backend acknowledged. Collection ids are never reused, so a list answer
  // that predates a deletion cannot bring the collection back.
  const deletedIds = new Set<string>()

  const forgetDeleted = (ids: string[]) => {
    ids.forEach((id) => deletedIds.add(id))
    collections.value = collections.value.filter((c) => !deletedIds.has(c.id))
    if (activeCollection.value && deletedIds.has(activeCollection.value.id)) activeCollection.value = null
  }

  // Collections visible in UI — excludes any IDs currently being deleted
  const visibleCollections = computed(() =>
    collections.value.filter((c) => !pendingDeleteIds.value.has(c.id))
  )

  const fetchCollections = async () => {
    listRequests.enter()
    const isCurrent = listRequests.capture()
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.getAll()
      if (isCurrent()) collections.value = data.filter((c) => !deletedIds.has(c.id))
    } catch (err) {
      if (!isCurrent()) return
      error.value = 'Failed to fetch collections'
      console.error('Error fetching collections:', err)
    } finally {
      if (isCurrent()) loading.value = false
    }
  }
  const fetchCollection = async (collectionId: string) => {
    activeRequests.enter()
    const isCurrent = activeRequests.capture()
    // Never show another collection's metadata (or rights) while this one loads.
    if (activeCollection.value?.id !== collectionId) activeCollection.value = null
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.getById(collectionId)
      if (isCurrent()) activeCollection.value = data
    } catch (err) {
      if (!isCurrent()) return
      error.value = 'Failed to fetch collection'
      console.error('Error fetching collection:', err)
    } finally {
      if (isCurrent()) loading.value = false
    }
  }

  /** Drops the user's collections (logout, another user). */
  const clear = () => {
    listRequests.enter()
    activeRequests.enter()
    deletedIds.clear()
    collections.value = []
    activeCollection.value = null
    error.value = null
    loading.value = false
  }
  const createCollection = async (collectionData: PostCollection) => {
    const notif = ongoingNotification('Creating collection...')
    const inSession = captureSession()
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.create(collectionData)
      if (!inSession()) return notif.dismiss()
      collections.value.push(data)
      notif.success('Collection created')
    } catch (err) {
      if (!inSession()) return notif.dismiss()
      error.value = 'Failed to create collection'
      console.error('Error creating collection:', err)
      notif.error('Failed to create collection')
    } finally {
      if (inSession()) loading.value = false
    }
  }
  const updateCollection = async (collectionId: string, collectionData: PatchCollection) => {
    const notif = ongoingNotification('Updating collection...')
    const inSession = captureSession()
    loading.value = true
    error.value = null
    try {
      const data = await collectionRepository.update(collectionId, collectionData)
      if (!inSession()) return notif.dismiss()
      const index = collections.value.findIndex((c) => c.id === collectionId)
      if (index !== -1) {
        collections.value[index] = data
      }
      if (activeCollection.value?.id === collectionId) {
        activeCollection.value = data
      }
      notif.success('Collection updated')
    } catch (err) {
      if (!inSession()) return notif.dismiss()
      error.value = 'Failed to update collection'
      console.error('Error updating collection:', err)
      notif.error('Failed to update collection')
    } finally {
      if (inSession()) loading.value = false
    }
  }
  const deleteCollection = async (collectionId: string) => {
    const notif = ongoingNotification('Deleting collection...')
    const inSession = captureSession()
    loading.value = true
    error.value = null
    try {
      await collectionRepository.remove(collectionId)
      if (!inSession()) return notif.dismiss()
      forgetDeleted([collectionId])
      notif.success('Collection deleted')
    } catch (err) {
      if (!inSession()) return notif.dismiss()
      error.value = 'Failed to delete collection'
      console.error('Error deleting collection:', err)
      notif.error(await incompleteWriteMessage(err, 'Failed to delete collection'))
    } finally {
      if (inSession()) loading.value = false
    }
  }

  const deleteManyCollections = async (collectionIds: string[]) => {
    if (collectionIds.length === 0) return
    const notif = ongoingNotification(`Deleting ${collectionIds.length} collections...`)
    const inSession = captureSession()
    // Hidden while pending so fetchCollections can't bring them back meanwhile; afterwards
    // only the deletions the backend acknowledged stay applied.
    collectionIds.forEach((id) => pendingDeleteIds.value.add(id))
    error.value = null
    try {
      const results = await Promise.allSettled(collectionIds.map((id) => collectionRepository.remove(id)))
      if (!inSession()) return notif.dismiss()
      const deleted = collectionIds.filter((_, i) => results[i].status === 'fulfilled')
      forgetDeleted(deleted)
      const failures = results.flatMap((r) => (r.status === 'rejected' ? [r.reason] : []))
      if (!failures.length) {
        notif.success(`${collectionIds.length} collection${collectionIds.length === 1 ? '' : 's'} deleted`)
      } else {
        error.value = 'Failed to delete some collections'
        console.error('Error deleting collections:', failures)
        const detail = await incompleteWriteMessage(failures[0], 'Failed to delete some collections')
        notif.error(`Deleted ${deleted.length} of ${collectionIds.length} collections. ${detail}`)
      }
    } finally {
      collectionIds.forEach((id) => pendingDeleteIds.value.delete(id))
    }
  }

  const shareManyCollections = async (collectionIds: string[], userId: string) => {
    if (collectionIds.length === 0) return
    const notif = ongoingNotification(`Sharing ${collectionIds.length} collection${collectionIds.length === 1 ? '' : 's'}...`)
    const inSession = captureSession()
    error.value = null
    const results = await Promise.allSettled(
      collectionIds.map((id) => collectionRepository.share(id, userId))
    )
    if (!inSession()) return notif.dismiss()
    const failedCount = results.filter((r) => r.status === 'rejected').length
    const succeededCount = results.length - failedCount

    results.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        const collectionIndex = collections.value.findIndex((c) => c.id === collectionIds[index])
        if (collectionIndex !== -1) {
          collections.value[collectionIndex] = result.value
        }
      }
    })

    if (failedCount === 0) {
      notif.success(`Shared ${succeededCount} collection${succeededCount === 1 ? '' : 's'}`)
    } else if (succeededCount === 0) {
      error.value = 'Failed to share the selected collections'
      console.error('Error sharing collections:', results)
      notif.error('Failed to share the selected collections')
    } else {
      error.value = `Shared ${succeededCount} of ${collectionIds.length} collections`
      console.error('Error sharing some collections:', results)
      notif.error(`Shared ${succeededCount} of ${collectionIds.length} collections — some failed`)
    }
  }

  return {
    collections: visibleCollections,
    activeCollection,
    error,
    loading,
    fetchCollections,
    fetchCollection,
    clear,
    createCollection,
    updateCollection,
    deleteCollection,
    deleteManyCollections,
    shareManyCollections
  }
})
