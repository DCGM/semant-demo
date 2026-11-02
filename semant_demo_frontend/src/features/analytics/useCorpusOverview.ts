import { getCurrentScope, onScopeDispose, ref, shallowRef } from 'vue'
import type { CorpusDistributions, DocumentFilters } from 'src/generated/api'
import { apiErrorMessage, errorStatus, isAbortError, useApi } from 'src/shared/api'
import { isUnfiltered } from './corpusOverview'

/** After this many milliseconds without an answer the page says that loading takes long. */
export const SLOW_AFTER_MS = 4000

/**
 * The document counts of the page using it, for the filters last requested (`filters`; once
 * answered, as the server normalized them, so that they hold the values the counts and their
 * filter chips show and every change can be built on them, #548). `load(filters)` aborts an earlier request, whose late answer is ignored; `retry()` loads
 * the same filters again; leaving the page aborts the request in flight. A failure keeps no
 * stale counts: the page shows the error instead of old numbers. `corpus` keeps the latest
 * unfiltered counts, which the filter choices and the corpus total are taken from.
 */
export function useCorpusOverview () {
  const api = useApi().default
  const distributions = shallowRef<CorpusDistributions | null>(null)
  const corpus = shallowRef<CorpusDistributions | null>(null)
  const filters = shallowRef<DocumentFilters>({})
  const loading = ref(false)
  const slow = ref(false)
  const error = ref<string | null>(null)
  /** The request was refused as invalid (422): loading the same filters again cannot help. */
  const invalid = ref(false)

  let controller: AbortController | null = null
  let slowTimer: ReturnType<typeof setTimeout> | null = null

  function stop () {
    controller?.abort()
    controller = null
    if (slowTimer) clearTimeout(slowTimer)
    slowTimer = null
  }

  async function load (requested: DocumentFilters = {}) {
    stop()
    const current = new AbortController()
    controller = current
    filters.value = requested
    loading.value = true
    slow.value = false
    error.value = null
    invalid.value = false
    slowTimer = setTimeout(() => { slow.value = true }, SLOW_AFTER_MS)
    try {
      const result = await api.corpusDistributionsApiAnalyticsCorpusDistributionsPost(
        { corpusDistributionsRequest: { filters: requested } }, { signal: current.signal })
      if (controller !== current) return
      distributions.value = result
      filters.value = result.filters
      if (isUnfiltered(result.filters)) corpus.value = result
    } catch (e) {
      if (controller !== current || isAbortError(e)) return
      console.error('Loading the corpus overview failed', e)
      const message = await apiErrorMessage(e, 'The corpus overview could not be loaded.')
      if (controller !== current) return
      distributions.value = null
      error.value = message
      invalid.value = errorStatus(e) === 422
    } finally {
      if (controller === current) {
        stop()
        loading.value = false
        slow.value = false
      }
    }
  }

  const retry = () => load(filters.value)

  if (getCurrentScope()) onScopeDispose(stop)

  return { distributions, corpus, filters, loading, slow, error, invalid, load, retry }
}
