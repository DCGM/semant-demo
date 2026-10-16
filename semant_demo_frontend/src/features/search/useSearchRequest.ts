import { ref, shallowRef } from 'vue'
import type { SearchRequest } from 'src/generated/api'
import { createContextGuard, isAbortError, useApi } from 'src/shared/api'
import type { SearchResultsContext } from './searchResults'

/**
 * Runs searches and holds the current {@link SearchResultsContext}. Starting a search
 * aborts the previous one; a response that still arrives for it is ignored and cannot
 * replace the newer results or end the newer search's loading state.
 */
export function useSearchRequest () {
  const api = useApi().default
  const context = shallowRef<SearchResultsContext | null>(null)
  const loading = ref(false)
  const guard = createContextGuard()
  let abort: AbortController | null = null
  let lastId = 0

  /** Resolves to the new context, or null when a later search or `cancel()` replaced it. */
  async function search (request: SearchRequest): Promise<SearchResultsContext | null> {
    abort?.abort()
    guard.enter()
    const isCurrent = guard.capture()
    const controller = new AbortController()
    abort = controller
    context.value = null
    loading.value = true
    try {
      const response = await api.searchApiSearchPost({ searchRequest: request }, { signal: controller.signal })
      if (!isCurrent()) return null
      context.value = { id: ++lastId, response }
      return context.value
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return null
      throw e
    } finally {
      if (isCurrent()) {
        loading.value = false
        abort = null
      }
    }
  }

  /** Stops a running search and forgets the current results. */
  function cancel () {
    abort?.abort()
    abort = null
    guard.enter()
    context.value = null
    loading.value = false
  }

  return { context, loading, search, cancel }
}
