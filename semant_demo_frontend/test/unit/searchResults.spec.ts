import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

import type { SearchResponse, TextChunkWithDocument } from 'src/generated/api'
import { selectResults, type SearchResultsContext } from 'src/features/search/searchResults'
import { parseSummaryTokens, useSearchSummary } from 'src/features/search/useSearchSummary'
import { useSearchRequest } from 'src/features/search/useSearchRequest'

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const hit = (id: string): TextChunkWithDocument => ({
  id,
  text: `text of ${id}`,
  startPageId: `page-${id}`,
  fromPage: 1,
  toPage: 1,
  document: `doc-${id}`,
  order: 1,
  documentObject: { id: `doc-${id}` }
})

const response = (ids: string[], query = 'q'): SearchResponse => ({
  results: ids.map(hit),
  searchRequest: { query, tagUuids: [], positive: true, automatic: true },
  timeSpent: 0.1,
  searchLog: []
})

const contextOf = (id: number, ids: string[]): SearchResultsContext => ({ id, response: response(ids) })

describe('selectResults', () => {
  const context = contextOf(1, ['a', 'b', 'c', 'd'])

  it('takes the first results or all of them', () => {
    expect(selectResults(context, { kind: 'top', count: 2 })).toEqual({ results: [hit('a'), hit('b')], numbers: [1, 2] })
    expect(selectResults(context, { kind: 'top', count: null })?.numbers).toEqual([1, 2, 3, 4])
  })

  it('takes exactly the selected results, numbered as in the full list', () => {
    expect(selectResults(context, { kind: 'selected', ids: ['d', 'b'] })).toEqual({
      results: [hit('b'), hit('d')], numbers: [2, 4]
    })
  })

  it('reports an empty or unknown selection instead of widening it', () => {
    expect(selectResults(context, { kind: 'selected', ids: [] })).toBeNull()
    expect(selectResults(context, { kind: 'selected', ids: ['not-a-result'] })).toBeNull()
  })

  it('keeps source references of the hits', () => {
    const [selected] = selectResults(context, { kind: 'selected', ids: ['c'] })!.results
    expect([selected.id, selected.document, selected.startPageId]).toEqual(['c', 'doc-c', 'page-c'])
  })
})

describe('parseSummaryTokens', () => {
  it('maps citations of the summarized subset to result numbers', () => {
    expect(parseSummaryTokens('See [doc1] and [doc2].', [2, 4])).toEqual([
      { type: 'text', value: 'See ' },
      { type: 'citation', docNumber: 2 },
      { type: 'text', value: ' and ' },
      { type: 'citation', docNumber: 4 },
      { type: 'text', value: '.' }
    ])
  })
})

/** Fetch stand-in: each call waits until the test answers it. */
function controlledFetch () {
  const calls: { url: string, body: unknown, signal?: AbortSignal | null, answer: (body: unknown) => void }[] = []
  const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => new Promise<Response>((resolve, reject) => {
    const abort = () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
    if (init?.signal?.aborted) abort()
    init?.signal?.addEventListener('abort', abort)
    calls.push({
      url: String(input),
      body: init?.body ? JSON.parse(String(init.body)) : null,
      signal: init?.signal,
      answer: (body) => resolve(new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } }))
    })
  }))
  return { calls, fetchMock }
}

describe('useSearchSummary', () => {
  const originalFetch = globalThis.fetch
  let calls: ReturnType<typeof controlledFetch>['calls']

  beforeEach(() => {
    const controlled = controlledFetch()
    calls = controlled.calls
    globalThis.fetch = controlled.fetchMock as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('summarizes only the selected results and maps their citations', async () => {
    const context = ref<SearchResultsContext | null>(contextOf(1, ['a', 'b', 'c']))
    const selected = ref<string[]>([])
    const summary = useSearchSummary(context, selected)
    selected.value = ['c']
    await nextTick()
    expect(summary.scope.value).toBe('selected')

    const running = summary.summarize()
    await flush()
    expect(calls[0].url).toMatch(/\/api\/summarize\/results$/)
    expect((calls[0].body as { results: { id: string }[] }).results.map((r) => r.id)).toEqual(['c'])
    calls[0].answer({ summary: 'Only [doc1].', time_spent: 0.5 })
    await running

    expect(summary.tokens.value).toContainEqual({ type: 'citation', docNumber: 3 })
    expect([summary.summarizing.value, summary.error.value]).toEqual([false, null])
  })

  it('reports an empty selection without calling the backend', async () => {
    const summary = useSearchSummary(ref(contextOf(1, ['a'])), ref<string[]>([]))
    summary.scope.value = 'selected'

    await summary.summarize()

    expect(calls).toHaveLength(0)
    expect(summary.error.value).toBe('Please select at least one result for summarization.')
  })

  it('drops the answer for results of an earlier search', async () => {
    const context = ref<SearchResultsContext | null>(contextOf(1, ['a', 'b']))
    const summary = useSearchSummary(context, ref<string[]>([]))
    const running = summary.summarize()
    await flush()

    context.value = contextOf(2, ['x']) // a new search finished meanwhile
    await nextTick()
    expect(calls[0].signal?.aborted).toBe(true)
    await running

    expect([summary.summary.value, summary.summarizing.value, summary.error.value]).toEqual(['', false, null])
  })

  it('drops a pending summary when the selection changes and clears a shown one', async () => {
    const selected = ref<string[]>(['a'])
    const summary = useSearchSummary(ref(contextOf(1, ['a', 'b'])), selected)
    await nextTick()
    const running = summary.summarize()
    await flush()

    selected.value = ['b'] // the user picks another result before the answer arrives
    await nextTick()
    expect(calls[0].signal?.aborted).toBe(true)
    await running
    expect([summary.summary.value, summary.summarizing.value]).toEqual(['', false])

    const second = summary.summarize()
    await flush()
    expect((calls[1].body as { results: { id: string }[] }).results.map((r) => r.id)).toEqual(['b'])
    calls[1].answer({ summary: 'About [doc1].', time_spent: 0.1 })
    await second
    expect(summary.summary.value).toBe('About [doc1].')

    selected.value = ['a', 'b'] // the shown summary no longer matches the selection
    await nextTick()
    expect(summary.summary.value).toBe('')
  })

  it('clears the summary when the scope changes', async () => {
    const summary = useSearchSummary(ref(contextOf(1, ['a', 'b', 'c', 'd'])), ref<string[]>([]))
    const running = summary.summarize()
    await flush()
    calls[0].answer({ summary: 'Top ten [doc1].', time_spent: 0.1 })
    await running

    summary.scope.value = 'focused'
    await nextTick()
    expect(summary.summary.value).toBe('')
  })

  it('keeps the newer request loading when an older one answers late', async () => {
    const context = ref<SearchResultsContext | null>(contextOf(1, ['a', 'b']))
    const summary = useSearchSummary(context, ref<string[]>([]))
    // A slow request whose answer is already on its way when it is superseded.
    globalThis.fetch = vi.fn(() => new Promise<Response>((resolve) => {
      calls.push({ url: '', body: null, answer: (body) => resolve(new Response(JSON.stringify(body))) })
    })) as typeof fetch
    const first = summary.summarize()
    await flush()
    const second = summary.summarize()
    await flush()

    calls[0].answer({ summary: 'old [doc1]', time_spent: 1 })
    await first
    expect([summary.summary.value, summary.summarizing.value]).toEqual(['', true])

    calls[1].answer({ summary: 'new [doc2]', time_spent: 1 })
    await second
    expect([summary.summary.value, summary.summarizing.value]).toEqual(['new [doc2]', false])
  })
})

describe('useSearchRequest', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('lets a late answer of an earlier search neither replace the results nor end loading', async () => {
    const answers: ((body: unknown) => void)[] = []
    // Answers arrive regardless of abort: the response was already on its way.
    globalThis.fetch = vi.fn(() => new Promise<Response>((resolve) => {
      answers.push((body) => resolve(new Response(JSON.stringify(body))))
    })) as typeof fetch
    const search = useSearchRequest()

    const first = search.search({ query: 'one', tagUuids: [], positive: true, automatic: true })
    await flush()
    const second = search.search({ query: 'two', tagUuids: [], positive: true, automatic: true })
    await flush()

    answers[0]({ results: [hit('old')], search_request: { query: 'one', tag_uuids: [], positive: true, automatic: true }, time_spent: 1, search_log: [] })
    expect(await first).toBeNull()
    expect([search.context.value, search.loading.value]).toEqual([null, true])

    answers[1]({ results: [hit('new')], search_request: { query: 'two', tag_uuids: [], positive: true, automatic: true }, time_spent: 1, search_log: [] })
    const context = await second
    expect(context?.response.results.map((r) => r.id)).toEqual(['new'])
    expect([search.context.value?.id, search.loading.value]).toEqual([context?.id, false])
  })
})
