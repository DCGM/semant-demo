import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { effectScope } from 'vue'

import { normalizeCriteria } from 'src/features/explore/criteria'
import {
  inspectedMembers, inspectionCount, inspectionLabel, useResultCharts, type RankedPopulation
} from 'src/features/explore/useResultCharts'
import { useResultInspection, type InspectedSubset } from 'src/features/explore/useResultInspection'
import RankedResultCharts from 'src/features/explore/RankedResultCharts.vue'
import ExploreVisualizations from 'src/features/explore/ExploreVisualizations.vue'
import type { RankedResultsDistributions } from 'src/generated/api'
import { loadEmbed } from 'src/shared/visualization/loadEmbed'
import { muteConsole } from './console'

// Charts of a text query's ranked results (#620): the counts of exactly the ids the shown search
// ranked (#619), labelled with their unit and ranking, and their categories inspected within it.

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
  members: [
    { id: 'p1', document_id: 'd1', year: 1851, library: 'mzk', language: 'ces' },
    { id: 'p2', document_id: 'd1', year: 1851, library: 'nkp', language: 'ces' },
    { id: 'p3', document_id: 'd2', year: null, library: null, language: 'ces' }
  ],
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
  members: [
    { id: 'p1', documentId: 'd1', year: 1851, library: 'mzk', language: 'ces' },
    { id: 'p2', documentId: 'd1', year: 1851, library: 'nkp', language: 'ces' },
    { id: 'p3', documentId: 'd2', year: null, library: null, language: 'ces' }
  ],
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
      ranking: { type: 'hybrid', vector: null, bounded: true },
      members: true
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

describe('inspecting a chart category', () => {
  const ids = (list: { id: string }[] | null) => list?.map(m => m.id) ?? null

  it('selects the counted results of the category, in ranking order, from the same answer', () => {
    const c = counts()
    expect(ids(inspectedMembers(c, { dimension: 'year', value: '1850-1859' }))).toEqual(['p1', 'p2'])
    expect(ids(inspectedMembers(c, { dimension: 'year', value: '1852' }))).toEqual([])
    expect(ids(inspectedMembers(c, { dimension: 'year', value: '~unknown' }))).toEqual(['p3'])
    expect(ids(inspectedMembers(c, { dimension: 'library', value: 'mzk' }))).toEqual(['p1'])
    // Other: a value the counts do not list (nkp); Unknown: none recorded.
    expect(ids(inspectedMembers(c, { dimension: 'library', value: '~other' }))).toEqual(['p2'])
    expect(ids(inspectedMembers(c, { dimension: 'library', value: '~unknown' }))).toEqual(['p3'])
    expect(ids(inspectedMembers(c, { dimension: 'language', value: 'ces' }))).toEqual(['p1', 'p2', 'p3'])
    // A property the store does not record cannot be inspected (not an empty category).
    const unrecorded = counts({ libraries: { available: false, unavailableReason: 'missing_property' } })
    expect(inspectedMembers(unrecorded, { dimension: 'library', value: '~unknown' })).toBeNull()
  })

  it('names the category and the counted population', () => {
    expect(inspectionLabel({ dimension: 'year', value: '1850-1859' })).toBe('published 1850–1859')
    expect(inspectionLabel({ dimension: 'year', value: '1851' })).toBe('published in 1851')
    expect(inspectionLabel({ dimension: 'library', value: 'mzk' })).toBe('from Moravian Library (mzk)')
    expect(inspectionLabel({ dimension: 'language', value: '~unknown' })).toBe('without a document language')
    expect(inspectionCount(2, counts())).toBe('2 of the 3 counted passages')
  })
})

describe('useResultInspection', () => {
  const subset = (key: string, changes: Partial<InspectedSubset> = {}): InspectedSubset => ({
    key, criteria: CRITERIA, userCollectionId: 'c1', documents: null, passageIds: ['p1', 'p2', 'p3'], ...changes
  })
  const chunk = (id: string) => ({ id, text: id, document: 'd1', documentObject: { id: 'd1' } })

  it('reads the inspected passages by id under the search criteria, never searching', async () => {
    const scope = effectScope()
    const inspection = scope.run(() => useResultInspection())!
    void inspection.open(subset('a'))
    await flush()
    expect(requests.map(r => r.path)).toEqual(['/api/search/passages/read'])
    expect(requests[0].body).toMatchObject({ ids: ['p1', 'p2', 'p3'], user_collection_id: 'c1', criteria: { text_query: 'Lhota' } })
    requests[0].answer({ items: [chunk('p1'), chunk('p3')], time_spent: 0 })
    await flushPromises()
    expect(inspection.passages.value.map(p => p.id)).toEqual(['p1', 'p3']) // p2 is gone: left out
    expect([inspection.readCount.value, inspection.hasMore()]).toEqual([3, false])
    // The same subset again: nothing read again.
    void inspection.open(subset('a'))
    await flush()
    expect(requests).toHaveLength(1)
    scope.stop()
  })

  it('reads inspected documents by their ranking entries and drops the answer of an earlier subset', async () => {
    const scope = effectScope()
    const inspection = scope.run(() => useResultInspection())!
    const entry = (id: string) => ({ id, match: 'text' as const, chunkId: `${id}-c` })
    void inspection.open(subset('a', { documents: [entry('d1')], passageIds: null }))
    await flush()
    void inspection.open(subset('b', { documents: [entry('d2')], passageIds: null }))
    await flush()
    expect(requests.map(r => r.path)).toEqual(['/api/search/documents/read', '/api/search/documents/read'])
    expect(requests[1].body.ranked).toEqual([{ id: 'd2', match: 'text', chunk_id: 'd2-c' }])
    const hit = (id: string) => ({ document: { id, title: id }, match: 'text' })
    requests[0].answer({ items: [hit('d1')], time_spent: 0 })
    requests[1].answer({ items: [hit('d2')], time_spent: 0 })
    await flushPromises()
    expect(inspection.documents.value.map(d => d.document.id)).toEqual(['d2'])
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
    expect(wrapper.get('[data-testid="charts-ranking"]').text()).toContain('Bounded: only the best 4 by relevance')
    expect(wrapper.get('[data-testid="charts-missing"]').text()).toContain('1 of the 4 ranked passages is not counted')
  })

  it('says when every match was retrieved, counted once per document', async () => {
    const wrapper = view(counts({ mode: 'documents', unit: 'documents', ranking: { type: 'hybrid', vector: null, bounded: false, retrievalLimit: 3000 } }))
    await flushPromises()
    expect(wrapper.get('[data-testid="charts-ranking"]').text()).toContain('Every matching document was retrieved')
    expect(wrapper.find('[data-testid="charts-distinct-documents"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="charts-scope"]').text()).toContain('Each document is counted once')
  })

  it('inspects a category, Other and Unknown; a property not recorded is unavailable, not zero', async () => {
    const wrapper = view(counts({ libraries: { available: false, unavailableReason: 'missing_property' } }))
    await flushPromises()
    expect(wrapper.get('[data-testid="results-libraries"]').text()).toContain('Not available')
    expect(wrapper.find('[data-testid^="inspect-libraries-"]').exists()).toBe(false)
    await wrapper.get('[data-testid="inspect-languages-ces"]').trigger('click')
    await wrapper.get('[data-testid="timeline-inspect-unknown"]').trigger('click')
    await wrapper.get('[data-testid="timeline-inspect-period"]').trigger('click')
    expect(wrapper.emitted('inspect')).toEqual([
      [{ dimension: 'language', value: 'ces' }], [{ dimension: 'year', value: '~unknown' }], [{ dimension: 'year', value: '1850-1859' }]
    ])

    const withOther = view(counts())
    await flushPromises()
    await withOther.get('[data-testid="inspect-libraries-other"]').trigger('click')
    expect(withOther.emitted('inspect')).toEqual([[{ dimension: 'library', value: '~other' }]])
    // An empty category offers nothing to inspect (languages: no Unknown).
    expect(withOther.find('[data-testid="inspect-languages-unknown"]').exists()).toBe(false)
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
    await charted.get('[data-testid="inspect-languages-ces"]').trigger('click')
    expect(charted.emitted('inspect')).toEqual([[{ dimension: 'language', value: 'ces' }]])
  })
})
