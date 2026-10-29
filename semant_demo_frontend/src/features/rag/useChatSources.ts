import { computed, reactive, ref, shallowRef, watch, type Ref } from 'vue'
import type { SearchResultChunk } from 'src/generated/api'
import { useChunkContext } from 'src/features/documents/useChunkContext'

/** A chat message as far as its sources are concerned. */
export interface MessageWithSources {
  sources?: SearchResultChunk[]
}

/** One source chunk of the conversation, with its conversation-wide display label. */
export interface ChatSourceEntry {
  /** The chunk id; a chunk cited by several answers is one entry. */
  id: string
  /** `S1`, `S2`, ... in order of first appearance; stays the same for the conversation. */
  label: string
  source: SearchResultChunk
}

/**
 * All source chunks of the conversation's answers, in order of first appearance (answer by
 * answer, each in its own source order), deduplicated by chunk id and labelled `S1`, `S2`...
 * New answers only append, so a label never changes while the conversation lasts.
 */
export function sourceRegistry (messages: readonly MessageWithSources[]): ChatSourceEntry[] {
  const entries: ChatSourceEntry[] = []
  const seen = new Set<string>()
  for (const message of messages) {
    for (const source of message.sources ?? []) {
      if (seen.has(source.id)) continue
      seen.add(source.id)
      entries.push({ id: source.id, label: `S${entries.length + 1}`, source })
    }
  }
  return entries
}

/**
 * Whether the source is a corpus chunk with a document to show. A web search result of an
 * answer (`origin: 'web'`, #370) is not: its ids name no corpus document.
 */
export function hasDocument (source: SearchResultChunk): boolean {
  return source.origin !== 'web'
}

/**
 * The page of a web search result (its `documentObject.url`), or null for a corpus source
 * or a URL that is not a well-formed HTTP(S) URL.
 */
export function webPageUrl (source: SearchResultChunk): string | null {
  const url: unknown = source.documentObject?.url
  if (source.origin !== 'web' || typeof url !== 'string') return null
  try {
    const parsed = new URL(url.trim())
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null
  } catch {
    return null
  }
}

/**
 * The chunk id an answer's own citation `[doc N]` refers to (its `sources[N-1]`), or null
 * when the answer has no such source; such a citation must not be relabelled.
 */
export function citedChunkId (message: MessageWithSources | undefined, docNumber: number): string | null {
  if (!Number.isInteger(docNumber) || docNumber < 1) return null
  return message?.sources?.[docNumber - 1]?.id ?? null
}

/**
 * The sources of a chat conversation (#246): the conversation-wide list with stable
 * display labels, one selected source, and one source shown in its document context.
 *
 * Selection and the document are named by chunk id. A new answer does not change them;
 * selecting another source closes the document of the previous one (so the Document panel
 * never shows another source than the selected one); a source that is no longer in the
 * conversation (reset, another account) clears everything. Opening another document aborts
 * the previous context request and drops its late answer (`useChunkContext`).
 */
export function useChatSources (messages: Ref<readonly MessageWithSources[]>) {
  const entries = computed(() => sourceRegistry(messages.value))
  const byId = computed(() => new Map(entries.value.map(e => [e.id, e])))

  const selectedId = ref<string | null>(null)
  const documentSourceId = ref<string | null>(null)
  /** A request to bring a source of the list into view; changes with every request. */
  const reveal = shallowRef<{ id: string, seq: number } | null>(null)
  const context = reactive(useChunkContext())

  const selected = computed(() => (selectedId.value && byId.value.get(selectedId.value)) || null)
  const documentSource = computed(() => (documentSourceId.value && byId.value.get(documentSourceId.value)) || null)

  function labelOf (chunkId: string | null): string | null {
    return (chunkId && byId.value.get(chunkId)?.label) || null
  }

  function revealSource (id: string) {
    reveal.value = { id, seq: (reveal.value?.seq ?? 0) + 1 }
  }

  function closeDocument () {
    documentSourceId.value = null
    context.clear()
  }

  /** Forgets the selection and the document. */
  function clear () {
    selectedId.value = null
    reveal.value = null
    closeDocument()
  }

  /**
   * Selects a source (also the selected one again, which keeps it) and asks the list to
   * bring it into view. Another source closes the previous one's document. Returns whether
   * the source is in the conversation.
   */
  function select (id: string): boolean {
    if (!byId.value.has(id)) return false
    if (documentSourceId.value !== null && documentSourceId.value !== id) closeDocument()
    selectedId.value = id
    revealSource(id)
    return true
  }

  /**
   * Selects a source and shows it in its document (again: brings it back into view). Returns
   * false, changing nothing, for a source without a document (`hasDocument`).
   */
  function openDocument (id: string): boolean {
    const entry = byId.value.get(id)
    if (!entry || !hasDocument(entry.source) || !select(id)) return false
    const { source } = entry
    documentSourceId.value = id
    void context.open({ documentId: source.document, chunkId: source.id })
    return true
  }

  // Sources that are gone (a reset conversation, another account) take the selection and
  // the document with them.
  watch(byId, (current) => {
    if ((selectedId.value && !current.has(selectedId.value)) ||
        (documentSourceId.value && !current.has(documentSourceId.value))) clear()
  })

  return {
    entries,
    selectedId,
    selected,
    documentSource,
    reveal,
    context,
    labelOf,
    revealSource,
    select,
    openDocument,
    clear
  }
}
