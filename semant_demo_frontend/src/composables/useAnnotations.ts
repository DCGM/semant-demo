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
export interface ProjectedSpan extends TagSpan {
  /** Original start/end before projection (for editing) */
  originalStart: number
  originalEnd: number
  originalChunkId: string
}

/** Emitted by ChunkAnnotator when the user makes a text selection */
export interface ChunkSelectionEvent {
  chunkId: string
  start: number
  end: number
}

/** Emitted by ChunkAnnotator when the user clicks an existing span */
export interface SpanClickEvent {
  span: ProjectedSpan
}

// ── Composable ─────────────────────────────────────────

export function useAnnotations(chunksRef: () => Chunk[]) {
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

  const spansByChunkId = computed(() => store.spansByChunkId)
  const loading = computed(() => store.loading)

  // ── Span loading ──

  const loadAllSpans = async () => {
    const chunkIds = chunks.value.map((c) => c.id)
    if (chunkIds.length) {
      await store.fetchSpansForChunks(chunkIds)
    }
  }

  const refreshChunkSpans = async (chunkId: string) => {
    await store.fetchSpansForChunk(chunkId)
  }

  // ── Cross-chunk offset math ──

  /**
   * Compute the cumulative character offset from the start of `fromChunkId`
   * to the start of `toChunkId`.
   */
  const getOffsetBetweenChunks = (fromChunkId: string, toChunkId: string): number | null => {
    const fromIndex = chunkIndexById.value[fromChunkId]
    const toIndex = chunkIndexById.value[toChunkId]
    if (fromIndex === undefined || toIndex === undefined) return null
    if (toIndex < fromIndex) return null

    let offset = 0
    for (let i = fromIndex; i < toIndex; i++) {
      offset += chunks.value[i].text.length
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
    const targetIndex = chunkIndexById.value[targetChunkId]
    if (targetIndex === undefined) return []

    const targetLength = chunks.value[targetIndex].text.length
    const result: ProjectedSpan[] = []

    // Check all chunks from the start up to and including the target
    for (let srcIndex = 0; srcIndex <= targetIndex; srcIndex++) {
      const srcChunk = chunks.value[srcIndex]
      const srcSpans = spansByChunkId.value[srcChunk.id] || []

      for (const span of srcSpans) {
        if (span.type === SpanType.neg) continue

        // Offset from source chunk start to target chunk start
        let offsetToTarget = 0
        for (let i = srcIndex; i < targetIndex; i++) {
          offsetToTarget += chunks.value[i].text.length
        }

        if (srcIndex === targetIndex) {
          // Same chunk — no projection needed
          result.push({
            ...span,
            originalStart: span.start,
            originalEnd: span.end,
            originalChunkId: srcChunk.id
          })
        } else {
          // Cross-chunk projection
          const localStart = Math.max(0, span.start - offsetToTarget)
          const localEnd = Math.min(targetLength, span.end - offsetToTarget)

          if (localEnd <= localStart) continue

          result.push({
            ...span,
            start: localStart,
            end: localEnd,
            originalStart: span.start,
            originalEnd: span.end,
            originalChunkId: srcChunk.id
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

    // Compute global end relative to firstChunkId
    const offsetToLast = getOffsetBetweenChunks(firstChunkId, lastChunkId)
    if (offsetToLast === null) return

    selection.value = {
      chunkId: firstChunkId,
      start: firstOffset,
      end: offsetToLast + lastOffset,
      editingSpanId,
      tagId
    }
  }

  const editSpan = (span: ProjectedSpan) => {
    selection.value = {
      chunkId: span.originalChunkId,
      start: span.originalStart,
      end: span.originalEnd,
      editingSpanId: span.id ?? undefined,
      tagId: span.tagId
    }
    originalPosition.value = {
      chunkId: span.originalChunkId,
      start: span.originalStart,
      end: span.originalEnd
    }
  }

  const clearSelection = () => {
    selection.value = null
    originalPosition.value = null
  }

  // ── CRUD actions ──

  const createSpan = async (tagId: string) => {
    if (!selection.value) return

    await store.createSpan({
      chunkId: selection.value.chunkId,
      tagId,
      start: selection.value.start,
      end: selection.value.end,
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

    const spanId = selection.value.editingSpanId
    const ownerChunkId = findSpanOwnerChunkId(spanId)

    if (ownerChunkId && ownerChunkId !== selection.value.chunkId) {
      // Span moved to a different chunk → delete + create
      await store.deleteSpan(spanId, ownerChunkId)
      await store.createSpan({
        chunkId: selection.value.chunkId,
        tagId: selection.value.tagId!,
        start: selection.value.start,
        end: selection.value.end,
        type: SpanType.pos
      })
    } else {
      await store.updateSpan(spanId, selection.value.chunkId, {
        start: selection.value.start,
        end: selection.value.end
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

    const sel = selection.value

    if (handle === 'start') {
      // Compute the new start as a global offset from current anchor chunk
      const offsetFromAnchorToTarget = getOffsetBetweenChunks(sel.chunkId, targetChunkId)

      if (offsetFromAnchorToTarget !== null) {
        // Target is at or after anchor chunk
        const newStart = offsetFromAnchorToTarget + charOffset
        if (newStart >= sel.end) return
        selection.value = { ...sel, start: newStart }
      } else {
        // Target is before anchor chunk — re-anchor to the target chunk
        const offsetFromTargetToAnchor = getOffsetBetweenChunks(targetChunkId, sel.chunkId)
        if (offsetFromTargetToAnchor === null) return
        const newEnd = offsetFromTargetToAnchor + sel.end
        if (charOffset >= newEnd) return
        selection.value = {
          ...sel,
          chunkId: targetChunkId,
          start: charOffset,
          end: newEnd
        }
      }
    } else {
      // Moving end handle
      const offsetFromAnchorToTarget = getOffsetBetweenChunks(sel.chunkId, targetChunkId)
      if (offsetFromAnchorToTarget === null) return
      const newEnd = offsetFromAnchorToTarget + charOffset
      if (newEnd <= sel.start) return
      selection.value = { ...sel, end: newEnd }
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
