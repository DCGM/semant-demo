import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import type { DocumentChunk, SearchResultChunk } from 'src/generated/api'
import ChunkContextPanel from 'src/features/documents/ChunkContextPanel.vue'
import { CONTEXT_SIDE, CONTEXT_STEP, mergeChunks, useChunkContext } from 'src/features/documents/useChunkContext'
import { leadJump } from 'src/features/documents/contextScroll'
import SearchResultCard from 'src/features/search/SearchResultCard.vue'

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const chunk = (order: number, document = 'doc-1'): DocumentChunk => ({
  id: `${document}-c${order}`,
  text: `Paragraph ${order}`,
  startPageId: `page-${order}`,
  fromPage: order + 1,
  toPage: order + 1,
  document,
  order
})

/** Backend answer (snake_case, as the API sends it) for the chunks at `orders`. */
const windowBody = (anchor: number, orders: number[], more: { before?: boolean, after?: boolean } = {}, document = 'doc-1') => ({
  document: { id: document, title: `Title of ${document}`, author: ['Jan Novák'], year_issued: 1921 },
  chunks: orders.map(o => chunk(o, document)).map(c => ({
    id: c.id, text: c.text, start_page_id: c.startPageId, from_page: c.fromPage, to_page: c.toPage, document, order: c.order
  })),
  anchor_chunk_id: `${document}-c${anchor}`,
  has_before: more.before ?? false,
  has_after: more.after ?? false,
  total_chunks: 100
})

/** Backend answer of the extension read for the chunks at `orders`. */
const adjacentBody = (orders: number[], hasMore: boolean) => ({
  chunks: windowBody(orders[0] ?? 0, orders).chunks,
  has_more: hasMore
})

/** Fetch stand-in: each call waits until the test answers it. */
function controlledFetch () {
  const calls: { url: URL, signal?: AbortSignal | null, answer: (body: unknown, status?: number) => void }[] = []
  const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => new Promise<Response>((resolve, reject) => {
    const abort = () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))
    if (init?.signal?.aborted) abort()
    init?.signal?.addEventListener('abort', abort)
    calls.push({
      url: new URL(String(input)),
      signal: init?.signal,
      answer: (body, status = 200) => resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
    })
  }))
  return { calls, fetchMock }
}

describe('mergeChunks', () => {
  const loaded = [chunk(5), chunk(6), chunk(7)]

  it('adds new chunks on the requested side without duplicates', () => {
    expect(mergeChunks(loaded, [chunk(3), chunk(4), chunk(5)], 'before').chunks.map(c => c.order)).toEqual([3, 4, 5, 6, 7])
    expect(mergeChunks(loaded, [chunk(7), chunk(8)], 'after').chunks.map(c => c.order)).toEqual([5, 6, 7, 8])
  })

  it('keeps at most `max` chunks by dropping the other end', () => {
    expect(mergeChunks(loaded, [chunk(3), chunk(4)], 'before', 4)).toEqual({ chunks: [chunk(3), chunk(4), chunk(5), chunk(6)], trimmed: true })
    expect(mergeChunks(loaded, [chunk(8), chunk(9)], 'after', 4)).toEqual({ chunks: [chunk(6), chunk(7), chunk(8), chunk(9)], trimmed: true })
  })
})

describe('leadJump', () => {
  const viewport = 400

  it('smooth-scrolls from where the passage is to a nearby target on its side', () => {
    expect(leadJump(300, viewport, 1)).toBe(0)
    expect(leadJump(-300, viewport, -1)).toBe(0)
    expect(leadJump(-50, viewport, 1)).toBe(0) // barely past the centre
  })

  it('jumps close to a far target, keeping it on the side it lies on', () => {
    expect(leadJump(5000, viewport, 1)).toBe(5000 - 300)
    expect(leadJump(-5000, viewport, -1)).toBe(-5000 + 300)
  })

  it('moves a target shown on the wrong side to its side, so the motion goes the right way', () => {
    // An earlier target is below the centre (the passage was replaced): it goes above.
    expect(leadJump(200, viewport, -1)).toBe(200 + 300)
    expect(leadJump(-200, viewport, 1)).toBe(-200 - 300)
  })

  it('after a replaced passage, brings even a target just past the centre in from its side', () => {
    // Regression: a later target just above the centre after the replace scrolled up a little.
    expect(leadJump(-40, viewport, 1, true)).toBe(-40 - 300)
    expect(leadJump(40, viewport, -1, true)).toBe(40 + 300)
    // Already a clear distance on its side: smooth from there.
    expect(leadJump(200, viewport, 1, true)).toBe(0)
  })

  it('leaves the scroll alone without a direction', () => {
    expect(leadJump(5000, viewport, 0)).toBe(0)
  })
})

describe('useChunkContext', () => {
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

  it('reads a bounded passage around the target chunk', async () => {
    const context = useChunkContext()

    const opening = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c10' })
    await flush()
    expect(context.loading.value).toBe(true)
    expect(calls[0].url.pathname).toBe('/api/documents/doc-1/chunks/doc-1-c10/window')
    expect(Object.fromEntries(calls[0].url.searchParams)).toEqual({ before: `${CONTEXT_SIDE}`, after: `${CONTEXT_SIDE}` })
    calls[0].answer(windowBody(10, [7, 8, 9, 10, 11, 12, 13], { before: true, after: true }))
    await opening

    expect(context.chunks.value.map(c => c.order)).toEqual([7, 8, 9, 10, 11, 12, 13])
    expect(context.document.value?.title).toBe('Title of doc-1')
    expect([context.hasBefore.value, context.hasAfter.value, context.totalChunks.value]).toEqual([true, true, 100])
    expect([context.loading.value, context.error.value, context.containsTarget.value]).toEqual([false, null, true])
  })

  it('extends the passage from its edges, reading only the neighbours', async () => {
    const context = useChunkContext()
    const opening = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c10' })
    await flush()
    calls[0].answer(windowBody(10, [9, 10, 11], { before: true, after: true }))
    await opening

    const earlier = context.extend('before')
    await flush()
    expect(context.extending.value).toBe('before')
    expect(calls[1].url.pathname).toBe('/api/documents/doc-1/chunks/doc-1-c9/adjacent')
    expect(Object.fromEntries(calls[1].url.searchParams)).toEqual({ direction: 'before', limit: `${CONTEXT_STEP}` })
    calls[1].answer(adjacentBody([4, 5, 6, 7, 8], false))
    await earlier

    expect(context.chunks.value.map(c => c.order)).toEqual([4, 5, 6, 7, 8, 9, 10, 11])
    expect([context.hasBefore.value, context.hasAfter.value, context.extending.value]).toEqual([false, true, null])
    // The header's document and count are kept from the first read.
    expect([context.document.value?.title, context.totalChunks.value]).toEqual(['Title of doc-1', 100])
    // Nothing more before the start of the document.
    await context.extend('before')
    expect(calls).toHaveLength(2)
  })

  it('asks to show the target again on every open, also of the same target', async () => {
    const context = useChunkContext()
    const target = { documentId: 'doc-1', chunkId: 'doc-1-c10' }

    const first = context.open(target)
    await flush()
    calls[0].answer(windowBody(10, [9, 10, 11]))
    await first
    await context.open(target)

    // Shown again without reading it again (#493).
    expect([context.focusRequest.value, calls.length]).toEqual([2, 1])
  })

  it('switches to a target of the shown passage without reading or clearing it', async () => {
    // Regression (#493): every switch blanked the panel and read the passage again.
    const context = useChunkContext()
    const first = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c10' })
    await flush()
    calls[0].answer(windowBody(10, [8, 9, 10, 11, 12]))
    await first
    const shown = context.chunks.value

    await context.open({ documentId: 'doc-1', chunkId: 'doc-1-c12' })

    expect(calls).toHaveLength(1)
    expect(context.target.value?.chunkId).toBe('doc-1-c12')
    expect(context.chunks.value).toBe(shown)
    expect([context.loading.value, context.focusRequest.value, context.containsTarget.value]).toEqual([false, 2, true])
  })

  it('stops an extension of the previous target when switching within the passage', async () => {
    const context = useChunkContext()
    const first = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c10' })
    await flush()
    calls[0].answer(windowBody(10, [9, 10, 11], { after: true }))
    await first

    const extending = context.extend('after')
    await flush()
    await context.open({ documentId: 'doc-1', chunkId: 'doc-1-c9' })
    expect(calls[1].signal?.aborted).toBe(true)
    calls[1].answer(adjacentBody([12, 13], false))
    await extending

    expect(context.chunks.value.map(c => c.order)).toEqual([9, 10, 11])
    expect(context.extending.value).toBeNull()
  })

  it('keeps the shown passage of the same document while the passage around a new target loads', async () => {
    const context = useChunkContext()
    const first = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c10' })
    await flush()
    calls[0].answer(windowBody(10, [9, 10, 11]))
    await first

    const second = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c40' })
    await flush()
    expect(calls[1].url.pathname).toBe('/api/documents/doc-1/chunks/doc-1-c40/window')
    expect(context.loading.value).toBe(true)
    expect(context.chunks.value.map(c => c.order)).toEqual([9, 10, 11])
    expect(context.document.value?.id).toBe('doc-1')

    calls[1].answer(windowBody(40, [39, 40, 41]))
    await second
    expect(context.chunks.value.map(c => c.order)).toEqual([39, 40, 41])
    expect([context.loading.value, context.containsTarget.value]).toEqual([false, true])
  })

  it('starts from nothing for another document or after a failed read', async () => {
    const context = useChunkContext()
    const first = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c10' })
    await flush()
    calls[0].answer(windowBody(10, [9, 10, 11]))
    await first

    const other = context.open({ documentId: 'doc-2', chunkId: 'doc-2-c4' })
    await flush()
    expect([context.chunks.value, context.document.value]).toEqual([[], null])
    calls[1].answer({ detail: 'Chunk not found' }, 404)
    await other

    // After the failure, even a chunk id of the earlier passage is read again.
    const retry = context.open({ documentId: 'doc-2', chunkId: 'doc-2-c4' })
    await flush()
    expect(calls).toHaveLength(3)
    expect(context.error.value).toBeNull()
    calls[2].answer(windowBody(4, [3, 4, 5], {}, 'doc-2'))
    await retry
    expect(context.chunks.value.map(c => c.id)).toEqual(['doc-2-c3', 'doc-2-c4', 'doc-2-c5'])
  })

  it('ends on the last of quickly switched targets of one document', async () => {
    const context = useChunkContext()
    const first = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c10' })
    await flush()
    calls[0].answer(windowBody(10, [9, 10, 11]))
    await first

    const toB = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c40' })
    await flush()
    const toC = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c80' })
    await flush()
    expect(calls[1].signal?.aborted).toBe(true)
    calls[1].answer(windowBody(40, [39, 40, 41]))
    calls[2].answer(windowBody(80, [79, 80, 81]))
    await Promise.all([toB, toC])

    expect(context.target.value?.chunkId).toBe('doc-1-c80')
    expect(context.chunks.value.map(c => c.order)).toEqual([79, 80, 81])
  })

  it('focuses the target again, reloading it only when extending dropped it', async () => {
    const context = useChunkContext()
    const opening = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c10' })
    await flush()
    calls[0].answer(windowBody(10, [9, 10, 11]))
    await opening

    await context.focus()
    expect([context.focusRequest.value, calls.length]).toEqual([2, 1])

    // As if extending had trimmed the target away.
    context.chunks.value = [chunk(40), chunk(41)]
    const focusing = context.focus()
    await flush()
    expect(context.focusRequest.value).toBe(3)
    expect(calls[1].url.pathname).toBe('/api/documents/doc-1/chunks/doc-1-c10/window')
    calls[1].answer(windowBody(10, [9, 10, 11]))
    await focusing
    expect(context.containsTarget.value).toBe(true)
  })

  it('drops the answer for an earlier target', async () => {
    const context = useChunkContext()
    const first = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c1' })
    await flush()
    const second = context.open({ documentId: 'doc-2', chunkId: 'doc-2-c4' })
    await flush()

    expect(calls[0].signal?.aborted).toBe(true)
    calls[0].answer(windowBody(1, [0, 1, 2]))
    calls[1].answer(windowBody(4, [3, 4, 5], {}, 'doc-2'))
    await Promise.all([first, second])

    expect(context.document.value?.id).toBe('doc-2')
    expect(context.chunks.value.map(c => c.id)).toEqual(['doc-2-c3', 'doc-2-c4', 'doc-2-c5'])
  })

  it('drops an extension answered after the target changed', async () => {
    const context = useChunkContext()
    const opening = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c10' })
    await flush()
    calls[0].answer(windowBody(10, [9, 10, 11], { after: true }))
    await opening

    const later = context.extend('after')
    await flush()
    context.clear()
    calls[1].answer(adjacentBody([12, 13], false))
    await later

    expect([context.target.value, context.chunks.value, context.extending.value]).toEqual([null, [], null])
  })

  it('reports a missing or inaccessible passage without showing other text', async () => {
    const context = useChunkContext()
    const opening = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c0' })
    await flush()
    calls[0].answer({ detail: 'Chunk not found' }, 404)
    await opening

    expect(context.error.value).toBe('This passage or its document is no longer available.')
    expect([context.chunks.value, context.document.value, context.loading.value]).toEqual([[], null, false])

    // Retry reads the same target again.
    const retry = context.load()
    await flush()
    expect(calls[1].url.pathname).toBe('/api/documents/doc-1/chunks/doc-1-c0/window')
    calls[1].answer(windowBody(0, [0, 1]))
    await retry
    expect([context.error.value, context.containsTarget.value]).toEqual([null, true])
  })
})

describe('ChunkContextPanel', () => {
  const chunks = [chunk(3), chunk(4), chunk(5)]
  const document = { id: 'doc-1', title: 'Kronika', author: ['Jan Novák'], yearIssued: 1921 }
  let scroll: ReturnType<typeof vi.fn>
  let scrolled: Element[] // the elements scrolled into view, in order

  beforeEach(() => {
    // jsdom has no scrollIntoView.
    scrolled = []
    scroll = vi.fn(function (this: Element) { scrolled.push(this) })
    HTMLElement.prototype.scrollIntoView = scroll
  })

  afterEach(() => {
    delete (HTMLElement.prototype as Partial<HTMLElement>).scrollIntoView
  })

  function mountPanel (props: Record<string, unknown> = {}) {
    return mount(ChunkContextPanel, {
      props: { targetChunkId: 'doc-1-c4', document, chunks, focusRequest: 1, ...props },
      global: { plugins: [[Quasar, {}]] }
    })
  }

  const button = (wrapper: ReturnType<typeof mountPanel>, label: string) =>
    wrapper.findAll('button').find(b => b.text().includes(label))

  it('marks an exact span, continuing into the following chunk until a gap in order', async () => {
    // "Paragraph 4" + "Paragraph 5": offsets 10..14 cover "4" and "Para".
    const wrapper = mountPanel({ highlight: { chunkId: 'doc-1-c4', start: 10, end: 15 } })
    await flushPromises()
    expect(wrapper.findAll('[data-testid="chunk-context-mark"]').map(m => m.text())).toEqual(['4', 'Para'])
    expect(wrapper.get('[data-chunk-id="doc-1-c4"]').text()).toBe('Paragraph 4')

    const gap = [chunk(3), chunk(4), chunk(6)]
    const withGap = mountPanel({ chunks: gap, highlight: { chunkId: 'doc-1-c4', start: 10, end: 15 } })
    await flushPromises()
    expect(withGap.findAll('[data-testid="chunk-context-mark"]').map(m => m.text())).toEqual(['4'])
  })

  it('highlights the target chunk under a header with title, year and Focus on result', async () => {
    const wrapper = mountPanel({ hasBefore: true, returnLabel: 'Focus on result' })
    await flushPromises()

    const target = wrapper.get('[aria-current="true"]')
    expect(target.attributes('data-chunk-id')).toBe('doc-1-c4')
    expect(wrapper.findAll('.chunk-context__chunk--target')).toHaveLength(1)
    expect(scroll).toHaveBeenCalledTimes(1)
    const header = wrapper.get('[data-testid="chunk-context-header"]')
    expect(header.text()).toContain('Kronika')
    expect(header.text()).toContain('1921')
    expect(header.text()).toContain('Focus on result')
    // No positions or page labels, and no separate "Jump to match".
    expect(wrapper.text()).not.toMatch(/Passage|Pages|Jump to match/)
    expect(wrapper.text()).toContain('Show earlier text')
    expect(wrapper.text()).toContain('End of document')
  })

  it('shows a reference label with the target only when one is given', async () => {
    const plain = mountPanel()
    expect(plain.find('[data-testid="chunk-context-target-label"]').exists()).toBe(false)
    expect(plain.find('[aria-current="true"]').attributes('aria-label')).toBe('Matched passage')

    const cited = mountPanel({ targetLabel: 'S3' })
    const target = cited.find('[aria-current="true"]')
    expect(target.find('[data-testid="chunk-context-target-label"]').text()).toBe('S3')
    expect(target.attributes('aria-label')).toBe('Cited passage S3')
    expect(cited.findAll('[data-testid="chunk-context-target-label"]')).toHaveLength(1)
  })

  it('scrolls to the same target again on every focus request', async () => {
    // Regression: opening the same result again after reading elsewhere did not return to it.
    const wrapper = mountPanel()
    await flushPromises()
    expect(scroll).toHaveBeenCalledTimes(1)

    // The same target is opened again: reloading, then the same chunks.
    await wrapper.setProps({ focusRequest: 2, loading: true, chunks: [] })
    await wrapper.setProps({ loading: false, chunks })
    await flushPromises()
    expect(scroll).toHaveBeenCalledTimes(2)
    expect(scrolled[1]).toBe(wrapper.get('[aria-current="true"]').element)

    // Extending (no focus request) does not scroll back.
    await wrapper.setProps({ chunks: [chunk(2), ...chunks] })
    await flushPromises()
    expect(scroll).toHaveBeenCalledTimes(2)
  })

  it('offers extension, return and retry as events', async () => {
    const wrapper = mountPanel({ hasBefore: true, hasAfter: true, returnLabel: 'Focus on result' })

    await button(wrapper, 'Show earlier text')!.trigger('click')
    await button(wrapper, 'Show later text')!.trigger('click')
    await button(wrapper, 'Focus on result')!.trigger('click')

    expect(wrapper.emitted('extend')).toEqual([['before'], ['after']])
    expect(wrapper.emitted('return')).toHaveLength(1)

    await wrapper.setProps({ chunks: [], document: null, error: 'Gone.' })
    expect(wrapper.get('[role="alert"]').text()).toContain('Gone.')
    await button(wrapper, 'Retry')!.trigger('click')
    expect(wrapper.emitted('reload')).toHaveLength(1)
  })

  it('shows only a loading state while loading with nothing shown, and nothing without a target', async () => {
    // The composable clears the passage for another document, so no other document's text shows.
    const wrapper = mountPanel({ loading: true, chunks: [] })
    expect(wrapper.findAll('.chunk-context__chunk')).toHaveLength(0)
    expect(wrapper.text()).toContain('Loading the document…')

    await wrapper.setProps({ loading: false, targetChunkId: null, emptyText: 'Pick a result.' })
    expect(wrapper.text()).toBe('Pick a result.')
  })

  it('keeps the shown passage while another passage of the document loads', async () => {
    // Regression (#493): switching annotations of one document blanked the panel.
    const wrapper = mountPanel({ hasAfter: true })
    await flushPromises()
    await wrapper.setProps({ targetChunkId: 'doc-1-c40', focusRequest: 2, loading: true })

    expect(wrapper.findAll('.chunk-context__chunk')).toHaveLength(3)
    expect(wrapper.text()).not.toContain('Loading the document…')
    expect(wrapper.find('[data-testid="chunk-context-reloading"]').exists()).toBe(true)
    expect(button(wrapper, 'Show later text')!.attributes('disabled')).toBeDefined()

    await wrapper.setProps({ loading: false, chunks: [chunk(39), chunk(40), chunk(41)] })
    await flushPromises()
    expect(wrapper.find('[data-testid="chunk-context-reloading"]').exists()).toBe(false)
    expect(scrolled.at(-1)).toBe(wrapper.get('[aria-current="true"]').element)
  })
})

describe('SearchResultCard context action', () => {
  const hit = {
    id: 'chunk-1',
    title: 'Chunk title',
    text: 'Passage text',
    fromPage: 1,
    toPage: 1,
    document: 'doc-1',
    documentObject: { id: 'doc-1', title: 'Kronika' }
  } as unknown as SearchResultChunk

  function mountCard () {
    return mount(SearchResultCard, {
      props: { chunk: hit, number: 3, filters: [] },
      global: { plugins: [[Quasar, {}]] }
    })
  }

  it('opens the context from an accessible button', async () => {
    const wrapper = mountCard()
    const button = wrapper.get('[data-testid="view-context"]')

    expect(button.attributes('aria-label')).toBe('View result 3 in its document')
    await button.trigger('click')
    expect(wrapper.emitted('view-context')).toHaveLength(1)
  })

  it('opens the context on a double-click of the text without selecting the result', async () => {
    const wrapper = mountCard()

    await wrapper.get('.search-result__text').trigger('dblclick')
    expect(wrapper.emitted('view-context')).toHaveLength(1)
    expect(wrapper.emitted('update:selected')).toBeUndefined()
  })

  it('ignores a double-click on the checkbox', async () => {
    const wrapper = mountCard()

    await wrapper.get('[role="checkbox"]').trigger('dblclick')
    await flushPromises()
    expect(wrapper.emitted('view-context')).toBeUndefined()
  })
})
