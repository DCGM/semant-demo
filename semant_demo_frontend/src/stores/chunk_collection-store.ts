import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useApi } from 'src/composables/useApi'
import type { Collection } from 'src/generated/api'

export const useCollectionStore = defineStore('collections', () => {
  const api = useApi().default

  const collections = ref<Collection[]>([])
  const userId = ref('')

  const isEmpty = computed(() => collections.value.length === 0)

  const setUser = (newUserId: string) => {
    userId.value = newUserId
  }

  const fetchCollections = async (currentUserId: string) => {
    // fetches all collections for current user from weaviate
    try {
      const response = await api.fetchCollectionsApiCollectionsGet({ userId: currentUserId })
      console.log('Collections fetched:', response)
      collections.value = response.collections
    } catch (error) {
      console.error('Error fetching collections:', error)
    }
  }

  return {
    collections,
    userId,
    isEmpty,
    setUser,
    fetchCollections
  }
})
