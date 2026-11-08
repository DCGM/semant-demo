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
// for Documents without a text query; explicit states for what cannot be charted yet.

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
    expect(chartsAvailability(filtered(), 'documents', null)).toBe('documents')
    expect(chartsAvailability(normalizeCriteria({}), 'documents', null)).toBe('documents')
    // A text query: only its retrieved results could be charted (#619/#620), not the filtered corpus.
    expect(chartsAvailability(filtered('Brno'), 'documents', null)).toBe('textQuery')
    expect(chartsAvailability(filtered('Brno'), 'passages', null)).toBe('textQuery')
    // Filter-only passages are not retrievable; document counts are not shown in their place.
    expect(chartsAvailability(filtered(), 'passages', null)).toBe('passages')
    expect(chartsAvailability(filtered(), 'documents', 'c1')).toBe('collection')
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
    charts.show(filtered())
    await flush()
    expect(requests.map(r => r.path)).toEqual(['/api/analytics/corpus/distributions'])
    expect(requests[0].body).toEqual({
      filters: { year_min: 1900, year_max: null, title_contains: [], libraries: ['mzk'], languages: [] },
      chunk_filters: { languages: ['ces'], classifications: { complexity: ['easy'] } }
    })
    // Shown again (a view switch) while counting and once counted: no new request.
    charts.show(filtered())
    requests[0].answer(distributionsBody(7))
    await flushPromises()
    charts.show(filtered())
    await flush()
    expect(requests).toHaveLength(1)
    expect(charts.distributions.value?.totalDocuments).toBe(7)

    // An explicit Search counts again.
    charts.show(filtered(), { force: true })
    await flush()
    expect(requests).toHaveLength(2)
    scope.stop()
  })

  it('sends no chunk filters when none are set', async () => {
    const scope = effectScope()
    const charts = scope.run(() => useExploreCharts())!
    charts.show(normalizeCriteria({ documentFilters: { languages: ['ces'] } }))
    await flush()
    expect(requests[0].body).toEqual({ filters: { ...NO_DOCUMENT_FILTERS, languages: ['ces'] } })
    scope.stop()
  })

  it('drops the late answer of earlier filters and counts again after a failure', async () => {
    muteConsole('error')
    const scope = effectScope()
    const charts = scope.run(() => useExploreCharts())!
    charts.show(filtered())
    await flush()
    charts.show(normalizeCriteria({}))
    await flush()
    expect(requests[0].signal?.aborted).toBe(true)
    requests[1].answer(distributionsBody(10))
    requests[0].answer(distributionsBody(7))
    await flushPromises()
    expect(charts.distributions.value?.totalDocuments).toBe(10)

    charts.show(filtered())
    await flush()
    requests[2].answer({ detail: 'Weaviate unavailable' }, 503)
    await flushPromises()
    expect([charts.error.value !== null, charts.distributions.value]).toEqual([true, null])
    charts.show(filtered()) // the same filters, but the last count failed
    await flush()
    expect(requests).toHaveLength(4)
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

  it('charts nothing for a text query, filter-only passages or a collection, and says why', async () => {
    const counted = distributions(10)
    for (const [availability, testId] of [['textQuery', 'charts-text-query'], ['passages', 'charts-passages'], ['collection', 'charts-collection']]) {
      const wrapper = view({ availability, distributions: counted })
      expect(testIds(wrapper)).toEqual(availability === 'passages' ? [testId, 'charts-show-documents'] : [testId])
      expect(wrapper.find('[data-testid="corpus-years"]').exists()).toBe(false)
    }
    const passages = view({ availability: 'passages' })
    await passages.get('[data-testid="charts-show-documents"]').trigger('click')
    expect(passages.emitted('showDocuments')).toHaveLength(1)
  })
})
