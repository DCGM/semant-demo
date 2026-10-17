import { onScopeDispose, watch } from 'vue'
import { useUserStore } from 'src/features/auth/userStore'
import { onAiOperation } from 'src/shared/api'
import { useQuotaStore, type QuotaPrincipal } from './quotaStore'

/**
 * Keeps the shown allowance the current principal's: a guest's while signed out, the
 * account's once its session is verified, nobody's while a stored session awaits
 * verification. Signing in, out or into another account (also in another tab) forgets the
 * previous allowance before the next one is read. Reads it again after each AI operation.
 */
export function useQuotaScope (): void {
  const userStore = useUserStore()
  const quota = useQuotaStore()
  const principalKey = () => {
    if (userStore.isLoggedIn) return `account:${userStore.getUserId}`
    return userStore.awaitingVerification ? null : 'guest'
  }
  watch(principalKey, (key) => {
    const principal: QuotaPrincipal = key === null ? null : key === 'guest' ? 'guest' : 'account'
    void quota.follow(principal)
  }, { immediate: true })
  const stop = onAiOperation(() => { void quota.refresh() })
  onScopeDispose(() => {
    stop()
    void quota.follow(null)
  })
}
