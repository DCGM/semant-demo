import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { effectScope } from 'vue'

import { normalizeCriteria } from 'src/features/explore/criteria'
import { useResultCharts, type RankedPopulation } from 'src/features/explore/useResultCharts'
import { categoryBarSpec, categoryRows, withChartFilter } from 'src/features/analytics/corpusOverview'
import RankedResultCharts from 'src/features/explore/RankedResultCharts.vue'
import ExploreVisualizations from 'src/features/explore/ExploreVisualizations.vue'
import type { RankedResultsDistributions } from 'src/generated/api'
import { loadEmbed } from 'src/shared/visualization/loadEmbed'
import { muteConsole } from './console'

// Charts of a text query's ranked results (#620): the counts of exactly the ids the shown search
// ranked (#619), labelled with their unit and ranking; a clicked category is applied as a filter.

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

const CRITERIA = normalizeCriteria({ textQuery: 'Lhota', chunkFilters: { languages: ['ces'] } })

const population = (key = 'passages:1', changes: Partial<RankedPopulation> = {}): RankedPopulation => ({
  key, mode: 'passages', ids: ['p1', 'p2', 'p3'], criteria: CRITERIA, vector: null, userCollectionId: 'c1', bounded: true, ...changes
})

/** The API answer (snake case). */
const answer = (changes: Record<string, unknown> = {}) => ({
  scope: 'ranked_results',
  mode: 'passages',
  unit: 'passages',
  criteria: { text_query: 'Lhota', document_filters: {}, chunk_filters: { languages: ['ces'], classifications: {} } },
  ranking: { type: 'hybrid', vector: 'default-vector', bounded: true, retrieval_limit: 3 },
  input_count: 3,
  total_count: 3,
  missing_count: 0,
  distinct_documents: 2,
  computed_at: '2026-11-08T12:00:00Z',
  publication_year: { available: true, years: [{ year: 1851, count: 2 }], unknown_count: 1 },
  libraries: { available: true, values: [{ value: 'mzk', count: 1 }], other_count: 1, unknown_count: 1 },
  languages: { available: true, values: [{ value: 'ces', count: 3 }], other_count: 0, unknown_count: 0 },
  ...changes
})

/** The same answer as the generated client hands it to the page (camel case). */
const counts = (changes: Partial<RankedResultsDistributions> = {}): RankedResultsDistributions => ({
  scope: 'ranked_results',
  mode: 'passages',
  unit: 'passages',
  criteria: { textQuery: 'Lhota', documentFilters: {}, chunkFilters: { languages: ['ces'], classifications: {} } },
  ranking: { type: 'hybrid', vector: 'default-vector', bounded: true, retrievalLimit: 3 },
  inputCount: 3,
  totalCount: 3,
  missingCount: 0,
  distinctDocuments: 2,
  computedAt: new Date('2026-11-08T12:00:00Z'),
  publicationYear: { available: true, years: [{ year: 1851, count: 2 }], unknownCount: 1 },
  libraries: { available: true, values: [{ value: 'mzk', count: 1 }], otherCount: 1, unknownCount: 1 },
  languages: { available: true, values: [{ value: 'ces', count: 3 }], otherCount: 0, unknownCount: 0 },
  ...changes
})

describe('useResultCharts', () => {
  it('counts exactly the ranked ids of the search, with its criteria, collection and ranking, once per search', async () => {
    const scope = effectScope()
    const charts = scope.run(() => useResultCharts())!
    void charts.show(population())
    await flush()
    expect(requests.map(r => r.path)).toEqual(['/api/analytics/results/distributions'])
    expect(requests[0].body).toEqual({
      mode: 'passages',
      ids: ['p1', 'p2', 'p3'],
      criteria: {
        text_query: 'Lhota',
        document_filters: { year_min: null, year_max: null, title_contains: [], libraries: [], languages: [] },
        chunk_filters: { languages: ['ces'], classifications: {} }
      },
      user_collection_id: 'c1',
      ranking: { type: 'hybrid', vector: null, bounded: true }
    })
    // Shown again (a view switch) while counting and once counted: no new request.
    void charts.show(population())
    requests[0].answer(answer())
    await flushPromises()
    void charts.show(population())
    await flush()
    expect(requests).toHaveLength(1)
    expect(charts.distributions.value?.distinctDocuments).toBe(2)

    // Another search (or mode) is another population.
    void charts.show(population('documents:2', { mode: 'documents', ids: ['d1'] }))
    await flush()
    expect([requests.length, requests[1].body.mode, charts.distributions.value]).toEqual([2, 'documents', null])
    scope.stop()
  })

  it('drops the late answer of an earlier search, and a refused request is not offered again', async () => {
    muteConsole('error')
    const scope = effectScope()
    const charts = scope.run(() => useResultCharts())!
    void charts.show(population('passages:1'))
    await flush()
    void charts.show(population('passages:2'))
    await flush()
    expect(requests[0].signal?.aborted).toBe(true)
    requests[1].answer(answer({ total_count: 2 }))
    requests[0].answer(answer({ total_count: 3 }))
    await flushPromises()
    expect([charts.population.value?.key, charts.distributions.value?.totalCount]).toEqual(['passages:2', 2])

    void charts.show(population('passages:3'))
    await flush()
    requests[2].answer({ detail: 'At most 1 ranked ids can be counted.' }, 400)
    await flushPromises()
    expect([charts.error.value, charts.invalid.value]).toEqual(['At most 1 ranked ids can be counted.', true])
    void charts.retry()
    await flush()
    expect(requests).toHaveLength(4)
    charts.clear()
    expect([charts.population.value, charts.error.value, requests[3].signal?.aborted]).toEqual([null, null, true])
    scope.stop()
  })
})

describe('RankedResultCharts', () => {
  const view = (c: RankedResultsDistributions) => mount(RankedResultCharts, {
    props: { counts: c, vectorName: 'Default vector' }, global: { plugins: [[Quasar, {}]] }
  })

  it('names the unit, the distinct documents, the ranking and that it is bounded', async () => {
    const wrapper = view(counts({ missingCount: 1, inputCount: 4 }))
    await flushPromises()
    expect(wrapper.get('[data-testid="charts-total"]').text()).toBe('3')
    const scope = wrapper.get('[data-testid="charts-scope"]').text()
    expect(scope).toContain('passages counted: the ranked passages of this search, not the whole corpus')
    expect(wrapper.get('[data-testid="charts-distinct-documents"]').text()).toContain('come from 2 distinct documents')
    expect(wrapper.get('[data-testid="charts-ranking"]').text()).toContain('hybrid search (keywords and meaning) (Default vector)')
    expect(wrapper.get('[data-testid="charts-ranking"]').text()).toContain('Bounded: only the best 4 passages by relevance')
    expect(scope).toContain('Clicking a bar applies it as a filter and searches again')
    expect(wrapper.get('[data-testid="charts-missing"]').text()).toContain('1 of the 4 ranked passages is not counted')
  })

  it('says when every match was retrieved, counted once per document', async () => {
    const wrapper = view(counts({ mode: 'documents', unit: 'documents', ranking: { type: 'hybrid', vector: null, bounded: false, retrievalLimit: 3000 } }))
    await flushPromises()
    // Documents are ordered metadata matches first, not by one relevance ranking (#607).
    expect(wrapper.get('[data-testid="charts-ranking"]').text()).toContain('Ordered as the Documents results: Matches in the title, author or publisher first')
    expect(wrapper.get('[data-testid="charts-ranking"]').text()).toContain('Every matching document was retrieved')
    expect(wrapper.find('[data-testid="charts-distinct-documents"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="charts-scope"]').text()).toContain('Each document is counted once')
  })

  it('applies a year bin, library or document language as a filter; Other, Unknown and unavailable ones are not', async () => {
    const wrapper = view(counts({ libraries: { available: false, unavailableReason: 'missing_property' } }))
    await flushPromises()
    expect(wrapper.get('[data-testid="results-libraries"]').text()).toContain('Not available')
    expect(wrapper.find('[data-testid^="results-libraries-filter-"]').exists()).toBe(false)
    // Keyboard equivalents of the bars in the collapsed data tables.
    expect(wrapper.get('[data-testid="results-languages-table"]').classes()).not.toContain('q-expansion-item--expanded')
    await wrapper.get('[data-testid="results-languages-filter-ces"]').trigger('click')
    await wrapper.get('[data-testid="timeline-filter-bin-1851"]').trigger('click')
    expect(wrapper.emitted('applyFilter')).toEqual([
      [{ dimension: 'languages', value: 'ces' }], [{ dimension: 'years', start: 1851, end: 1851 }]
    ])

    const withOther = view(counts())
    await flushPromises()
    expect(withOther.find('[data-testid="results-libraries-filter-mzk"]').exists()).toBe(true)
    expect(withOther.findAll('[data-testid^="results-libraries-filter-"]')).toHaveLength(1) // not Other or Unknown
  })

  it('tells no ranked results apart from ranked results that could not be counted', () => {
    const none = view(counts({ inputCount: 0, totalCount: 0, distinctDocuments: 0 }))
    expect(none.get('[data-testid="charts-empty"]').text()).toContain('No results match this search.')
    const gone = view(counts({ inputCount: 2, totalCount: 0, missingCount: 2, distinctDocuments: 0 }))
    expect(gone.get('[data-testid="charts-empty"]').text()).toContain('None of the ranked results could be counted.')
  })
})

describe('ExploreVisualizations of a text query', () => {
  const state = (changes = {}) => ({ searching: false, searchError: null, counts: null, slow: false, error: null, invalid: false, vectorName: null, ...changes })
  const view = (ranked: ReturnType<typeof state>) => mount(ExploreVisualizations, {
    props: { availability: 'ranked', distributions: null, loading: false, slow: false, error: null, invalid: false, ranked },
    global: { plugins: [[Quasar, {}]] }
  })

  it('shows the search, then the counting, then the charts; failures of either can be retried', async () => {
    expect(view(state({ searching: true })).get('[data-testid="charts-loading"]').text()).toContain('Searching…')
    expect(view(state()).get('[data-testid="charts-loading"]').text()).toContain('Counting the search results…')
    const failedSearch = view(state({ searchError: 'Weaviate unavailable' }))
    await failedSearch.get('[data-testid="charts-search-retry"]').trigger('click')
    expect(failedSearch.emitted('retrySearch')).toHaveLength(1)
    const failedCount = view(state({ error: 'Weaviate unavailable' }))
    await failedCount.get('[data-testid="charts-retry"]').trigger('click')
    expect(failedCount.emitted('retryRanked')).toHaveLength(1)
    expect(view(state({ error: 'refused', invalid: true })).find('[data-testid="charts-retry"]').exists()).toBe(false)

    const charted = view(state({ counts: counts() }))
    await flushPromises()
    expect(charted.get('[data-testid="charts-total"]').text()).toBe('3')
    await charted.get('[data-testid="results-languages-filter-ces"]').trigger('click')
    expect(charted.emitted('applyFilter')).toEqual([[{ dimension: 'languages', value: 'ces' }]])
  })
})

describe('chart filters', () => {
  it('replace only their own dimension', () => {
    const filters = { yearMin: 1800, yearMax: 1900, titleContains: ['Kronika'], libraries: ['nkp'], languages: ['deu'] }
    expect(withChartFilter(filters, { dimension: 'years', start: 1850, end: 1859 }))
      .toEqual({ ...filters, yearMin: 1850, yearMax: 1859 })
    expect(withChartFilter(filters, { dimension: 'libraries', value: 'mzk' })).toEqual({ ...filters, libraries: ['mzk'] })
    expect(withChartFilter(filters, { dimension: 'languages', value: 'ces' })).toEqual({ ...filters, languages: ['ces'] })
  })

  it('say which bars a click applies, and highlight only those', () => {
    const rows = categoryRows({ available: true, values: [{ value: 'mzk', count: 2 }], otherCount: 1, unknownCount: 1 }, String)
    const spec = categoryBarSpec(rows, 'Library', 'passages', true) as { data: { values: { action: string }[] }, encoding: Record<string, unknown> }
    expect(spec.data.values.map(v => v.action)).toEqual(['Click to filter by mzk', 'Not available as a filter', 'Not available as a filter'])
    expect(JSON.stringify(spec.encoding.opacity)).toContain("datum.kind === 'value'")
    expect(JSON.stringify(categoryBarSpec(rows, 'Library'))).not.toContain('action')
  })
})
