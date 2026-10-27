import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { effectScope, nextTick, ref } from 'vue'

import type { SearchResultChunk } from 'src/generated/api'
import ChatSourcesPanel from 'src/features/rag/ChatSourcesPanel.vue'
import { citedChunkId, sourceRegistry, useChatSources, type MessageWithSources } from 'src/features/rag/useChatSources'

/** A web search result of an answer (#370): its own ids, no corpus document. */
const webSource = (id: string): SearchResultChunk => ({
  ...source(id, `doc-${id}`),
  origin: 'web',
  fromPage: 0,
  toPage: 0,
  title: `Page ${id}`,
  documentObject: { id: `doc-${id}`, title: `Page ${id}` }
})

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const source = (id: string, document = 'doc-1'): SearchResultChunk => ({
  id,
  text: `Text of ${id}`,
  startPageId: `page-${id}`,
  fromPage: 2,
  toPage: 3,
  document,
  order: 0,
  documentObject: { id: document, title: `Title of ${document}`, yearIssued: 1921 }
})

/** Fetch stand-in recording the requested paths; answers only when the test says so. */
function recordingFetch () {
  const calls: { path: string, signal?: AbortSignal | null, answer: (body: unknown) => void }[] = []
  const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => new Promise<Response>((resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
    calls.push({
      path: new URL(String(input)).pathname,
      signal: init?.signal,
      answer: (body) => resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    })
  }))
  return { calls, fetchMock }
}

const windowBody = (document: string, chunkId: string) => ({
  document: { id: document, title: `Title of ${document}` },
  chunks: [{ id: chunkId, text: `Text of ${chunkId}`, start_page_id: 'p', from_page: 1, to_page: 1, document, order: 0 }],
  anchor_chunk_id: chunkId,
  has_before: false,
  has_after: false,
  total_chunks: 1
})

describe('sourceRegistry', () => {
  it('lists the sources of all answers in first-appearance order, once per chunk', () => {
    const entries = sourceRegistry([
      {},
      { sources: [source('a'), source('b')] },
      { sources: [source('c'), source('a')] }, // a again, cited by a later answer
      { sources: [] }
    ])
    expect(entries.map(e => [e.label, e.id])).toEqual([['S1', 'a'], ['S2', 'b'], ['S3', 'c']])
  })

  it('keeps the labels when answers are added', () => {
    const answers: MessageWithSources[] = [{ sources: [source('a'), source('b')] }]
    const before = sourceRegistry(answers)
    const after = sourceRegistry([...answers, { sources: [source('d'), source('b')] }])
    expect(after.slice(0, 2)).toEqual(before)
    expect(after.map(e => e.label)).toEqual(['S1', 'S2', 'S3'])
  })
})

describe('citedChunkId', () => {
  const answer = { sources: [source('a'), source('b')] }

  it("resolves an answer's own [doc N] to its N-th source", () => {
    expect(citedChunkId(answer, 1)).toBe('a')
    expect(citedChunkId(answer, 2)).toBe('b')
  })

  it('does not resolve a citation without such a source', () => {
    expect([citedChunkId(answer, 3), citedChunkId(answer, 0), citedChunkId({}, 1), citedChunkId(undefined, 1)])
      .toEqual([null, null, null, null])
  })
})

describe('useChatSources', () => {
  const originalFetch = globalThis.fetch
  let calls: ReturnType<typeof recordingFetch>['calls']

  beforeEach(() => {
    const recording = recordingFetch()
    calls = recording.calls
    globalThis.fetch = recording.fetchMock as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  function setup () {
    const messages = ref<MessageWithSources[]>([
      {},
      { sources: [source('a'), source('b', 'doc-2')] },
      { sources: [source('c', 'doc-3'), source('a')] }
    ])
    const scope = effectScope()
    const chat = scope.run(() => useChatSources(messages))!
    return { messages, chat, scope }
  }

  it('labels a chunk cited by several answers once', () => {
    const { chat } = setup()
    expect(chat.entries.value.map(e => e.label)).toEqual(['S1', 'S2', 'S3'])
    expect([chat.labelOf('a'), chat.labelOf('c'), chat.labelOf('zzz'), chat.labelOf(null)]).toEqual(['S1', 'S3', null, null])
  })

  it('selects a source and asks the list to show it, also the selected one again', () => {
    const { chat } = setup()

    expect(chat.select('b')).toBe(true)
    expect(chat.selected.value?.label).toBe('S2')
    expect(chat.reveal.value).toEqual({ id: 'b', seq: 1 })
    expect(chat.select('b')).toBe(true)
    expect([chat.selectedId.value, chat.reveal.value?.seq]).toEqual(['b', 2])

    // Unknown sources are refused, the selected one stays.
    expect(chat.select('zzz')).toBe(false)
    expect(chat.selectedId.value).toBe('b')
    expect(calls).toHaveLength(0) // selecting reads nothing
  })

  it('a new answer keeps the selection and its labels', async () => {
    const { messages, chat } = setup()
    chat.select('c')
    messages.value.push({ sources: [source('d'), source('c')] })
    await nextTick()
    expect([chat.selectedId.value, chat.selected.value?.label, chat.labelOf('d')]).toEqual(['c', 'S3', 'S4'])
  })

  it('opens the selected source in its document', async () => {
    const { chat } = setup()

    expect(chat.openDocument('b')).toBe(true)
    await flush()
    expect(calls[0].path).toBe('/api/documents/doc-2/chunks/b/window')
    expect([chat.selectedId.value, chat.documentSource.value?.label]).toEqual(['b', 'S2'])
    calls[0].answer(windowBody('doc-2', 'b'))
    await flush()
    expect(chat.context.containsTarget).toBe(true)

    // Selecting it again keeps its document.
    chat.select('b')
    expect(chat.documentSource.value?.id).toBe('b')
  })

  it("selecting another source closes the previous one's document", async () => {
    const { chat } = setup()
    chat.openDocument('a')
    await flush()

    chat.select('c')
    expect(calls[0].signal?.aborted).toBe(true)
    calls[0].answer(windowBody('doc-1', 'a')) // late answer for the old source
    await flush()
    expect([chat.selectedId.value, chat.documentSource.value, chat.context.target, chat.context.chunks]).toEqual(['c', null, null, []])
  })

  it('drops the answer for a previously opened document', async () => {
    const { chat } = setup()
    chat.openDocument('a')
    chat.openDocument('c')
    await flush()

    calls[0].answer(windowBody('doc-1', 'a'))
    calls[1].answer(windowBody('doc-3', 'c'))
    await flush()
    expect(chat.context.document?.id).toBe('doc-3')
    expect(chat.context.chunks.map(c => c.id)).toEqual(['c'])
  })

  it('forgets the selection and document when their sources are gone (a reset conversation)', async () => {
    const { messages, chat } = setup()
    chat.openDocument('a')
    await flush()

    messages.value = [{}]
    await nextTick()
    expect([chat.entries.value, chat.selectedId.value, chat.documentSource.value, chat.reveal.value]).toEqual([[], null, null, null])
    expect(calls[0].signal?.aborted).toBe(true)
    expect(chat.context.target).toBeNull()

    // The next conversation starts again at S1.
    messages.value = [{ sources: [source('z')] }]
    await nextTick()
    expect(chat.labelOf('z')).toBe('S1')
  })

  it('does not open a web search result, which has no document', async () => {
    const { messages, chat } = setup()
    messages.value.push({ sources: [webSource('w1'), webSource('w2')] })
    await nextTick()
    // Distinct web results are distinct sources.
    expect([chat.labelOf('w1'), chat.labelOf('w2')]).toEqual(['S4', 'S5'])
    chat.openDocument('a')
    await flush()

    expect(chat.openDocument('w1')).toBe(false)
    await flush()
    // Nothing changed: the open corpus document stays, no request was made.
    expect([chat.selectedId.value, chat.documentSource.value?.id]).toEqual(['a', 'a'])
    expect(calls).toHaveLength(1)
    // It can still be selected to read its text.
    expect(chat.select('w1')).toBe(true)
    expect([chat.selectedId.value, chat.documentSource.value]).toEqual(['w1', null])
  })

  it('aborts its request when the page goes away', async () => {
    const { chat, scope } = setup()
    chat.openDocument('a')
    await flush()
    scope.stop()
    expect(calls[0].signal?.aborted).toBe(true)
  })
})

describe('ChatSourcesPanel', () => {
  const entries = sourceRegistry([{ sources: [source('a'), { ...source('b', 'doc-2'), fromPage: 4, toPage: 4 }] }])
  const mountPanel = (props: Record<string, unknown> = {}) => mount(ChatSourcesPanel, {
    props: { entries, ...props },
    global: { plugins: [Quasar] }
  })

  it('lists the sources with their labels; only the selected one is expanded', () => {
    const wrapper = mountPanel({ selectedId: 'b' })

    const items = wrapper.findAll('li')
    expect(items.map(i => i.attributes('aria-label'))).toEqual(['Source S1', 'Source S2'])
    expect(items[0].text()).toContain('Title of doc-1')
    expect(items[0].text()).toContain('1921 · pages 2–3')
    expect(items[1].text()).toContain('page 4')
    expect(items.map(i => i.attributes('aria-current'))).toEqual([undefined, 'true'])
    expect(items.map(i => i.find('[role="button"]').attributes('aria-expanded'))).toEqual(['false', 'true'])
    const texts = wrapper.findAll('[data-testid="chat-source-text"]')
    expect(texts.map(t => t.classes('chat-sources__text--collapsed'))).toEqual([true, false])
    expect(texts[1].text()).toBe('Text of b')
    expect(wrapper.findAll('.chat-sources__view')).toHaveLength(2)
  })

  it('selects on a click and opens the document on a double click or View document', async () => {
    const wrapper = mountPanel({ selectedId: 'a' })
    const summaries = wrapper.findAll('[role="button"]')

    await summaries[1].trigger('click')
    await summaries[1].trigger('keydown', { key: 'Enter' })
    await summaries[1].trigger('dblclick')
    await wrapper.find('[aria-label="View source S1 in its document"]').trigger('click')

    expect(wrapper.emitted('select')).toEqual([['b'], ['b']])
    expect(wrapper.emitted('open')).toEqual([['b'], ['a']])
  })

  it('shows a web search result as such, without a document to open', async () => {
    const wrapper = mount(ChatSourcesPanel, {
      props: { entries: sourceRegistry([{ sources: [source('a'), webSource('w')] }]), selectedId: 'w' },
      global: { plugins: [Quasar] }
    })
    const items = wrapper.findAll('li')

    expect(items[1].text()).toContain('Page w')
    expect(items[1].text()).toContain('Web search')
    expect(items[1].text()).toContain('Text of w')
    expect(items[1].find('[data-testid="chat-source-web"]').text()).toBe('Web search result, not in the corpus')
    expect(items[1].find('.chat-sources__view').exists()).toBe(false)
    expect(items[0].find('.chat-sources__view').exists()).toBe(true)

    await items[1].find('[role="button"]').trigger('click')
    await items[1].find('[role="button"]').trigger('dblclick')
    expect(wrapper.emitted('select')).toEqual([['w']])
    expect(wrapper.emitted('open')).toBeUndefined()
  })
})
