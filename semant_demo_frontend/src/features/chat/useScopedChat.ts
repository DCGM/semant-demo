import { computed, onScopeDispose, ref, watch } from 'vue'
import { aiErrorMessage, createContextGuard, isAbortError, postNdjson, reportAiOperation } from 'src/shared/api'
import { tokenizeCitations, type TextToken } from 'src/shared/citationTokens'
import { ContextChatRequestToJSON, SearchChatRequestToJSON, type ChatTurn, type SearchCriteria } from 'src/generated/api'

/**
 * Contextual chat in the right sidebar (ADR 0012). One composable for every scope; the
 * page owns the scope and passes it in: a document of a collection (#248) or search
 * results (#245).
 *
 * The conversation lives in memory only. A scope change stops a running answer and keeps
 * the conversation with `scopeChanged` set, so the panel can say what the next question is
 * about; that question then starts an empty conversation (ADR 0012 decision 1). Unmount and
 * *New conversation* start an empty one at once. A late event of an old request never
 * reaches a newer conversation.
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

export function useScopedChat (scope: () => ChatScope | null) {
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

  /** Stops a running answer and starts an empty conversation. */
  function reset () {
    stopRequest()
    conversation.enter()
    messages.value = []
    labels = new Map()
    scopeChanged.value = false
  }

  /** ADR 0012 decision 1: the old conversation stays visible until the next question. */
  function changeScope () {
    if (!messages.value.length) {
      reset()
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

  async function ask (text: string): Promise<void> {
    const question = text.trim()
    const current = scope()
    if (!question || !current || streaming.value) return
    if (scopeChanged.value) reset()

    const history = historyTurns(messages.value)
    messages.value.push({ role: 'user', text: question, sources: [], status: 'done' })
    messages.value.push({ role: 'assistant', text: '', sources: [], status: 'streaming' })
    // The reactive proxy, so the stream's changes render.
    const reply = messages.value[messages.value.length - 1]
    const isCurrent = conversation.capture()
    const controller = new AbortController()
    abort = controller
    streaming.value = true

    try {
      const request = chatRequest(current, question, history)
      await postNdjson(request.path, request.body, {
        signal: controller.signal,
        onValue: (value) => {
          if (!isCurrent() || reply.status !== 'streaming') return
          const event = value as ChatEvent
          if (event.event === 'delta') {
            reply.text += event.text
          } else if (event.event === 'sources') {
            reply.sources = event.sources.map(source => ({
              citation: source.citation,
              chunkId: source.chunk_id,
              documentId: source.document_id,
              order: source.order,
              fromPage: source.from_page,
              toPage: source.to_page,
              label: label(source.chunk_id)
            }))
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
      if (isCurrent() && reply.status === 'streaming') {
        reply.status = 'interrupted'
        reply.error = INTERRUPTED
      }
    } catch (e: unknown) {
      if (isCurrent() && !isAbortError(e)) {
        console.error('Chat request failed', e)
        // 401/404, 413 and a refusal for the daily AI allowance (429) come before the stream.
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
    }
  }

  watch(() => scopeKey(scope()), changeScope)
  onScopeDispose(reset)

  return {
    messages: computed(() => messages.value),
    streaming: computed(() => streaming.value),
    scopeChanged: computed(() => scopeChanged.value),
    ask,
    stop,
    reset
  }
}

export default useScopedChat
