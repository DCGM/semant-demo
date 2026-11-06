import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import { FilterType, type PassageSearchResponse, type SearchFilter, type SearchResultChunk } from 'src/generated/api'
import {
  criteriaKey, effectiveMode, emptyLocation, locationQuery, normalizeCriteria, parseLocationQuery, sameCriteria,
  type ExploreLocation
} from 'src/features/explore/criteria'
import { useExploreLocation, type AppliedReason } from 'src/features/explore/useExploreLocation'
import { passageCoverage, usePassageSearch, type PassageQuery, type PassageResults } from 'src/features/explore/usePassageSearch'
import {
  criteriaChips, criteriaOfFilterValues, historyFiltersOf, nominalValuesOf, offeredCriteria, withNominalValues,
  withYearRange, yearRangeOf
} from 'src/features/search/searchFilters'
import { muteConsole } from './console'

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
const NOW = new Date('2026-11-06T12:00:00Z')

const criteria = (overrides: Parameters<typeof normalizeCriteria>[0] = {}) => normalizeCriteria(overrides)
const location = (overrides: Partial<ExploreLocation> = {}): ExploreLocation => ({ ...emptyLocation(), ...overrides })

// The configured search filters as the server describes them (configs/search_filters.yaml).
const YEAR: SearchFilter = { id: 'year_range', name: 'Year range', type: FilterType.interval, description: '', targetProperty: 'yearIssued', minValue: 1800, maxValue: 1950 }
const LANGUAGE: SearchFilter = {
  id: 'language',
  name: 'Language',
  type: FilterType.nominal,
  description: '',
  targetProperty: 'language',
  values: [{ userForm: 'Czech', backendForm: 'ces' }, { userForm: 'German', backendForm: 'deu' }]
}
const COMPLEXITY: SearchFilter = {
  id: 'complexity',
  name: 'Complexity',
  type: FilterType.nominal,
  description: '',
  targetProperty: 'complexity',
  values: [{ userForm: 'Easy', backendForm: 'easy' }, { userForm: 'Very Easy', backendForm: 'very_easy' }]
}
const FILTERS = [YEAR, LANGUAGE, COMPLEXITY]

describe('search criteria', () => {
  it('are canonical: order, repeats, blanks and empty lists do not make them differ', () => {
    const a = criteria({ textQuery: ' Lhota ', chunkFilters: { languages: ['deu', 'ces', 'ces'], classifications: { style: ['b', 'a'], complexity: [] } } })
    const b = criteria({ textQuery: 'Lhota', chunkFilters: { languages: ['ces', 'deu'], classifications: { style: ['a', 'b'] } } })
    expect(sameCriteria(a, b)).toBe(true)
    expect(a.chunkFilters.classifications).toEqual({ style: ['a', 'b'] })
    expect(criteria({ textQuery: '   ' }).textQuery).toBeNull()
    expect(criteriaKey(a)).not.toBe(criteriaKey(criteria({ textQuery: 'Lhota' })))
  })

  it('default to Passages for a text query and to Documents without, unless a mode is chosen', () => {
    expect(effectiveMode(location({ criteria: criteria({ textQuery: 'x' }) }))).toBe('passages')
    expect(effectiveMode(location({ criteria: criteria({ documentFilters: { yearMin: 1900 } }) }))).toBe('documents')
    expect(effectiveMode(location({ criteria: criteria({ textQuery: 'x' }), mode: 'documents' }))).toBe('documents')
  })
})

describe('the Explore URL', () => {
  it('round-trips the applied criteria, mode, view and search vector', () => {
    const applied = location({
      criteria: criteria({
        textQuery: 'požár v Lhotě',
        documentFilters: { yearMin: 1850, yearMax: 1900, titleContains: ['Kronika'], libraries: ['mzk'], languages: ['ces'] },
        chunkFilters: { languages: ['ces', 'deu'], classifications: { complexity: ['easy'], style: ['formal', 'informal'] } }
      }),
      mode: 'passages',
      view: 'results',
      vector: 'second'
    })
    const query = locationQuery(applied)
    expect(query).toEqual({
      q: 'požár v Lhotě',
      year_min: '1850',
      year_max: '1900',
      title_contains: ['Kronika'],
      libraries: ['mzk'],
      languages: ['ces'],
      chunk_languages: ['ces', 'deu'],
      chunk_classifications: ['complexity:easy', 'style:formal', 'style:informal'],
      mode: 'passages',
      view: 'results',
      vector: 'second'
    })
    // As the router hands it back: single values as strings, repeated ones as arrays.
    expect(parseLocationQuery(query as never, NOW)).toEqual({ location: applied, invalid: [] })
  })

  it('has no parameters for the empty criteria and ignores parameters it does not use', () => {
    expect(locationQuery(emptyLocation())).toEqual({})
    expect(parseLocationQuery({ chunk: 'c1', from: 'search' }, NOW)).toEqual({ location: emptyLocation(), invalid: [] })
  })

  it('leaves out malformed values and names them', () => {
    const { location: parsed, invalid } = parseLocationQuery({
      q: ['one', 'two'],
      year_min: 'abc',
      year_max: '2999',
      chunk_classifications: ['complexity:easy', 'complexity', ':easy'],
      libraries: Array.from({ length: 51 }, (_, i) => `lib${i}`),
      mode: 'charts',
      view: 'visualizations'
    }, NOW)

    expect(parsed).toEqual(location({
      criteria: criteria({ chunkFilters: { classifications: { complexity: ['easy'] } } }),
      view: 'visualizations'
    }))
    expect(invalid).toEqual([
      'Text query (given more than once)', 'Publication year from: abc', 'Publication year to: 2999', 'Library',
      'Passage filter: complexity', 'Passage filter: :easy', 'Results mode: charts'
    ])
  })

  it('refuses reversed years and a too long text query', () => {
    expect(parseLocationQuery({ year_min: '1900', year_max: '1850' }, NOW).invalid).toEqual(['Publication years 1900–1850'])
    const long = parseLocationQuery({ q: 'x'.repeat(1001) }, NOW)
    expect([long.location.criteria.textQuery, long.invalid]).toEqual([null, ['Text query (too long)']])
  })
})

describe('configured filters as criteria', () => {
  it('edit the publication year; an end at the filter bound leaves it open', () => {
    let c = withYearRange(criteria(), YEAR, { min: 1850, max: 1950 })
    expect([c.documentFilters.yearMin, c.documentFilters.yearMax]).toEqual([1850, null])
    expect(yearRangeOf(c, YEAR)).toEqual({ min: 1850, max: 1950 })
    c = withYearRange(c, YEAR, { min: 1800, max: 1950 })
    expect([c.documentFilters.yearMin, c.documentFilters.yearMax]).toEqual([null, null])
    // A year from a link outside the bounds is shown clamped and kept until moved.
    expect(yearRangeOf(criteria({ documentFilters: { yearMin: 1500 } }), YEAR)).toEqual({ min: 1800, max: 1950 })
  })

  it('edit the passage language and the classifications by stored property', () => {
    let c = withNominalValues(criteria(), LANGUAGE, ['deu', 'ces'])
    c = withNominalValues(c, COMPLEXITY, ['easy'])
    expect(c.chunkFilters).toEqual({ languages: ['ces', 'deu'], classifications: { complexity: ['easy'] } })
    expect(c.documentFilters.languages).toEqual([]) // not the document language
    expect(nominalValuesOf(c, COMPLEXITY)).toEqual(['easy'])
    expect(withNominalValues(c, COMPLEXITY, null).chunkFilters.classifications).toEqual({})
  })

  it('keep only the offered passage filters, in their configured spelling, naming the rest', () => {
    const { criteria: offered, dropped } = offeredCriteria(criteria({
      documentFilters: { libraries: ['nkp'] },
      chunkFilters: { languages: ['CES', 'eng'], classifications: { complexity: ['EASY', 'trivial'], mood: ['calm'] } }
    }), FILTERS)
    expect(offered).toEqual(criteria({
      documentFilters: { libraries: ['nkp'] },
      chunkFilters: { languages: ['ces'], classifications: { complexity: ['easy'] } }
    }))
    expect(dropped).toEqual(['Passage language: eng', 'Complexity: trivial', 'Mood: calm'])
  })

  it('convert to and from the search history form', () => {
    const c = criteria({ textQuery: 'Lhota', documentFilters: { yearMin: 1850, libraries: ['mzk'] }, chunkFilters: { languages: ['ces'], classifications: { complexity: ['easy'] } } })
    const kept = historyFiltersOf(c, FILTERS)
    expect(kept).toEqual([
      { id: 'year_range', minValue: 1850, maxValue: 1950 },
      { id: 'language', values: ['ces'] },
      { id: 'complexity', values: ['easy'] }
    ])
    // The history cannot hold the library (no widget); the rest comes back.
    const values = { year_range: { min: 1850, max: 1950 }, language: ['ces'], complexity: ['easy'] }
    expect(criteriaOfFilterValues('Lhota', values, FILTERS)).toEqual(criteria({
      textQuery: 'Lhota', documentFilters: { yearMin: 1850 }, chunkFilters: { languages: ['ces'], classifications: { complexity: ['easy'] } }
    }))
  })

  it('are shown as chips that each remove one value', () => {
    const c = criteria({ documentFilters: { yearMax: 1900, libraries: ['mzk'] }, chunkFilters: { languages: ['ces', 'deu'] } })
    const chips = criteriaChips(c, FILTERS)
    expect(chips.map(chip => chip.label)).toEqual(['Year Range: to 1900', 'Library: mzk', 'Language: Czech', 'Language: German'])
    expect(chips[2].without.chunkFilters.languages).toEqual(['deu'])
    expect(chips[0].without.documentFilters).toMatchObject({ yearMax: null, libraries: ['mzk'] })
  })
})

describe('useExploreLocation', () => {
  const Page = { render: () => null }

  async function setup (initial: string) {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { name: 'search', path: '/search', component: Page },
        { name: 'document', path: '/documents/:id', component: Page }
      ]
    })
    await router.push(initial)
    const calls: { reason: AppliedReason, invalid: string[], q: string | null }[] = []
    let explore!: ReturnType<typeof useExploreLocation>
    const Host = defineComponent({
      setup () {
        explore = useExploreLocation('search', (loc, { reason, invalid }) => calls.push({ reason, invalid, q: loc.criteria.textQuery }))
        return () => h('div')
      }
    })
    mount(Host, { global: { plugins: [router] } })
    await router.isReady()
    return { router, calls, explore: () => explore }
  }

  it('applies the URL, records applied criteria in history and restores them on Back/Forward', async () => {
    const { router, calls, explore } = await setup('/search?q=one')
    expect(calls).toEqual([{ reason: 'navigation', invalid: [], q: 'one' }])

    await explore().apply(location({ criteria: criteria({ textQuery: 'two', chunkFilters: { languages: ['ces'] } }) }))
    expect(router.currentRoute.value.fullPath).toBe('/search?q=two&chunk_languages=ces')
    expect(calls.at(-1)).toEqual({ reason: 'apply', invalid: [], q: 'two' })
    expect(calls).toHaveLength(2) // the URL change it made is not applied a second time

    router.back()
    await flush()
    expect(calls.at(-1)).toEqual({ reason: 'navigation', invalid: [], q: 'one' })
    expect(explore().applied.value.criteria.chunkFilters.languages).toEqual([])
    router.forward()
    await flush()
    expect(explore().applied.value.criteria).toEqual(criteria({ textQuery: 'two', chunkFilters: { languages: ['ces'] } }))
  })

  it('searches again when the applied criteria are applied unchanged, without a new history entry', async () => {
    const { router, calls, explore } = await setup('/search?q=one')
    const push = vi.spyOn(router, 'push')
    await explore().apply(location({ criteria: criteria({ textQuery: 'one' }) }))
    expect(calls.map(c => c.reason)).toEqual(['navigation', 'apply'])
    expect(router.currentRoute.value.fullPath).toBe('/search?q=one')
    expect(push).not.toHaveBeenCalled()
  })

  it('replaces malformed URL values and reports them', async () => {
    const { router, calls } = await setup('/search?q=one&year_min=soon')
    await flush()
    expect(calls[0]).toEqual({ reason: 'navigation', invalid: ['Publication year from: soon'], q: 'one' })
    expect(router.currentRoute.value.fullPath).toBe('/search?q=one')
    expect(calls).toHaveLength(1)
  })

  it('ignores the URLs of other pages and changes nothing when coming back to the same search', async () => {
    const { router, calls } = await setup('/search?q=one')
    await router.push({ name: 'document', params: { id: 'd1' }, query: { q: 'other', from: 'search' } })
    await router.push('/search?q=one')
    expect(calls).toHaveLength(1)
  })
})

const hit = (id: string): SearchResultChunk => ({
  id, text: `text of ${id}`, startPageId: 'p', fromPage: 1, toPage: 1, document: `doc-${id}`, order: 1, documentObject: { id: `doc-${id}` }
})

/** A page as the server sends it (snake_case). */
const page = (ids: string[], more: Partial<{ next_offset: number | null, has_more: boolean, bounded: boolean | null, total_count: number | null }> = {}) => ({
  items: ids.map(hit).map(h => ({ id: h.id, text: h.text, start_page_id: 'p', from_page: 1, to_page: 1, document: h.document, order: 1, document_object: { id: h.document } })),
  offset: 0,
  next_offset: null,
  has_more: false,
  retrieval_limit: 1000,
  bounded: false,
  total_count: ids.length,
  criteria: { text_query: 'q', document_filters: {}, chunk_filters: {} },
  time_spent: 0.2,
  ...more
})

describe('usePassageSearch', () => {
  const originalFetch = globalThis.fetch
  const requests: { body: Record<string, unknown>, answer: (body: unknown, status?: number) => void }[] = []

  afterEach(() => {
    globalThis.fetch = originalFetch
    requests.length = 0
  })

  function serve () {
    globalThis.fetch = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((resolve) => {
      requests.push({
        body: JSON.parse(String(init?.body)),
        answer: (body, status = 200) => resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
      })
    })) as typeof fetch
  }

  const query = (text: string, userCollectionId: string | null = null): PassageQuery => ({
    criteria: criteria({ textQuery: text, chunkFilters: { languages: ['ces'] } }), vector: null, userCollectionId
  })

  it('sends the criteria and retrieval options, and pages with Load more under the same search', async () => {
    serve()
    const search = usePassageSearch()
    const first = search.search(query('Lhota', 'c1'))
    await flush()
    expect(requests[0].body).toEqual({
      criteria: { text_query: 'Lhota', document_filters: { year_min: null, year_max: null, title_contains: [], libraries: [], languages: [] }, chunk_filters: { languages: ['ces'], classifications: {} } },
      offset: 0,
      limit: 20,
      type: 'hybrid',
      vector: null,
      user_collection_id: 'c1'
    })
    requests[0].answer(page(['a', 'b'], { next_offset: 2, has_more: true, bounded: null, total_count: null }))
    const results = await first
    expect(results?.items.map(i => i.id)).toEqual(['a', 'b'])

    const more = search.loadMore()
    await flush()
    expect(requests[1].body).toMatchObject({ offset: 2, user_collection_id: 'c1' })
    expect(search.loadingMore.value).toBe(true)
    requests[1].answer(page(['b', 'c'])) // b ranked again: shown once
    await more
    expect(search.results.value?.items.map(i => i.id)).toEqual(['a', 'b', 'c'])
    expect(search.results.value?.id).toBe(results?.id)
    expect([search.loadingMore.value, search.results.value?.last.hasMore]).toEqual([false, false])
  })

  it('drops the late answers of an earlier search and of its Load more', async () => {
    serve()
    const search = usePassageSearch()
    const first = search.search(query('one'))
    await flush()
    requests[0].answer(page(['a'], { next_offset: 1, has_more: true, bounded: null, total_count: null }))
    await first
    const more = search.loadMore()
    await flush()
    const second = search.search(query('two'))
    await flush()
    expect(search.results.value).toBeNull() // no earlier results while the new search runs

    requests[1].answer(page(['late']))
    await more
    expect([search.results.value, search.loading.value]).toEqual([null, true])
    requests[2].answer(page(['new']))
    expect((await second)?.items.map(i => i.id)).toEqual(['new'])
    expect([search.loading.value, search.loadingMore.value]).toEqual([false, false])
  })

  it('reports a refused search with the server reason and keeps loaded passages when Load more fails', async () => {
    const logged = muteConsole('error')
    serve()
    const search = usePassageSearch()
    const refused = search.search(query('one'))
    await flush()
    requests[0].answer({ detail: 'Passages cannot be filtered by complexity: this corpus database is not recorded.' }, 422)
    expect(await refused).toBeNull()
    expect(search.error.value).toBe('Passages cannot be filtered by complexity: this corpus database is not recorded.')

    const ok = search.search(query('two'))
    await flush()
    expect(search.error.value).toBeNull()
    requests[1].answer(page(['a'], { next_offset: 1, has_more: true, bounded: null, total_count: null }))
    await ok
    const more = search.loadMore()
    await flush()
    requests[2].answer({ detail: 'Weaviate unavailable' }, 500)
    await more
    expect(search.results.value?.items.map(i => i.id)).toEqual(['a'])
    expect(search.loadMoreError.value).toBe('Weaviate unavailable')
    expect(logged).toHaveBeenCalled()
  })
})

describe('passage coverage', () => {
  const results = (items: number, last: Partial<PassageSearchResponse>): PassageResults => ({
    id: 1,
    query: { criteria: criteria({ textQuery: 'q' }), vector: null, userCollectionId: null },
    items: Array.from({ length: items }, (_, i) => hit(String(i))),
    last: { items: [], offset: 0, nextOffset: null, hasMore: false, retrievalLimit: 1000, bounded: false, totalCount: items, criteria: { textQuery: 'q' }, timeSpent: 0, ...last },
    timeSpent: 0
  })

  it('says whether the passages are all matches, the best up to the limit, or the best so far', () => {
    expect(passageCoverage(results(1, {}))).toBe('All 1 matching passage.')
    expect(passageCoverage(results(37, {}))).toBe('All 37 matching passages.')
    expect(passageCoverage(results(1000, { bounded: true, totalCount: null }))).toBe(
      'The best 1,000 passages by relevance; more may match. Refine the query or filters to reach others.')
    expect(passageCoverage(results(20, { bounded: null, totalCount: null, hasMore: true }))).toBe(
      'The 20 best passages by relevance so far (at most 1,000 per search).')
  })
})
