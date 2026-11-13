import { computed, onScopeDispose, ref, watch } from 'vue'
import { aiErrorMessage, createContextGuard, isAbortError, postNdjson, reportAiOperation } from 'src/shared/api'
import { tokenizeCitations, type TextToken } from 'src/shared/citationTokens'
import { ContextChatRequestToJSON, SearchChatRequestToJSON, type ChatTurn, type SearchCriteria } from 'src/generated/api'
import { forgetConversation, loadConversation, saveConversation } from './chatStorage'

/**
 * Contextual chat in the right sidebar (ADR 0012). One composable for every scope; the
 * page owns the scope and passes it in: a document of a collection (#248) or search
 * results (#245).
 *
 * The conversation lives in memory, and with `storageKey` also in this browser
 * (`chatStorage.ts`; document chat, ADR 0012 decision 1): each finished answer saves it, and
 * the scope's saved conversation comes back when the chat starts empty on that scope.
 * A scope change stops a running answer. With
 * `keepOnScopeChange` (Search, ADR 0012 decision 1) the conversation stays with `scopeChanged`
 * set, so the panel can say what the next question is about, and that question starts an
 * empty conversation. Without it (another document is another page) the conversation starts
 * empty at once (or with that scope's saved conversation), as on unmount. *New conversation*
 * also forgets the saved one. A late event of an old request never reaches a newer
 * conversation.
 *
 * Each answer is streamed as NDJSON events (`delta`, `sources`, `end` or `error`, see
 * `features/chat/schemas.py`). Its `[docN]` citations are numbered per request; the
 * `sources` event maps them to chunks, which get conversation-wide labels S1, S2... The
 * earlier turns go back to the server with their cited chunk ids, never source text.
 */

export interface DocumentChatScope {
  kind: 'document'
  collectionId: string
  documentId: string
}

/**
 * Search results (#245): `chunkIds` are the selected results, or all loaded ones, in result
 * order; `criteria` and `userCollectionId` are those of the search, under which the server
 * reads them again.
 */
export interface SearchChatScope {
  kind: 'search'
  chunkIds: readonly string[]
  criteria: SearchCriteria
  userCollectionId: string | null
}

export type ChatScope = DocumentChatScope | SearchChatScope

export interface ChatSource {
  /** The answer's `[docN]` number. */
  citation: number
  chunkId: string
  documentId: string
  order: number | null
  fromPage: number
  toPage: number
  /** Conversation-wide label: `S{label}`. */
  label: number
}

export interface ChatCoverage {
  coverage: 'all' | 'part'
  usedChunks: number
  totalChunks: number
}

export type ChatMessageStatus = 'streaming' | 'done' | 'stopped' | 'interrupted' | 'error'

export interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  /** Assistant: the cited chunks, known when the answer ends. */
  sources: ChatSource[]
  status: ChatMessageStatus
  error?: string
  coverage?: ChatCoverage
}

/**
 * An answer that was not streamed (a summary): its text, the chunks its `[docN]` cite and
 * its coverage, or `error` when it failed (the answer then shows only the error and is not
 * sent back as history).
 */
export interface ChatAnswer {
  text: string
  sources: Omit<ChatSource, 'label'>[]
  coverage?: ChatCoverage
  error?: string
}

interface Turn<S extends ChatScope> {
  /** The question as shown and sent (trimmed). */
  prompt: string
  scope: S
  history: ChatTurn[]
  reply: ChatMessage
  isCurrent: () => boolean
  signal: AbortSignal
}

export type ChatCitationToken = { type: 'citation', source: ChatSource }
export type ChatToken = TextToken | ChatCitationToken

interface WireSource {
  citation: number
  chunk_id: string
  document_id: string
  order: number | null
  from_page: number
  to_page: number
}

type ChatEvent =
  | { event: 'delta', text: string }
  | { event: 'sources', sources: WireSource[] }
  | { event: 'end', coverage: 'all' | 'part', used_chunks: number, total_chunks: number }
  | { event: 'error', code: string, message: string }

/** Earlier turns a request carries (`MAX_HISTORY_TURNS` of the backend). */
export const MAX_HISTORY_TURNS = 40
/** Longest question the backend takes (`MAX_QUESTION_CHARS`, `features/chat/schemas.py`). */
export const MAX_QUESTION_CHARS = 4000
/** Most search results one question is about (`MAX_SEARCH_CHAT_RESULTS` of the backend). */
export const MAX_SEARCH_CHAT_RESULTS = 20
const CITATION = /\[doc([1-9][0-9]*)]/g
const FAILED = 'The assistant could not answer.'
const INTERRUPTED = 'The answer was interrupted.'

/** The route and body of a question about `scope` (generated request models, so a schema change breaks the type check here). */
function chatRequest (scope: ChatScope, question: string, history: ChatTurn[]): { path: string, body: unknown } {
  if (scope.kind === 'search') {
    return {
      path: '/search/chat',
      body: SearchChatRequestToJSON({
        question,
        history,
        chunkIds: [...scope.chunkIds],
        criteria: scope.criteria,
        userCollectionId: scope.userCollectionId
      })
    }
  }
  return {
    path: `/user_collections/${encodeURIComponent(scope.collectionId)}/documents/${encodeURIComponent(scope.documentId)}/chat`,
    body: ContextChatRequestToJSON({ question, history })
  }
}

/** What the conversation is about: the same key, the same scope. */
export function scopeKey (scope: ChatScope | null): string {
  if (!scope) return ''
  if (scope.kind === 'search') {
    return `search:${scope.userCollectionId ?? ''}:${JSON.stringify(scope.criteria)}:${scope.chunkIds.join(',')}`
  }
  return `document:${scope.collectionId}:${scope.documentId}`
}

/**
 * An answer's text and citations: citations with a source become citation tokens, the
 * others (still streaming, or not mappable by the server) are left out.
 */
export function chatTokens (message: ChatMessage): ChatToken[] {
  const byCitation = new Map(message.sources.map(source => [source.citation, source]))
  return tokenizeCitations(message.text, number => {
    const source = byCitation.get(number)
    return source ? { source } : null
  }).filter(token => token.type === 'citation' || !/^\[doc[1-9][0-9]*]$/.test(token.value)) as ChatToken[]
}

/**
 * The sources of a summary's `[docN]` citations, `candidates[N - 1]` being `[docN]`, in the
 * order of their first citation; numbers without a candidate are left out (as the server's
 * `cited_sources` does for a streamed answer).
 */
export function citedSources (text: string, candidates: readonly Omit<ChatSource, 'citation' | 'label'>[]): Omit<ChatSource, 'label'>[] {
  const sources: Omit<ChatSource, 'label'>[] = []
  const seen = new Set<number>()
  for (const match of text.matchAll(CITATION)) {
    const number = Number(match[1])
    const candidate = candidates[number - 1]
    if (seen.has(number) || !candidate) continue
    seen.add(number)
    sources.push({ ...candidate, citation: number })
  }
  return sources
}

/**
 * The earlier turns as the server takes them: an answer's citations renumbered to
 * `[docK]` citing its K-th source, citations without a source removed. Failed answers
 * and their questions are left out.
 */
export function historyTurns (messages: ChatMessage[]): ChatTurn[] {
  const turns: ChatTurn[] = []
  for (let i = 0; i < messages.length; i++) {
    const message = messages[i]
    if (message.role === 'user') {
      const answer = messages[i + 1]
      if (answer?.role === 'assistant' && answer.text && answer.status !== 'error') {
        turns.push({ role: 'user', text: message.text, chunkIds: [] })
      }
      continue
    }
    if (!message.text || message.status === 'error') continue
    const index = new Map(message.sources.map((source, k) => [source.citation, k + 1]))
    const text = message.text.replace(CITATION, (_match, n: string) => {
      const k = index.get(Number(n))
      return k ? `[doc${k}]` : ''
    })
    turns.push({ role: 'assistant', text, chunkIds: message.sources.map(source => source.chunkId) })
  }
  return turns.slice(-MAX_HISTORY_TURNS)
}

export interface ScopedChatOptions<S extends ChatScope = ChatScope> {
  /** Keep the conversation, marked `scopeChanged`, until the next question after a scope change. */
  keepOnScopeChange?: boolean
  /**
   * Where the scope's conversation is kept in this browser (`chatStorage.ts`), or null to
   * keep it in memory only (also when nobody is signed in).
   */
  storageKey?: (scope: S) => string | null
}

export function useScopedChat<S extends ChatScope> (scope: () => S | null, options: ScopedChatOptions<S> = {}) {
  const messages = ref<ChatMessage[]>([])
  const streaming = ref(false)
  /** The scope changed since the shown conversation; the next question starts a new one. */
  const scopeChanged = ref(false)
  const conversation = createContextGuard()
  let labels = new Map<string, number>()
  let abort: AbortController | null = null

  function stopRequest () {
    abort?.abort()
    abort = null
    streaming.value = false
  }

  /** Where the current scope's conversation is kept, if anywhere. */
  function currentStorageKey (): string | null {
    const current = scope()
    return current && options.storageKey ? options.storageKey(current) : null
  }

  /** Stops a running answer and starts an empty conversation; a saved one stays saved. */
  function clear () {
    stopRequest()
    conversation.enter()
    messages.value = []
    labels = new Map()
    scopeChanged.value = false
  }

  /** The saved conversation of the current scope, when the shown one is empty. */
  function restore () {
    const key = currentStorageKey()
    if (!key || messages.value.length) return
    const saved = loadConversation(key)
    if (!saved) return
    messages.value = saved
    labels = new Map(saved.flatMap(message => message.sources.map(source => [source.chunkId, source.label] as const)))
  }

  /** *New conversation*: starts an empty conversation and forgets the saved one. */
  function reset () {
    clear()
    const key = currentStorageKey()
    if (key) forgetConversation(key)
  }

  /** ADR 0012 decision 1: with `keepOnScopeChange` the old conversation stays visible until the next question. */
  function changeScope () {
    if (!options.keepOnScopeChange || !messages.value.length) {
      clear()
      restore()
      return
    }
    stop()
    conversation.enter()
    scopeChanged.value = true
  }

  /** Stops the running answer; what arrived so far stays. */
  function stop () {
    const reply = messages.value[messages.value.length - 1]
    if (streaming.value && reply?.status === 'streaming') reply.status = 'stopped'
    stopRequest()
  }

  function label (chunkId: string): number {
    let value = labels.get(chunkId)
    if (value === undefined) {
      value = labels.size + 1
      labels.set(chunkId, value)
    }
    return value
  }

  /**
   * Adds a question and its answer to the conversation and runs `answer` to fill the reply:
   * one place for the scope-change reset, the abort, the guard against late events and the
   * error message, shared by questions and summaries.
   */
  async function runTurn (text: string, answer: (turn: Turn<S>) => Promise<void>): Promise<void> {
    const prompt = text.trim()
    const current = scope()
    if (!prompt || !current || streaming.value) return
    if (scopeChanged.value) clear()

    const history = historyTurns(messages.value)
    messages.value.push({ role: 'user', text: prompt, sources: [], status: 'done' })
    messages.value.push({ role: 'assistant', text: '', sources: [], status: 'streaming' })
    // The reactive proxy, so the stream's changes render.
    const reply = messages.value[messages.value.length - 1]
    const storageKey = options.storageKey?.(current) ?? null
    const isCurrent = conversation.capture()
    const controller = new AbortController()
    abort = controller
    streaming.value = true

    try {
      await answer({ prompt, scope: current, history, reply, isCurrent, signal: controller.signal })
      if (isCurrent() && reply.status === 'streaming') {
        reply.status = 'interrupted'
        reply.error = INTERRUPTED
      }
    } catch (e: unknown) {
      if (isCurrent() && !isAbortError(e)) {
        console.error('Chat request failed', e)
        // 401/404, 413 and a refusal for the daily AI allowance (429) come before the stream;
        // a failed summary is a 502 with a safe message.
        const message = await aiErrorMessage(e, FAILED)
        if (isCurrent()) {
          reply.error = message
          reply.status = 'error'
        }
      }
    } finally {
      reportAiOperation()
      if (isCurrent() && abort === controller) {
        abort = null
        streaming.value = false
      }
      // Kept once the answer has ended (also stopped or failed); one cut off by another
      // scope or unmount is not, so the saved conversation keeps its earlier turns. Nor is
      // one that ends after sign-out or an account switch, before the watcher clears it.
      if (isCurrent() && storageKey && currentStorageKey() === storageKey) saveConversation(storageKey, messages.value)
    }
  }

  function labelled (sources: readonly Omit<ChatSource, 'label'>[]): ChatSource[] {
    return sources.map(source => ({ ...source, label: label(source.chunkId) }))
  }

  async function ask (text: string): Promise<void> {
    await runTurn(text, async ({ prompt: question, scope: current, history, reply, isCurrent, signal }) => {
      const request = chatRequest(current, question, history)
      await postNdjson(request.path, request.body, {
        signal,
        onValue: (value) => {
          if (!isCurrent() || reply.status !== 'streaming') return
          const event = value as ChatEvent
          if (event.event === 'delta') {
            reply.text += event.text
          } else if (event.event === 'sources') {
            reply.sources = labelled(event.sources.map(source => ({
              citation: source.citation,
              chunkId: source.chunk_id,
              documentId: source.document_id,
              order: source.order,
              fromPage: source.from_page,
              toPage: source.to_page
            })))
          } else if (event.event === 'end') {
            reply.coverage = { coverage: event.coverage, usedChunks: event.used_chunks, totalChunks: event.total_chunks }
            reply.status = 'done'
          } else if (event.event === 'error') {
            reply.error = event.message || FAILED
            reply.status = 'error'
          }
        },
        onInvalid: (line, e) => console.warn('useScopedChat: malformed NDJSON line', line, e)
      })
    })
  }

  /**
   * A summary of the current scope as the conversation's next answer (the summary is the
   * chat's answer to `prompt`, e.g. "Summarize briefly"). The page's summary route makes it;
   * its `[docN]` citations become sources like a streamed answer's, so a follow-up question
   * sends them back as the turn's chunk ids.
   */
  async function summarize (prompt: string, run: (scope: S, signal: AbortSignal) => Promise<ChatAnswer>): Promise<void> {
    await runTurn(prompt, async ({ scope: current, reply, isCurrent, signal }) => {
      const answer = await run(current, signal)
      if (!isCurrent() || reply.status !== 'streaming') return
      if (answer.error) {
        reply.error = answer.error
        reply.status = 'error'
        return
      }
      reply.text = answer.text
      reply.sources = labelled(answer.sources)
      reply.coverage = answer.coverage
      reply.status = 'done'
    })
  }

  // The storage key is watched too: the user may become known after the chat starts
  // (session restored), and then the saved conversation is shown.
  watch(() => `${scopeKey(scope())}\n${currentStorageKey() ?? ''}`, changeScope)
  restore()
  onScopeDispose(clear)

  return {
    messages: computed(() => messages.value),
    streaming: computed(() => streaming.value),
    scopeChanged: computed(() => scopeChanged.value),
    ask,
    summarize,
    stop,
    reset
  }
}

export default useScopedChat
