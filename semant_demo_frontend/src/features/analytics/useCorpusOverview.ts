import { getCurrentScope, onScopeDispose, ref, shallowRef } from 'vue'
import type { CorpusOverview } from 'src/generated/api'
import { apiErrorMessage, isAbortError, useApi } from 'src/shared/api'

/** After this many milliseconds without an answer the page says that loading takes long. */
export const SLOW_AFTER_MS = 4000

/**
 * The corpus overview of the page using it. `load()` (also a retry) aborts an earlier
 * request, whose late answer is ignored; leaving the page aborts the request in flight.
 * A failure keeps no stale overview: the page shows the error instead of old numbers.
 */
export function useCorpusOverview () {
  const api = useApi().default
  const overview = shallowRef<CorpusOverview | null>(null)
  const loading = ref(false)
  const slow = ref(false)
  const error = ref<string | null>(null)

  let controller: AbortController | null = null
  let slowTimer: ReturnType<typeof setTimeout> | null = null

  function stop () {
    controller?.abort()
    controller = null
    if (slowTimer) clearTimeout(slowTimer)
    slowTimer = null
  }

  async function load () {
    stop()
    const current = new AbortController()
    controller = current
    loading.value = true
    slow.value = false
    error.value = null
    slowTimer = setTimeout(() => { slow.value = true }, SLOW_AFTER_MS)
    try {
      const result = await api.corpusOverviewApiAnalyticsCorpusOverviewGet({ signal: current.signal })
      if (controller !== current) return
      overview.value = result
    } catch (e) {
      if (controller !== current || isAbortError(e)) return
      console.error('Loading the corpus overview failed', e)
      const message = await apiErrorMessage(e, 'The corpus overview could not be loaded.')
      if (controller !== current) return
      overview.value = null
      error.value = message
    } finally {
      if (controller === current) {
        stop()
        loading.value = false
        slow.value = false
      }
    }
  }

  if (getCurrentScope()) onScopeDispose(stop)

  return { overview, loading, slow, error, load }
}
