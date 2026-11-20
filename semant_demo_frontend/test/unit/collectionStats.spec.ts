import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, reactive } from 'vue'
import { routeLocationKey, routerKey } from 'vue-router'
import { VueQueryPlugin } from '@tanstack/vue-query'

import type { Collection, CollectionStats, CorpusDistributions } from 'src/generated/api'
import ScopedDocumentCharts from 'src/features/analytics/ScopedDocumentCharts.vue'
import { exploreCollection } from 'src/features/explore/exploreHandoff'
import { collectionDocumentChartsKey } from 'src/features/user_collections/useCollectionDocumentCharts'
import CollectionOverviewPage from 'src/features/user_collections/CollectionOverviewPage.vue'
import { collectionStatsKey } from 'src/features/user_collections/useCollectionStats'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import { useUserStore } from 'src/features/auth/userStore'
import { useSessionScope } from 'src/app/session'
import { queryClient } from 'src/shared/query'

// #632: collection statistics as a Vue Query read on the collection Overview tab, keyed by
// the collection and the signed-in user.

const getById = vi.fn()
const getStats = vi.fn()
const getDocumentDistributions = vi.fn()
const remove = vi.fn()

vi.mock('src/features/user_collections/useUserCollectionsRepository', () => ({
  useUserCollectionsRepository: () => ({ getById, getStats, getDocumentDistributions, remove, getMembers: async () => [] })
}))
// The charts are drawn by a stand-in, not Vega (no canvas in jsdom).
vi.mock('src/shared/visualization/loadEmbed', () => ({
  loadEmbed: async () => async (element: HTMLElement) => {
    element.innerHTML = '<svg></svg>'
    const view = { addSignalListener: () => view }
    return { finalize: () => undefined, view }
  }
}))
vi.mock('src/features/explore/exploreHandoff', async () => ({
  ...(await vi.importActual<typeof import('src/features/explore/exploreHandoff')>('src/features/explore/exploreHandoff')),
  exploreCollection: vi.fn(async () => undefined)
}))
vi.mock('src/features/annotations/annotationCounts', () => ({
  countAnnotations: async () => ({ approved: 0, suggestions: 0, rejected: 0 })
}))
vi.mock('src/shared/notification', () => {
  const notif = { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() }
  return { ongoingNotification: () => notif, warningNotification: vi.fn() }
})

const collection = (id: string): Collection => ({
  id,
  name: `Collection ${id}`,
  owner: 'Owner Name',
  createdAt: new Date('2026-01-01'),
  updatedAt: new Date('2026-01-02'),
  color: '#123456',
  isSharedWithMe: false
})

/** The unfiltered document charts of a collection, as the server answers them (#768). */
const distributions = (collectionId: string, total: number, changes: Partial<CorpusDistributions> = {}): CorpusDistributions => ({
  scope: 'user_collection',
  userCollectionId: collectionId,
  unit: 'documents',
  filters: { titleContains: [], libraries: [], languages: [] },
  chunkFilters: { languages: [], classifications: {} },
  totalDocuments: total,
  computedAt: new Date('2026-11-19T12:00:00Z'),
  dataSource: 'live_aggregation',
  publicationYear: { available: true, years: total ? [{ year: 1905, count: total }] : [], unknownCount: 0 },
  libraries: { available: true, values: total ? [{ value: 'mzk', count: total }] : [], otherCount: 0, unknownCount: 0 },
  languages: { available: true, values: total ? [{ value: 'ces', count: total }] : [], otherCount: 0, unknownCount: 0 },
  ...changes
})

const stats = (collectionId: string, documentsCount: number): CollectionStats =>
  ({ collectionId, documentsCount, chunksCount: documentsCount * 10, tagsCount: 2, annotationsCount: 5 })

/** An answer the test gives (or refuses) later. */
function held<T> () {
  let answer: (value: T) => void = () => undefined
  let fail: (error: unknown) => void = () => undefined
  const promise = new Promise<T>((resolve, reject) => { answer = resolve; fail = reject })
  return { promise, answer, fail }
}

const route = reactive({ params: { collectionId: 'A' }, query: {} })
const pages: Set<{ unmount: () => void }> = new Set()

// The page inside an app that follows the session as `App.vue` does (`useSessionScope` in
// its setup), so the session watcher runs before the page's own watchers, as in the app.
const App = defineComponent({
  setup () {
    useSessionScope()
    return () => h(CollectionOverviewPage)
  }
})

function mountPage () {
  const page = mount(App, {
    global: {
      plugins: [[Quasar, {}] as never, [VueQueryPlugin, { queryClient }]],
      provide: {
        [routeLocationKey as symbol]: route,
        [routerKey as symbol]: { push: () => undefined }
      }
    }
  })
  pages.add(page)
  return page
}

function unmount (page: { unmount: () => void }) {
  pages.delete(page)
  page.unmount()
}

/** The four statistics cards (documents, chunks, tags, annotations), without the suggestions card. */
const counts = (page: ReturnType<typeof mountPage>) => page.findAll('.stat-value').slice(0, 4).map((value) => value.text())

const statsError = 'Failed to fetch collection statistics'

async function signIn (id: string) {
  useUserStore().user = { id, email: `${id}@example.com` }
  await flushPromises()
}

beforeEach(async () => {
  setActivePinia(createPinia())
  getById.mockReset().mockImplementation(async (id: string) => collection(id))
  getStats.mockReset()
  getDocumentDistributions.mockReset().mockImplementation(async (id: string) => distributions(id, 3))
  vi.mocked(exploreCollection).mockClear()
  remove.mockReset().mockResolvedValue(undefined)
  route.params.collectionId = 'A'
  await signIn('u1')
})

afterEach(() => {
  for (const page of [...pages]) unmount(page)
  queryClient.clear()
})

describe('collection statistics on the Overview tab', () => {
  it('shows the statistics of the loaded collection, unknown while they load', async () => {
    const answer = held<CollectionStats>()
    getStats.mockReturnValue(answer.promise)
    const page = mountPage()
    await flushPromises()
    expect(counts(page)).toEqual(['–', '–', '–', '–'])

    answer.answer(stats('A', 3))
    await flushPromises()

    expect(counts(page)).toEqual(['3', '30', '2', '5'])
    expect(getStats).toHaveBeenCalledTimes(1)
    expect(getStats.mock.calls[0][0]).toBe('A')
  })

  it('shows zeros for an empty collection', async () => {
    getStats.mockResolvedValue({ collectionId: 'A', documentsCount: 0, chunksCount: 0, tagsCount: 0, annotationsCount: 0 })
    const page = mountPage()
    await flushPromises()

    expect(counts(page)).toEqual(['0', '0', '0', '0'])
    expect(page.text()).not.toContain(statsError)
  })

  it('reports a failed load without retrying it or showing numbers', async () => {
    getStats.mockRejectedValue(new Error('503'))
    const page = mountPage()
    await flushPromises()

    expect(page.text()).toContain(statsError)
    expect(counts(page)).toEqual(['–', '–', '–', '–'])
    expect(getStats).toHaveBeenCalledTimes(1)
  })

  it('does not ask for the statistics of a collection that could not be loaded', async () => {
    getById.mockRejectedValue(new Error('404'))
    const page = mountPage()
    await flushPromises()

    expect(page.text()).toContain('Failed to fetch collection')
    expect(page.text()).not.toContain(statsError)
    expect(getStats).not.toHaveBeenCalled()
  })

  it('never shows the previous collection\'s statistics or error under the next one, whatever answers first', async () => {
    const forA = held<CollectionStats>()
    const forB = held<CollectionStats>()
    getStats.mockImplementation((id: string) => id === 'A' ? forA.promise : forB.promise)
    const page = mountPage()
    await flushPromises()

    route.params.collectionId = 'B'
    await flushPromises()
    forB.answer(stats('B', 7))
    await flushPromises()
    expect(counts(page)).toEqual(['7', '70', '2', '5'])

    forA.answer(stats('A', 3)) // late
    await flushPromises()
    expect(counts(page)).toEqual(['7', '70', '2', '5'])

    // Back to A, which fails this time; then B again, whose answer is late too.
    getStats.mockReset()
    const failingA = held<CollectionStats>()
    const lateB = held<CollectionStats>()
    getStats.mockImplementation((id: string) => id === 'A' ? failingA.promise : lateB.promise)
    route.params.collectionId = 'A'
    await flushPromises()
    route.params.collectionId = 'B'
    await flushPromises()
    failingA.fail(new Error('503'))
    await flushPromises()

    expect(page.text()).not.toContain(statsError)
    expect(counts(page)).toEqual(['7', '70', '2', '5']) // B's last known numbers while B is asked again
    lateB.answer(stats('B', 8))
    await flushPromises()
    expect(counts(page)).toEqual(['8', '80', '2', '5'])
  })

  it('asks again on every visit, so changes made on another page show, and leaves other collections alone', async () => {
    getStats.mockImplementation(async (id: string) => stats(id, id === 'A' ? 3 : 7))
    const first = mountPage()
    await flushPromises()
    route.params.collectionId = 'B'
    await flushPromises()
    unmount(first)
    const bAnsweredAt = queryClient.getQueryState(collectionStatsKey('u1', 'B'))?.dataUpdatedAt

    // A document is added to A on its Documents tab, then its Overview is opened again.
    const fresh = held<CollectionStats>()
    getStats.mockReset().mockReturnValue(fresh.promise)
    route.params.collectionId = 'A'
    const again = mountPage()
    await flushPromises()
    expect(counts(again)).toEqual(['3', '30', '2', '5']) // last known, under the loading overlay
    fresh.answer(stats('A', 4))
    await flushPromises()

    expect(counts(again)).toEqual(['4', '40', '2', '5'])
    expect(getStats.mock.calls.map(([id]) => id)).toEqual(['A'])
    expect(queryClient.getQueryState(collectionStatsKey('u1', 'B'))?.dataUpdatedAt).toBe(bAnsweredAt)
  })

  it('does not show a collection\'s cached statistics while it loads again, nor once it can no longer be loaded', async () => {
    getStats.mockImplementation(async (id: string) => stats(id, id === 'A' ? 3 : 7))
    const page = mountPage()
    await flushPromises()
    route.params.collectionId = 'B'
    await flushPromises()

    // A is no longer shared with the user when they come back to it.
    const loadingA = held<Collection>()
    getById.mockReturnValue(loadingA.promise)
    route.params.collectionId = 'A'
    await flushPromises()
    expect(counts(page)).toEqual(['–', '–', '–', '–'])
    loadingA.fail(new Error('404'))
    await flushPromises()

    expect(page.text()).toContain('Failed to fetch collection')
    expect(counts(page)).toEqual(['–', '–', '–', '–'])
    expect(getStats.mock.calls.map(([id]) => id)).toEqual(['A', 'B'])
  })

  it('revalidates the same collection before showing or asking for its statistics again', async () => {
    getStats.mockResolvedValue(stats('A', 3))
    const first = mountPage()
    await flushPromises()
    expect(counts(first)).toEqual(['3', '30', '2', '5'])
    unmount(first) // another tab of A; A stays the open collection

    // A is no longer shared with the user when they come back to its Overview.
    const loadingA = held<Collection>()
    getById.mockReturnValue(loadingA.promise)
    const again = mountPage()
    await flushPromises()
    expect(useUserCollectionsStore().activeCollection?.id).toBe('A')
    expect(counts(again)).toEqual(['–', '–', '–', '–'])
    expect(getStats).toHaveBeenCalledTimes(1)

    loadingA.fail(new Error('404'))
    await flushPromises()

    expect(again.text()).toContain('Failed to fetch collection')
    expect(again.text()).not.toContain(statsError)
    expect(counts(again)).toEqual(['–', '–', '–', '–'])
    expect(getStats).toHaveBeenCalledTimes(1)
  })

  it('does not show the cached statistics as current once asking for them again fails', async () => {
    getStats.mockResolvedValue(stats('A', 3))
    unmount(mountPage())
    await flushPromises()

    getStats.mockReset().mockRejectedValue(new Error('503'))
    const again = mountPage()
    await flushPromises()

    expect(getStats).toHaveBeenCalledTimes(1)
    expect(again.text()).toContain(statsError)
    expect(counts(again)).toEqual(['–', '–', '–', '–'])
  })

  it('forgets the statistics of a deleted collection, and keeps the others', async () => {
    queryClient.setQueryData(collectionStatsKey('u1', 'A'), stats('A', 3))
    queryClient.setQueryData(collectionStatsKey('u1', 'B'), stats('B', 7))

    await useUserCollectionsStore().deleteCollection('A')

    expect(queryClient.getQueryData(collectionStatsKey('u1', 'A'))).toBeUndefined()
    expect(queryClient.getQueryData(collectionStatsKey('u1', 'B'))).toEqual(stats('B', 7))
  })
})

describe('collection statistics at the session boundary', () => {
  it('stops showing them at sign-out, also with the page still open and an answer under way', async () => {
    getStats.mockResolvedValue(stats('A', 3))
    const page = mountPage()
    await flushPromises()
    expect(counts(page)).toEqual(['3', '30', '2', '5'])
    const late = held<CollectionStats>()
    getStats.mockReset().mockReturnValue(late.promise)
    void queryClient.refetchQueries({ queryKey: collectionStatsKey('u1', 'A') })

    useUserStore().user = null
    await flushPromises()
    late.answer(stats('A', 99))
    await flushPromises()

    expect(counts(page)).toEqual(['–', '–', '–', '–'])
    expect(queryClient.getQueryData(collectionStatsKey('u1', 'A'))).toBeUndefined()
  })

  it('never serves one user\'s statistics to the next, and asks under the new user', async () => {
    getStats.mockResolvedValue(stats('A', 3))
    const page = mountPage()
    await flushPromises()
    expect(counts(page)).toEqual(['3', '30', '2', '5'])

    // Another account signs in (here or in another tab; both end in the user change). Shown
    // again only once the collection was loaded for u2.
    getStats.mockReset().mockResolvedValue(stats('A', 1))
    await signIn('u2')
    expect(counts(page)).toEqual(['–', '–', '–', '–'])
    expect(queryClient.getQueryData(collectionStatsKey('u1', 'A'))).toBeUndefined()

    // The collection is loaded again for u2, here by the page shown for it anew.
    await useUserCollectionsStore().fetchCollection('A')
    await flushPromises()

    expect(counts(page)).toEqual(['1', '10', '2', '5'])
    expect(queryClient.getQueryData(collectionStatsKey('u2', 'A'))).toEqual(stats('A', 1))
  })
})

// #795: the document charts of the whole collection, loaded as the statistics are.
describe('collection document charts on the Overview tab', () => {
  const chartIds = (page: ReturnType<typeof mountPage>) =>
    page.findAll('[data-testid]').map(e => e.attributes('data-testid')).filter(id => id?.startsWith('charts-'))

  beforeEach(() => getStats.mockResolvedValue(stats('A', 3)))

  it('charts the documents of the loaded collection, named from the answer, asked for once it has loaded', async () => {
    const loaded = held<Collection>()
    getById.mockReturnValue(loaded.promise)
    const page = mountPage()
    await flushPromises()
    expect(getDocumentDistributions).not.toHaveBeenCalled()
    expect(page.find('[data-testid="collection-document-charts"]').exists()).toBe(false)

    loaded.answer(collection('A'))
    await flushPromises()

    expect(getDocumentDistributions).toHaveBeenCalledTimes(1)
    expect(getDocumentDistributions.mock.calls[0][0]).toBe('A')
    const scope = page.get('[data-testid="charts-scope"]').text()
    expect(scope).toMatch(/^3\s+documents of collection\s+Collection A\./)
    expect(page.get('[data-testid="corpus-libraries"]').text()).toContain('of 3 collection documents')
    expect(queryClient.getQueryData(collectionDocumentChartsKey('u1', 'A'))).toEqual(distributions('A', 3))
  })

  it('shows no counts that are not of this collection, but reports them as an error to retry', async () => {
    // Review of #796: such an answer is complete, so the page does not keep loading for good.
    getDocumentDistributions.mockImplementation(async () => distributions('B', 7))
    const page = mountPage()
    await flushPromises()
    expect(chartIds(page)).toEqual(['charts-error', 'charts-retry'])
    expect(page.find('[data-testid="charts-total"]').exists()).toBe(false)

    const retried = held<CorpusDistributions>()
    getDocumentDistributions.mockReturnValueOnce(retried.promise)
    await page.get('[data-testid="charts-retry"]').trigger('click')
    await flushPromises()
    expect(chartIds(page)).toEqual(['charts-loading'])
    retried.answer(distributions('A', 7, { scope: 'searchable_corpus', userCollectionId: null }))
    await flushPromises()
    expect(chartIds(page)).toEqual(['charts-error', 'charts-retry'])
    expect(page.find('[data-testid="charts-total"]').exists()).toBe(false)

    getDocumentDistributions.mockImplementation(async () => distributions('A', 7))
    await page.get('[data-testid="charts-retry"]').trigger('click')
    await flushPromises()
    expect(page.get('[data-testid="charts-total"]').text()).toBe('7')
  })

  it('reports a failed count without zeros, and counts again on Try again', async () => {
    getDocumentDistributions.mockRejectedValueOnce(new Error('503'))
    const page = mountPage()
    await flushPromises()
    expect(page.get('[data-testid="charts-error"]').text()).toContain('could not be counted')
    expect(page.find('[data-testid="charts-total"]').exists()).toBe(false)
    expect(getDocumentDistributions).toHaveBeenCalledTimes(1) // not retried behind the user's back

    const retried = held<CorpusDistributions>()
    getDocumentDistributions.mockReturnValueOnce(retried.promise)
    await page.get('[data-testid="charts-retry"]').trigger('click')
    await flushPromises()
    expect(getDocumentDistributions).toHaveBeenCalledTimes(2)
    // While it is counted again, the page says so instead of keeping the error (review of #796).
    expect(chartIds(page)).toEqual(['charts-loading'])

    retried.answer(distributions('A', 3))
    await flushPromises()
    expect(page.get('[data-testid="charts-total"]').text()).toBe('3')
  })

  it('says that an empty collection has no documents', async () => {
    getDocumentDistributions.mockImplementation(async (id: string) => distributions(id, 0))
    const page = mountPage()
    await flushPromises()
    expect(page.get('[data-testid="charts-empty"]').text()).toContain('This collection has no documents.')
  })

  it('opens Explore with the collection and the clicked filter alone', async () => {
    const page = mountPage()
    await flushPromises()

    page.findComponent(ScopedDocumentCharts).vm.$emit('applyFilter', { dimension: 'libraries', value: 'mzk' })

    expect(exploreCollection).toHaveBeenCalledTimes(1)
    const [, handoff] = vi.mocked(exploreCollection).mock.calls[0]
    expect(handoff.userId).toBe('u1')
    expect(handoff.collectionId).toBe('A')
    expect(handoff.location).toMatchObject({ mode: 'documents', view: 'visualizations', vector: null })
    expect(handoff.location.criteria.documentFilters.libraries).toEqual(['mzk'])
  })

  it('forgets the charts of a deleted collection with its statistics, and keeps the others', async () => {
    queryClient.setQueryData(collectionDocumentChartsKey('u1', 'A'), distributions('A', 3))
    queryClient.setQueryData(collectionDocumentChartsKey('u1', 'B'), distributions('B', 7))

    await useUserCollectionsStore().deleteCollection('A')

    expect(queryClient.getQueryData(collectionDocumentChartsKey('u1', 'A'))).toBeUndefined()
    expect(queryClient.getQueryData(collectionDocumentChartsKey('u1', 'B'))).toEqual(distributions('B', 7))
  })
})
