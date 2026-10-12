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
import { endSession, onUnauthorized } from 'src/shared/api'

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
 */
export function useSessionScope (): void {
  const userStore = useUserStore()
  const stopUnauthorized = onUnauthorized((token) => {
    if (token !== userStore.token) return
    const wasLoggedIn = userStore.isLoggedIn
    userStore.forgetSession()
    if (wasLoggedIn) Notify.create({ type: 'warning', position: 'top', message: 'Your session has expired. Please log in again.' })
  })
  onScopeDispose(stopUnauthorized)
  watch(() => userStore.getUserId, (userId, previousUserId) => {
    if (previousUserId && userId !== previousUserId) clearUserScopedState()
  })
}
