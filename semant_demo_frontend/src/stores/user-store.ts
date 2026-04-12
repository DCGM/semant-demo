import { api } from 'boot/axios'
import { defineStore } from 'pinia'
import type { User } from 'src/models'

const TOKEN_KEY = 'auth_token'

interface UserStoreState {
  user: User | null
  token: string | null
}

export const useUserStore = defineStore('user', {
  state: (): UserStoreState => ({
    user: null,
    token: localStorage.getItem(TOKEN_KEY)
  }),

  getters: {
    isLoggedIn: (state) => !!state.token && !!state.user,
    getUserId: (state) => state.user?.id,
    getEmail: (state) => state.user?.email,
    getDisplayName: (state) => state.user?.name || state.user?.username || state.user?.email || ''
  },

  actions: {
    async register (email: string, password: string, username: string, name: string, institution?: string): Promise<void> {
      await api.post('/auth/register', { email, password, username, name, institution })
    },

    async login (email: string, password: string): Promise<void> {
      const params = new URLSearchParams()
      params.append('username', email)
      params.append('password', password)
      const response = await api.post('/auth/jwt/login', params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })
      const token: string = response.data.access_token
      this.token = token
      localStorage.setItem(TOKEN_KEY, token)
      await this.fetchCurrentUser()
    },

    async logout (): Promise<void> {
      try {
        if (this.token) {
          await api.post(
            '/auth/jwt/logout',
            {},
            { headers: { Authorization: `Bearer ${this.token}` } }
          )
        }
      } finally {
        this.token = null
        this.user = null
        localStorage.removeItem(TOKEN_KEY)
      }
    },

    async fetchCurrentUser (): Promise<void> {
      if (!this.token) return
      try {
        const response = await api.get('/users/me', {
          headers: { Authorization: `Bearer ${this.token}` }
        })
        this.user = response.data as User
      } catch {
        // Token invalid or expired
        this.token = null
        this.user = null
        localStorage.removeItem(TOKEN_KEY)
      }
    },

    async updateUser (data: { email?: string; password?: string; name?: string; institution?: string | null }): Promise<void> {
      if (!this.token) throw new Error('Not authenticated')
      const response = await api.patch('/users/me', data, {
        headers: { Authorization: `Bearer ${this.token}` }
      })
      this.user = response.data as User
    }
  }
})
