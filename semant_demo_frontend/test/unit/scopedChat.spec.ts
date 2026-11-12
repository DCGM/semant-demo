import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

import { ResponseError } from 'src/generated/api'
import useScopedChat, { chatTokens, citedSources, historyTurns, type ChatAnswer, type ChatMessage, type ChatSource, type SearchChatScope } from 'src/features/chat/useScopedChat'
import { documentChatKey, loadConversation } from 'src/features/chat/chatStorage'
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

describe('citedSources', () => {
  const candidate = (chunkId: string) => ({ chunkId, documentId: 'd1', order: 1, fromPage: 1, toPage: 1 })

  it('maps [docN] to the Nth candidate in order of first citation, leaving out unknown numbers', () => {
    expect(citedSources('B [doc2], A [doc1], again [doc2], none [doc9].', [candidate('a'), candidate('b')]))
      .toEqual([{ ...candidate('b'), citation: 2 }, { ...candidate('a'), citation: 1 }])
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
    }), { keepOnScopeChange: true }))!
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

  describe('summarize', () => {
    const summary = (text: string, coverage?: ChatAnswer['coverage']): ChatAnswer => ({
      text,
      sources: [{ citation: 2, chunkId: 'c2', documentId: 'd1', order: 2, fromPage: 1, toPage: 1 }],
      coverage
    })

    it('adds the summary as an answer with its sources and coverage, and a follow-up carries them', async () => {
      const { chat } = mountChat()
      let scopeSeen: unknown

      await chat.summarize('Summarize briefly', async (scope) => {
        scopeSeen = scope
        return summary('A fire [doc2].', { coverage: 'part', usedChunks: 40, totalChunks: 55 })
      })

      expect(scopeSeen).toEqual({ kind: 'document', collectionId: 'c1', documentId: 'd1' })
      expect(chat.messages.value.map(m => [m.role, m.text, m.status])).toEqual([
        ['user', 'Summarize briefly', 'done'], ['assistant', 'A fire [doc2].', 'done']])
      expect(chat.messages.value[1].sources.map(s => [s.chunkId, s.label])).toEqual([['c2', 1]])
      expect(chat.messages.value[1].coverage).toEqual({ coverage: 'part', usedChunks: 40, totalChunks: 55 })
      expect(chat.streaming.value).toBe(false)

      const followUp = chat.ask('Why?')
      await flush()
      expect((requests[0].body as { history: unknown[] }).history).toEqual([
        { role: 'user', text: 'Summarize briefly', chunk_ids: [] },
        { role: 'assistant', text: 'A fire [doc1].', chunk_ids: ['c2'] }
      ])
      streams[0].close()
      await followUp
    })

    it('shows a failed summary\'s safe message', async () => {
      muteConsole('error')
      const { chat } = mountChat()
      const failed = new ResponseError(new Response(JSON.stringify({ detail: 'The summary could not be generated.' }), { status: 502 }))

      await chat.summarize('Summarize briefly', () => Promise.reject(failed))

      expect([chat.messages.value[1].status, chat.messages.value[1].error]).toEqual(['error', 'The summary could not be generated.'])
    })

    it('shows a summary that failed with a fallback as an error and leaves it out of the history', async () => {
      const { chat } = mountChat()

      await chat.summarize('Summarize briefly', async () => ({ text: '', sources: [], error: 'The summary could not be generated.' }))

      expect([chat.messages.value[1].status, chat.messages.value[1].error, chat.messages.value[1].text])
        .toEqual(['error', 'The summary could not be generated.', ''])
      expect(historyTurns(chat.messages.value)).toEqual([])
    })

    it('stop aborts the summary request and keeps the conversation usable', async () => {
      const { chat } = mountChat()
      let aborted = false

      const running = chat.summarize('Summarize briefly', (_scope, signal) => new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => { aborted = true; reject(new DOMException('aborted', 'AbortError')) })
      }))
      await flush()
      expect(chat.streaming.value).toBe(true)
      chat.stop()
      await running

      expect([aborted, chat.messages.value[1].status, chat.messages.value[1].error, chat.streaming.value])
        .toEqual([true, 'stopped', undefined, false])
    })

    it('drops a late summary after the document changed', async () => {
      const { chat, documentId } = mountChat()
      let finish!: (answer: ChatAnswer) => void

      const running = chat.summarize('Summarize briefly', () => new Promise(resolve => { finish = resolve }))
      await flush()
      documentId.value = 'd2'
      await nextTick()
      finish(summary('Late [doc2].'))
      await running

      expect([chat.messages.value, chat.streaming.value]).toEqual([[], false])
    })
  })

  describe('kept in the browser', () => {
    // Document chat (ADR 0012 decision 1): the conversation of a document is kept per user.
    beforeEach(() => localStorage.clear())
    afterEach(() => localStorage.clear())

    const keyOf = (documentId: string) => documentChatKey('u1', { kind: 'document', collectionId: 'c1', documentId })

    function mountKeptChat (userId = ref<string | null>('u1')) {
      const documentId = ref('d1')
      const scope = effectScope()
      const chat = scope.run(() => useScopedChat(() => ({ kind: 'document', collectionId: 'c1', documentId: documentId.value }), {
        storageKey: (s) => userId.value ? documentChatKey(userId.value, s) : null
      }))!
      return { chat, documentId, scope, userId }
    }

    async function answerWith (chat: { ask: (text: string) => Promise<void> }, text: string, reply: string, chunkId: string) {
      const asking = chat.ask(text)
      await flush()
      const stream = streams[streams.length - 1]
      stream.push({ event: 'delta', text: `${reply} [doc1]` })
      stream.push({ event: 'sources', sources: [wireSource(1, chunkId)] })
      stream.push({ event: 'end', coverage: 'all', used_chunks: 1, total_chunks: 1 })
      stream.close()
      await asking
    }

    it('shows the saved conversation again, and a follow-up continues its history and labels', async () => {
      const first = mountKeptChat()
      await answerWith(first.chat, 'Q1', 'A1', 'k1')
      first.scope.stop()
      expect(loadConversation(keyOf('d1'))?.map(m => m.text)).toEqual(['Q1', 'A1 [doc1]'])

      const { chat } = mountKeptChat()
      expect(chat.messages.value.map(m => m.text)).toEqual(['Q1', 'A1 [doc1]'])
      await answerWith(chat, 'Q2', 'A2', 'k2')

      expect((requests[1].body as { history: unknown[] }).history).toEqual([
        { role: 'user', text: 'Q1', chunk_ids: [] },
        { role: 'assistant', text: 'A1 [doc1]', chunk_ids: ['k1'] }
      ])
      expect(chat.messages.value[3].sources.map(s => s.label)).toEqual([2])
      expect(loadConversation(keyOf('d1'))).toHaveLength(4)
    })

    it('keeps each document\'s conversation, and New conversation forgets only the current one', async () => {
      const { chat, documentId } = mountKeptChat()
      await answerWith(chat, 'About d1', 'A1', 'k1')

      documentId.value = 'd2'
      await nextTick()
      expect(chat.messages.value).toEqual([])
      await answerWith(chat, 'About d2', 'A2', 'k2')

      documentId.value = 'd1'
      await nextTick()
      expect(chat.messages.value.map(m => m.text)).toEqual(['About d1', 'A1 [doc1]'])

      chat.reset()
      expect(chat.messages.value).toEqual([])
      expect(loadConversation(keyOf('d1'))).toBeNull()
      expect(loadConversation(keyOf('d2'))).not.toBeNull()
    })

    it('keeps a stopped answer, but not one cut off by leaving the document', async () => {
      const { chat, scope } = mountKeptChat()
      const stopped = chat.ask('Q1')
      await flush()
      streams[0].push({ event: 'delta', text: 'Part' })
      await flush()
      chat.stop()
      streams[0].close()
      await stopped
      expect(loadConversation(keyOf('d1'))?.map(m => [m.text, m.status])).toEqual([['Q1', 'done'], ['Part', 'stopped']])

      const cut = chat.ask('Q2')
      await flush()
      scope.stop()
      streams[1].push({ event: 'delta', text: 'late' })
      streams[1].close()
      await cut
      expect(loadConversation(keyOf('d1'))).toHaveLength(2)
    })

    it('shows the saved conversation once the user is known, and keeps nothing without one', async () => {
      const first = mountKeptChat()
      await answerWith(first.chat, 'Q1', 'A1', 'k1')
      first.scope.stop()

      const userId = ref<string | null>(null)
      const { chat } = mountKeptChat(userId)
      expect(chat.messages.value).toEqual([])
      await answerWith(chat, 'Anonymous', 'A', 'k9')
      expect(loadConversation(keyOf('d1'))?.[0].text).toBe('Q1')

      userId.value = 'u1'
      await nextTick()
      expect(chat.messages.value.map(m => m.text)).toEqual(['Q1', 'A1 [doc1]'])
    })

    it('keeps nothing without a storage key', async () => {
      const { chat } = mountChat()
      await answerWith(chat, 'Q', 'A', 'k1')
      expect(Object.keys(localStorage)).toEqual([])
    })
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
