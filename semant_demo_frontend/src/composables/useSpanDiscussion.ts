import { computed, ref } from 'vue'

/**
 * Streaming chat-with-AI helper for span discussion.
 *
 * Calls `POST /api/ai/discuss_span` with the full chat history and parses
 * the NDJSON response into incremental deltas appended to the assistant's
 * latest message. The backend is stateless w.r.t. conversation memory — the
 * frontend re-sends the entire history each turn.
 */

export type SpanChatRole = 'user' | 'assistant'

export interface SpanChatMessage {
  role: SpanChatRole
  content: string
}

export interface SpanChatStartArgs {
  spanId: string
}

const BACKEND_BASE_PATH = process.env.BACKEND_URL || 'http://pcvaskom.fit.vutbr.cz:8024'

export function useSpanDiscussion() {
  const messages = ref<SpanChatMessage[]>([])
  const isStreaming = ref(false)
  const error = ref<string | null>(null)
  const context = ref<SpanChatStartArgs | null>(null)
  let activeAbort: AbortController | null = null

  /** Reset all state (called when dialog closes / reopens for another span). */
  const reset = (ctx: SpanChatStartArgs | null = null) => {
    cancel()
    messages.value = []
    error.value = null
    isStreaming.value = false
    context.value = ctx
  }

  const cancel = () => {
    if (activeAbort) {
      activeAbort.abort()
      activeAbort = null
    }
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
    const assistantIndex = messages.value.push({ role: 'assistant', content: '' }) - 1

    error.value = null
    isStreaming.value = true
    const abort = new AbortController()
    activeAbort = abort

    const token = localStorage.getItem('auth_token')
    try {
      const resp = await fetch(`${BACKEND_BASE_PATH}/api/ai/discuss_span`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/x-ndjson',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          span_id: context.value.spanId,
          // Strip the trailing empty assistant placeholder before sending.
          messages: messages.value
            .slice(0, assistantIndex)
            .map((m) => ({ role: m.role, content: m.content }))
        }),
        signal: abort.signal
      })

      if (!resp.ok) {
        const body = await resp.text().catch(() => '')
        throw new Error(`Span discussion error (${resp.status}): ${body || resp.statusText}`)
      }
      if (!resp.body) {
        throw new Error('Span discussion: backend did not return a streaming body.')
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      const handleLine = (line: string) => {
        const trimmedLine = line.trim()
        if (!trimmedLine) return
        let parsed: { delta?: string; done?: boolean; error?: string }
        try {
          parsed = JSON.parse(trimmedLine)
        } catch (e) {
          console.warn('useSpanDiscussion: malformed NDJSON line', trimmedLine, e)
          return
        }
        if (parsed.error) {
          error.value = parsed.error
          return
        }
        if (parsed.delta) {
          messages.value[assistantIndex]!.content += parsed.delta
        }
      }

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let nl = buffer.indexOf('\n')
        while (nl !== -1) {
          handleLine(buffer.slice(0, nl))
          buffer = buffer.slice(nl + 1)
          nl = buffer.indexOf('\n')
        }
      }
      buffer += decoder.decode()
      if (buffer.trim()) handleLine(buffer)
    } catch (e: unknown) {
      const err = e as { name?: string; message?: string }
      if (err?.name === 'AbortError') {
        // user cancelled — leave whatever was streamed so far
      } else {
        console.error('Span discussion failed', e)
        error.value = err?.message || 'Span discussion request failed'
      }
    } finally {
      if (activeAbort === abort) activeAbort = null
      isStreaming.value = false
      // Drop trailing empty assistant message if nothing arrived.
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant' && !last.content) {
        messages.value.pop()
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
