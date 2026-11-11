import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

import useScopedChat, { chatTokens, historyTurns, type ChatMessage, type ChatSource, type SearchChatScope } from 'src/features/chat/useScopedChat'
import { muteConsole } from './console'

// Document chat (#248) and Search chat (#245), ADR 0012: the composable's stream handling,
// history and scope.

const encoder = new TextEncoder()
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

/** An answer stream that keeps delivering after abort (a read already under way). */
function answerStream () {
  let controller!: { enqueue (chunk: Uint8Array): void, close (): void }
  const body = new ReadableStream<Uint8Array>({ start (c) { controller = c } })
  return {
    body,
    push: (event: object) => controller.enqueue(encoder.encode(JSON.stringify(event) + '\n')),
    close: () => controller.close()
  }
}

const wireSource = (citation: number, chunkId: string) =>
  ({ citation, chunk_id: chunkId, document_id: 'd1', order: citation, from_page: 1, to_page: 1 })
const source = (citation: number, chunkId: string, label: number): ChatSource =>
  ({ citation, chunkId, documentId: 'd1', order: citation, fromPage: 1, toPage: 1, label })
const answer = (text: string, sources: ChatSource[] = [], status: ChatMessage['status'] = 'done'): ChatMessage =>
  ({ role: 'assistant', text, sources, status })
const question = (text: string): ChatMessage => ({ role: 'user', text, sources: [], status: 'done' })

describe('chatTokens', () => {
  it('links cited sources and leaves out citations without one', () => {
    const tokens = chatTokens(answer('A [doc3] b [doc9].', [source(3, 'c3', 1)]))

    expect(tokens).toEqual([
      { type: 'text', value: 'A ' },
      { type: 'citation', source: source(3, 'c3', 1) },
      { type: 'text', value: ' b ' },
      { type: 'text', value: '.' }
    ])
  })
})

describe('historyTurns', () => {
  it('renumbers an answer to its own sources, drops unmapped citations and failed turns', () => {
    const messages = [
      question('Who?'), answer('X [doc7] and [doc2], not [doc5].', [source(7, 'c7', 1), source(2, 'c2', 2)]),
      question('Failed?'), { ...answer('', [], 'error'), error: 'No.' },
      question('Stopped?'), answer('Partial [doc1]', [], 'stopped')
    ]

    expect(historyTurns(messages)).toEqual([
      { role: 'user', text: 'Who?', chunkIds: [] },
      { role: 'assistant', text: 'X [doc1] and [doc2], not .', chunkIds: ['c7', 'c2'] },
      { role: 'user', text: 'Stopped?', chunkIds: [] },
      { role: 'assistant', text: 'Partial ', chunkIds: [] }
    ])
  })

  it('keeps only the newest 40 turns', () => {
    const messages = Array.from({ length: 30 }, (_, i) => [question(`q${i}`), answer(`a${i}`)]).flat()

    const turns = historyTurns(messages)

    expect(turns).toHaveLength(40)
    expect(turns[0].text).toBe('q10')
  })
})

describe('useScopedChat', () => {
  const originalFetch = globalThis.fetch
  let streams: ReturnType<typeof answerStream>[]
  let requests: { url: string, body: unknown }[]

  beforeEach(() => {
    streams = []
    requests = []
    globalThis.fetch = vi.fn((url: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
      const stream = answerStream()
      streams.push(stream)
      requests.push({ url: String(url), body: JSON.parse(String(init?.body)) })
      return Promise.resolve(new Response(stream.body))
    }) as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  function mountChat () {
    const documentId = ref('d1')
    const scope = effectScope()
    const chat = scope.run(() => useScopedChat(() => ({ kind: 'document', collectionId: 'c1', documentId: documentId.value })))!
    return { chat, documentId, scope }
  }

  it('streams an answer with its sources, coverage and conversation-wide labels', async () => {
    const { chat } = mountChat()

    const first = chat.ask(' What happened? ')
    await flush()
    streams[0].push({ event: 'delta', text: 'A fire [doc2]' })
    streams[0].push({ event: 'delta', text: ' and a feast [doc1].' })
    streams[0].push({ event: 'sources', sources: [wireSource(2, 'c2'), wireSource(1, 'c1')] })
    streams[0].push({ event: 'end', coverage: 'part', used_chunks: 2, total_chunks: 5 })
    streams[0].close()
    await first

    expect(requests[0].url).toMatch(/\/user_collections\/c1\/documents\/d1\/chat$/)
    expect(requests[0].body).toEqual({ question: 'What happened?', history: [] })
    const reply = chat.messages.value[1]
    expect([reply.text, reply.status, reply.coverage]).toEqual([
      'A fire [doc2] and a feast [doc1].', 'done', { coverage: 'part', usedChunks: 2, totalChunks: 5 }])
    expect(reply.sources.map(s => [s.chunkId, s.label])).toEqual([['c2', 1], ['c1', 2]])
    expect(chat.streaming.value).toBe(false)

    // A later answer citing the same chunk under another number keeps its label.
    const second = chat.ask('More?')
    await flush()
    expect((requests[1].body as { history: unknown[] }).history).toEqual([
      { role: 'user', text: 'What happened?', chunk_ids: [] },
      { role: 'assistant', text: 'A fire [doc1] and a feast [doc2].', chunk_ids: ['c2', 'c1'] }
    ])
    streams[1].push({ event: 'delta', text: 'Yes [doc4].' })
    streams[1].push({ event: 'sources', sources: [wireSource(4, 'c1')] })
    streams[1].push({ event: 'end', coverage: 'all', used_chunks: 5, total_chunks: 5 })
    streams[1].close()
    await second
    expect(chat.messages.value[3].sources.map(s => s.label)).toEqual([2])
  })

  it('shows a stream error, and an answer without end as interrupted', async () => {
    const { chat } = mountChat()

    const failing = chat.ask('Q1')
    await flush()
    streams[0].push({ event: 'delta', text: 'Part [doc1]' })
    streams[0].push({ event: 'sources', sources: [wireSource(1, 'c1')] }) // a partial answer keeps its citations
    streams[0].push({ event: 'error', code: 'failed', message: 'The assistant could not answer.' })
    streams[0].close()
    await failing
    const cut = chat.ask('Q2')
    await flush()
    streams[1].push({ event: 'delta', text: 'Half' })
    streams[1].close()
    await cut

    expect(chat.messages.value.map(m => [m.status, m.error])).toEqual([
      ['done', undefined], ['error', 'The assistant could not answer.'],
      ['done', undefined], ['interrupted', 'The answer was interrupted.']])
    expect(chat.messages.value[1].sources.map(s => s.chunkId)).toEqual(['c1'])
  })

  it('stops an answer and keeps what arrived', async () => {
    const { chat } = mountChat()

    const asking = chat.ask('Q')
    await flush()
    streams[0].push({ event: 'delta', text: 'So far' })
    await flush()
    chat.stop()
    streams[0].push({ event: 'delta', text: ' late' })
    streams[0].close()
    await asking

    expect([chat.messages.value[1].text, chat.messages.value[1].status, chat.streaming.value])
      .toEqual(['So far', 'stopped', false])
  })

  it('starts an empty conversation on another document, and the old answer cannot reach it', async () => {
    const { chat, documentId } = mountChat()
    const old = chat.ask('About d1')
    await flush()

    documentId.value = 'd2'
    await nextTick()
    expect(chat.messages.value).toEqual([])
    expect([chat.streaming.value, chat.scopeChanged.value]).toEqual([false, false])

    const current = chat.ask('About d2')
    await flush()
    streams[0].push({ event: 'delta', text: 'late answer about d1' })
    streams[0].close()
    await old
    expect(chat.streaming.value).toBe(true) // the old answer's end does not end the new one

    streams[1].push({ event: 'delta', text: 'answer about d2' })
    streams[1].push({ event: 'end', coverage: 'all', used_chunks: 1, total_chunks: 1 })
    streams[1].close()
    await current
    expect(requests[1].url).toMatch(/\/documents\/d2\/chat$/)
    expect(chat.messages.value.map(m => m.text)).toEqual(['About d2', 'answer about d2'])
  })

  function mountSearchChat (ids: string[]) {
    const chunkIds = ref(ids)
    const scope = effectScope()
    const chat = scope.run(() => useScopedChat((): SearchChatScope => ({
      kind: 'search',
      chunkIds: chunkIds.value,
      criteria: { textQuery: 'fire', documentFilters: { languages: ['ces'] } },
      userCollectionId: 'c1'
    })))!
    return { chat, chunkIds, scope }
  }

  it('keeps a search conversation on a scope change until the next question, which starts a new one the old answer cannot reach', async () => {
    const { chat, chunkIds } = mountSearchChat(['r1', 'r2'])
    const old = chat.ask('About r1, r2')
    await flush()
    streams[0].push({ event: 'delta', text: 'So far' })
    await flush()

    chunkIds.value = ['r2']
    await nextTick()
    // ADR 0012 decision 1: stopped, still shown, marked as about the old scope.
    expect(chat.messages.value.map(m => [m.text, m.status])).toEqual([['About r1, r2', 'done'], ['So far', 'stopped']])
    expect([chat.streaming.value, chat.scopeChanged.value]).toEqual([false, true])

    const current = chat.ask('About r2')
    await flush()
    streams[0].push({ event: 'delta', text: 'late answer' })
    streams[0].close()
    await old
    expect(chat.streaming.value).toBe(true)

    streams[1].push({ event: 'delta', text: 'answer about r2' })
    streams[1].push({ event: 'end', coverage: 'all', used_chunks: 1, total_chunks: 1 })
    streams[1].close()
    await current
    expect(requests[1].body).toMatchObject({ chunk_ids: ['r2'], history: [] })
    expect(chat.messages.value.map(m => m.text)).toEqual(['About r2', 'answer about r2'])
    expect(chat.scopeChanged.value).toBe(false)
  })

  it('starts empty on a search scope change while nothing was asked', async () => {
    const { chat, chunkIds } = mountSearchChat(['r1'])

    chunkIds.value = ['r2']
    await nextTick()

    expect([chat.messages.value, chat.scopeChanged.value]).toEqual([[], false])
  })

  it('asks about search results by id under the search criteria, and a new selection is a new scope', async () => {
    const { chat, chunkIds, scope } = mountSearchChat(['r1', 'r2', 'r3'])

    const first = chat.ask('What burned?')
    await flush()
    streams[0].push({ event: 'delta', text: 'A mill [doc2].' })
    streams[0].push({ event: 'sources', sources: [wireSource(2, 'r2')] })
    streams[0].push({ event: 'end', coverage: 'all', used_chunks: 3, total_chunks: 3 })
    streams[0].close()
    await first

    expect(requests[0].url).toMatch(/\/search\/chat$/)
    expect(requests[0].body).toEqual({
      question: 'What burned?',
      history: [],
      chunk_ids: ['r1', 'r2', 'r3'],
      criteria: { text_query: 'fire', document_filters: { languages: ['ces'] } },
      user_collection_id: 'c1'
    })

    // Other results (another search) are a new scope too.
    chunkIds.value = ['r1', 'r2', 'r3', 'r4']
    await nextTick()
    expect([chat.messages.value.length, chat.scopeChanged.value]).toEqual([2, true])

    chunkIds.value = ['r2']
    await nextTick()
    const second = chat.ask('And here?')
    await flush()
    expect(requests[1].body).toMatchObject({ chunk_ids: ['r2'], history: [] })
    expect(chat.messages.value.map(m => m.text)).toEqual(['And here?', ''])
    streams[1].close()
    await second
    scope.stop()
  })

  it('drops the conversation when its owner unmounts', async () => {
    const { chat, scope } = mountChat()
    const asking = chat.ask('Q')
    await flush()

    scope.stop()
    streams[0].push({ event: 'delta', text: 'late' })
    streams[0].close()
    await asking

    expect([chat.messages.value, chat.streaming.value]).toEqual([[], false])
  })

  it('explains a refusal for the daily AI allowance', async () => {
    const logged = muteConsole('error')
    globalThis.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({
      detail: 'Insufficient remaining daily AI allowance for this operation; it resets at 2026-10-18 00:00 UTC.',
      code: 'llm_quota_exhausted',
      principal: 'account',
      reset_at: '2026-10-18T00:00:00Z',
      limit_usd: 0.25,
      used_usd: 0.25
    }), { status: 429 }))) as typeof fetch
    const { chat } = mountChat()

    await chat.ask('Q')

    expect(chat.messages.value[1].status).toBe('error')
    expect(chat.messages.value[1].error).toMatch(/^Today's AI allowance has no room for this request/)
    expect(logged).toHaveBeenCalledWith('Chat request failed', expect.anything())
  })
})
