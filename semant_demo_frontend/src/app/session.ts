import { watch } from 'vue'
import { useUserStore } from 'src/stores/user-store'
import { useCollectionsStore } from 'src/stores/collectionsStore'
import { useDocumentsStore } from 'src/stores/documentsStore'
import { useTagsStore } from 'src/stores/tagsStore'
import { useTagSpansStore } from 'src/stores/tagSpansStore'
import { useChunksStore } from 'src/stores/chunksStore'
import { useCollectionStatsStore } from 'src/stores/collectionStatsStore'
import useAiAssistance from 'src/composables/useAiAssistance'
import { endSession } from 'src/shared/api'

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
  useCollectionsStore().clear()
}

/**
 * Clears user-scoped state when the signed-in user signs out or another user signs in.
 * Restoring the session at startup (no user -> user) keeps what pages already loaded
 * with the stored token.
 */
export function useSessionScope (): void {
  const userStore = useUserStore()
  watch(() => userStore.getUserId, (userId, previousUserId) => {
    if (previousUserId && userId !== previousUserId) clearUserScopedState()
  })
}
