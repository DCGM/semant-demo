import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useConcordanceStore } from 'src/features/annotations/concordance/concordanceStore'
import { useAnnotationReviewStore } from 'src/features/annotations/concordance/annotationReviewStore'
import { MAX_SELECTION, useAnnotationSelectionStore } from 'src/features/annotations/annotationSelectionStore'
import { endSession } from 'src/shared/api'

// The annotation workspace's state (#329): server-side queries, late answers dropped by
// query, collection and session, failures reported as such, and selection kept. The
// selection (#459): explicit ids, "all matches" frozen as resolved ids, hidden members
// counted, and review actions sent in parts with per-item results.

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
/** Annotations at version 0, as selected before anyone changed them. */
const at0 = (list: string[]) => list.map(id => [id, 0] as const)

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
  const calls: { url: URL, body: unknown, answer: (body: unknown, status?: number) => void }[] = []
  const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => new Promise<Response>((resolve, reject) => {
    const abort = () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
    if (init?.signal?.aborted) abort()
    init?.signal?.addEventListener('abort', abort)
    calls.push({
      url: new URL(String(input)),
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
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
  const idCalls = () => calls.filter(c => c.url.pathname.endsWith('/annotations/ids'))

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
    const selection = useAnnotationSelectionStore()
    selection.toggle('a', 0)
    const paging = store.goTo(50)
    await flush()
    rowCalls()[1].answer(page(['c'], 51, 50))
    await paging
    selection.toggle('c', 0)

    const reopening = store.open('col-1')
    await flush()
    expect(rowCalls()[2].url.searchParams.get('offset')).toBe('50')
    expect(store.rows.map(r => r.id)).toEqual(['c']) // shown while it is read again
    rowCalls()[2].answer(page(['c'], 51, 50))
    documentCalls()[1].answer([])
    expect(idCalls()[0].body).toMatchObject({ within: ['a', 'c'], types: ['pos', 'auto'] })
    idCalls()[0].answer({ ids: ['a', 'c'] })
    await reopening
    expect([...selection.ids]).toEqual(['a', 'c'])
    expect(store.hiddenSelected).toBe(0)
  })

  it('starts afresh for another collection and ignores the previous one\'s late answer', async () => {
    const store = await opened()
    const selection = useAnnotationSelectionStore()
    selection.toggle('a', 0)
    const stale = store.load()
    await flush()

    const other = store.open('col-2')
    await flush()
    expect([...selection.ids]).toEqual([])
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
    expect([store.page, store.collectionId, useAnnotationSelectionStore().size]).toEqual([null, null, 0])
  })

  it('updates the focused row from the page read again, and tells when it left the page', async () => {
    const store = await opened(['a', 'b'], 60)
    const selection = useAnnotationSelectionStore()
    selection.focus(store.rows[0])
    const reloading = store.load() // back from the document, where "a" was moved
    await flush()
    rowCalls()[1].answer({ ...page(['a', 'b'], 60), rows: [{ ...row('a', 'moved'), start: 3, end: 8, revision: 2 }, row('b')] })
    await reloading
    expect([selection.focused?.text, selection.focused?.start, selection.focusedGone]).toEqual(['moved', 3, false])

    const again = store.load() // and now deleted or retagged out of the filters
    await flush()
    rowCalls()[2].answer(page(['b', 'c'], 59))
    await again
    expect([selection.focused?.id, selection.focusedGone]).toEqual(['a', true])

    selection.focus(store.rows[0])
    const paging = store.goTo(50) // another page does not list it, which is no change
    await flush()
    rowCalls()[3].answer(page(['x'], 59, 50))
    await paging
    expect([selection.focused?.id, selection.focusedGone]).toEqual(['b', false])
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

  it('selects all matches as the ids resolved for the filters, which later filters do not widen', async () => {
    const store = await opened(['a', 'b'], 3)
    const selection = useAnnotationSelectionStore()
    const filtering = store.setFilters({ tagIds: ['t1'] })
    await flush()
    rowCalls()[1].answer(page(['a', 'b'], 3))
    documentCalls()[1].answer([])
    await filtering

    const selecting = store.selectAllMatches()
    await flush()
    expect(idCalls()[0].body).toMatchObject({ tag_ids: ['t1'], types: ['pos', 'auto'], within: null })
    idCalls()[0].answer({ ids: ['a', 'b', 'c'] })
    expect(await selecting).toBeNull()
    expect([...selection.ids]).toEqual(['a', 'b', 'c'])
    expect(store.hiddenSelected).toBe(0)

    // Wider filters show more rows; the selection keeps its members and says none is hidden.
    const widening = store.setFilters({ tagIds: [] })
    await flush()
    expect(store.hiddenSelected).toBeNull() // not known for the new filters yet
    rowCalls()[2].answer(page(['a', 'b', 'x', 'y'], 6))
    documentCalls()[2].answer([])
    expect(idCalls()[1].body).toMatchObject({ tag_ids: null, within: ['a', 'b', 'c'] })
    idCalls()[1].answer({ ids: ['a', 'b', 'c'] })
    await widening
    expect([...selection.ids]).toEqual(['a', 'b', 'c'])
  })

  it('counts selected annotations the filters hide and deselects them only on request', async () => {
    const store = await opened(['a', 'b'])
    const selection = useAnnotationSelectionStore()
    store.setPageSelected(true)
    const narrowing = store.setFilters({ text: 'Novák' })
    await flush()
    rowCalls()[1].answer(page(['b']))
    idCalls()[0].answer({ ids: ['b'] })
    await narrowing
    expect([...selection.ids]).toEqual(['a', 'b'])
    expect(store.hiddenSelected).toBe(1)

    store.deselectHidden()
    expect([...selection.ids]).toEqual(['b'])
    expect(store.hiddenSelected).toBe(0)
  })

  it('refuses "all matches" beyond the limit without changing the selection', async () => {
    const store = await opened(['a'])
    const selection = useAnnotationSelectionStore()
    selection.toggle('a', 0)
    const tooMany = store.selectAllMatches()
    await flush()
    idCalls()[0].answer({ detail: '6000 annotations match; at most 5000 can be selected at once. Narrow the filters.' }, 400)
    expect(await tooMany).toContain('6000 annotations match')

    const overLimit = store.selectAllMatches()
    await flush()
    idCalls()[1].answer({ ids: Array.from({ length: MAX_SELECTION }, (_, i) => `id-${i}`) })
    expect(await overLimit).toContain(`at most ${MAX_SELECTION}`)
    expect([...selection.ids]).toEqual(['a'])
  })

  it('ends "select all" on a filter change without adding the old matches', async () => {
    const store = await opened(['a', 'b'], 3)
    const selection = useAnnotationSelectionStore()
    const selecting = store.selectAllMatches()
    await flush()
    expect(store.resolving).toBe(true)
    const filtering = store.setFilters({ text: 'Novák' })
    expect(store.resolving).toBe(false)
    idCalls()[0].answer({ ids: ['a', 'b', 'c'] })
    expect(await selecting).toBeNull()
    expect(selection.size).toBe(0)
    await flush()
    rowCalls()[1].answer(page(['a']))
    await filtering
    expect(store.resolving).toBe(false)
  })

  it('selects all matches at the versions the server resolved', async () => {
    const store = await opened(['a', 'b'], 3)
    const selection = useAnnotationSelectionStore()
    const selecting = store.selectAllMatches()
    await flush()
    idCalls()[0].answer({ ids: ['a', 'b', 'c'], versions: { a: 0, b: 2, c: 1 } })
    expect(await selecting).toBeNull()
    expect(['a', 'b', 'c'].map(i => selection.versionOf(i))).toEqual([0, 2, 1])
  })

  it('finishes "select all" while the hidden members are asked about, and knows them all after', async () => {
    const store = await opened(['a', 'b'], 3)
    const selection = useAnnotationSelectionStore()
    selection.add(at0(['old']))
    const asking = store.loadShown()
    const selecting = store.selectAllMatches()
    await flush()
    const [shownCall, allCall] = idCalls()
    expect([shownCall.body, allCall.body]).toMatchObject([{ within: ['old'] }, { within: null }])
    // Asking again about the members does not end "select all".
    const again = store.loadShown()
    await flush()
    allCall.answer({ ids: ['a', 'b', 'c'] })
    expect(await selecting).toBeNull()
    expect(store.resolving).toBe(false)
    // "old" is not among all matches: hidden, without waiting for the pending answers.
    expect(store.hiddenSelected).toBe(1)

    // The pending answers predate "select all" and are dropped.
    shownCall.answer({ ids: [] })
    idCalls()[2].answer({ ids: ['old'] })
    await Promise.all([asking, again])
    expect([...selection.ids].sort()).toEqual(['a', 'b', 'c', 'old'])
    expect(store.hiddenSelected).toBe(1)
  })

  it('drops the hidden-selection answer of a collection left meanwhile', async () => {
    const store = await opened(['a'])
    useAnnotationSelectionStore().toggle('a', 0)
    const asking = store.loadShown()
    await flush()
    const other = store.open('col-2')
    await flush()
    idCalls()[0].answer({ ids: [] })
    await asking
    expect(store.hiddenSelected).toBe(0) // the new collection's empty selection
    rowCalls()[1].answer(page([]))
    documentCalls()[1].answer([])
    await other
  })
})

describe('annotation review store', () => {
  const originalFetch = globalThis.fetch
  let calls: ReturnType<typeof controlledFetch>['calls']
  const reviewCalls = () => calls.filter(c => c.url.pathname.endsWith('/annotations/review'))
  const syncCalls = () => calls.filter(c => c.url.pathname.endsWith('/annotations/chunk-tags/sync'))

  beforeEach(() => {
    setActivePinia(createPinia())
    const controlled = controlledFetch()
    calls = controlled.calls
    globalThis.fetch = controlled.fetchMock as typeof fetch
    useAnnotationSelectionStore().enter('col-1')
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  const ids = (n: number) => Array.from({ length: n }, (_, i) => `id-${i}`)

  it('sends the resolved targets in parts and reports every item', async () => {
    const review = useAnnotationReviewStore()
    const running = review.review('col-1', 'reject' as never, at0(ids(250)))
    await flush()
    expect(reviewCalls()[0].url.pathname).toBe('/api/user_collections/col-1/annotations/review')
    expect(reviewCalls()[0].body).toMatchObject({ action: 'reject', annotation_ids: ids(200), tag_id: null })
    reviewCalls()[0].answer({
      outcome: 'partial',
      succeeded: ids(198),
      failed: [
        { item_id: 'id-198', step: 'update_span', message: 'boom', uncertain: false },
        { item_id: 'id-199', step: 'find_annotation', message: 'gone' },
        { item_id: 'c:t', step: 'update_chunk_tags', message: 'search' }
      ]
    })
    await flush()
    expect(review.progress).toBe(200)
    expect(reviewCalls()[1].body).toMatchObject({ annotation_ids: ids(250).slice(200) })
    reviewCalls()[1].answer({ detail: 'down' }, 503)
    const report = await running

    expect(report?.saved.length).toBe(198)
    expect(report?.missing).toEqual(['id-199'])
    expect(report?.unsynced).toEqual(['c:t'])
    expect(report?.failed.map(f => [f.id, f.uncertain])).toEqual([
      ['id-198', false], ...ids(250).slice(200).map(id => [id, true])])
    expect(review.running).toBe(false)

    // A retry sends only the failed and uncertain items, then repairs the search pair.
    const retrying = review.retry('col-1')
    await flush()
    expect(reviewCalls()[2].body).toMatchObject({ annotation_ids: ['id-198', ...ids(250).slice(200)] })
    reviewCalls()[2].answer({ outcome: 'complete', succeeded: ['id-198', ...ids(250).slice(200)], failed: [] })
    await flush()
    expect(syncCalls()[0].body).toEqual({ pairs: [{ chunk_id: 'c', tag_id: 't' }] })
    syncCalls()[0].answer({ outcome: 'complete', succeeded: ['c:t'], failed: [] })
    const retried = await retrying
    expect([retried?.saved.length, retried?.failed.length, retried?.missing, retried?.unsynced])
      .toEqual([249, 0, ['id-199'], []])
  })

  it('sends each annotation with its version and reports the ones changed meanwhile apart', async () => {
    const review = useAnnotationReviewStore()
    const selection = useAnnotationSelectionStore()
    selection.add([['a', 2], ['b', 0], ['c', 5]])
    const running = review.review('col-1', 'approve' as never, [...selection.ids].map(i => [i, selection.versionOf(i)] as const))
    await flush()
    expect(reviewCalls()[0].body).toMatchObject({ annotation_ids: ['a', 'b', 'c'], expected_versions: { a: 2, b: 0, c: 5 } })
    reviewCalls()[0].answer({
      outcome: 'partial',
      succeeded: ['a'],
      failed: [
        { item_id: 'b', step: 'edit_conflict', message: 'changed' },
        { item_id: 'c', step: 'update_span', message: 'boom', uncertain: true }
      ],
      versions: { a: 3, b: 4 }
    })
    const report = await running

    expect(report?.conflicts).toEqual([{ id: 'b', version: 4 }])
    expect(report?.failed.map(f => [f.id, f.version])).toEqual([['c', 5]])
    // This user's saved write moves the selection on; the changed one keeps its old version.
    expect(['a', 'b', 'c'].map(i => selection.versionOf(i))).toEqual([3, 0, 5])

    // A retry sends the uncertain item at the version it expected, never the changed one.
    const retrying = review.retry('col-1')
    await flush()
    expect(reviewCalls()[1].body).toMatchObject({ annotation_ids: ['c'], expected_versions: { c: 5 } })
    reviewCalls()[1].answer({ outcome: 'complete', succeeded: ['c'], failed: [], versions: { c: 6 } })
    const retried = await retrying
    expect([retried?.saved, retried?.conflicts.length]).toEqual([['a', 'c'], 1])
  })

  it('stops sending parts once the selection changes and keeps what was sent', async () => {
    const review = useAnnotationReviewStore()
    const selection = useAnnotationSelectionStore()
    selection.add(at0(ids(450)))
    const running = review.review('col-1', 'delete' as never, at0([...selection.ids]))
    await flush()
    selection.toggle('id-449', 0, false)
    reviewCalls()[0].answer({ outcome: 'complete', succeeded: ids(200), failed: [] })
    const report = await running

    expect(reviewCalls()).toHaveLength(1)
    expect([report?.saved.length, report?.failed.length, report?.notSent]).toEqual([200, 0, 250])
    expect(report?.error).toContain('selection changed')
    expect(review.report).toBe(report)

    // The ids not sent are not retried: they may no longer be selected.
    expect(await review.retry('col-1')).toBe(report)
    expect(reviewCalls()).toHaveLength(1)
  })

  it('repairs the search pairs of deleted annotations, which cannot be reviewed again', async () => {
    const review = useAnnotationReviewStore()
    const running = review.review('col-1', 'delete' as never, at0(['a', 'b']))
    await flush()
    reviewCalls()[0].answer({
      outcome: 'partial',
      succeeded: ['a', 'b'],
      failed: [
        { item_id: 'c1:t', step: 'update_chunk_tags', message: 'x' },
        { item_id: 'c2:t', step: 'update_chunk_tags', message: 'x' },
        { item_id: 'c1:t', step: 'update_chunk_tags', message: 'x' }
      ]
    })
    expect((await running)?.unsynced).toEqual(['c1:t', 'c2:t'])

    const repairing = review.retry('col-1')
    await flush()
    expect(reviewCalls()).toHaveLength(1)
    expect(syncCalls()[0].url.pathname).toBe('/api/user_collections/col-1/annotations/chunk-tags/sync')
    syncCalls()[0].answer({ outcome: 'partial', succeeded: ['c1:t'], failed: [{ item_id: 'c2:t', step: 'update_chunk_tags', message: 'x' }] })
    const partly = await repairing
    expect([partly?.saved, partly?.unsynced, partly?.error]).toEqual([['a', 'b'], ['c2:t'], null])

    const failing = review.retry('col-1')
    await flush()
    syncCalls()[1].answer({ detail: 'Tag not found' }, 404)
    const refused = await failing
    expect([refused?.unsynced, refused?.error]).toEqual([['c2:t'], 'Tag not found'])
  })

  it('stops at a refused part and keeps the rest as not sent', async () => {
    const review = useAnnotationReviewStore()
    const running = review.review('col-1', 'delete' as never, at0(ids(450)))
    await flush()
    reviewCalls()[0].answer({ outcome: 'complete', succeeded: ids(200), failed: [] })
    await flush()
    reviewCalls()[1].answer({ detail: 'Collection not found' }, 404)
    const report = await running

    expect(reviewCalls()).toHaveLength(2)
    expect([report?.saved.length, report?.failed.length, report?.notSent, report?.error])
      .toEqual([200, 250, 50, 'Collection not found'])
  })

  it('sends nothing more after the collection was left or the session ended', async () => {
    const review = useAnnotationReviewStore()
    const running = review.review('col-1', 'approve' as never, at0(ids(300)))
    await flush()
    useAnnotationSelectionStore().enter('col-2')
    reviewCalls()[0].answer({ outcome: 'complete', succeeded: ids(200), failed: [] })
    expect(await running).toBeNull()
    expect(reviewCalls()).toHaveLength(1)
    expect(review.report).toBeNull()

    useAnnotationSelectionStore().enter('col-1')
    const again = review.review('col-1', 'approve' as never, at0(ids(1)))
    await flush()
    endSession()
    reviewCalls()[1].answer({ outcome: 'complete', succeeded: ['id-0'], failed: [] })
    expect(await again).toBeNull()
  })
})

describe('annotation selection store', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('tells a captured membership that any change of the members ended it', () => {
    const selection = useAnnotationSelectionStore()
    selection.enter('col-1')
    selection.add(at0(['a']))
    const changes: [string, () => void][] = [
      ['add', () => selection.add(at0(['b']))],
      ['remove', () => selection.remove(['a'])],
      ['toggle', () => selection.toggle('a', 0)],
      ['retain', () => selection.retain(new Set())],
      ['clear selection', () => selection.clearSelection()],
      ['another collection', () => selection.enter('col-2')]
    ]
    for (const [name, change] of changes) {
      selection.enter('col-1')
      const unchanged = selection.captureMembership()
      selection.focus(null)
      expect(unchanged(), name).toBe(true)
      change()
      expect(unchanged(), name).toBe(false)
    }
  })

  it('keeps the version each member was selected at until this user saves it', () => {
    const selection = useAnnotationSelectionStore()
    selection.enter('col-1')
    selection.add([['a', 1], ['b', 2]])
    // Selecting again (a page, all matches) keeps the version it was first selected at.
    selection.add([['a', 7], ['c', 3]])
    selection.noteVersions({ b: 4, gone: 9 })
    expect(['a', 'b', 'c', 'gone'].map(i => selection.versionOf(i))).toEqual([1, 4, 3, 0])

    const unchanged = selection.captureMembership()
    selection.noteVersions({ a: 2 })
    expect(unchanged()).toBe(true) // a saved version is no change of the members

    selection.replace([['b', 8]])
    expect([[...selection.ids], selection.versionOf('b'), selection.versionOf('a')]).toEqual([['b'], 8, 0])
  })

  it('holds explicit ids of one collection up to its limit', () => {
    const selection = useAnnotationSelectionStore()
    selection.enter('col-1')
    expect(selection.add(at0(['a', 'b']))).toBe(true)
    expect(selection.add(at0(Array.from({ length: MAX_SELECTION - 1 }, (_, i) => `x${i}`)))).toBe(false)
    expect(selection.toggle('b', 0)).toBe(true)
    expect([...selection.ids]).toEqual(['a'])

    selection.enter('col-1')
    expect(selection.size).toBe(1)
    selection.enter('col-2')
    expect(selection.size).toBe(0)
  })
})
