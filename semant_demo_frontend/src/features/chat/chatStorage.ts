import { readStored, removeStored, storedKeys } from 'src/shared/browserStorage'
import type { ChatMessage, ChatMessageStatus, ChatSource, DocumentChatScope } from './useScopedChat'

/**
 * Document chat conversations kept in this browser (ADR 0012 decision 1, maintainer
 * 2026-11-12): one per document of a collection and signed-in user, its latest. A user keeps
 * the `MAX_STORED_CONVERSATIONS` most recently used ones, each for `STORED_CONVERSATION_DAYS`
 * after its last answer; signing out removes them all. Only what the panel shows is kept
 * (messages and the chunks they cite), never source text. Storage can be unavailable or
 * full; then a conversation simply isn't kept.
 */

export const MAX_STORED_CONVERSATIONS = 20
export const STORED_CONVERSATION_DAYS = 30
const MAX_AGE_MS = STORED_CONVERSATION_DAYS * 24 * 60 * 60 * 1000
const PREFIX = 'semant.chat.v1.'
const STATUSES: readonly ChatMessageStatus[] = ['streaming', 'done', 'stopped', 'interrupted', 'error']

interface StoredConversation {
  savedAt: number
  messages: readonly ChatMessage[]
}

function userPrefix (userId: string): string {
  return `${PREFIX}${userId}.`
}

/** The storage key of a user's conversation about a document of a collection. */
export function documentChatKey (userId: string, scope: DocumentChatScope): string {
  return `${userPrefix(userId)}${scope.collectionId}.${scope.documentId}`
}

const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const isString = (value: unknown): value is string => typeof value === 'string'

function isSource (value: unknown): value is ChatSource {
  const s = value as Partial<ChatSource> | null
  return !!s && typeof s === 'object' && isNumber(s.citation) && isString(s.chunkId) && isString(s.documentId) &&
    (s.order === null || isNumber(s.order)) && isNumber(s.fromPage) && isNumber(s.toPage) && isNumber(s.label)
}

function isMessage (value: unknown): value is ChatMessage {
  const m = value as Partial<ChatMessage> | null
  return !!m && typeof m === 'object' && (m.role === 'user' || m.role === 'assistant') && isString(m.text) &&
    Array.isArray(m.sources) && m.sources.every(isSource) && STATUSES.includes(m.status as ChatMessageStatus) &&
    (m.error === undefined || isString(m.error))
}

/** The stored value of `key`, or null when it is missing or not a conversation. */
function parse (raw: string | null): StoredConversation | null {
  if (raw === null) return null
  try {
    const value = JSON.parse(raw) as Partial<StoredConversation> | null
    if (!value || !isNumber(value.savedAt) || !Array.isArray(value.messages) || !value.messages.every(isMessage)) return null
    return { savedAt: value.savedAt, messages: value.messages }
  } catch {
    return null
  }
}

const expired = (conversation: StoredConversation) => Date.now() - conversation.savedAt > MAX_AGE_MS

/**
 * The conversation kept under `key`, or null. A malformed or expired one is removed. An
 * answer kept while streaming (a write cut short) comes back as interrupted.
 */
export function loadConversation (key: string): ChatMessage[] | null {
  const raw = readStored(key)
  const stored = parse(raw)
  if (!stored || expired(stored)) {
    if (raw !== null) removeStored(key)
    return null
  }
  return stored.messages.map((message): ChatMessage => message.status === 'streaming'
    ? { ...message, status: 'interrupted' }
    : message)
}

/** The prefix of the user a key belongs to (`documentChatKey`). */
function prefixOf (key: string): string {
  const end = key.indexOf('.', PREFIX.length)
  return key.slice(0, end + 1)
}

/**
 * Keeps the user's newest `MAX_STORED_CONVERSATIONS` conversations that have not expired;
 * `keep` is never removed. Returns the others, oldest first.
 */
function prune (prefix: string, keep: string): string[] {
  const entries = storedKeys(prefix)
    .filter(key => key !== keep)
    .map(key => ({ key, stored: parse(readStored(key)) }))
  const live: { key: string, savedAt: number }[] = []
  for (const { key, stored } of entries) {
    if (!stored || expired(stored)) removeStored(key)
    else live.push({ key, savedAt: stored.savedAt })
  }
  live.sort((a, b) => b.savedAt - a.savedAt)
  for (const { key } of live.slice(MAX_STORED_CONVERSATIONS - 1)) removeStored(key)
  return live.slice(0, MAX_STORED_CONVERSATIONS - 1).reverse().map(entry => entry.key)
}

function write (key: string, value: string): boolean {
  try {
    localStorage.setItem(key, value)
    return true
  } catch {
    return false
  }
}

/**
 * Keeps `messages` under `key` as the latest conversation of that document; an empty
 * conversation removes it. When storage is full, the user's oldest other conversation
 * makes room once; if that is not enough, the conversation isn't kept.
 */
export function saveConversation (key: string, messages: readonly ChatMessage[]): void {
  if (!messages.length) {
    removeStored(key)
    return
  }
  const stored: StoredConversation = { savedAt: Date.now(), messages }
  const value = JSON.stringify(stored)
  const others = prune(prefixOf(key), key)
  if (write(key, value)) return
  const oldest = others[0]
  if (oldest === undefined) return
  removeStored(oldest)
  write(key, value)
}

/** Removes the conversation kept under `key`. */
export function forgetConversation (key: string): void {
  removeStored(key)
}

/** Removes every conversation kept for `userId` (on sign-out). */
export function forgetStoredConversations (userId: string | null | undefined): void {
  if (!userId) return
  for (const key of storedKeys(userPrefix(userId))) removeStored(key)
}
