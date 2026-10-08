import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { Tags, PostTag, PatchTag, Tag } from 'src/models/tags'
import { useTagsRepository } from 'src/repositories/useTagsRepository'
import { ongoingNotification } from 'src/utils/notification'
import { incompleteWriteMessage } from 'src/utils/writeOutcome'
import { captureSession, createContextGuard, createScope } from 'src/shared/api'

/** Outcome of a bulk deletion: only `deleted` were acknowledged by the backend. */
export interface DeleteManyResult {
  deleted: string[]
  failed: string[]
}

/**
 * Tag definitions of one collection. Loading another collection's tags first drops the
 * current ones, and an answer for an earlier collection (or an earlier reload) is ignored.
 * Nothing started before a sign-out changes the store afterwards (`captureSession`).
 */
export const useTagsStore = defineStore('tags', () => {
  const tagsRepository = useTagsRepository()
  const scope = createScope()
  const listRequests = createContextGuard()
  const tagRequests = createContextGuard()
  const tags = ref<Tags>([])
  const activeTag = ref<Tag | null>(null)
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)
  const pendingDeleteIds = ref<Set<string>>(new Set())
  // Deletions the backend acknowledged in this scope. Tag ids are never reused, so a list
  // answer that predates a deletion cannot bring the tag back.
  const deletedIds = new Set<string>()

  const visibleTags = computed(() =>
    tags.value.filter((tag) => !pendingDeleteIds.value.has(tag.id))
  )

  const forgetDeleted = (ids: string[]) => {
    ids.forEach((id) => deletedIds.add(id))
    tags.value = tags.value.filter((tag) => !deletedIds.has(tag.id))
    if (activeTag.value && deletedIds.has(activeTag.value.id)) activeTag.value = null
  }

  const fetchTagsByCollection = async (collectionId: string) => {
    if (scope.enter(collectionId)) {
      tags.value = []
      activeTag.value = null
      deletedIds.clear()
    }
    listRequests.enter()
    const isCurrent = listRequests.capture()
    loading.value = true
    error.value = null
    try {
      const data = await tagsRepository.getAllByCollection(collectionId)
      if (isCurrent()) tags.value = data.filter((tag) => !deletedIds.has(tag.id))
    } catch (err) {
      if (!isCurrent()) return
      error.value = 'Failed to fetch tags'
      console.error('Error fetching tags:', err)
    } finally {
      if (isCurrent()) loading.value = false
    }
  }

  /** Drops all tags (logout). */
  const clear = () => {
    scope.reset()
    listRequests.enter()
    tagRequests.enter()
    deletedIds.clear()
    tags.value = []
    activeTag.value = null
    error.value = null
    loading.value = false
  }

  const fetchTag = async (tagUuid: string) => {
    tagRequests.enter()
    const isCurrent = tagRequests.capture()
    const inSession = captureSession()
    const applies = () => isCurrent() && inSession()
    if (activeTag.value?.id !== tagUuid) activeTag.value = null
    loading.value = true
    error.value = null
    try {
      const data = await tagsRepository.getById(tagUuid)
      if (applies()) activeTag.value = data
    } catch (err) {
      if (!applies()) return
      error.value = 'Failed to fetch tag'
      console.error('Error fetching tag:', err)
    } finally {
      if (applies()) loading.value = false
    }
  }

  const createTag = async (collectionId: string, payload: PostTag) => {
    const notif = ongoingNotification('Creating tag...')
    const inScope = scope.capture()
    const inSession = captureSession()
    loading.value = true
    error.value = null
    try {
      const createdTag = await tagsRepository.create(collectionId, payload)
      if (!inSession()) {
        notif.dismiss()
        return createdTag
      }
      if (inScope() && scope.key === collectionId) tags.value.push(createdTag)
      notif.success('Tag created')
      return createdTag
    } catch (err) {
      if (!inSession()) {
        notif.dismiss()
        throw err
      }
      error.value = 'Failed to create tag'
      console.error('Error creating tag:', err)
      notif.error(await incompleteWriteMessage(err, 'Failed to create tag'))
      throw err
    } finally {
      if (inSession()) loading.value = false
    }
  }

  const deleteTag = async (tagUuid: string) => {
    const notif = ongoingNotification('Deleting tag...')
    const inScope = scope.capture()
    const inSession = captureSession()
    loading.value = true
    error.value = null
    try {
      await tagsRepository.delete(tagUuid)
      if (!inSession()) {
        notif.dismiss()
        return
      }
      if (inScope()) forgetDeleted([tagUuid])
      notif.success('Tag deleted')
    } catch (err) {
      if (!inSession()) {
        notif.dismiss()
        return
      }
      error.value = 'Failed to delete tag'
      console.error('Error deleting tag:', err)
      notif.error(await incompleteWriteMessage(err, 'Failed to delete tag'))
    } finally {
      if (inSession()) loading.value = false
    }
  }

  /**
   * Deletes the tags one by one (best effort). The selected tags are hidden while their
   * deletions run; afterwards only the acknowledged deletions are applied, failed tags stay
   * visible and are reported. Resolves when every deletion has finished.
   */
  const deleteManyTags = async (tagUuids: string[]): Promise<DeleteManyResult> => {
    if (tagUuids.length === 0) return { deleted: [], failed: [] }
    const notif = ongoingNotification(`Deleting ${tagUuids.length} tags...`)
    const inScope = scope.capture()
    const inSession = captureSession()
    tagUuids.forEach((id) => pendingDeleteIds.value.add(id))
    error.value = null
    try {
      const results = await Promise.allSettled(tagUuids.map((id) => tagsRepository.delete(id)))
      const deleted = tagUuids.filter((_, i) => results[i].status === 'fulfilled')
      const failed = tagUuids.filter((_, i) => results[i].status === 'rejected')
      if (!inSession()) {
        notif.dismiss()
        return { deleted, failed }
      }
      if (inScope()) forgetDeleted(deleted)
      if (!failed.length) {
        notif.success(`${deleted.length} tag${deleted.length === 1 ? '' : 's'} deleted`)
      } else {
        const failures = results.flatMap((r) => (r.status === 'rejected' ? [r.reason] : []))
        error.value = 'Failed to delete some tags'
        console.error('Error deleting tags:', failures)
        const detail = await incompleteWriteMessage(failures[0], 'The others could not be deleted.')
        notif.error(`Deleted ${deleted.length} of ${tagUuids.length} tags. ${detail}`)
      }
      return { deleted, failed }
    } finally {
      tagUuids.forEach((id) => pendingDeleteIds.value.delete(id))
    }
  }

  const updateTag = async (tagUuid: string, payload: PatchTag) => {
    const notif = ongoingNotification('Updating tag...')
    const inScope = scope.capture()
    const inSession = captureSession()
    loading.value = true
    error.value = null
    try {
      const updatedTag = await tagsRepository.update(tagUuid, payload)
      if (!inSession()) {
        notif.dismiss()
        return updatedTag
      }
      if (inScope()) {
        const existingIndex = tags.value.findIndex((tag) => tag.id === updatedTag.id)
        if (existingIndex >= 0) {
          tags.value[existingIndex] = updatedTag
        }
        if (activeTag.value?.id === updatedTag.id) activeTag.value = updatedTag
      }
      notif.success('Tag updated')
      return updatedTag
    } catch (err) {
      if (!inSession()) {
        notif.dismiss()
        throw err
      }
      error.value = 'Failed to update tag'
      console.error('Error updating tag:', err)
      notif.error('Failed to update tag')
      throw err
    } finally {
      if (inSession()) loading.value = false
    }
  }

  return {
    tags: visibleTags,
    error,
    loading,
    activeTag,
    deleteTag,
    deleteManyTags,
    updateTag,
    fetchTagsByCollection,
    clear,
    createTag,
    fetchTag
  }
})
