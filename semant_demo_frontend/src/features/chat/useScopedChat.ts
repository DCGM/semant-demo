import { computed, onScopeDispose, ref, watch } from 'vue'
import { aiErrorMessage, createContextGuard, isAbortError, postNdjson, reportAiOperation } from 'src/shared/api'
import { tokenizeCitations, type TextToken } from 'src/shared/citationTokens'

/**
 * Contextual chat in the right sidebar (ADR 0012). One composable for every scope; the
 * page owns the scope and passes it in. Only the document scope (#248) exists so far.
 *
 * The conversation lives in memory only. A scope change, unmount or *New conversation*
 * stops a running answer and starts an empty conversation (another document is another
 * page, ADR 0012 decision 1); a late event of the old request never reaches it.
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

export type ChatScope = DocumentChatScope

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

interface HistoryTurn {
  role: 'user' | 'assistant'
  text: string
  chunk_ids: string[]
}

/** Earlier turns a request carries (`MAX_HISTORY_TURNS` of the backend). */
export const MAX_HISTORY_TURNS = 40
/** Longest question the backend takes (`MAX_QUESTION_CHARS`, `features/chat/schemas.py`). */
export const MAX_QUESTION_CHARS = 4000
const CITATION = /\[doc([1-9][0-9]*)]/g
const FAILED = 'The assistant could not answer.'
const INTERRUPTED = 'The answer was interrupted.'

function chatPath (scope: ChatScope): string {
  return `/user_collections/${encodeURIComponent(scope.collectionId)}/documents/${encodeURIComponent(scope.documentId)}/chat`
}

function scopeKey (scope: ChatScope | null): string {
  return scope ? `${scope.kind}:${scope.collectionId}:${scope.documentId}` : ''
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
export function historyTurns (messages: ChatMessage[]): HistoryTurn[] {
  const turns: HistoryTurn[] = []
  for (let i = 0; i < messages.length; i++) {
    const message = messages[i]
    if (message.role === 'user') {
      const answer = messages[i + 1]
      if (answer?.role === 'assistant' && answer.text && answer.status !== 'error') {
        turns.push({ role: 'user', text: message.text, chunk_ids: [] })
      }
      continue
    }
    if (!message.text || message.status === 'error') continue
    const index = new Map(message.sources.map((source, k) => [source.citation, k + 1]))
    const text = message.text.replace(CITATION, (_match, n: string) => {
      const k = index.get(Number(n))
      return k ? `[doc${k}]` : ''
    })
    turns.push({ role: 'assistant', text, chunk_ids: message.sources.map(source => source.chunkId) })
  }
  return turns.slice(-MAX_HISTORY_TURNS)
}

export function useScopedChat (scope: () => ChatScope | null) {
  const messages = ref<ChatMessage[]>([])
  const streaming = ref(false)
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
      await postNdjson(chatPath(current), { question, history }, {
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

  // Another document or collection is another page: its chat starts empty.
  watch(() => scopeKey(scope()), reset)
  onScopeDispose(reset)

  return {
    messages: computed(() => messages.value),
    streaming: computed(() => streaming.value),
    ask,
    stop,
    reset
  }
}

export default useScopedChat
