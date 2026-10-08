import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { Tags, PostTag, PatchTag, Tag } from 'src/models/tags'
import { useTagsRepository } from 'src/repositories/useTagsRepository'
import { ongoingNotification } from 'src/utils/notification'
import { incompleteWriteMessage } from 'src/utils/writeOutcome'
import { createContextGuard, createScope } from 'src/shared/api'

/**
 * Tag definitions of one collection. Loading another collection's tags first drops the
 * current ones, and an answer for an earlier collection (or an earlier reload) is ignored.
 */
export const useTagsStore = defineStore('tags', () => {
  const tagsRepository = useTagsRepository()
  const scope = createScope()
  const listRequests = createContextGuard()
  const tags = ref<Tags>([])
  const activeTag = ref<Tag | null>(null)
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)
  const pendingDeleteIds = ref<Set<string>>(new Set())

  const visibleTags = computed(() =>
    tags.value.filter((tag) => !pendingDeleteIds.value.has(tag.id))
  )

  const fetchTagsByCollection = async (collectionId: string) => {
    if (scope.enter(collectionId)) {
      tags.value = []
      activeTag.value = null
    }
    listRequests.enter()
    const isCurrent = listRequests.capture()
    loading.value = true
    error.value = null
    try {
      const data = await tagsRepository.getAllByCollection(collectionId)
      if (isCurrent()) tags.value = data
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
    tags.value = []
    activeTag.value = null
    error.value = null
    loading.value = false
  }

  const fetchTag = async (tagUuid: string) => {
    // const notif = ongoingNotification('Loading tag...')
    loading.value = true
    error.value = null
    try {
      const data = await tagsRepository.getById(tagUuid)
      activeTag.value = data
      // notif.success('Tag loaded')
    } catch (err) {
      error.value = 'Failed to fetch tag'
      console.error('Error fetching tag:', err)
      // notif.error('Failed to load tag')
    } finally {
      loading.value = false
    }
  }

  const createTag = async (collectionId: string, payload: PostTag) => {
    const notif = ongoingNotification('Creating tag...')
    loading.value = true
    error.value = null
    const isCurrent = scope.capture()
    try {
      const createdTag = await tagsRepository.create(collectionId, payload)
      if (isCurrent() && scope.key === collectionId) tags.value.push(createdTag)
      notif.success('Tag created')
      return createdTag
    } catch (err) {
      error.value = 'Failed to create tag'
      console.error('Error creating tag:', err)
      notif.error(await incompleteWriteMessage(err, 'Failed to create tag'))
      throw err
    } finally {
      loading.value = false
    }
  }

  const deleteTag = async (tagUuid: string) => {
    const notif = ongoingNotification('Deleting tag...')
    loading.value = true
    error.value = null
    try {
      await tagsRepository.delete(tagUuid)
      tags.value = tags.value.filter((tag) => tag.id !== tagUuid)
      notif.success('Tag deleted')
    } catch (err) {
      error.value = 'Failed to delete tag'
      console.error('Error deleting tag:', err)
      notif.error(await incompleteWriteMessage(err, 'Failed to delete tag'))
    } finally {
      loading.value = false
    }
  }

  const deleteManyTags = async (tagUuids: string[]) => {
    if (tagUuids.length === 0) return
    const notif = ongoingNotification(`Deleting ${tagUuids.length} tags...`)
    tagUuids.forEach((id) => pendingDeleteIds.value.add(id))
    tags.value = tags.value.filter((tag) => !tagUuids.includes(tag.id))
    error.value = null
    try {
      await Promise.all(tagUuids.map((id) => tagsRepository.delete(id)))
      notif.success(`${tagUuids.length} tag${tagUuids.length === 1 ? '' : 's'} deleted`)
    } catch (err) {
      error.value = 'Failed to delete some tags'
      console.error('Error deleting tags:', err)
      notif.error(await incompleteWriteMessage(err, 'Failed to delete some tags'))
      throw err
    } finally {
      tagUuids.forEach((id) => pendingDeleteIds.value.delete(id))
    }
  }

  const updateTag = async (tagUuid: string, payload: PatchTag) => {
    const notif = ongoingNotification('Updating tag...')
    loading.value = true
    error.value = null
    try {
      const updatedTag = await tagsRepository.update(tagUuid, payload)
      const existingIndex = tags.value.findIndex((tag) => tag.id === updatedTag.id)
      if (existingIndex >= 0) {
        tags.value[existingIndex] = updatedTag
      }
      notif.success('Tag updated')
      return updatedTag
    } catch (err) {
      error.value = 'Failed to update tag'
      console.error('Error updating tag:', err)
      notif.error('Failed to update tag')
      throw err
    } finally {
      loading.value = false
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
