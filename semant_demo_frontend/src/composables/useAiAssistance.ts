import { computed, ref } from 'vue'
import type { TagSpan } from 'src/models/tagSpans'
import { SpanType } from 'src/generated/api'
import { useTagSpansStore } from 'src/stores/tagSpansStore'

/**
 * Streamed AI span suggestion (NDJSON) helper.
 *
 * Calls the backend's `/api/ai/suggest_spans/{thorough|optimized}` endpoint,
 * parses the NDJSON response line-by-line and pushes newly-created auto spans
 * into the shared {@link useTagSpansStore} so they appear in the document
 * immediately as each chunk completes.
 */

export type AiAssistanceMode = 'thorough' | 'optimized'

export interface AiAssistanceRequest {
  collectionId: string
  documentId: string
  tagIds: string[]
  mode: AiAssistanceMode
}

export interface AiAssistanceChunkEvent {
  chunkId: string
  spans: TagSpan[]
  error?: string | null
}

const BACKEND_BASE_PATH = process.env.BACKEND_URL ? process.env.BACKEND_URL + '/api' : 'http://localhost:8000/api'

const isRunning = ref(false)
const lastError = ref<string | null>(null)
const processedChunkIds = ref<Set<string>>(new Set())
const totalSpansAdded = ref(0)
let activeAbort: AbortController | null = null

// Shared UI state across the document layout (AI panel) and the document page.
// Auto (AI-suggested) spans should only be rendered while the user is on the
// "AI assist" tab; the highlighted id supports two-way selection between a
// suggestion card in the panel and the corresponding span in the text.
const aiTabActive = ref(false)
const highlightedAutoSpanId = ref<string | null>(null)

export function useAiAssistance() {
  const spansStore = useTagSpansStore()

  /**
   * All currently-pending auto spans across the document, sorted in display
   * order (confidence desc, then chunkId, then start). This is the canonical
   * order used by the AI panel, the gutter popover and the "advance to next
   * suggestion" helper below — keep it here so callers don't drift apart.
   */
  const pendingAutoSpans = computed<TagSpan[]>(() => {
    const out: TagSpan[] = []
    const byChunk = spansStore.spansByChunkId
    for (const chunkId of Object.keys(byChunk)) {
      for (const s of byChunk[chunkId] || []) {
        if (s.type === SpanType.auto) out.push(s)
      }
    }
    out.sort((a, b) => {
      const confA = a.confidence ?? -Infinity
      const confB = b.confidence ?? -Infinity
      if (confA !== confB) return confB - confA
      if (a.chunkId === b.chunkId) return a.start - b.start
      return a.chunkId.localeCompare(b.chunkId)
    })
    return out
  })

  /**
   * Pick the suggestion that should become highlighted after `spanId` is
   * resolved (approved / rejected). Returns the next entry in the pending
   * order; if `spanId` was last, returns the previous one; null when
   * nothing else is pending.
   */
  const nextPendingSuggestionAfter = (spanId: string): string | null => {
    const list = pendingAutoSpans.value
    if (list.length <= 1) return null
    const idx = list.findIndex((s) => s.id === spanId)
    if (idx === -1) return list[0]?.id ?? null
    const candidate = list[idx + 1] ?? list[idx - 1]
    return candidate?.id ?? null
  }

  /**
   * Resolve a single auto span (approve = pos / reject = neg) and advance
   * the highlight to the next pending suggestion in the same order. Used
   * both from the AI panel and from the gutter popover so the behaviour
   * stays consistent.
   */
  const resolveAutoSpan = async (
    span: TagSpan,
    type: SpanType
  ): Promise<void> => {
    if (!span.id) return
    const nextId = nextPendingSuggestionAfter(span.id)
    await spansStore.updateSpan(span.id, span.chunkId, { type })
    highlightedAutoSpanId.value = nextId
  }

  /**
   * Run a streaming AI suggestion request. Auto spans are persisted in the
   * backend; we push them into the local store so they render immediately.
   */
  const run = async (
    req: AiAssistanceRequest,
    onEvent?: (event: AiAssistanceChunkEvent) => void
  ): Promise<void> => {
    if (isRunning.value) return
    if (!req.tagIds.length) {
      lastError.value = 'Vyberte alespoň jeden tag.'
      return
    }

    cancel() // make sure no stale controller
    const abort = new AbortController()
    activeAbort = abort
    isRunning.value = true
    lastError.value = null
    processedChunkIds.value = new Set()
    totalSpansAdded.value = 0

    const path = req.mode === 'thorough'
      ? '/ai/suggest_spans/thorough'
      : '/ai/suggest_spans/optimized'
    const token = localStorage.getItem('auth_token')

    try {
      const resp = await fetch(`${BACKEND_BASE_PATH}${path}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/x-ndjson',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          collection_id: req.collectionId,
          document_id: req.documentId,
          tag_ids: req.tagIds
        }),
        signal: abort.signal
      })

      if (!resp.ok) {
        const text = await resp.text().catch(() => '')
        throw new Error(`AI assistance backend error (${resp.status}): ${text || resp.statusText}`)
      }
      if (!resp.body) {
        throw new Error('AI assistance backend did not return a streaming body.')
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      const handleLine = (line: string) => {
        const trimmed = line.trim()
        if (!trimmed) return
        let parsed: { chunk_id?: string; spans?: TagSpan[]; error?: string | null }
        try {
          parsed = JSON.parse(trimmed)
        } catch (e) {
          console.warn('AI assistance: failed to parse NDJSON line', trimmed, e)
          return
        }
        const event: AiAssistanceChunkEvent = {
          chunkId: parsed.chunk_id || '',
          spans: parsed.spans || [],
          error: parsed.error ?? null
        }
        if (event.chunkId) processedChunkIds.value.add(event.chunkId)
        if (event.spans.length) {
          totalSpansAdded.value += event.spans.length
          // Merge new auto spans into the store so they render immediately.
          const existing = spansStore.spansByChunkId[event.chunkId] || []
          // Avoid duplicates if the same span id was already in the store.
          const known = new Set(existing.map((s) => s.id).filter(Boolean) as string[])
          const fresh = event.spans.filter((s) => !s.id || !known.has(s.id))
          spansStore.spansByChunkId = {
            ...spansStore.spansByChunkId,
            [event.chunkId]: [...existing, ...fresh]
          }
        }
        if (event.error) {
          lastError.value = event.error
        }
        onEvent?.(event)
      }

      // Read & split the stream on newlines.
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let newlineIdx = buffer.indexOf('\n')
        while (newlineIdx !== -1) {
          handleLine(buffer.slice(0, newlineIdx))
          buffer = buffer.slice(newlineIdx + 1)
          newlineIdx = buffer.indexOf('\n')
        }
      }
      buffer += decoder.decode()
      if (buffer.trim()) handleLine(buffer)
    } catch (e: unknown) {
      const err = e as { name?: string; message?: string }
      if (err?.name === 'AbortError') {
        // Cancelled by user — not an error.
      } else {
        console.error('AI assistance failed', e)
        lastError.value = err?.message || 'AI assistance request failed'
      }
    } finally {
      if (activeAbort === abort) activeAbort = null
      isRunning.value = false
    }
  }

  const cancel = () => {
    if (activeAbort) {
      activeAbort.abort()
      activeAbort = null
    }
  }

  /**
   * Reset all run-state (counters, errors, highlight). Called when the user
   * navigates between documents so stale "Processed X chunks" / pending
   * suggestions don't leak across documents.
   */
  const reset = () => {
    cancel()
    isRunning.value = false
    lastError.value = null
    processedChunkIds.value = new Set()
    totalSpansAdded.value = 0
    highlightedAutoSpanId.value = null
  }

  return {
    run,
    cancel,
    reset,
    isRunning: computed(() => isRunning.value),
    lastError: computed(() => lastError.value),
    processedChunkCount: computed(() => processedChunkIds.value.size),
    totalSpansAdded: computed(() => totalSpansAdded.value),
    aiTabActive,
    highlightedAutoSpanId,
    pendingAutoSpans,
    nextPendingSuggestionAfter,
    resolveAutoSpan
  }
}

export default useAiAssistance
