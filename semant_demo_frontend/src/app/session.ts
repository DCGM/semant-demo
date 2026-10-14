import { onScopeDispose, watch } from 'vue'
import { Notify } from 'quasar'
import { useUserStore } from 'src/features/auth/userStore'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import { useDocumentsStore } from 'src/features/documents/documentsStore'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import { useTagSpansStore } from 'src/features/annotations/tagSpansStore'
import { useChunksStore } from 'src/features/documents/chunksStore'
import { useCollectionStatsStore } from 'src/features/user_collections/collectionStatsStore'
import useAiAssistance from 'src/features/annotations/useAiAssistance'
import { endSession, onStoredTokenChange, onUnauthorized } from 'src/shared/api'

/**
 * Forgets everything loaded for the signed-in user: collections, documents, tags,
 * annotations, statistics and running AI suggestion runs. Requests still under way
 * for that user are ignored when they answer.
 */
export function clearUserScopedState (): void {
  endSession()
  useAiAssistance().reset()
  useTagSpansStore().clearAll()
  useTagsStore().clear()
  useChunksStore().clear()
  useDocumentsStore().clear()
  useCollectionStatsStore().clear()
  useUserCollectionsStore().clear()
}

/**
 * Clears user-scoped state when the signed-in user signs out or another user signs in.
 * Restoring the session at startup (no user -> user) keeps what pages already loaded
 * with the stored token. A 401 answer to a request sent with the current token (expired
 * or revoked) signs the user out locally; answers for an earlier token are ignored.
 * Signing in, out or into another account in another browser tab is followed here too:
 * the old user's data is cleared and protected routes are left (`router/authGuard.ts`);
 * a new token of the same user (signed in again or renewed) keeps the session.
 * A stored session that could not be confirmed (offline, server error) is kept, not ended:
 * the user is told so, can retry, and it is retried when the browser comes back online.
 */
export function useSessionScope (): void {
  const userStore = useUserStore()
  const stopUnauthorized = onUnauthorized((token) => {
    if (token !== userStore.token) return
    const wasLoggedIn = userStore.isLoggedIn
    userStore.forgetSession()
    if (wasLoggedIn) Notify.create({ type: 'warning', position: 'top', message: 'Your session has expired. Please log in again.' })
  })
  const stopTokenSync = onStoredTokenChange((token) => {
    const previousUserId = userStore.isLoggedIn ? userStore.getUserId : undefined
    if (token === userStore.token) return
    void userStore.adoptStoredToken(token)
    if (previousUserId && userStore.getUserId !== previousUserId) {
      Notify.create({
        type: 'info',
        position: 'top',
        message: token ? 'Your session changed in another tab.' : 'You signed out in another tab.'
      })
    }
  })
  let dismissRestoreNotice: (() => void) | null = null
  const retryRestore = () => { if (userStore.restoreFailed) void userStore.restoreSession({ retry: true }) }
  const stopRestoreNotice = watch(() => userStore.restoreFailed, (failed) => {
    dismissRestoreNotice?.()
    dismissRestoreNotice = failed
      ? Notify.create({
        type: 'warning',
        position: 'top',
        timeout: 0,
        message: 'Could not restore your session: the server is unreachable or failing. Your sign-in is kept on this device.',
        actions: [
          { label: 'Retry', color: 'white', handler: retryRestore },
          { icon: 'close', color: 'white', round: true }
        ]
      })
      : null
  })
  if (typeof window !== 'undefined') window.addEventListener('online', retryRestore)
  onScopeDispose(() => {
    stopUnauthorized()
    stopTokenSync()
    stopRestoreNotice()
    dismissRestoreNotice?.()
    if (typeof window !== 'undefined') window.removeEventListener('online', retryRestore)
  })
  watch(() => userStore.getUserId, (userId, previousUserId) => {
    if (previousUserId && userId !== previousUserId) clearUserScopedState()
  })
}
