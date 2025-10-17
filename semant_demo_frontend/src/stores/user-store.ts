import { api } from 'boot/axios'
import { defineStore } from 'pinia'
import { User } from 'src/models'
import { actionNotification } from 'src/utils/notification'

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
    isNotAdmin: (state) => {
      return state.user?.user_type !== 'admin'
    }
  },
  actions: {
    async setToken () {
      this.authorized = true
      this.testAuthentication()
    },
    async testAuthentication () {
      try {
        const response: User = await api.get('me')
          .then(response => response.data)
          .catch(error => {
            if (error.response.status === 401) {
              Promise.resolve(null)
            }
          })
        if (response != null) {
          this.authorized = true
          this.user = response
        } else {
          this.authorized = false
          this.user = null
        }
      } catch (error: any) {
        useErrorStore().reportError('ERROR', 'Failed authentication test.', error)
      }
    },
    signOut () {
      this.authorized = false
      this.user = null
      localStorage.clear()
      document.cookie = 'Authorization=;  Max-Age=0'
    },
    async getAllUsers () {
      const dismiss = actionNotification('Fetching all users.')
      try {
        const response = await api.get('/user')
        return new Map<string, User>(response.data.map((user: User) => [user.id, user]))
      } catch (error: any) {
        useErrorStore().reportError('ERROR', 'Failed to fetch all users.', error)
      } finally {
        dismiss()
      }
    }
  }
})
