import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { effectScope } from 'vue'

import { normalizeCriteria } from 'src/features/explore/criteria'
import { chartFilters, chartsAvailability, useExploreCharts } from 'src/features/explore/useExploreCharts'
import ExploreVisualizations from 'src/features/explore/ExploreVisualizations.vue'
import type { CorpusDistributions } from 'src/generated/api'
import { loadEmbed } from 'src/shared/visualization/loadEmbed'
import { muteConsole } from './console'

// Explore Visualizations, first slice (#618): charts of every document the applied filters match,
// for Documents without a text query, of the corpus or of a collection's documents (#768);
// explicit states for what cannot be charted.

vi.mock('src/shared/visualization/loadEmbed', () => ({ loadEmbed: vi.fn() }))

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const requests: { path: string, body: Record<string, unknown>, signal?: AbortSignal | null, answer: (body: unknown, status?: number) => void }[] = []
const originalFetch = globalThis.fetch

beforeEach(() => {
  vi.mocked(loadEmbed).mockResolvedValue(async (element) => {
    (element as HTMLElement).innerHTML = '<svg></svg>'
    const view = { addSignalListener: () => view }
    return { finalize: vi.fn(), view } as never
  })
  globalThis.fetch = vi.fn((url: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
    requests.push({
      path: new URL(String(url), 'http://test').pathname,
      body: JSON.parse(String(init?.body)),
      signal: init?.signal,
      answer: (body, status = 200) => resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
    })
  })) as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  requests.length = 0
  vi.restoreAllMocks()
})

const NO_DOCUMENT_FILTERS = { year_min: null, year_max: null, title_contains: [], libraries: [], languages: [] }

const distributionsBody = (total: number, changes: Record<string, unknown> = {}) => ({
  scope: 'searchable_corpus',
  unit: 'documents',
  filters: NO_DOCUMENT_FILTERS,
  chunk_filters: { languages: [], classifications: {} },
  total_documents: total,
  computed_at: '2026-11-08T12:00:00Z',
  data_source: 'live_aggregation',
  publication_year: { available: true, years: [{ year: 1905, count: total }], unknown_count: 0 },
  libraries: { available: true, values: [{ value: 'mzk', count: total }], other_count: 0, unknown_count: 0 },
  languages: { available: true, values: [{ value: 'ces', count: total }], other_count: 0, unknown_count: 0 },
  ...changes
})

const filtered = (textQuery: string | null = null) => normalizeCriteria({
  textQuery,
  documentFilters: { yearMin: 1900, libraries: ['mzk'] },
  chunkFilters: { languages: ['ces'], classifications: { complexity: ['easy'] } }
})

describe('chartsAvailability', () => {
  it('charts Documents without a text query, and names why other criteria are not charted', () => {
    // With or without a collection scope (#768: then its documents are counted).
    expect(chartsAvailability(filtered(), 'documents')).toBe('documents')
    expect(chartsAvailability(normalizeCriteria({}), 'documents')).toBe('documents')
    // A text query: only its ranked results are charted (#620), not the filtered corpus; a
    // collection's search too.
    expect(chartsAvailability(filtered('Brno'), 'documents')).toBe('ranked')
    expect(chartsAvailability(filtered('Brno'), 'passages')).toBe('ranked')
    // Filter-only passages are not retrievable; document counts are not shown in their place.
    expect(chartsAvailability(filtered(), 'passages')).toBe('passages')
  })

  it('send the document filters and the chunk filters of the criteria, without the text query', () => {
    expect(chartFilters(filtered('Brno'))).toEqual({
      filters: { yearMin: 1900, yearMax: null, titleContains: [], libraries: ['mzk'], languages: [] },
      chunkFilters: { languages: ['ces'], classifications: { complexity: ['easy'] } }
    })
  })
})

describe('useExploreCharts', () => {
  it('counts the documents of the filters per dimension, and not again for the same filters', async () => {
    const scope = effectScope()
    const charts = scope.run(() => useExploreCharts())!
    charts.show(filtered(), null)
    await flush()
    expect(requests.map(r => r.path)).toEqual(['/api/analytics/corpus/distributions'])
    expect(requests[0].body).toEqual({
      filters: { year_min: 1900, year_max: null, title_contains: [], libraries: ['mzk'], languages: [] },
      chunk_filters: { languages: ['ces'], classifications: { complexity: ['easy'] } }
    })
    // Shown again (a view switch) while counting and once counted: no new request.
    charts.show(filtered(), null)
    requests[0].answer(distributionsBody(7))
    await flushPromises()
    charts.show(filtered(), null)
    await flush()
    expect(requests).toHaveLength(1)
    expect(charts.distributions.value?.totalDocuments).toBe(7)

    // An explicit Search counts again.
    charts.show(filtered(), null, { force: true })
    await flush()
    expect(requests).toHaveLength(2)
    scope.stop()
  })

  it('sends no chunk filters when none are set', async () => {
    const scope = effectScope()
    const charts = scope.run(() => useExploreCharts())!
    charts.show(normalizeCriteria({ documentFilters: { languages: ['ces'] } }), null)
    await flush()
    expect(requests[0].body).toEqual({ filters: { ...NO_DOCUMENT_FILTERS, languages: ['ces'] } })
    scope.stop()
  })

  it('drops the late answer of earlier filters and counts again after a failure', async () => {
    muteConsole('error')
    const scope = effectScope()
    const charts = scope.run(() => useExploreCharts())!
    charts.show(filtered(), null)
    await flush()
    charts.show(normalizeCriteria({}), null)
    await flush()
    expect(requests[0].signal?.aborted).toBe(true)
    requests[1].answer(distributionsBody(10))
    requests[0].answer(distributionsBody(7))
    await flushPromises()
    expect(charts.distributions.value?.totalDocuments).toBe(10)

    charts.show(filtered(), null)
    await flush()
    requests[2].answer({ detail: 'Weaviate unavailable' }, 503)
    await flushPromises()
    expect([charts.error.value !== null, charts.distributions.value]).toEqual([true, null])
    charts.show(filtered(), null) // the same filters, but the last count failed
    await flush()
    expect(requests).toHaveLength(4)
    scope.stop()
  })
})

describe('useExploreCharts with a collection (#768)', () => {
  const collectionBody = (total: number, id = 'c1') => distributionsBody(total, { scope: 'user_collection', user_collection_id: id })

  it('sends the collection, and counts again for another collection or none, aborting the count in flight', async () => {
    const scope = effectScope()
    const charts = scope.run(() => useExploreCharts())!
    charts.show(filtered(), 'c1')
    await flush()
    expect(requests[0].body).toMatchObject({ user_collection_id: 'c1' })
    requests[0].answer(collectionBody(3))
    await flushPromises()
    charts.show(filtered(), 'c1')
    await flush()
    expect(requests).toHaveLength(1)

    // The same filters in another collection.
    charts.show(filtered(), 'c2')
    await flush()
    expect(requests).toHaveLength(2)
    expect(requests[1].body).toMatchObject({ user_collection_id: 'c2' })
    // Signed out meanwhile: the collection is gone, the corpus is counted; c2's late answer is dropped.
    charts.show(filtered(), null)
    await flush()
    expect(requests[1].signal?.aborted).toBe(true)
    expect(requests[2].body).not.toHaveProperty('user_collection_id')
    requests[2].answer(distributionsBody(40))
    requests[1].answer(collectionBody(5, 'c2'))
    await flushPromises()
    expect([charts.distributions.value?.scope, charts.distributions.value?.totalDocuments]).toEqual(['searchable_corpus', 40])
    scope.stop()
  })

  it('counts a collection again after documents were added to it, and Retry keeps the collection', async () => {
    muteConsole('error')
    const scope = effectScope()
    const charts = scope.run(() => useExploreCharts())!
    charts.show(normalizeCriteria({}), 'c1')
    await flush()
    requests[0].answer(collectionBody(3))
    await flushPromises()

    charts.markStale('c2') // another collection: these counts are still current
    charts.show(normalizeCriteria({}), 'c1')
    await flush()
    expect(requests).toHaveLength(1)
    charts.markStale('c1')
    charts.show(normalizeCriteria({}), 'c1')
    await flush()
    expect(requests).toHaveLength(2)

    requests[1].answer({ detail: 'Weaviate unavailable' }, 503)
    await flushPromises()
    void charts.retry()
    await flush()
    expect(requests[2].body).toMatchObject({ user_collection_id: 'c1' })
    scope.stop()
  })

  it('never keeps a collection\'s unfiltered counts as the corpus', async () => {
    const scope = effectScope()
    const charts = scope.run(() => useExploreCharts())!
    charts.show(normalizeCriteria({}), 'c1')
    await flush()
    requests[0].answer(collectionBody(3))
    await flushPromises()
    expect(charts.corpus.value).toBeNull()
    charts.show(normalizeCriteria({}), null)
    await flush()
    requests[1].answer(distributionsBody(40))
    await flushPromises()
    expect(charts.corpus.value?.totalDocuments).toBe(40)
    scope.stop()
  })
})

describe('ExploreVisualizations', () => {
  const distributions = (total: number, changes: Partial<CorpusDistributions> = {}): CorpusDistributions => ({
    scope: 'searchable_corpus',
    unit: 'documents',
    filters: { yearMin: 1900, titleContains: [], libraries: [], languages: [] },
    chunkFilters: { languages: [], classifications: {} },
    totalDocuments: total,
    computedAt: new Date('2026-11-08T12:00:00Z'),
    dataSource: 'live_aggregation',
    publicationYear: { available: true, years: [{ year: 1905, count: total }], unknownCount: 0 },
    libraries: { available: true, values: [{ value: 'mzk', count: total }], otherCount: 0, unknownCount: 0 },
    languages: { available: true, values: [{ value: 'ces', count: total }], otherCount: 0, unknownCount: 0 },
    ...changes
  })
  const view = (props: Record<string, unknown>) => mount(ExploreVisualizations, {
    props: { availability: 'documents', distributions: null, loading: false, slow: false, error: null, invalid: false, ...props },
    global: { plugins: [[Quasar, {}]] }
  })
  const testIds = (wrapper: ReturnType<typeof view>) =>
    wrapper.findAll('[data-testid]').map(e => e.attributes('data-testid')).filter(id => id?.startsWith('charts-'))

  it('shows the number of matching documents and their charts, counted per dimension for passage filters', async () => {
    const wrapper = view({ distributions: distributions(1234, { chunkFilters: { languages: ['ces'], classifications: {} } }) })
    await flushPromises()
    expect(wrapper.get('[data-testid="charts-total"]').text()).toBe('1,234')
    const scope = wrapper.get('[data-testid="charts-scope"]').text()
    expect(scope).toContain('documents match the applied filters')
    expect(scope).toContain('distinct documents')
    expect(scope).toContain('different filters may be met by different passages')
    expect(wrapper.find('[data-testid="corpus-years"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="corpus-libraries"]').exists()).toBe(true)
  })

  it('says when the counts are of the whole corpus, and leaves out the per-dimension note without passage filters', async () => {
    const wrapper = view({ distributions: distributions(10, { filters: { titleContains: [], libraries: [], languages: [] } }) })
    await flushPromises()
    const scope = wrapper.get('[data-testid="charts-scope"]').text()
    expect(scope).toContain('the whole searchable corpus')
    expect(scope).not.toContain('passages')
  })

  it('tells an empty population apart from the loading and failed states', async () => {
    expect(testIds(view({ distributions: distributions(0) }))).toContain('charts-empty')
    expect(testIds(view({ loading: true }))).toEqual(['charts-loading'])
    const failed = view({ error: 'The corpus overview could not be loaded.' })
    expect(failed.get('[data-testid="charts-error"]').text()).toContain('could not be counted')
    await failed.get('[data-testid="charts-retry"]').trigger('click')
    expect(failed.emitted('retry')).toHaveLength(1)
    // A refused filter cannot succeed by trying again.
    expect(view({ error: 'invalid', invalid: true }).find('[data-testid="charts-retry"]').exists()).toBe(false)
  })

  it('charts nothing for filter-only passages, and says why', async () => {
    const wrapper = view({ availability: 'passages', distributions: distributions(10) })
    expect(testIds(wrapper)).toEqual(['charts-passages', 'charts-show-documents'])
    expect(wrapper.find('[data-testid="corpus-years"]').exists()).toBe(false)
    const passages = view({ availability: 'passages' })
    await passages.get('[data-testid="charts-show-documents"]').trigger('click')
    expect(passages.emitted('showDocuments')).toHaveLength(1)
  })

  // #768: what the counts describe comes from their answer, never from the requested scope.
  const ofCollection = (total: number, changes: Partial<CorpusDistributions> = {}) =>
    distributions(total, { scope: 'user_collection', userCollectionId: 'c1', ...changes })
  const label = (id: string) => (id === 'c1' ? 'Kroniky a dopisy' : `Collection ${id}`)
  const unfiltered = { titleContains: [], libraries: [], languages: [] }

  it('names the collection and its documents as the unit of every chart', async () => {
    const wrapper = view({ distributions: ofCollection(6, { filters: unfiltered }), collectionLabel: label })
    await flushPromises()
    const scope = wrapper.get('[data-testid="charts-scope"]').text()
    expect(scope).toMatch(/^6\s+documents of collection\s+Kroniky a dopisy\./)
    expect(scope).toContain('also those without a passage in it')
    expect(scope).not.toContain('searchable corpus')
    for (const card of ['corpus-years', 'corpus-libraries', 'corpus-languages']) {
      expect(wrapper.get(`[data-testid="${card}"]`).text()).toContain('of 6 collection documents')
    }
  })

  it('says that passage filters consider every passage of a collection document', async () => {
    const wrapper = view({
      distributions: ofCollection(1, { filters: unfiltered, chunkFilters: { languages: ['ces'], classifications: {} } }),
      collectionLabel: label
    })
    await flushPromises()
    const scope = wrapper.get('[data-testid="charts-scope"]').text()
    expect(scope).toMatch(/^1\s+document of collection\s+Kroniky a dopisy\s+matches the applied filters\./)
    expect(scope).toContain('All passages of each document count, not only those in the collection.')
  })

  it('shows the corpus wording for corpus counts even while a collection is being counted', async () => {
    const wrapper = view({ distributions: distributions(10, { filters: unfiltered }), loading: true, collectionLabel: label })
    await flushPromises()
    expect(wrapper.get('[data-testid="charts-scope"]').text()).toContain('the whole searchable corpus')
    expect(wrapper.find('[data-testid="charts-collection-name"]').exists()).toBe(false)
  })

  it('tells an empty collection apart from a collection without matching documents', async () => {
    const empty = view({ distributions: ofCollection(0, { filters: unfiltered }), collectionLabel: label })
    expect(empty.get('[data-testid="charts-empty"]').text()).toContain('This collection has no documents.')
    const none = view({ distributions: ofCollection(0), collectionLabel: label })
    expect(none.get('[data-testid="charts-empty"]').text()).toContain('No documents of this collection match these filters.')
    expect(view({ distributions: distributions(0) }).get('[data-testid="charts-empty"]').text())
      .toContain('No documents match these filters.')
  })

  it('counts the heatmap of the same collection', async () => {
    const wrapper = view({ distributions: ofCollection(6, { filters: unfiltered }), collectionLabel: label })
    await flushPromises()
    await wrapper.get('[data-testid="heatmap-show"]').trigger('click')
    await flushPromises()
    await flush()
    const heatmap = requests.filter(r => r.path === '/api/analytics/corpus/library-years')
    expect(heatmap).toHaveLength(1)
    expect(heatmap[0].body).toMatchObject({ user_collection_id: 'c1' })
  })
})
