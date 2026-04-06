import { defineStore } from 'pinia'
import { ref } from 'vue'

import { TagCreate, Tags } from 'src/models/tags'
import TagsRepository from 'src/repositories/TagsRepository'
import { ongoingNotification } from 'src/utils/notification'

export const useTagsStore = defineStore('tags', () => {
  const tags = ref<Tags>([])
  const error = ref<string | null>(null)
  const loading = ref<boolean>(false)

  const fetchTags = async (collectionId: string) => {
    const notif = ongoingNotification('Loading tags...')
    loading.value = true
    error.value = null
    try {
      const data = await TagsRepository.getByCollection(collectionId)
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

  const createTag = async (collectionId: string, payload: TagCreate) => {
    const notif = ongoingNotification('Creating tag...')
    loading.value = true
    error.value = null
    try {
      const createdTag = await TagsRepository.createInCollection(collectionId, payload)
      const existingIndex = tags.value.findIndex((tag) => tag.tagUuid === createdTag.tagUuid)
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

  return {
    tags,
    error,
    loading,
    fetchTags,
    createTag
  }
})
