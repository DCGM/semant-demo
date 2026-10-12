import { defineStore } from 'pinia'
import type { UserRead } from 'src/generated/api'
import { clearAuthToken, getAuthToken, setAuthToken, useApi } from 'src/shared/api'

// The restore of a stored token in flight, shared by everyone who waits for that token.
let restoring: { token: string, promise: Promise<void> } | null = null

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

    /**
     * Restores the session of a stored token once (layout start-up and the first guarded
     * navigation share one request). Resolves at once without a token or when already done.
     * A restore for another token (after sign-out or a new sign-in) never reuses an older one.
     */
    restoreSession (): Promise<void> {
      const token = this.token
      if (!token || this.user) return Promise.resolve()
      if (restoring?.token !== token) {
        const entry = {
          token,
          promise: this.fetchCurrentUser().finally(() => {
            if (restoring === entry) restoring = null
          })
        }
        restoring = entry
      }
      return restoring.promise
    },

    /**
     * Reads the user of the current token. The answer (or failure) applies only while that
     * token is still the session's: a late answer after sign-out or a switch to another
     * account neither restores the old user nor ends the new session.
     */
    async fetchCurrentUser (): Promise<void> {
      const token = this.token
      if (!token) return
      try {
        // Sent with this token explicitly, so the answer belongs to the token checked below.
        const user = await useApi().users.usersCurrentUserApiUsersMeGet({ headers: { Authorization: `Bearer ${token}` } })
        if (this.token === token) this.user = user
      } catch {
        // Token invalid or expired
        if (this.token === token) this.forgetSession()
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
