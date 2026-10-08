import { defineStore } from 'pinia'
import type { UserRead } from 'src/generated/api'
import { clearAuthToken, getAuthToken, setAuthToken, useApi } from 'src/shared/api'

interface UserStoreState {
  user: UserRead | null
  token: string | null
}

export const useUserStore = defineStore('user', {
  state: (): UserStoreState => ({
    user: null,
    token: getAuthToken()
  }),

  getters: {
    isLoggedIn: (state) => !!state.token && !!state.user,
    getUserId: (state) => state.user?.id,
    getEmail: (state) => state.user?.email,
    getDisplayName: (state) => state.user?.name || state.user?.username || state.user?.email || ''
  },

  actions: {
    async register (email: string, password: string, username: string, name: string, institution?: string): Promise<void> {
      await useApi().auth.registerRegisterApiAuthRegisterPost({
        userCreate: { email, password, username, name, institution }
      })
    },

    async login (email: string, password: string): Promise<void> {
      const { accessToken } = await useApi().auth.authJwtLoginApiAuthJwtLoginPost({ username: email, password })
      this.token = accessToken
      setAuthToken(accessToken)
      await this.fetchCurrentUser()
    },

    async logout (): Promise<void> {
      try {
        if (this.token) await useApi().auth.authJwtLogoutApiAuthJwtLogoutPost()
      } finally {
        this.forgetSession()
      }
    },

    async fetchCurrentUser (): Promise<void> {
      if (!this.token) return
      try {
        this.user = await useApi().users.usersCurrentUserApiUsersMeGet()
      } catch {
        // Token invalid or expired
        this.forgetSession()
      }
    },

    async updateUser (data: { email?: string; password?: string; name?: string; institution?: string | null }): Promise<void> {
      if (!this.token) throw new Error('Not authenticated')
      this.user = await useApi().users.usersPatchCurrentUserApiUsersMePatch({ userUpdate: data })
    },

    forgetSession (): void {
      this.token = null
      this.user = null
      clearAuthToken()
    }
  }
})
