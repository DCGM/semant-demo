import { api } from 'boot/axios'
import { defineStore } from 'pinia'
import { User } from 'src/models'
import { actionNotification } from 'src/utils/notification'
import { useCollectionStore } from 'src/stores/chunk_collection-store'

interface UserStoreState {
  user: null | User
  authorized: boolean
}

export const useUserStore = defineStore('user', {
  state: (): UserStoreState => ({
    user: null,
    authorized: false
  }),
  getters: {
    getUserId: (state) => {
      return state.user?.id
    }
  },
  actions: {
    setUser (userId: string) {
      this.user = { id: userId } as User
      const collectionStore = useCollectionStore()
      collectionStore.setUser(userId)
    }
  }
})
