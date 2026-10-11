import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { Quasar } from 'quasar'

import type { TextChunk, TextChunkWithDocument } from 'src/generated/api'
import ChunkContextPanel from 'src/features/documents/ChunkContextPanel.vue'
import { CONTEXT_SIDE, CONTEXT_STEP, mergeChunks, useChunkContext } from 'src/features/documents/useChunkContext'
import SearchResultCard from 'src/features/search/SearchResultCard.vue'

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const chunk = (order: number, document = 'doc-1'): TextChunk => ({
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

  it('extends the passage from its edges', async () => {
    const context = useChunkContext()
    const opening = context.open({ documentId: 'doc-1', chunkId: 'doc-1-c10' })
    await flush()
    calls[0].answer(windowBody(10, [9, 10, 11], { before: true, after: true }))
    await opening

    const earlier = context.extend('before')
    await flush()
    expect(context.extending.value).toBe('before')
    expect(calls[1].url.pathname).toBe('/api/documents/doc-1/chunks/doc-1-c9/window')
    expect(Object.fromEntries(calls[1].url.searchParams)).toEqual({ before: `${CONTEXT_STEP}`, after: '0' })
    calls[1].answer(windowBody(9, [4, 5, 6, 7, 8, 9], { before: false, after: true }))
    await earlier

    expect(context.chunks.value.map(c => c.order)).toEqual([4, 5, 6, 7, 8, 9, 10, 11])
    expect([context.hasBefore.value, context.hasAfter.value, context.extending.value]).toEqual([false, true, null])
    // Nothing more before the start of the document.
    await context.extend('before')
    expect(calls).toHaveLength(2)
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
    calls[1].answer(windowBody(11, [11, 12, 13]))
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
  afterEach(() => {
    // jsdom has no scrollIntoView; the tests add a spy.
    delete (HTMLElement.prototype as Partial<HTMLElement>).scrollIntoView
  })

  const chunks = [chunk(3), chunk(4), chunk(5)]
  const document = { id: 'doc-1', title: 'Kronika', author: ['Jan Novák'], yearIssued: 1921 }

  function mountPanel (props: Record<string, unknown> = {}) {
    return mount(ChunkContextPanel, {
      props: { targetChunkId: 'doc-1-c4', document, chunks, totalChunks: 20, ...props },
      global: { plugins: [[Quasar, {}]] }
    })
  }

  it('highlights the target chunk and shows the document and position', () => {
    const scroll = vi.fn()
    HTMLElement.prototype.scrollIntoView = scroll
    const wrapper = mountPanel({ hasBefore: true })

    const target = wrapper.get('[aria-current="true"]')
    expect(target.attributes('data-chunk-id')).toBe('doc-1-c4')
    expect(target.classes()).toContain('chunk-context__chunk--target')
    expect(wrapper.findAll('.chunk-context__chunk--target')).toHaveLength(1)
    expect(wrapper.get('[data-testid="chunk-context-document"]').text()).toContain('Kronika')
    expect(wrapper.get('[data-testid="chunk-context-position"]').text()).toBe('Passage 5 of 20 · Pages 5–5')
    expect(wrapper.text()).toContain('Show earlier text')
    expect(wrapper.text()).toContain('End of document')
  })

  it('jumps to the loaded target and reloads a dropped one', async () => {
    const scroll = vi.fn()
    HTMLElement.prototype.scrollIntoView = scroll
    const wrapper = mountPanel()
    await flushPromises()
    expect(scroll).toHaveBeenCalledTimes(1) // the new target is brought into view once loaded
    scroll.mockClear()

    await wrapper.findAll('button').find(b => b.text().includes('Jump to match'))!.trigger('click')
    expect(scroll).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('reload')).toBeUndefined()

    await wrapper.setProps({ chunks: [chunk(10), chunk(11)] })
    await wrapper.findAll('button').find(b => b.text().includes('Jump to match'))!.trigger('click')
    expect(wrapper.emitted('reload')).toHaveLength(1)
  })

  it('offers extension, return and retry as events', async () => {
    const wrapper = mountPanel({ hasBefore: true, hasAfter: true, returnLabel: 'Back to result 7' })

    const button = (label: string) => wrapper.findAll('button').find(b => b.text().includes(label))!
    await button('Show earlier text').trigger('click')
    await button('Show later text').trigger('click')
    await button('Back to result 7').trigger('click')

    expect(wrapper.emitted('extend')).toEqual([['before'], ['after']])
    expect(wrapper.emitted('return')).toHaveLength(1)

    await wrapper.setProps({ chunks: [], document: null, error: 'Gone.' })
    expect(wrapper.get('[role="alert"]').text()).toContain('Gone.')
    await button('Retry').trigger('click')
    expect(wrapper.emitted('reload')).toHaveLength(1)
  })

  it('shows no stale text while loading or without a target', async () => {
    const wrapper = mountPanel({ loading: true })
    expect(wrapper.findAll('.chunk-context__chunk')).toHaveLength(0)

    await wrapper.setProps({ loading: false, targetChunkId: null, emptyText: 'Pick a result.' })
    expect(wrapper.text()).toBe('Pick a result.')
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
  } as unknown as TextChunkWithDocument

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
