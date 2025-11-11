import { api } from 'boot/axios'
import { defineStore } from 'pinia'
import { Collection, GetUserCollectionsResponse } from 'src/models'
import { actionNotification } from 'src/utils/notification'

interface CollectionStoreState {
    collections: Collection[]
    userId: string
}

export const useCollectionStore = defineStore('collections', {
  state: (): CollectionStoreState => ({
    collections: [],
    userId: ""
  }),
  getters: {
    isEmpty: (state) => {
      return state.collections.length === 0
    }
  },
  actions: {
    setUser (userId: string) {
      this.userId = userId
    },

    async fetchCollections (userId: string) {
      // fetches all collections for current user from weaviate
      try {
        const { data } = await api.get<CollectionStoreState>('/collections', { params: { userId } })
        console.log('Collections fetched:', data)
        this.collections = data.collections
      } catch (error) {
        console.error('Error fetching collections:', error)
      }
    }
  }
})
