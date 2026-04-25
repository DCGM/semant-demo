import { computed, ref } from 'vue'
import { useTagSpansStore } from 'src/stores/tagSpansStore'
import { SpanType } from 'src/generated/api'
import type { TagSpan } from 'src/models/tagSpans'
import type { Chunk } from 'src/models/chunks'

// ── Types ──────────────────────────────────────────────

/** Selection expressed in local chunk coordinates */
export interface LocalSelection {
  start: number
  end: number
  editingSpanId?: string
  tagId?: string
  showStartHandle: boolean
  showEndHandle: boolean
}

/** Selection expressed in "document-global" coordinates (offset from first chunk) */
export interface GlobalSelection {
  chunkId: string // chunk where the selection starts
  start: number // offset from beginning of chunkId
  end: number // may exceed chunkId length → spans into later chunks
  editingSpanId?: string
  tagId?: string
}

/** A tag span projected into a specific chunk's local coordinate space */
export type ProjectedSpan = TagSpan

// ── Composable ─────────────────────────────────────────

export function useAnnotations(chunksRef: () => Chunk[], hiddenChunksRef: () => Chunk[] = () => []) {
  const store = useTagSpansStore()

  // ── State ──

  const selection = ref<GlobalSelection | null>(null)
  /** Stores the original position when editing starts, to detect changes */
  const originalPosition = ref<{ chunkId: string; start: number; end: number } | null>(null)

  // ── Computed helpers ──

  const chunks = computed(() => chunksRef())

  const chunkIndexById = computed(() => {
    const map: Record<string, number> = {}
    chunks.value.forEach((chunk, index) => {
      map[chunk.id] = index
    })
    return map
  })

  // All known chunks: display chunks + hidden gap chunks, sorted by document order.
  // Used for cross-chunk span projection across gaps (e.g. a span spanning a removed chunk).
  const allKnownChunks = computed(() => {
    const byId = new Map<string, Chunk>()
    for (const c of chunks.value) byId.set(c.id, c)
    for (const c of hiddenChunksRef()) if (!byId.has(c.id)) byId.set(c.id, c)
    return Array.from(byId.values()).sort((a, b) => a.order - b.order)
  })

  const allKnownChunkIndexById = computed(() => {
    const map: Record<string, number> = {}
    allKnownChunks.value.forEach((chunk, index) => { map[chunk.id] = index })
    return map
  })

  const spansByChunkId = computed(() => store.spansByChunkId)
  const loading = computed(() => store.loading)

  // ── Span loading ──

  const loadAllSpans = async (collectionId: string) => {
    const chunkIds = chunks.value.map((c) => c.id)
    if (chunkIds.length) {
      await store.fetchSpansForChunksInCollection(chunkIds, collectionId)
    }
  }

  const refreshChunkSpans = async (chunkId: string, collectionId: string) => {
    await store.fetchSpansForChunkInCollection(chunkId, collectionId)
  }

  // ── Cross-chunk offset math ──

  /**
   * Returns true if all display chunks from fromIndex to toIndex (inclusive)
   * have consecutive order values (no document gaps between them).
   */
  const areConsecutiveChunks = (fromIndex: number, toIndex: number): boolean => {
    for (let i = fromIndex; i < toIndex; i++) {
      if (allKnownChunks.value[i + 1].order !== allKnownChunks.value[i].order + 1) return false
    }
    return true
  }

  /**
   * Compute the cumulative character offset from the start of `fromChunkId`
   * to the start of `toChunkId`. Returns null if there is a document gap
   * anywhere along the path.
   */
  const getOffsetBetweenChunks = (fromChunkId: string, toChunkId: string): number | null => {
    const fromIndex = allKnownChunkIndexById.value[fromChunkId]
    const toIndex = allKnownChunkIndexById.value[toChunkId]
    if (fromIndex === undefined || toIndex === undefined) return null
    if (toIndex < fromIndex) return null
    if (!areConsecutiveChunks(fromIndex, toIndex)) return null

    let offset = 0
    for (let i = fromIndex; i < toIndex; i++) {
      offset += allKnownChunks.value[i].text.length
    }
    return offset
  }

  // ── Selection projection ──

  /**
   * Project the global selection into a specific chunk's local coordinates.
   * Returns null if the selection does not overlap this chunk.
   */
  const getLocalSelection = (chunkId: string): LocalSelection | null => {
    if (!selection.value) return null

    const offset = getOffsetBetweenChunks(selection.value.chunkId, chunkId)
    if (offset === null) return null

    const chunkIndex = chunkIndexById.value[chunkId]
    const chunkLength = chunks.value[chunkIndex].text.length

    const localStart = Math.max(0, selection.value.start - offset)
    const localEnd = Math.min(chunkLength, selection.value.end - offset)

    if (localEnd <= localStart) return null

    // Only show start handle if the real selection start is in this chunk
    const showStartHandle = selection.value.start - offset >= 0 && selection.value.start - offset <= chunkLength
    // Only show end handle if the real selection end is in this chunk
    const showEndHandle = selection.value.end - offset >= 0 && selection.value.end - offset <= chunkLength

    return {
      start: localStart,
      end: localEnd,
      editingSpanId: selection.value.editingSpanId,
      tagId: selection.value.tagId,
      showStartHandle,
      showEndHandle
    }
  }

  // ── Span projection ──

  /**
   * Get all visible spans projected into a specific chunk's local coordinates.
   * Spans from earlier chunks that overflow into this chunk are included.
   * Negative (declined) spans are filtered out.
   */
  const getProjectedSpans = (targetChunkId: string): ProjectedSpan[] => {
    const targetIndex = allKnownChunkIndexById.value[targetChunkId]
    if (targetIndex === undefined) return []

    const targetLength = allKnownChunks.value[targetIndex].text.length
    const result: ProjectedSpan[] = []

    // Check all known chunks (incl. hidden gap chunks) from the start up to and including the target
    for (let srcIndex = 0; srcIndex <= targetIndex; srcIndex++) {
      const srcChunk = allKnownChunks.value[srcIndex]
      const srcSpans = spansByChunkId.value[srcChunk.id] || []

      for (const span of srcSpans) {
        if (span.type === SpanType.neg) continue

        if (srcIndex === targetIndex) {
          // Same chunk — no projection needed
          result.push({ ...span })
        } else {
          // Cross-chunk projection — only if every intermediate known chunk is consecutive
          if (!areConsecutiveChunks(srcIndex, targetIndex)) continue

          let offsetToTarget = 0
          for (let i = srcIndex; i < targetIndex; i++) {
            offsetToTarget += allKnownChunks.value[i].text.length
          }

          const localStart = Math.max(0, span.start - offsetToTarget)
          const localEnd = Math.min(targetLength, span.end - offsetToTarget)

          if (localEnd <= localStart) continue

          result.push({
            ...span,
            start: localStart,
            end: localEnd
          })
        }
      }
    }

    return result
  }

  // ── Selection handling ──

  const setSelection = (chunkId: string, start: number, end: number, editingSpanId?: string, tagId?: string) => {
    if (start >= end) {
      selection.value = null
      return
    }
    selection.value = { chunkId, start, end, editingSpanId, tagId }
  }

  /**
   * Handle a cross-chunk selection where start and end are in different chunks.
   * Normalizes into a single GlobalSelection anchored to the earlier chunk.
   */
  const setCrossChunkSelection = (
    startChunkId: string, startOffset: number,
    endChunkId: string, endOffset: number,
    editingSpanId?: string, tagId?: string
  ) => {
    const startIndex = chunkIndexById.value[startChunkId]
    const endIndex = chunkIndexById.value[endChunkId]
    if (startIndex === undefined || endIndex === undefined) return

    // Ensure start comes before end
    let firstChunkId = startChunkId
    let firstOffset = startOffset
    let lastChunkId = endChunkId
    let lastOffset = endOffset

    if (startIndex > endIndex || (startIndex === endIndex && startOffset > endOffset)) {
      firstChunkId = endChunkId
      firstOffset = endOffset
      lastChunkId = startChunkId
      lastOffset = startOffset
    }

    // Compute global end relative to firstChunkId — only if no gap in between
    const offsetToLast = getOffsetBetweenChunks(firstChunkId, lastChunkId)
    if (offsetToLast === null) {
      // There's a document gap between the two chunks — clamp to just the first chunk
      const firstIndex = chunkIndexById.value[firstChunkId]
      if (firstIndex === undefined) return
      const firstChunkLength = chunks.value[firstIndex].text.length
      if (firstOffset >= firstChunkLength) return
      selection.value = {
        chunkId: firstChunkId,
        start: firstOffset,
        end: firstChunkLength,
        editingSpanId,
        tagId
      }
      return
    }

    selection.value = {
      chunkId: firstChunkId,
      start: firstOffset,
      end: offsetToLast + lastOffset,
      editingSpanId,
      tagId
    }
  }

  const editSpan = (span: TagSpan) => {
    selection.value = {
      chunkId: span.chunkId,
      start: span.start,
      end: span.end,
      editingSpanId: span.id ?? undefined,
      tagId: span.tagId
    }
    originalPosition.value = {
      chunkId: span.chunkId,
      start: span.start,
      end: span.end
    }
  }

  const clearSelection = () => {
    selection.value = null
    originalPosition.value = null
  }

  /**
   * Keep GlobalSelection anchored to the chunk that really contains `start`.
   */
  const normalizeSelectionToStartChunk = (sel: GlobalSelection): GlobalSelection | null => {
    let chunkIndex = chunkIndexById.value[sel.chunkId]
    if (chunkIndex === undefined) return null

    let chunkId = sel.chunkId
    let start = sel.start
    let end = sel.end

    // Move anchor forward while start is outside current chunk to the right.
    // Stop at document gaps to avoid crossing into non-consecutive chunks.
    while (chunkIndex < chunks.value.length - 1 && start >= chunks.value[chunkIndex].text.length) {
      if (chunks.value[chunkIndex + 1].order !== chunks.value[chunkIndex].order + 1) break
      const len = chunks.value[chunkIndex].text.length
      start -= len
      end -= len
      chunkIndex += 1
      chunkId = chunks.value[chunkIndex].id
    }

    // Move anchor backward while start is outside current chunk to the left.
    // Stop at document gaps to avoid crossing into non-consecutive chunks.
    while (chunkIndex > 0 && start < 0) {
      if (chunks.value[chunkIndex].order !== chunks.value[chunkIndex - 1].order + 1) break
      chunkIndex -= 1
      const len = chunks.value[chunkIndex].text.length
      start += len
      end += len
      chunkId = chunks.value[chunkIndex].id
    }

    const chunkLength = chunks.value[chunkIndex].text.length
    if (start < 0 || start >= chunkLength || end <= start) return null

    return {
      ...sel,
      chunkId,
      start,
      end
    }
  }

  // ── CRUD actions ──

  const createSpan = async (tagId: string) => {
    if (!selection.value) return

    const normalized = normalizeSelectionToStartChunk(selection.value)
    if (!normalized) return

    await store.createSpan({
      chunkId: normalized.chunkId,
      tagId,
      start: normalized.start,
      end: normalized.end,
      type: SpanType.pos
    })
    clearSelection()
  }

  const updateSpanTag = async (tagId: string) => {
    if (!selection.value?.editingSpanId) return

    // Update visual highlight immediately
    selection.value = { ...selection.value, tagId }

    await store.updateSpan(
      selection.value.editingSpanId!,
      selection.value.chunkId,
      { tagId }
    )
    clearSelection()
  }

  const updateSpanPosition = async () => {
    if (!selection.value?.editingSpanId) return

    const normalized = normalizeSelectionToStartChunk(selection.value)
    if (!normalized?.editingSpanId) return

    // Keep UI state consistent with the normalized anchor used for persistence.
    selection.value = normalized

    const spanId = normalized.editingSpanId
    const ownerChunkId = findSpanOwnerChunkId(spanId)

    if (ownerChunkId && ownerChunkId !== normalized.chunkId) {
      // Span moved to a different chunk → delete + create
      await store.deleteSpan(spanId, ownerChunkId)
      await store.createSpan({
        chunkId: normalized.chunkId,
        tagId: normalized.tagId!,
        start: normalized.start,
        end: normalized.end,
        type: SpanType.pos
      })
    } else {
      await store.updateSpan(spanId, normalized.chunkId, {
        start: normalized.start,
        end: normalized.end
      })
    }
    clearSelection()
  }

  const deleteSpan = async () => {
    if (!selection.value?.editingSpanId) return

    const spanId = selection.value.editingSpanId
    const ownerChunkId = findSpanOwnerChunkId(spanId) || selection.value.chunkId
    await store.deleteSpan(spanId, ownerChunkId)
    clearSelection()
  }

  // ── Helpers ──

  const findSpanOwnerChunkId = (spanId: string): string | null => {
    for (const [chunkId, spans] of Object.entries(spansByChunkId.value)) {
      if (spans.some((s) => s.id === spanId)) return chunkId
    }
    return null
  }

  const isEditing = computed(() => !!selection.value?.editingSpanId)
  const hasSelection = computed(() => !!selection.value)
  const positionChanged = computed(() => {
    if (!selection.value || !originalPosition.value) return false
    return (
      selection.value.chunkId !== originalPosition.value.chunkId ||
      selection.value.start !== originalPosition.value.start ||
      selection.value.end !== originalPosition.value.end
    )
  })

  /**
   * Move a selection boundary (start or end) to a new position in a chunk.
   * Used by drag handles.
   */
  const adjustSelectionBoundary = (
    handle: 'start' | 'end',
    targetChunkId: string,
    charOffset: number
  ) => {
    if (!selection.value) return

    const normalized = normalizeSelectionToStartChunk(selection.value)
    if (!normalized) return

    if (handle === 'start') {
      // Compute the new start as a global offset from current anchor chunk
      const offsetFromAnchorToTarget = getOffsetBetweenChunks(normalized.chunkId, targetChunkId)

      if (offsetFromAnchorToTarget !== null) {
        // Target is at or after anchor chunk — re-anchor directly to target chunk
        const newEnd = normalized.end - offsetFromAnchorToTarget
        if (charOffset >= newEnd) return
        selection.value = {
          ...normalized,
          chunkId: targetChunkId,
          start: charOffset,
          end: newEnd
        }
      } else {
        // Target is before anchor chunk — re-anchor to the target chunk
        const offsetFromTargetToAnchor = getOffsetBetweenChunks(targetChunkId, normalized.chunkId)
        if (offsetFromTargetToAnchor === null) return
        const newEnd = offsetFromTargetToAnchor + normalized.end
        if (charOffset >= newEnd) return
        selection.value = {
          ...normalized,
          chunkId: targetChunkId,
          start: charOffset,
          end: newEnd
        }
      }
    } else {
      // Moving end handle
      const offsetFromAnchorToTarget = getOffsetBetweenChunks(normalized.chunkId, targetChunkId)
      if (offsetFromAnchorToTarget === null) return
      const newEnd = offsetFromAnchorToTarget + charOffset
      if (newEnd <= normalized.start) return
      selection.value = { ...normalized, end: newEnd }
    }
  }

  return {
    // State
    selection,
    loading,
    isEditing,
    hasSelection,
    positionChanged,
    spansByChunkId,

    // Loading
    loadAllSpans,
    refreshChunkSpans,

    // Selection
    setSelection,
    setCrossChunkSelection,
    editSpan,
    clearSelection,
    adjustSelectionBoundary,

    // Projection
    getLocalSelection,
    getProjectedSpans,

    // CRUD
    createSpan,
    updateSpanTag,
    updateSpanPosition,
    deleteSpan
  }
}
