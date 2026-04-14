import { defineStore } from 'pinia'
import { ref } from 'vue'

import { Tags, PostTag, PatchTag, Tag } from 'src/models/tags'
import { useTagsRepository } from 'src/repositories/useTagsRepository'
import { ongoingNotification } from 'src/utils/notification'

export const useTagsStore = defineStore('tags', () => {
  const tagsRepository = useTagsRepository()
  const tags = ref<Tags>([])
  const activeTag = ref<Tag | null>(null)
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)

  const fetchTagsByCollection = async (collectionId: string) => {
    const notif = ongoingNotification('Loading tags...')
    loading.value = true
    error.value = null
    try {
      const data = await tagsRepository.getAllByCollection(collectionId)
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

  const fetchTag = async (tagUuid: string) => {
    const notif = ongoingNotification('Loading tag...')
    loading.value = true
    error.value = null
    try {
      const data = await tagsRepository.getById(tagUuid)
      activeTag.value = data
      notif.success('Tag loaded')
    } catch (err) {
      error.value = 'Failed to fetch tag'
      console.error('Error fetching tag:', err)
      notif.error('Failed to load tag')
    } finally {
      loading.value = false
    }
  }

  const createTag = async (collectionId: string, payload: PostTag) => {
    const notif = ongoingNotification('Creating tag...')
    loading.value = true
    error.value = null
    try {
      const createdTag = await tagsRepository.create(collectionId, payload)
      tags.value.push(createdTag)
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
      notif.error('Failed to delete tag')
    } finally {
      loading.value = false
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
    tags,
    error,
    loading,
    activeTag,
    deleteTag,
    updateTag,
    fetchTagsByCollection,
    createTag,
    fetchTag
  }
})
