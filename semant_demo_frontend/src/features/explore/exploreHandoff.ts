import type { Router } from 'vue-router'
import { withChartFilter, type ChartFilter } from 'src/features/analytics/corpusOverview'
import { emptyCriteria, locationKey, locationQuery, normalizeCriteria, type ExploreLocation } from './criteria'

/**
 * Opening Explore with a collection as its scope from another page (#795, #622 decision 7).
 *
 * The collection scope of Explore is a page setting, never in the URL (#605): only the criteria,
 * mode, view and vector are. So the collection page leaves a one-shot hand-off here and navigates
 * to the Explore location; Explore takes it on that navigation (`takeExploreHandoff`) and applies
 * the location with the collection, also when it is kept alive with the same URL. The hand-off is
 * kept in memory only (not in the URL, the history state or local storage), belongs to the user
 * who left it, and is taken at most once.
 */
interface ExploreHandoff {
  userId: string
  collectionId: string
  /** The location it was left for: another navigation to Explore does not take it. */
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

/**
 * Opens Explore (route `search`) at `location` with the collection `collectionId` as its scope,
 * for the signed-in user `userId`. A navigation that does not happen (refused or cancelled)
 * leaves no hand-off behind.
 */
export async function exploreCollection (
  router: Router,
  { userId, collectionId, location }: { userId: string, collectionId: string, location: ExploreLocation }
): Promise<void> {
  const handoff = { userId, collectionId, locationKey: locationKey(location) }
  pending = handoff
  const failure = await router.push({ name: 'search', query: locationQuery(location) })
  if (failure && pending === handoff) pending = null
}

/** Whether a hand-off waits for a navigation to `location` by `userId` (not taken). */
export function hasExploreHandoff (location: ExploreLocation, userId: string | null): boolean {
  return pending !== null && pending.userId === userId && pending.locationKey === locationKey(location)
}

/**
 * Takes the hand-off left for a navigation to `location` by `userId`: its collection, once.
 * A hand-off of another user (signed out meanwhile) is discarded; one left for another location
 * stays for its own navigation.
 */
export function takeExploreHandoff (location: ExploreLocation, userId: string | null): string | null {
  if (pending && pending.userId !== userId) pending = null
  if (!pending || pending.locationKey !== locationKey(location)) return null
  const { collectionId } = pending
  pending = null
  return collectionId
}

/** Forgets any hand-off (tests). */
export function clearExploreHandoff (): void {
  pending = null
}
