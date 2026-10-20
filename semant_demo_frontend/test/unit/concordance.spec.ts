import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useConcordanceStore } from 'src/features/annotations/concordance/concordanceStore'
import { endSession } from 'src/shared/api'

// The annotation workspace's state (#329): server-side queries, late answers dropped by
// query, collection and session, failures reported as such, and selection kept.

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const row = (id: string, text = id) => ({
  id,
  tagId: 'tag-1',
  type: 'pos',
  chunkId: 'chunk-1',
  documentId: 'doc-1',
  start: 0,
  end: text.length,
  revision: 1,
  textStatus: 'ready',
  text,
  leftContext: 'left ',
  rightContext: ' right',
  documentAvailable: true,
  documentTitle: 'Kronika',
  documentYear: 1851
})
const page = (ids: string[], total = ids.length, offset = 0) => ({ rows: ids.map(id => row(id)), total, offset, limit: 50 })

/** Fetch stand-in: each call waits until the test answers it. */
function controlledFetch () {
  const calls: { url: URL, answer: (body: unknown, status?: number) => void }[] = []
  const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => new Promise<Response>((resolve, reject) => {
    const abort = () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
    if (init?.signal?.aborted) abort()
    init?.signal?.addEventListener('abort', abort)
    calls.push({
      url: new URL(String(input)),
      answer: (body, status = 200) => resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
    })
  }))
  return { calls, fetchMock }
}

describe('concordance store', () => {
  const originalFetch = globalThis.fetch
  let calls: ReturnType<typeof controlledFetch>['calls']
  const rowCalls = () => calls.filter(c => c.url.pathname.endsWith('/annotations'))
  const documentCalls = () => calls.filter(c => c.url.pathname.endsWith('/annotations/documents'))

  beforeEach(() => {
    setActivePinia(createPinia())
    const controlled = controlledFetch()
    calls = controlled.calls
    globalThis.fetch = controlled.fetchMock as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  async function opened (ids = ['a', 'b'], total = ids.length) {
    const store = useConcordanceStore()
    const opening = store.open('col-1')
    await flush()
    rowCalls()[0].answer(page(ids, total))
    documentCalls()[0].answer([])
    await opening
    return store
  }

  it('asks the server for one page of confirmed annotations and proposals in document order', async () => {
    const store = await opened()
    const params = rowCalls()[0].url.searchParams
    expect(rowCalls()[0].url.pathname).toBe('/api/user_collections/col-1/annotations')
    expect(params.getAll('type')).toEqual(['pos', 'auto'])
    expect(Object.fromEntries(['sort', 'limit', 'offset'].map(k => [k, params.get(k)]))).toEqual({ sort: 'document', limit: '50', offset: '0' })
    expect(store.rows.map(r => r.id)).toEqual(['a', 'b'])
    expect([store.loading, store.error]).toEqual([false, null])
  })

  it('sends the filters and drops the answer of a superseded query', async () => {
    const store = await opened()
    const first = store.setFilters({ tagIds: ['t1', 't2'], text: ' Novák ' })
    await flush()
    const second = store.setFilters({ yearFrom: 1900, types: ['neg'] as never })
    await flush()

    const latest = rowCalls()[rowCalls().length - 1].url.searchParams
    expect(latest.getAll('tag_id')).toEqual(['t1', 't2'])
    expect([latest.get('q'), latest.get('year_from'), latest.getAll('type')]).toEqual(['Novák', '1900', ['neg']])
    // The later query answers first; the earlier one (aborted) cannot replace it.
    rowCalls()[rowCalls().length - 1].answer(page(['rejected']))
    documentCalls().forEach(c => c.answer([]))
    await Promise.allSettled([first, second])
    expect(store.rows.map(r => r.id)).toEqual(['rejected'])
    expect(store.offset).toBe(0)
  })

  it('reports a failed read as an error, not as an empty result', async () => {
    const store = await opened()
    const reloading = store.load()
    await flush()
    rowCalls()[1].answer({ detail: 'boom' }, 500)
    await reloading
    expect(store.error).toBe('Failed to load the annotations.')
    expect(store.page).toBeNull()
    expect(store.loading).toBe(false)
  })

  it('keeps filters, page and selection when the same collection is opened again', async () => {
    const store = await opened(['a', 'b'], 51)
    store.toggleSelected('a')
    const paging = store.goTo(50)
    await flush()
    rowCalls()[1].answer(page(['c'], 51, 50))
    await paging
    store.toggleSelected('c')

    const reopening = store.open('col-1')
    await flush()
    expect(rowCalls()[2].url.searchParams.get('offset')).toBe('50')
    expect(store.rows.map(r => r.id)).toEqual(['c']) // shown while it is read again
    rowCalls()[2].answer(page(['c'], 51, 50))
    documentCalls()[1].answer([])
    await reopening
    expect([...store.selected]).toEqual(['a', 'c'])
  })

  it('starts afresh for another collection and ignores the previous one\'s late answer', async () => {
    const store = await opened()
    store.toggleSelected('a')
    const stale = store.load()
    await flush()

    const other = store.open('col-2')
    await flush()
    expect([...store.selected]).toEqual([])
    expect(store.page).toBeNull()
    rowCalls()[1].answer(page(['from-col-1']))
    await stale
    expect(store.page).toBeNull()
    rowCalls()[2].answer(page(['x']))
    documentCalls()[1].answer([])
    await other
    expect(store.rows.map(r => r.id)).toEqual(['x'])
  })

  it('drops answers that arrive after the session ended', async () => {
    const store = await opened()
    const reloading = store.load()
    await flush()
    endSession()
    store.clear()
    rowCalls()[1].answer(page(['late']))
    await reloading
    expect([store.page, store.collectionId, store.selected.size]).toEqual([null, null, 0])
  })

  it('goes back to the last page when the current one emptied meanwhile', async () => {
    const store = await opened(['a', 'b'], 60)
    const paging = store.goTo(50)
    await flush()
    rowCalls()[1].answer(page([], 3, 50)) // rows were deleted elsewhere
    await flush()
    expect(rowCalls()[2].url.searchParams.get('offset')).toBe('0')
    rowCalls()[2].answer(page(['a', 'b', 'c']))
    await paging
    await flush()
    expect([store.offset, store.rows.length]).toEqual([0, 3])
  })
})
