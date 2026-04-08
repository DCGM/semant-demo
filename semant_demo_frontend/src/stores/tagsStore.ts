import { defineStore } from 'pinia'
import { ref } from 'vue'

import { Tags, PostTag } from 'src/models/tags'
import { useTagsRepository } from 'src/repositories/useTagsRepository'
import { ongoingNotification } from 'src/utils/notification'
import { PatchTag } from 'src/generated/api'

export const useTagsStore = defineStore('tags', () => {
  const tagsRepository = useTagsRepository()
  const tags = ref<Tags>([])
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)

  const fetchTags = async (collectionId: string) => {
    const notif = ongoingNotification('Loading tags...')
    loading.value = true
    error.value = null
    try {
      const data = await tagsRepository.getByCollection(collectionId)
      tags.value = data
      notif.success('Tags loaded')
    } catch (err) {
      error.value = 'Failed to fetch tags'
      console.error('Error fetching tags:', err)
      notif.error('Failed to load tags')
    } finally {
      loading.value = false
    }
  }

  const createTag = async (collectionId: string, payload: PostTag) => {
    const notif = ongoingNotification('Creating tag...')
    loading.value = true
    error.value = null
    try {
      const createdTag = await tagsRepository.createInCollection(collectionId, payload)
      const existingIndex = tags.value.findIndex((tag) => tag.id === createdTag.id)
      if (existingIndex >= 0) {
        tags.value[existingIndex] = createdTag
      } else {
        tags.value = [createdTag, ...tags.value]
      }
      notif.success('Tag created')
      return createdTag
    } catch (err) {
      error.value = 'Failed to create tag'
      console.error('Error creating tag:', err)
      notif.error('Failed to create tag')
      throw err
    } finally {
      loading.value = false
    }
  }

  const deleteTag = async (collectionId: string, tagUuid: string) => {
    const notif = ongoingNotification('Deleting tag...')
    loading.value = true
    error.value = null
    try {
      await tagsRepository.deleteFromCollection(collectionId, tagUuid)
      tags.value = tags.value.filter((tag) => tag.id !== tagUuid)
      notif.success('Tag deleted')
    } catch (err) {
      error.value = 'Failed to delete tag'
      console.error('Error deleting tag:', err)
      notif.error('Failed to delete tag')
    } finally {
      loading.value = false
    }
  }

  const updateTag = async (collectionId: string, tagUuid: string, payload: PatchTag) => {
    const notif = ongoingNotification('Updating tag...')
    loading.value = true
    error.value = null
    try {
      const updatedTag = await tagsRepository.updateInCollection(collectionId, tagUuid, payload)
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
    tags,
    error,
    loading,
    deleteTag,
    updateTag,
    fetchTags,
    createTag
  }
})
