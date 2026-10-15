import { computed, reactive, shallowRef, watch, type Ref } from 'vue'
import type { SearchResultChunk } from 'src/generated/api'
import { useChunkContext } from 'src/features/documents/useChunkContext'

/** A chat message as far as its sources are concerned; `id` stays the same for its lifetime. */
export interface MessageWithSources {
  id: number
  sources?: SearchResultChunk[]
}

/** Whose sources are shown: one message, and optionally one of its sources in its document. */
export interface SourceSelection {
  messageId: number
  sourceIndex: number | null
}

/**
 * The sources of one assistant answer and, optionally, one of them in its document
 * context (#246). The selection names the message by its id, never "the latest answer",
 * so new answers do not change what is shown and a message that disappears (a reset
 * conversation) closes its sources. Opening another source or message aborts the previous
 * context request and drops its late answer (`useChunkContext`).
 */
export function useChatSources<M extends MessageWithSources> (messages: Ref<M[]>) {
  const selection = shallowRef<SourceSelection | null>(null)
  const context = reactive(useChunkContext())

  const message = computed(() => {
    const id = selection.value?.messageId
    return id === undefined ? null : messages.value.find(m => m.id === id) ?? null
  })
  const sources = computed<SearchResultChunk[]>(() => message.value?.sources ?? [])
  const sourceIndex = computed(() => {
    const index = selection.value?.sourceIndex ?? null
    return index !== null && index < sources.value.length ? index : null
  })
  const source = computed(() => sourceIndex.value === null ? null : sources.value[sourceIndex.value])

  /** Forgets the shown message and source. */
  function clear () {
    selection.value = null
    context.clear()
  }

  function sourcesOf (messageId: number): SearchResultChunk[] {
    return messages.value.find(m => m.id === messageId)?.sources ?? []
  }

  /**
   * Shows the sources of a message. Another message's open source is closed; the same
   * message keeps its open source. Returns whether the message has any sources.
   */
  function showMessage (messageId: number): boolean {
    if (!sourcesOf(messageId).length) return false
    if (selection.value?.messageId === messageId) return true
    context.clear()
    selection.value = { messageId, sourceIndex: null }
    return true
  }

  /**
   * Shows one source of a message in its document (also the same one again, which brings
   * it back into view). Returns whether the source exists; the context loads meanwhile.
   */
  function showSource (messageId: number, sourceIndex: number): boolean {
    const chunk = sourcesOf(messageId)[sourceIndex]
    if (!chunk) return false
    selection.value = { messageId, sourceIndex }
    void context.open({ documentId: chunk.document, chunkId: chunk.id })
    return true
  }

  // A message that is gone (reset, another account) takes its sources and context with it.
  watch(message, (current) => {
    if (!current && selection.value) clear()
  })

  return { selection, message, sources, sourceIndex, source, context, showMessage, showSource, clear }
}
