import { shallowRef, watch } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'
import { emptyLocation, locationKey, locationQuery, parseLocationQuery, type ExploreLocation } from './criteria'

export type AppliedReason = 'navigation' | 'apply'

/**
 * The applied Explore location of the page at route `routeName`, kept in its URL (#605).
 *
 * The URL is the source: opening a link, Back and Forward apply what it says; `apply`
 * records new criteria as a new history entry. `onApplied` runs whenever the applied location
 * changes, and also when `apply` is called with the current one (an explicit "search again").
 * Malformed URL values are left out, named in `invalid`, and replaced in the URL (no new
 * history entry). While another page is shown (a kept-alive page), its URLs are ignored, and
 * coming back to the same URL changes nothing.
 */
export function useExploreLocation (
  routeName: string,
  onApplied: (location: ExploreLocation, details: { reason: AppliedReason, invalid: string[] }) => void
) {
  const route = useRoute()
  const router = useRouter()
  const applied = shallowRef<ExploreLocation>(emptyLocation())
  let initialized = false

  function fromUrl (query: LocationQuery) {
    const { location, invalid } = parseLocationQuery(query)
    if (invalid.length) void router.replace({ name: routeName, query: locationQuery(location) })
    if (initialized && locationKey(location) === locationKey(applied.value)) {
      if (invalid.length) onApplied(applied.value, { reason: 'navigation', invalid })
      return
    }
    initialized = true
    applied.value = location
    onApplied(location, { reason: 'navigation', invalid })
  }

  watch(() => (route.name === routeName ? route.query : null), (query) => {
    if (query) fromUrl(query)
  }, { immediate: true })

  /**
   * Applies `location`: a new history entry when it differs from the applied one, otherwise
   * the same search again. With `replace`, the current entry is replaced instead (a
   * correction of the applied location, such as values that are not offered).
   */
  async function apply (location: ExploreLocation, { replace = false } = {}): Promise<void> {
    if (locationKey(location) === locationKey(applied.value)) {
      applied.value = location
      onApplied(location, { reason: 'apply', invalid: [] })
      return
    }
    // Applied before the URL changes, so the route watcher sees no change of its own.
    applied.value = location
    initialized = true
    const target = { name: routeName, query: locationQuery(location) }
    onApplied(location, { reason: 'apply', invalid: [] })
    await (replace ? router.replace(target) : router.push(target))
  }

  return { applied, apply }
}
