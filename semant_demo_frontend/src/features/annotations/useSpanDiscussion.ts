import { computed, ref } from 'vue'
import { createContextGuard, isAbortError, postNdjson } from 'src/shared/api'

/**
 * Streaming chat-with-AI helper for span discussion.
 *
 * Calls `POST /api/ai/discuss_span` with the full chat history and parses
 * the NDJSON response into incremental deltas appended to the assistant's
 * latest message. The backend is stateless w.r.t. conversation memory — the
 * frontend re-sends the entire history each turn.
 *
 * Each reply belongs to its turn and conversation: after `cancel()` its late deltas are
 * dropped, and after `reset()` (another span, dialog closed) it cannot touch the new
 * conversation's messages or streaming state.
 */

export type SpanChatRole = 'user' | 'assistant'

export interface SpanChatMessage {
  role: SpanChatRole
  content: string
}

export interface SpanChatStartArgs {
  spanId: string
}

interface ReplyLine {
  delta?: string
  done?: boolean
  error?: string
}

export function useSpanDiscussion() {
  const messages = ref<SpanChatMessage[]>([])
  const isStreaming = ref(false)
  const error = ref<string | null>(null)
  const context = ref<SpanChatStartArgs | null>(null)
  const conversation = createContextGuard()
  const turn = createContextGuard()
  let activeAbort: AbortController | null = null

  /** Reset all state (called when dialog closes / reopens for another span). */
  const reset = (ctx: SpanChatStartArgs | null = null) => {
    cancel()
    conversation.enter()
    messages.value = []
    error.value = null
    context.value = ctx
  }

  const cancel = () => {
    if (activeAbort) {
      activeAbort.abort()
      activeAbort = null
    }
    turn.enter()
    isStreaming.value = false
  }

  /**
   * Send a user message and stream the assistant reply. Pushes the user
   * message + a fresh empty assistant message into `messages`, then appends
   * `delta` chunks into the assistant message as they arrive.
   */
  const send = async (text: string): Promise<void> => {
    const trimmed = text.trim()
    if (!trimmed) return
    if (!context.value) {
      error.value = 'No span context.'
      return
    }
    if (isStreaming.value) return

    messages.value.push({ role: 'user', content: trimmed })
    // Strip the trailing empty assistant placeholder before sending.
    const history = messages.value.map((m) => ({ role: m.role, content: m.content }))
    messages.value.push({ role: 'assistant', content: '' })
    const reply = messages.value[messages.value.length - 1]

    turn.enter()
    const isCurrentTurn = turn.capture()
    const isCurrentConversation = conversation.capture()
    error.value = null
    isStreaming.value = true
    const abort = new AbortController()
    activeAbort = abort

    try {
      await postNdjson('/ai/discuss_span', { span_id: context.value.spanId, messages: history }, {
        signal: abort.signal,
        onValue: (value) => {
          if (!isCurrentTurn()) return
          const line = value as ReplyLine
          if (line.error) {
            error.value = line.error
            return
          }
          if (line.delta) reply.content += line.delta
        },
        onInvalid: (line, e) => console.warn('useSpanDiscussion: malformed NDJSON line', line, e)
      })
    } catch (e: unknown) {
      // A cancelled request is not an error; whatever was streamed so far stays.
      if (isCurrentTurn() && !isAbortError(e)) {
        console.error('Span discussion failed', e)
        error.value = (e as { message?: string })?.message || 'Span discussion request failed'
      }
    } finally {
      if (isCurrentTurn()) {
        activeAbort = null
        isStreaming.value = false
      }
      // Drop this turn's assistant message if nothing arrived (not another conversation's).
      if (isCurrentConversation() && !reply.content) {
        const index = messages.value.indexOf(reply)
        if (index !== -1) messages.value.splice(index, 1)
      }
    }
  }

  return {
    messages,
    isStreaming: computed(() => isStreaming.value),
    error: computed(() => error.value),
    context: computed(() => context.value),
    reset,
    cancel,
    send
  }
}

export default useSpanDiscussion
