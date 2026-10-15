import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { Quasar } from 'quasar'
import { effectScope, nextTick, ref } from 'vue'

import type { SearchResultChunk } from 'src/generated/api'
import ChatSourcesPanel from 'src/features/rag/ChatSourcesPanel.vue'
import { useChatSources, type MessageWithSources } from 'src/features/rag/useChatSources'

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
      { id: 1 },
      { id: 2, sources: [source('a'), source('b', 'doc-2')] },
      { id: 3, sources: [source('c', 'doc-3')] }
    ])
    const scope = effectScope()
    const chat = scope.run(() => useChatSources(messages))!
    return { messages, chat, scope }
  }

  it('shows the sources of the clicked message, not of the latest one', async () => {
    const { messages, chat } = setup()

    expect(chat.showMessage(2)).toBe(true)
    expect(chat.sources.value.map(s => s.id)).toEqual(['a', 'b'])
    expect(chat.source.value).toBeNull()

    // A new answer does not change what is shown.
    messages.value.push({ id: 4, sources: [source('d')] })
    await nextTick()
    expect(chat.message.value?.id).toBe(2)
    expect(chat.sources.value.map(s => s.id)).toEqual(['a', 'b'])

    // A message without sources shows nothing new.
    expect(chat.showMessage(1)).toBe(false)
    expect(chat.message.value?.id).toBe(2)
  })

  it("opens a source of a message in its document and highlights the message's citation", async () => {
    const { chat } = setup()

    expect(chat.showSource(2, 1)).toBe(true)
    await flush()
    expect(calls[0].path).toBe('/api/documents/doc-2/chunks/b/window')
    expect([chat.message.value?.id, chat.sourceIndex.value, chat.source.value?.id]).toEqual([2, 1, 'b'])
    calls[0].answer(windowBody('doc-2', 'b'))
    await flush()
    expect(chat.context.target?.chunkId).toBe('b')
    expect(chat.context.containsTarget).toBe(true)

    // Unknown sources are refused, the shown one stays.
    expect(chat.showSource(2, 5)).toBe(false)
    expect(chat.showSource(99, 0)).toBe(false)
    expect(chat.source.value?.id).toBe('b')
  })

  it("closes one message's source when another message's sources are shown", async () => {
    const { chat } = setup()
    chat.showSource(2, 0)
    await flush()

    // Showing the same message again keeps its open source.
    chat.showMessage(2)
    expect(chat.source.value?.id).toBe('a')

    chat.showMessage(3)
    expect(calls[0].signal?.aborted).toBe(true)
    calls[0].answer(windowBody('doc-1', 'a')) // late answer for the old source
    await flush()
    expect([chat.message.value?.id, chat.source.value, chat.context.target, chat.context.chunks]).toEqual([3, null, null, []])
  })

  it('drops the answer for a previously opened source', async () => {
    const { chat } = setup()
    chat.showSource(2, 0)
    chat.showSource(3, 0)
    await flush()

    calls[0].answer(windowBody('doc-1', 'a'))
    calls[1].answer(windowBody('doc-3', 'c'))
    await flush()
    expect(chat.context.document?.id).toBe('doc-3')
    expect(chat.context.chunks.map(c => c.id)).toEqual(['c'])
  })

  it('forgets the sources when their message is gone (a reset conversation)', async () => {
    const { messages, chat } = setup()
    chat.showSource(2, 0)
    await flush()

    // The new conversation reuses no message id.
    messages.value = [{ id: 5 }]
    await nextTick()
    expect([chat.selection.value, chat.message.value, chat.source.value]).toEqual([null, null, null])
    expect(calls[0].signal?.aborted).toBe(true)
    expect(chat.context.target).toBeNull()
  })

  it('aborts its request when the page goes away', async () => {
    const { chat, scope } = setup()
    chat.showSource(2, 0)
    await flush()
    scope.stop()
    expect(calls[0].signal?.aborted).toBe(true)
  })
})

describe('ChatSourcesPanel', () => {
  const mountPanel = (props: Record<string, unknown>) => mount(ChatSourcesPanel, {
    props: { sources: [source('a'), { ...source('b', 'doc-2'), fromPage: 4, toPage: 4 }], ...props },
    global: { plugins: [Quasar] }
  })

  it('lists the sources numbered as their citations, with the question they answered', () => {
    const wrapper = mountPanel({ question: 'Who founded Lhota?', selectedIndex: 1 })

    expect(wrapper.text()).toContain('Sources of the answer to')
    expect(wrapper.text()).toContain('Who founded Lhota?')
    const items = wrapper.findAll('li')
    expect(items.map(i => i.attributes('aria-label'))).toEqual(['Source doc 1', 'Source doc 2'])
    expect(items[0].text()).toContain('Title of doc-1')
    expect(items[0].text()).toContain('1921 · pages 2–3')
    expect(items[1].text()).toContain('page 4')
    expect(items[0].text()).toContain('Text of a')
    expect(items.map(i => i.attributes('aria-current'))).toEqual([undefined, 'true'])
  })

  it('asks to view a source in its document', async () => {
    const wrapper = mountPanel({})
    await wrapper.find('[aria-label="View source doc 2 in its document"]').trigger('click')
    expect(wrapper.emitted('view')).toEqual([[1]])
  })
})
