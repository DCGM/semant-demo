import type { Router } from 'vue-router'
import { withChartFilter, type ChartFilter } from 'src/features/analytics/corpusOverview'
import { emptyCriteria, locationKey, locationQuery, normalizeCriteria, parseLocationQuery, type ExploreLocation } from './criteria'

/**
 * Opening Explore with a collection as its scope from another page (#795, #622 decision 7).
 *
 * The collection scope of Explore is a page setting, never in the URL (#605): only the criteria,
 * mode, view and vector are. So the collection page leaves a one-shot hand-off here and navigates
 * to the Explore location; Explore takes it on that navigation (`takeExploreHandoff`) and applies
 * the location with the collection, also when it is kept alive with the same URL. The hand-off is
 * kept in memory only (not in the URL, the history state or local storage), belongs to the user
 * who left it, and is taken at most once: the next navigation to Explore takes it or, if it was
 * left for another location or user, discards it.
 */
interface ExploreHandoff {
  userId: string
  collectionId: string
  /**
   * The location it was left for, as Explore reads it from the URL (`parseLocationQuery`, which
   * leaves out values it does not accept, e.g. a future year), so the two always match.
   */
  locationKey: string
}

let pending: ExploreHandoff | null = null

/** Where "Explore this collection" opens: its documents in Results, no filters (#795). */
export function collectionExploreLocation (): ExploreLocation {
  return { criteria: emptyCriteria(), mode: 'documents', view: null, vector: null }
}

/** Where a clicked chart category of the collection page opens: the Visualizations of that filter alone. */
export function collectionChartLocation (filter: ChartFilter): ExploreLocation {
  const criteria = normalizeCriteria({ documentFilters: withChartFilter({}, filter) })
  return { criteria, mode: 'documents', view: 'visualizations', vector: null }
}

/** The key of `location` as Explore will read it from the URL `router` pushes it with. */
const urlKey = (router: Router, location: ExploreLocation) =>
  locationKey(parseLocationQuery(router.resolve({ name: 'search', query: locationQuery(location) }).query).location)

/**
 * Opens Explore (route `search`) at `location` with the collection `collectionId` as its scope,
 * for the signed-in user `userId`. A navigation that does not reach Explore (refused, cancelled,
 * redirected or failed) leaves no hand-off behind; a failure is logged, not thrown, so callers
 * need not handle it.
 */
export async function exploreCollection (
  router: Router,
  { userId, collectionId, location }: { userId: string, collectionId: string, location: ExploreLocation }
): Promise<void> {
  const handoff = { userId, collectionId, locationKey: urlKey(router, location) }
  pending = handoff
  let reached = false
  try {
    const failure = await router.push({ name: 'search', query: locationQuery(location) })
    reached = !failure && router.currentRoute.value.name === 'search'
  } catch (e) {
    console.error('Opening Explore with the collection failed:', e)
  } finally {
    if (!reached && pending === handoff) pending = null
  }
}

/** Whether a hand-off waits for a navigation to `location` by `userId` (not taken). */
export function hasExploreHandoff (location: ExploreLocation, userId: string | null): boolean {
  return pending !== null && pending.userId === userId && pending.locationKey === locationKey(location)
}

/**
 * Takes the hand-off on a navigation to Explore at `location` by `userId`: its collection, once.
 * Any other hand-off (another user, signed out meanwhile, or another location) is discarded, so a
 * hand-off never waits for a later visit.
 */
export function takeExploreHandoff (location: ExploreLocation, userId: string | null): string | null {
  const handoff = pending
  pending = null
  return handoff && handoff.userId === userId && handoff.locationKey === locationKey(location) ? handoff.collectionId : null
}

/** Forgets any hand-off (tests). */
export function clearExploreHandoff (): void {
  pending = null
}
