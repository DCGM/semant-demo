import { afterEach, describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { locationKey, type ExploreLocation } from 'src/features/explore/criteria'
import {
  clearExploreHandoff, collectionChartLocation, collectionExploreLocation, exploreCollection, hasExploreHandoff,
  takeExploreHandoff
} from 'src/features/explore/exploreHandoff'
import { useExploreLocation } from 'src/features/explore/useExploreLocation'

const Page = { render: () => null }

function makeRouter (): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { name: 'search', path: '/search', component: Page },
      { name: 'collectionOverview', path: '/collections/:id/overview', component: Page }
    ]
  })
}

afterEach(() => clearExploreHandoff())

describe('the locations the collection page opens', () => {
  it('are the collection documents in Results, or the Visualizations of one clicked filter', () => {
    expect(collectionExploreLocation()).toMatchObject({ mode: 'documents', view: null, vector: null })
    expect(collectionExploreLocation().criteria.textQuery).toBeNull()

    const library = collectionChartLocation({ dimension: 'libraries', value: 'mzk' })
    expect(library).toMatchObject({ mode: 'documents', view: 'visualizations', vector: null })
    expect(library.criteria.documentFilters).toMatchObject({ libraries: ['mzk'], languages: [], yearMin: null, yearMax: null })

    const years = collectionChartLocation({ dimension: 'years', start: 1900, end: 1909 })
    expect(years.criteria.documentFilters).toMatchObject({ yearMin: 1900, yearMax: 1909, libraries: [] })
  })
})

describe('exploreCollection', () => {
  it('navigates to the Explore location, never with the collection in the URL, and leaves a hand-off for it', async () => {
    const router = makeRouter()
    await router.push('/collections/c1/overview')
    const location = collectionChartLocation({ dimension: 'languages', value: 'ces' })

    await exploreCollection(router, { userId: 'u1', collectionId: 'c1', location })

    expect(router.currentRoute.value.name).toBe('search')
    expect(router.currentRoute.value.fullPath).not.toContain('c1')
    expect(hasExploreHandoff(location, 'u1')).toBe(true)
  })

  it('is taken once, only by its user and for its location', () => {
    const router = makeRouter()
    const location = collectionExploreLocation()
    void exploreCollection(router, { userId: 'u1', collectionId: 'c1', location })

    const other: ExploreLocation = { ...location, view: 'visualizations' }
    expect(locationKey(other)).not.toBe(locationKey(location))
    expect(takeExploreHandoff(other, 'u1')).toBeNull() // another navigation to Explore
    expect(takeExploreHandoff(location, 'u1')).toBe('c1')
    expect(takeExploreHandoff(location, 'u1')).toBeNull()
  })

  it('is discarded when another user (or nobody) comes to Explore', () => {
    const router = makeRouter()
    const location = collectionExploreLocation()
    void exploreCollection(router, { userId: 'u1', collectionId: 'c1', location })

    expect(hasExploreHandoff(location, null)).toBe(false)
    expect(takeExploreHandoff(location, 'u2')).toBeNull()
    expect(takeExploreHandoff(location, 'u1')).toBeNull()
  })

  it('leaves no hand-off when the navigation does not happen', async () => {
    const router = makeRouter()
    router.beforeEach((to) => to.name !== 'search')
    const location = collectionExploreLocation()

    await exploreCollection(router, { userId: 'u1', collectionId: 'c1', location })

    expect(hasExploreHandoff(location, 'u1')).toBe(false)
  })
})

describe('useExploreLocation with a hand-off', () => {
  it('applies the same URL again when a collection was handed over for it, and only then', async () => {
    const router = makeRouter()
    const location = collectionExploreLocation()
    await router.push({ name: 'search', query: { mode: 'documents' } })
    const calls: (string | null)[] = []
    const Host = defineComponent({
      setup () {
        useExploreLocation('search', (loc) => calls.push(takeExploreHandoff(loc, 'u1')), {
          appliesUnchanged: (loc) => hasExploreHandoff(loc, 'u1')
        })
        return () => h('div')
      }
    })
    mount(Host, { global: { plugins: [router] } })
    await router.isReady()
    expect(calls).toEqual([null])

    // Coming back to the same search changes nothing ...
    await router.push('/collections/c1/overview')
    await router.push({ name: 'search', query: { mode: 'documents' } })
    expect(calls).toEqual([null])

    // ... but a collection handed over for it is applied (Explore kept alive with the same URL).
    await router.push('/collections/c1/overview')
    await exploreCollection(router, { userId: 'u1', collectionId: 'c1', location })
    expect(calls).toEqual([null, 'c1'])
  })
})
