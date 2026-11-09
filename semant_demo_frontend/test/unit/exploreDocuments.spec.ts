import { afterEach, describe, expect, it, vi } from 'vitest'

import { normalizeCriteria } from 'src/features/explore/criteria'
import {
  documentCoverage, documentOrderLabel, hasMoreDocuments, useDocumentSearch, type DocumentQuery, type DocumentResults
} from 'src/features/explore/useDocumentSearch'
import { muteConsole } from './console'

// Explore Documents (#606): filter-only document results, paged in the server's stable order.

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
const ids = (count: number, from = 0) => Array.from({ length: count }, (_, i) => `d${from + i}`)
const doc = (id: string) => ({ document: { id, title: `Document ${id}` } })

const originalFetch = globalThis.fetch
const requests: { path: string, body: Record<string, unknown>, answer: (body: unknown, status?: number) => void }[] = []

afterEach(() => {
  globalThis.fetch = originalFetch
  requests.length = 0
})

function serve () {
  globalThis.fetch = vi.fn((url: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((resolve) => {
    requests.push({
      path: new URL(String(url), 'http://test').pathname,
      body: JSON.parse(String(init?.body)),
      answer: (body, status = 200) => resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
    })
  })) as typeof fetch
}

const query = (yearMin: number, userCollectionId: string | null = null): DocumentQuery => ({
  criteria: normalizeCriteria({ documentFilters: { yearMin }, chunkFilters: { languages: ['ces'] } }), userCollectionId
})
const sentCriteria = (yearMin: number) => ({
  text_query: null,
  document_filters: { year_min: yearMin, year_max: null, title_contains: [], libraries: [], languages: [] },
  chunk_filters: { languages: ['ces'], classifications: {} }
})
const page = (items: string[], offset: number, total: number, { retrievalLimit = 10000, nextOffset }: { retrievalLimit?: number, nextOffset?: number | null } = {}) => ({
  items: items.map(doc),
  offset,
  next_offset: nextOffset !== undefined ? nextOffset : offset + items.length < Math.min(total, retrievalLimit) ? offset + items.length : null,
  total_count: total,
  eligible_count: total,
  retrieval_limit: retrievalLimit,
  bounded: total > retrievalLimit,
  order: 'year_asc',
  criteria: {},
  time_spent: 0.01
})

describe('useDocumentSearch', () => {
  it('loads the first 20 documents, then 100 more per Load more from the next offset', async () => {
    serve()
    const search = useDocumentSearch()
    const first = search.search(query(1900, 'c1'))
    await flush()
    expect(requests[0].path).toMatch(/\/api\/search\/documents$/)
    expect(requests[0].body).toEqual({ criteria: sentCriteria(1900), limit: 20, offset: 0, user_collection_id: 'c1' })
    requests[0].answer(page(ids(20), 0, 125))
    const results = await first
    expect([results?.items.length, results?.totalCount, hasMoreDocuments(results!)]).toEqual([20, 125, true])

    const more = search.loadMore()
    await flush()
    expect(requests[1].body).toEqual({ criteria: sentCriteria(1900), limit: 100, offset: 20, user_collection_id: 'c1' })
    expect(search.loadingMore.value).toBe(true)
    // d19 again: the corpus changed between the pages; it is not shown twice.
    requests[1].answer(page(['d19', ...ids(99, 20)], 20, 125))
    await more
    expect(search.results.value?.items).toHaveLength(119)
    expect(search.results.value?.nextOffset).toBe(120)

    const last = search.loadMore()
    await flush()
    expect(requests[2].body).toMatchObject({ limit: 100, offset: 120 })
    requests[2].answer(page(ids(5, 119), 120, 125))
    await last
    const current = search.results.value!
    expect([current.id, current.items.length, hasMoreDocuments(current), search.loadingMore.value]).toEqual([results?.id, 124, false, false])

    await search.loadMore() // nothing left
    expect(requests).toHaveLength(3)
  })

  it('never asks for a page past the reachable documents', async () => {
    serve()
    const search = useDocumentSearch()
    const first = search.search(query(1900))
    await flush()
    requests[0].answer(page(ids(20), 0, 50_000, { retrievalLimit: 60 }))
    await first
    const more = search.loadMore()
    await flush()
    expect(requests[1].body).toMatchObject({ offset: 20, limit: 40 }) // offset + limit = the engine cap
    requests[1].answer(page(ids(40, 20), 20, 50_000, { retrievalLimit: 60 }))
    await more
    expect([search.results.value?.items.length, hasMoreDocuments(search.results.value!)]).toEqual([60, false])
  })

  it('drops the late answers of an earlier search and of its Load more', async () => {
    serve()
    const search = useDocumentSearch()
    const first = search.search(query(1800))
    await flush()
    requests[0].answer(page(['a'], 0, 2, { nextOffset: 1 }))
    await first
    const more = search.loadMore()
    await flush()
    const second = search.search(query(1900))
    await flush()
    expect(search.results.value).toBeNull()

    requests[1].answer(page(['b'], 1, 2))
    await more
    expect([search.results.value, search.loading.value]).toEqual([null, true])
    requests[2].answer(page(['new'], 0, 1))
    expect((await second)?.items.map(i => i.document.id)).toEqual(['new'])
  })

  it('reports a refused search with the server reason and keeps loaded documents when Load more fails', async () => {
    const logged = muteConsole('error')
    serve()
    const search = useDocumentSearch()
    const refused = search.search(query(1900))
    await flush()
    const reason = 'Documents cannot be filtered by chunk values (chunk_language): this corpus database has no chunk-value summaries of its documents.'
    requests[0].answer({ detail: reason }, 422)
    expect(await refused).toBeNull()
    expect(search.error.value).toBe(reason)

    const ok = search.search(query(1900))
    await flush()
    requests[1].answer(page(['a'], 0, 2, { nextOffset: 1 }))
    await ok
    const more = search.loadMore()
    await flush()
    requests[2].answer({ detail: 'Collection not found' }, 404)
    await more
    expect(search.results.value?.items.map(i => i.document.id)).toEqual(['a'])
    expect(search.results.value?.nextOffset).toBe(1) // Load more can try again
    expect(search.loadMoreError.value).toBe('Collection not found')
    expect(logged).toHaveBeenCalled()
  })

  it('ranks a text query once and reads its later pages by the ranking entries (#607)', async () => {
    serve()
    const search = useDocumentSearch()
    const textQuery = { ...query(1900, 'c1'), criteria: normalizeCriteria({ textQuery: 'Lhota', chunkFilters: { languages: ['ces'] } }), vector: 'small' }
    const first = search.search(textQuery)
    await flush()
    expect(requests[0].body).toMatchObject({ limit: 20, offset: 0, type: 'hybrid', vector: 'small', user_collection_id: 'c1' })
    expect((requests[0].body.criteria as Record<string, unknown>).text_query).toBe('Lhota')
    const entries = ['m', 'a', 'b', 'c'].map((id, i) => ({ id, match: i ? 'text' : 'metadata', chunk_id: `chunk-${id}` }))
    requests[0].answer({
      ...page(['m'], 0, 4, { nextOffset: null }),
      order: 'metadata_then_text',
      ranked: entries,
      read_count: 1,
      total_count: null,
      eligible_count: 50,
      bounded: true,
      retrieval: { metadata_limit: 1000, metadata_bounded: false, chunk_limit: 2000, chunk_bounded: true, ranked_chunks: 2000, type: 'hybrid', vector: 'small' }
    })
    const results = (await first)!
    expect([results.ranked?.length, results.readCount, results.totalCount, results.eligibleCount, hasMoreDocuments(results)]).toEqual([4, 1, null, 50, true])
    expect(documentCoverage(results)).toBe(
      'The best 4 documents by relevance (1 shown); more of the 50 documents these filters admit may match. Refine the query or filters to reach others.')
    expect(documentOrderLabel(results)).toMatch(/^Matches in the title, author or publisher first/)

    const more = search.loadMore()
    await flush()
    expect(requests[1].path).toMatch(/\/api\/search\/documents\/read$/)
    expect(requests[1].body).toEqual({
      ranked: entries.slice(1),
      criteria: { ...sentCriteria(1900), text_query: 'Lhota', document_filters: { ...sentCriteria(1900).document_filters, year_min: null } },
      user_collection_id: 'c1'
    })
    // "b" is no longer eligible: left out; "m" again is not shown twice.
    requests[1].answer({ items: ['a', 'm', 'c'].map(doc), time_spent: 0.01 })
    await more
    const current = search.results.value!
    expect([current.items.map(i => i.document.id), current.readCount, hasMoreDocuments(current)]).toEqual([['m', 'a', 'c'], 4, false])
    await search.loadMore() // nothing left
    expect(requests).toHaveLength(2)
  })
})

describe('document coverage', () => {
  const results = (shown: number, total: number, bounded = false): DocumentResults => ({
    id: 1,
    query: { criteria: normalizeCriteria({}), userCollectionId: null },
    items: ids(shown).map(doc),
    nextOffset: null,
    ranked: null,
    readCount: 0,
    totalCount: total,
    eligibleCount: total,
    retrievalLimit: 10000,
    bounded,
    retrieval: null,
    timeSpent: 0
  })

  it('states the actual number of matching documents, how many are shown and the engine cap', () => {
    expect(documentCoverage(results(1, 1))).toBe('All 1 matching document.')
    expect(documentCoverage(results(3, 3))).toBe('All 3 matching documents.')
    expect(documentCoverage(results(20, 1234))).toBe('1,234 matching documents (20 shown).')
    expect(documentCoverage(results(20, 25000, true))).toBe(
      '25,000 matching documents (20 shown); only the first 10,000 can be listed. Narrow the filters to reach the others.')
    expect(documentOrderLabel(results(1, 1))).toBe('Sorted by publication year, oldest first; documents without a year last.')
  })

  it('states the matching documents of a complete text-query ranking', () => {
    const ranking = (shown: number, ranked: number): DocumentResults => ({
      ...results(shown, ranked), ranked: ids(ranked).map(id => ({ id, match: 'text' })), readCount: shown, eligibleCount: 99
    })
    expect(documentCoverage(ranking(1, 1))).toBe('All 1 matching document.')
    expect(documentCoverage(ranking(20, 45))).toBe('45 matching documents (20 shown).')
  })
})
