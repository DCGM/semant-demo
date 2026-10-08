import { computed, ref } from 'vue'
import type { TagSpan } from 'src/models/tagSpans'
import { SpanType } from 'src/generated/api'
import { useTagSpansStore } from 'src/stores/tagSpansStore'
import { readNdjson } from 'src/utils/ndjson'

/**
 * Streamed AI span suggestion (NDJSON) helper.
 *
 * Calls the backend's `/api/ai/suggest_spans/{thorough|optimized|selection}` endpoints,
 * parses the NDJSON response line-by-line and pushes newly-created auto spans
 * into the shared {@link useTagSpansStore} so they appear in the document
 * immediately as each chunk completes.
 *
 * Each run belongs to the document/collection it was started for. `reset()` (called
 * when the document or collection changes) aborts it and makes its late events, errors
 * and loading-state changes no-ops, so they cannot alter the new context.
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
  /** Proposals the backend did not save (storage failure or invalid proposal); see ``error``. */
  unsaved: number
}

/** The final `SuggestSpansRunEnd` line of a suggestion stream. */
export interface AiRunEnd {
  event: 'end'
  outcome: 'complete' | 'partial' | 'failed'
  saved: number
  rejected: number
  save_failures: number
  search_tag_failures: number
  provider_failures: number
  error?: string | null
}

/** How the last run ended; `interrupted`: the stream ended without its final line. */
export type AiRunStatus = AiRunEnd['outcome'] | 'cancelled' | 'interrupted'

interface ResultLine {
  event?: 'result'
  chunk_id?: string
  spans?: TagSpan[]
  error?: string | null
  unsaved?: number
}

/** A readable message for a run that did not complete, or null. */
export function describeRunEnd (end: AiRunEnd | null): string | null {
  if (!end) {
    return 'AI suggestions stopped before completion. Suggestions saved so far are kept.'
  }
  if (end.outcome === 'complete') return null
  const problems: string[] = []
  if (end.provider_failures) problems.push(`${end.provider_failures} AI request(s) failed`)
  if (end.save_failures) problems.push(`${end.save_failures} suggestion(s) could not be saved`)
  if (end.search_tag_failures) problems.push(`${end.search_tag_failures} saved suggestion(s) not yet findable by tag search`)
  if (end.error) problems.push(end.error)
  const head = end.outcome === 'failed' ? 'AI suggestions failed' : 'AI suggestions were only partly completed'
  return `${head} (${end.saved} saved): ${problems.join('; ')}.`
}

function isRunEnd (value: unknown): value is AiRunEnd {
  return typeof value === 'object' && value !== null && (value as { event?: unknown }).event === 'end'
}

const BACKEND_BASE_PATH = process.env.BACKEND_URL ? process.env.BACKEND_URL + '/api' : 'http://localhost:8000/api'

const isRunning = ref(false)
const lastError = ref<string | null>(null)
const lastStatus = ref<AiRunStatus | null>(null)
const processedChunkIds = ref<Set<string>>(new Set())
const totalSpansAdded = ref(0)
const totalUnsaved = ref(0)
let activeAbort: AbortController | null = null

// Bumped by every run and by reset(); a run whose token is no longer current is stale.
let runToken = 0
let activeRunToken = 0
let activeSelectionToken = 0

// Shared UI state across the document layout (AI panel) and the document page.
// Auto (AI-suggested) spans should only be rendered while the user is on the
// "AI assist" tab; the highlighted id supports two-way selection between a
// suggestion card in the panel and the corresponding span in the text.
const aiTabActive = ref(false)
const highlightedAutoSpanId = ref<string | null>(null)

// Bumped when something outside the layout (e.g. the in-text selection
// popover's "Suggest tags" button) wants the right drawer to switch to the
// "AI assist" tab. The layout owns ``drawerTab`` / ``drawerOpen`` so we use a
// nonce-watch handshake instead of trying to share that state across files.
const aiPanelRequestNonce = ref(0)

const isSelectionRunning = ref(false)
const lastSelectionError = ref<string | null>(null)
let activeSelectionAbort: AbortController | null = null

/**
 * POST a suggestion request and feed its NDJSON lines to `onResult` while `isCurrent()`.
 * Returns the final line, or null when the stream ended without it.
 */
async function streamSuggestions (
  path: string,
  body: unknown,
  signal: AbortSignal,
  isCurrent: () => boolean,
  onResult: (line: ResultLine) => void
): Promise<AiRunEnd | null> {
  const token = localStorage.getItem('auth_token')
  const resp = await fetch(`${BACKEND_BASE_PATH}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/x-ndjson',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body),
    signal
  })
  if (!resp.ok) {
    const text = await resp.text().catch(() => '')
    throw new Error(`AI assistance backend error (${resp.status}): ${text || resp.statusText}`)
  }
  if (!resp.body) {
    throw new Error('AI assistance backend did not return a streaming body.')
  }
  let end: AiRunEnd | null = null
  await readNdjson(
    resp.body,
    (value) => {
      if (!isCurrent()) return
      if (isRunEnd(value)) end = value
      else onResult(value as ResultLine)
    },
    (line, e) => console.warn('AI assistance: failed to parse NDJSON line', line, e)
  )
  return end
}

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
   * Resolve a single auto span (approve = pos / reject = neg). Clears the
   * highlight afterwards so no auto-scroll to the next pending suggestion
   * happens — the user navigates manually.
   */
  const resolveAutoSpan = async (
    span: TagSpan,
    type: SpanType
  ): Promise<void> => {
    if (!span.id) return
    await spansStore.updateSpan(span.id, span.chunkId, { type })
    if (highlightedAutoSpanId.value === span.id) {
      highlightedAutoSpanId.value = null
    }
  }

  /** Add saved spans to the store (once per id); returns the ones that were new. */
  const addSpans = (chunkId: string, spans: TagSpan[]): TagSpan[] => {
    if (!chunkId || !spans.length) return []
    const existing = spansStore.spansByChunkId[chunkId] || []
    const known = new Set(existing.map((s) => s.id).filter(Boolean) as string[])
    const fresh = spans.filter((s) => !s.id || !known.has(s.id))
    if (fresh.length) {
      spansStore.spansByChunkId = {
        ...spansStore.spansByChunkId,
        [chunkId]: [...existing, ...fresh]
      }
    }
    return fresh
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
      lastError.value = 'Choose at least one tag to get suggestions.'
      return
    }

    cancel() // make sure no stale controller
    const abort = new AbortController()
    const myToken = ++runToken
    const isCurrent = () => activeRunToken === myToken
    activeAbort = abort
    activeRunToken = myToken
    isRunning.value = true
    lastError.value = null
    lastStatus.value = null
    processedChunkIds.value = new Set()
    totalSpansAdded.value = 0
    totalUnsaved.value = 0

    const path = req.mode === 'thorough'
      ? '/ai/suggest_spans/thorough'
      : '/ai/suggest_spans/optimized'

    try {
      const end = await streamSuggestions(path, {
        collection_id: req.collectionId,
        document_id: req.documentId,
        tag_ids: req.tagIds
      }, abort.signal, isCurrent, (parsed) => {
        const event: AiAssistanceChunkEvent = {
          chunkId: parsed.chunk_id || '',
          spans: parsed.spans || [],
          error: parsed.error ?? null,
          unsaved: parsed.unsaved ?? 0
        }
        totalUnsaved.value += event.unsaved
        if (event.chunkId) processedChunkIds.value.add(event.chunkId)
        // Merge new auto spans into the store so they render immediately.
        totalSpansAdded.value += addSpans(event.chunkId, event.spans).length
        if (event.error) {
          lastError.value = event.error
        }
        onEvent?.(event)
      })
      if (!isCurrent()) return
      lastStatus.value = end ? end.outcome : 'interrupted'
      const summary = describeRunEnd(end)
      if (summary) lastError.value = summary
    } catch (e: unknown) {
      if (!isCurrent()) return
      const err = e as { name?: string; message?: string }
      if (err?.name === 'AbortError') {
        // Cancelled by user — not an error.
        lastStatus.value = 'cancelled'
      } else {
        console.error('AI assistance failed', e)
        lastStatus.value = 'interrupted'
        lastError.value = err?.message || 'AI assistance request failed'
      }
    } finally {
      if (isCurrent()) {
        activeAbort = null
        isRunning.value = false
      }
    }
  }

  const cancel = () => {
    if (activeAbort) {
      activeAbort.abort()
      activeAbort = null
    }
  }

  /**
   * Run AI suggestion on a single user-selected passage that may span
   * multiple consecutive chunks.
   *
   * Hits the backend's NDJSON-streaming ``/ai/suggest_spans/selection``
   * endpoint and pushes each persisted auto span into the shared store
   * as it arrives so the user sees suggestions appear progressively.
   * Each event's ``chunk_id`` is the *anchor chunk* of that specific
   * span — i.e. the chunk where the span starts — matching how
   * non-AI cross-chunk spans are stored, so the gutter / panel pick the
   * span up automatically.
   *
   * Aborting the request via :func:`cancelSelection` cancels the upstream
   * Topicer call too. Resolves to the new spans, or null when the run was
   * cancelled or the document/collection changed meanwhile (nothing to report).
   */
  const runOnSelection = async (req: {
    collectionId: string
    documentId: string
    chunkIds: string[]
    selectionStart: number
    selectionEnd: number
    tagIds: string[]
  }): Promise<TagSpan[] | null> => {
    if (!req.tagIds.length) {
      lastSelectionError.value = 'No tags selected for AI suggestion.'
      return []
    }
    if (!req.chunkIds.length) {
      lastSelectionError.value = 'Empty selection.'
      return []
    }
    if (req.selectionEnd <= req.selectionStart) {
      lastSelectionError.value = 'Empty selection.'
      return []
    }

    cancelSelection() // make sure no stale controller
    const abort = new AbortController()
    const myToken = ++runToken
    const isCurrent = () => activeSelectionToken === myToken
    activeSelectionAbort = abort
    activeSelectionToken = myToken
    isSelectionRunning.value = true
    lastSelectionError.value = null
    const collected: TagSpan[] = []

    try {
      const end = await streamSuggestions('/ai/suggest_spans/selection', {
        collection_id: req.collectionId,
        document_id: req.documentId,
        chunk_ids: req.chunkIds,
        selection_start: req.selectionStart,
        selection_end: req.selectionEnd,
        tag_ids: req.tagIds
      }, abort.signal, isCurrent, (parsed) => {
        if (parsed.error) {
          lastSelectionError.value = parsed.error
        }
        totalUnsaved.value += parsed.unsaved ?? 0
        const newOnes = addSpans(parsed.chunk_id || '', parsed.spans || [])
        totalSpansAdded.value += newOnes.length
        collected.push(...newOnes)
      })
      if (!isCurrent()) return null
      const summary = describeRunEnd(end)
      if (summary) lastSelectionError.value = summary
      return collected
    } catch (e: unknown) {
      if (!isCurrent()) return null
      const err = e as { name?: string; message?: string }
      if (err?.name === 'AbortError') {
        // Cancelled by user — not an error.
        return null
      }
      console.error('AI selection assistance failed', e)
      lastSelectionError.value = err?.message || 'AI selection request failed'
      return collected
    } finally {
      if (isCurrent()) {
        activeSelectionAbort = null
        isSelectionRunning.value = false
      }
    }
  }

  const cancelSelection = () => {
    if (activeSelectionAbort) {
      activeSelectionAbort.abort()
      activeSelectionAbort = null
    }
  }

  /**
   * Ask the document layout to switch the right drawer to the "AI assist"
   * tab (and open it if it's collapsed). Implemented via a nonce so that
   * repeated calls each trigger the layout's watcher.
   */
  const requestOpenAiPanel = () => {
    aiPanelRequestNonce.value += 1
  }

  /**
   * Reset all run-state (counters, errors, highlight). Called when the user
   * navigates between documents or collections so stale "Processed X chunks" /
   * pending suggestions don't leak across them. Running requests are aborted and
   * their late events ignored.
   */
  const reset = () => {
    cancel()
    cancelSelection()
    activeRunToken = 0
    activeSelectionToken = 0
    isRunning.value = false
    isSelectionRunning.value = false
    lastError.value = null
    lastStatus.value = null
    lastSelectionError.value = null
    processedChunkIds.value = new Set()
    totalSpansAdded.value = 0
    totalUnsaved.value = 0
    highlightedAutoSpanId.value = null
  }

  return {
    run,
    cancel,
    reset,
    runOnSelection,
    cancelSelection,
    requestOpenAiPanel,
    isRunning: computed(() => isRunning.value),
    isSelectionRunning: computed(() => isSelectionRunning.value),
    lastError: computed(() => lastError.value),
    lastStatus: computed(() => lastStatus.value),
    lastSelectionError: computed(() => lastSelectionError.value),
    processedChunkCount: computed(() => processedChunkIds.value.size),
    totalSpansAdded: computed(() => totalSpansAdded.value),
    totalUnsaved: computed(() => totalUnsaved.value),
    aiTabActive,
    aiPanelRequestNonce,
    highlightedAutoSpanId,
    pendingAutoSpans,
    nextPendingSuggestionAfter,
    resolveAutoSpan
  }
}

export default useAiAssistance
