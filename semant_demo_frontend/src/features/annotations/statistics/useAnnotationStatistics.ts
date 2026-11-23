import { onBeforeUnmount, ref, shallowRef, watch, type Ref } from 'vue'
import type { AnnotationFacets } from 'src/generated/api'
import { captureSession, createContextGuard, errorStatus, isAbortError, useApi } from 'src/shared/api'
import type { ConcordanceFilters } from '../concordance/concordanceStore'
import { statisticsRequest } from './statistics'

/**
 * Reads the statistics of the workspace query (#818) whenever the collection or the query changes
 * (not the sort order). A newer query, another collection or a sign-out drops a late answer; a
 * failed read is an error, never empty or zero counts.
 */
export function useAnnotationStatistics (collectionId: Ref<string | null>, filters: Ref<ConcordanceFilters>) {
  const api = useApi().default
  const requests = createContextGuard()
  let abort: AbortController | null = null

  const statistics = shallowRef<AnnotationFacets | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load () {
    abort?.abort()
    requests.enter()
    const id = collectionId.value
    if (!id) return
    const isCurrent = requests.capture()
    const inSession = captureSession()
    const applies = () => isCurrent() && inSession()
    const controller = new AbortController()
    abort = controller
    loading.value = true
    error.value = null
    try {
      const result = await api.facetCollectionAnnotationsApiUserCollectionsCollectionIdAnnotationsFacetsPost({
        collectionId: id, annotationFacetsRequest: statisticsRequest(filters.value)
      }, { signal: controller.signal })
      if (applies()) statistics.value = result
    } catch (e) {
      if (!applies() || isAbortError(e)) return
      statistics.value = null
      const status = errorStatus(e)
      if (status === 404) error.value = 'This collection is not available to you.'
      else if (status === 400) error.value = 'The statistics could not be computed for this query; narrow it and try again.'
      else {
        console.error('Loading the annotation statistics failed', e)
        error.value = 'Failed to load the statistics.'
      }
    } finally {
      if (applies()) {
        loading.value = false
        abort = null
      }
    }
  }

  /** The query without its display settings: a sort change does not change the counts. */
  const queryKey = () => {
    const { sort, sortAttribute, descending, ...query } = filters.value
    void sort; void sortAttribute; void descending
    return JSON.stringify([collectionId.value, query])
  }
  watch(queryKey, () => { void load() }, { immediate: true })

  onBeforeUnmount(() => {
    abort?.abort()
    requests.enter()
  })

  return { statistics, loading, error, load }
}
