import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  MAX_STORED_CONVERSATIONS,
  STORED_CONVERSATION_DAYS,
  documentChatKey,
  forgetConversation,
  forgetStoredConversations,
  loadConversation,
  saveConversation
} from 'src/features/chat/chatStorage'
import type { ChatMessage } from 'src/features/chat/useScopedChat'

// Document chat conversations kept in the browser (ADR 0012 decision 1, #248).

const DAY = 24 * 60 * 60 * 1000
const key = (documentId: string, userId = 'u1') => documentChatKey(userId, { kind: 'document', collectionId: 'c1', documentId })
const conversation = (text: string, status: ChatMessage['status'] = 'done'): ChatMessage[] => [
  { role: 'user', text, sources: [], status: 'done' },
  {
    role: 'assistant',
    text: `Answer [doc1] to ${text}`,
    sources: [{ citation: 1, chunkId: 'k1', documentId: 'd1', order: 1, fromPage: 1, toPage: 2, label: 1 }],
    status,
    coverage: { coverage: 'all', usedChunks: 3, totalChunks: 3 }
  }
]

beforeEach(() => {
  localStorage.clear()
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-12T10:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('chatStorage', () => {
  it('keeps a conversation per user, collection and document', () => {
    saveConversation(key('d1'), conversation('Q1'))
    saveConversation(key('d2'), conversation('Q2'))
    saveConversation(key('d1', 'u2'), conversation('Q3'))

    expect(loadConversation(key('d1'))).toEqual(conversation('Q1'))
    expect(loadConversation(key('d2'))).toEqual(conversation('Q2'))
    expect(loadConversation(key('d1', 'u2'))).toEqual(conversation('Q3'))
    expect(loadConversation(key('d3'))).toBeNull()
  })

  it('removes the conversation when it is saved empty or forgotten', () => {
    saveConversation(key('d1'), conversation('Q1'))
    saveConversation(key('d1'), [])
    expect(loadConversation(key('d1'))).toBeNull()

    saveConversation(key('d2'), conversation('Q2'))
    forgetConversation(key('d2'))
    expect(loadConversation(key('d2'))).toBeNull()
  })

  it('drops a value that is not a conversation', () => {
    const stored = (messages: unknown[]) => JSON.stringify({ savedAt: Date.now(), messages })
    const malformed = {
      d1: '{not json',
      d2: stored([{ role: 'system', text: 'x', sources: [], status: 'done' }]),
      d3: stored(conversation('Q', 'streaming')), // never saved while an answer streams
      d4: stored([{ ...conversation('Q')[1], coverage: {} }])
    }
    for (const [documentId, value] of Object.entries(malformed)) localStorage.setItem(key(documentId), value)

    for (const documentId of Object.keys(malformed)) {
      expect(loadConversation(key(documentId)), documentId).toBeNull()
      expect(localStorage.getItem(key(documentId)), documentId).toBeNull()
    }
  })

  it(`drops a conversation unused for more than ${STORED_CONVERSATION_DAYS} days`, () => {
    saveConversation(key('d1'), conversation('Q1'))
    saveConversation(key('d2'), conversation('Q2'))
    vi.setSystemTime(Date.now() + STORED_CONVERSATION_DAYS * DAY - 1000)
    expect(loadConversation(key('d1'))).not.toBeNull()
    saveConversation(key('d2'), conversation('Q2 again'))

    vi.setSystemTime(Date.now() + 2000)
    expect(loadConversation(key('d1'))).toBeNull()
    expect(localStorage.getItem(key('d1'))).toBeNull()
    expect(loadConversation(key('d2'))).not.toBeNull()
  })

  it('drops another user\'s expired conversations on any save', () => {
    saveConversation(key('d1', 'u2'), conversation('Old'))
    vi.advanceTimersByTime(10 * DAY)
    saveConversation(key('d2', 'u2'), conversation('Newer'))
    vi.advanceTimersByTime(STORED_CONVERSATION_DAYS * DAY - 5 * DAY)

    saveConversation(key('d1'), conversation('Q1'))

    expect(localStorage.getItem(key('d1', 'u2'))).toBeNull()
    expect(localStorage.getItem(key('d2', 'u2'))).not.toBeNull()
  })

  it(`keeps the ${MAX_STORED_CONVERSATIONS} most recently used conversations of a user`, () => {
    for (let i = 0; i < MAX_STORED_CONVERSATIONS; i++) {
      saveConversation(key(`d${i}`), conversation(`Q${i}`))
      vi.advanceTimersByTime(1000)
    }
    saveConversation(key('d0'), conversation('Q0 again')) // d0 is now the newest, d1 the oldest
    vi.advanceTimersByTime(1000)
    saveConversation(key('other', 'u2'), conversation('Other user'))
    saveConversation(key('new'), conversation('New'))

    expect(loadConversation(key('d1'))).toBeNull()
    expect(loadConversation(key('d0'))?.[0].text).toBe('Q0 again')
    expect(loadConversation(key('d2'))).not.toBeNull()
    expect(loadConversation(key('new'))).not.toBeNull()
    expect(loadConversation(key('other', 'u2'))).not.toBeNull()
    expect(Object.keys(localStorage).filter(k => k.startsWith('semant.chat.v1.u1.'))).toHaveLength(MAX_STORED_CONVERSATIONS)
  })

  it('makes room by dropping the oldest conversation when storage is full', () => {
    saveConversation(key('d1'), conversation('Q1'))
    vi.advanceTimersByTime(1000)
    saveConversation(key('d2'), conversation('Q2'))
    vi.advanceTimersByTime(1000)
    const setItem = Storage.prototype.setItem
    let refusals = 1
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, k: string, v: string) {
      if (refusals-- > 0) throw new DOMException('full', 'QuotaExceededError')
      setItem.call(this, k, v)
    })

    saveConversation(key('d3'), conversation('Q3'))

    expect(loadConversation(key('d1'))).toBeNull()
    expect(loadConversation(key('d2'))).not.toBeNull()
    expect(loadConversation(key('d3'))).not.toBeNull()
  })

  it('keeps no older copy when even the room made is not enough', () => {
    saveConversation(key('d1'), conversation('Q1'))
    vi.advanceTimersByTime(1000)
    saveConversation(key('d2'), conversation('Q2'))
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError') })

    saveConversation(key('d2'), [...conversation('Q2'), ...conversation('Q3')])

    expect(loadConversation(key('d1'))).toBeNull() // made room, still not enough
    expect(loadConversation(key('d2'))).toBeNull() // not the shorter copy
  })

  it('does nothing when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })

    expect(() => saveConversation(key('d1'), conversation('Q1'))).not.toThrow()
    expect(loadConversation(key('d1'))).toBeNull()
  })

  it('forgets all conversations of a user on sign-out, and only theirs', () => {
    saveConversation(key('d1'), conversation('Q1'))
    saveConversation(key('d2'), conversation('Q2'))
    saveConversation(key('d1', 'u2'), conversation('Q3'))
    localStorage.setItem('semant.tagPanelSort', 'name')

    forgetStoredConversations('u1')
    forgetStoredConversations(undefined)

    expect(loadConversation(key('d1'))).toBeNull()
    expect(loadConversation(key('d2'))).toBeNull()
    expect(loadConversation(key('d1', 'u2'))).not.toBeNull()
    expect(localStorage.getItem('semant.tagPanelSort')).toBe('name')
  })
})
