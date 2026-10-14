import { defineStore } from 'pinia'
import type { UserRead } from 'src/generated/api'
import { clearAuthToken, errorStatus, getAuthToken, setAuthToken, tokenSubject, useApi } from 'src/shared/api'

// The restore of a stored token in flight, shared by everyone who waits for that token.
let restoring: { token: string, promise: Promise<void> } | null = null

interface UserStoreState {
  user: UserRead | null
  token: string | null
  /** The token whose user could not be read for another reason than a rejected token. */
  unconfirmedToken: string | null
}

export const useUserStore = defineStore('user', {
  state: (): UserStoreState => ({
    user: null,
    token: getAuthToken(),
    unconfirmedToken: null
  }),

  getters: {
    /** A verified session: the user's account was read with the current token. */
    isLoggedIn: (state) => !!state.token && !!state.user,
    /**
     * A session whose token is stored but not verified yet (restore under way or failed).
     * Neither signed in nor signed out: user data stays hidden, Sign out stays available.
     */
    awaitingVerification: (state) => !!state.token && !state.user,
    /**
     * The stored session could not be verified (offline, server error): the token is kept
     * and the session awaits verification until a retry reads the user's account.
     */
    restoreFailed: (state) => !!state.token && !state.user && state.unconfirmedToken === state.token,
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

    /**
     * Rejects also when the new session's account cannot be read afterwards (offline, server
     * error); that session is dropped again, so the user simply signs in once more.
     */
    async login (email: string, password: string): Promise<void> {
      const { accessToken } = await useApi().auth.authJwtLoginApiAuthJwtLoginPost({ username: email, password })
      this.token = accessToken
      setAuthToken(accessToken)
      try {
        const user = await useApi().users.usersCurrentUserApiUsersMeGet({ headers: { Authorization: `Bearer ${accessToken}` } })
        if (this.token === accessToken) this.user = user
      } catch (error) {
        if (this.token === accessToken) this.forgetSession()
        throw error
      }
    },

    /**
     * Ends this session, also when the server request fails. If the session changed while
     * the request was pending (another tab signed in or out), that newer session stays.
     * A session awaiting verification ends here at once, without asking the server.
     */
    async logout (): Promise<void> {
      const token = this.token
      if (!this.user) {
        this.forgetSession()
        return
      }
      try {
        if (token) await useApi().auth.authJwtLogoutApiAuthJwtLogoutPost()
      } finally {
        if (this.token === token) this.forgetSession()
      }
    },

    /**
     * Restores the session of a stored token once (layout start-up and the first guarded
     * navigation share one request). Resolves at once without a token or when already done.
     * A restore for another token (after sign-out or a new sign-in) never reuses an older one.
     * After a failed restore (`restoreFailed`) only an explicit `retry` asks the server again.
     */
    restoreSession ({ retry = false }: { retry?: boolean } = {}): Promise<void> {
      const token = this.token
      if (!token || this.user || (this.restoreFailed && !retry)) return Promise.resolve()
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
     * Reads the user of the current token. Only a 401 (expired, revoked or otherwise invalid
     * token) ends the session; a network or server failure keeps the token for a later
     * restore (`restoreFailed`, which stays set while a retry is under way). The answer (or
     * failure) applies only while that token is still the session's: a late answer after
     * sign-out or a switch to another account neither restores the old user nor ends the
     * new session.
     */
    async fetchCurrentUser (): Promise<void> {
      const token = this.token
      if (!token) return
      try {
        // Sent with this token explicitly, so the answer belongs to the token checked below.
        const user = await useApi().users.usersCurrentUserApiUsersMeGet({ headers: { Authorization: `Bearer ${token}` } })
        if (this.token !== token) return
        this.user = user
        this.unconfirmedToken = null
      } catch (error) {
        if (this.token !== token) return
        if (errorStatus(error) === 401) this.forgetSession()
        else this.unconfirmedToken = token
      }
    },

    async updateUser (data: { email?: string; password?: string; name?: string; institution?: string | null }): Promise<void> {
      const token = this.token
      if (!token) throw new Error('Not authenticated')
      const user = await useApi().users.usersPatchCurrentUserApiUsersMePatch({ userUpdate: data })
      // A late answer after sign-out or an account switch must not bring the old user back.
      if (this.token === token) this.user = user
    },

    /**
     * Follows a sign-in, sign-out or account switch made in another browser tab: the stored
     * token is already the new one, so it is adopted, not written back. A new token of the
     * signed-in user (signed in again, or renewed) keeps the session and its data. Any
     * other token, or one whose user cannot be read, ends the old session first (clearing
     * its data) before the new token's user is restored.
     */
    async adoptStoredToken (token: string | null): Promise<void> {
      if (token === this.token) return
      if (token && this.user && tokenSubject(token) === this.user.id) {
        this.token = token
        return
      }
      this.token = null
      this.user = null
      if (!token) return
      this.token = token
      await this.restoreSession()
    },

    /**
     * Ends this tab's session. The stored token is removed only while it is still this
     * session's: a newer token another tab stored meanwhile (sign-in, account switch) is
     * kept, and this tab adopts it when the storage event arrives.
     */
    forgetSession (): void {
      const token = this.token
      this.token = null
      this.user = null
      this.unconfirmedToken = null
      if (token) clearAuthToken(token)
    }
  }
})
