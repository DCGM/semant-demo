import { computed, ref } from 'vue'
import { useTagSpansStore } from './tagSpansStore'
import { SpanType, TagSpan, CollectionChunk } from 'src/generated/api'
import { anchorAtStart, knownChunksInOrder, localRange, projectSpan, reuseIfSameReferences } from './spanOffsets'
import { createContextGuard, errorStatus } from 'src/shared/api'

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
  /** The chunk the edited span is stored on; a boundary drag moves only `chunkId`. */
  spanChunkId?: string
  tagId?: string
}

/** A tag span projected into a specific chunk's local coordinate space */
export type ProjectedSpan = TagSpan

// ── Composable ─────────────────────────────────────────

export function useAnnotations(chunksRef: () => CollectionChunk[], hiddenChunksRef: () => CollectionChunk[] = () => []) {
  const store = useTagSpansStore()

  // ── State ──

  const selection = ref<GlobalSelection | null>(null)
  /** Stores the original position when editing starts, to detect changes */
  const originalPosition = ref<{ chunkId: string; start: number; end: number } | null>(null)
  /**
   * Identifies the current selection: entered whenever a new selection replaces it or it is
   * cleared, but not when its boundaries or tag change. A span request uses it to tell whether
   * the selection it was made for is still the open one once it finishes.
   */
  const selectionGuard = createContextGuard()
  /** A span request for the current selection is in flight; the popover shows it as busy. */
  const saving = ref(false)
  /** Starts a new selection (or none): earlier span requests no longer own what is open. */
  const enterSelection = () => {
    selectionGuard.enter()
    saving.value = false
  }

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
  const allKnownChunks = computed(() =>
    knownChunksInOrder(chunks.value, hiddenChunksRef())
  )

  interface KnownChunkPosition {
    index: number
    segment: number
    offset: number
  }

  const allKnownChunkPositionById = computed(() => {
    const map: Record<string, KnownChunkPosition> = {}
    const known = allKnownChunks.value

    let segment = 0
    let offset = 0

    for (let i = 0; i < known.length; i++) {
      if (i > 0) {
        const previous = known[i - 1]
        const current = known[i]

        if (current.order === previous.order + 1) {
          offset += previous.text.length
        } else {
          segment++
          offset = 0
        }
      }

      map[known[i].id] = {
        index: i,
        segment,
        offset
      }
    }

    return map
  })

  const spansByChunkId = computed(() => store.spansByChunkId)
  const spansVersion = computed(() => store.spansVersion)
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
   * Compute the cumulative character offset from the start of `fromChunkId`
   * to the start of `toChunkId`. Returns null if there is a document gap
   * anywhere along the path.
   */
  const getOffsetBetweenChunks = (fromChunkId: string, toChunkId: string): number | null => {
    const from = allKnownChunkPositionById.value[fromChunkId]
    const to = allKnownChunkPositionById.value[toChunkId]

    if (!from || !to) return null
    if (to.index < from.index) return null
    if (to.segment !== from.segment) return null

    return to.offset - from.offset
  }

  // ── Selection projection ──

  /**
   * Project the global selection into every chunk's local coordinates, keyed
   * by chunk id. Memoized so it only recomputes when `chunks` or `selection`
   * actually change, instead of on every render (e.g. hover-only ones).
   */
  const localSelectionByChunkId = computed(() => {
    const map: Record<string, LocalSelection> = {}
    const sel = selection.value
    if (!sel) return map

    for (const chunk of chunks.value) {
      const offset = getOffsetBetweenChunks(sel.chunkId, chunk.id)
      if (offset === null) continue

      const chunkLength = chunk.text.length
      const range = localRange(sel.start, sel.end, offset, chunkLength)
      if (!range) continue

      // Only show start/end handle if the real selection boundary is in this chunk
      const showStartHandle = sel.start - offset >= 0 && sel.start - offset <= chunkLength
      const showEndHandle = sel.end - offset >= 0 && sel.end - offset <= chunkLength

      map[chunk.id] = {
        ...range,
        editingSpanId: sel.editingSpanId,
        tagId: sel.tagId,
        showStartHandle,
        showEndHandle
      }
    }

    return map
  })

  /**
   * Get the global selection projected into a specific chunk's local
   * coordinates. Returns null if the selection does not overlap this chunk.
   */
  const getLocalSelection = (chunkId: string): LocalSelection | null => {
    return localSelectionByChunkId.value[chunkId] ?? null
  }

  // ── Span projection ──

  /**
   * Projected span objects are cached by source-span identity and target
   * chunk. The store replaces span objects on updates rather than mutating
   * them in place.
   */
  const projectedSpanCache = new WeakMap<TagSpan, Map<string, ProjectedSpan>>()

  let previousAllProjectedSpansByChunkId: Record<string, ProjectedSpan[]> = {}
  let previousProjectedSpansByChunkId: Record<string, ProjectedSpan[]> = {}

  const cachedProjectedSpan = (
    span: TagSpan,
    targetChunkId: string,
    start: number,
    end: number
  ): ProjectedSpan => {
    let byChunk = projectedSpanCache.get(span)

    if (!byChunk) {
      byChunk = new Map()
      projectedSpanCache.set(span, byChunk)
    }

    const cached = byChunk.get(targetChunkId)

    if (cached && cached.start === start && cached.end === end) {
      return cached
    }

    const projected: ProjectedSpan = {
      ...span,
      start,
      end
    }

    byChunk.set(targetChunkId, projected)
    return projected
  }

  /**
   * Project all spans into known chunks, including declined spans needed
   * by the gutter when an annotation is opened through a direct link.
   *
   * Each source span is walked once through the consecutive chunks it
   * overlaps. Unchanged per-chunk arrays retain their identity.
   */
  const allProjectedSpansByChunkId = computed(() => {
    const known = allKnownChunks.value
    const next: Record<string, ProjectedSpan[]> = {}

    // Every known chunk gets a bucket once.
    for (const chunk of known) {
      next[chunk.id] = []
    }

    for (let srcIndex = 0; srcIndex < known.length; srcIndex++) {
      const srcChunk = known[srcIndex]
      const spans = spansByChunkId.value[srcChunk.id] ?? []

      for (const span of spans) {
        // Preserve the original anchor entry and its full coordinates.
        // This also preserves the old behavior for legacy invalid offsets.
        next[srcChunk.id].push(
          cachedProjectedSpan(span, srcChunk.id, span.start, span.end)
        )

        // Project into subsequent chunks only. The anchor was added above.
        for (const part of projectSpan(known, srcIndex, span.start, span.end)) {
          if (part.chunk === srcIndex) continue

          const target = known[part.chunk]

          next[target.id].push(
            cachedProjectedSpan(span, target.id, part.start, part.end)
          )
        }
      }
    }

    // Keep stable array identities for chunks whose spans did not change.
    for (const chunk of known) {
      next[chunk.id] = reuseIfSameReferences(
        previousAllProjectedSpansByChunkId[chunk.id],
        next[chunk.id]
      )
    }

    previousAllProjectedSpansByChunkId = next
    return next
  })

  /**
   * Regular text annotations exclude declined spans.
   * This separate memoization layer preserves stable array references
   * for unaffected ChunkAnnotator components.
   */
  const projectedSpansByChunkId = computed(() => {
    const next: Record<string, ProjectedSpan[]> = {}

    for (const chunk of allKnownChunks.value) {
      const filtered = (
        allProjectedSpansByChunkId.value[chunk.id] ?? []
      ).filter((span) => span.type !== SpanType.neg)

      next[chunk.id] = reuseIfSameReferences(
        previousProjectedSpansByChunkId[chunk.id],
        filtered
      )
    }

    previousProjectedSpansByChunkId = next
    return next
  })

  /**
   * Get non-declined spans projected into a chunk's local coordinates.
   * Includes spans anchored on earlier chunks that overlap this chunk.
   */
  const getProjectedSpans = (targetChunkId: string): ProjectedSpan[] => {
    return projectedSpansByChunkId.value[targetChunkId] ?? []
  }

  /**
   * Get all projected spans, including declined ones.
   * The gutter decides which of these spans should be displayed.
   */
  const getAllProjectedSpans = (targetChunkId: string): ProjectedSpan[] => {
    return allProjectedSpansByChunkId.value[targetChunkId] ?? []
  }

  // ── Selection handling ──

  const setSelection = (chunkId: string, start: number, end: number, editingSpanId?: string, tagId?: string) => {
    enterSelection()
    if (start >= end) {
      selection.value = null
      return
    }
    selection.value = { chunkId, start, end, editingSpanId, tagId }
  }

  /**
   * Handle a cross-chunk selection where start and end are in different chunks.
   * Normalizes into a single GlobalSelection anchored to the earlier chunk. Returns whether
   * it was cut to the end of the first chunk because of a document gap before the last one.
   */
  const setCrossChunkSelection = (
    startChunkId: string, startOffset: number,
    endChunkId: string, endOffset: number,
    editingSpanId?: string, tagId?: string
  ): boolean => {
    const startIndex = chunkIndexById.value[startChunkId]
    const endIndex = chunkIndexById.value[endChunkId]
    if (startIndex === undefined || endIndex === undefined) return false

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
      if (firstIndex === undefined) return false
      const firstChunkLength = chunks.value[firstIndex].text.length
      if (firstOffset >= firstChunkLength) return false
      enterSelection()
      selection.value = {
        chunkId: firstChunkId,
        start: firstOffset,
        end: firstChunkLength,
        editingSpanId,
        tagId
      }
      return true
    }

    enterSelection()
    selection.value = {
      chunkId: firstChunkId,
      start: firstOffset,
      end: offsetToLast + lastOffset,
      editingSpanId,
      tagId
    }
    return false
  }

  const editSpan = (span: TagSpan) => {
    enterSelection()
    selection.value = {
      chunkId: span.chunkId,
      start: span.start,
      end: span.end,
      editingSpanId: span.id ?? undefined,
      spanChunkId: span.chunkId,
      tagId: span.tagId
    }
    originalPosition.value = {
      chunkId: span.chunkId,
      start: span.start,
      end: span.end
    }
  }

  const clearSelection = () => {
    enterSelection()
    selection.value = null
    originalPosition.value = null
  }

  /**
   * Keep GlobalSelection anchored to the chunk that really contains `start`.
   */
  const normalizeSelectionToStartChunk = (sel: GlobalSelection): GlobalSelection | null => {
    const chunkIndex = chunkIndexById.value[sel.chunkId]
    if (chunkIndex === undefined) return null
    const anchored = anchorAtStart(chunks.value, chunkIndex, sel.start, sel.end)
    if (!anchored) return null
    return {
      ...sel,
      chunkId: chunks.value[anchored.index].id,
      start: anchored.start,
      end: anchored.end
    }
  }

  // ── CRUD actions ──

  /**
   * Run a span request for the current selection, then close that selection — unless the user
   * has moved on to a newer one by then, which stays open. While a request for the selection is
   * in flight (`saving`), further requests on it are ignored, so a double-click runs only one.
   * Returns whether the request ran; a request that fails throws and leaves the selection open.
   */
  const applyToSelection = async (request: () => Promise<void>): Promise<boolean> => {
    if (saving.value) return false
    const isCurrent = selectionGuard.capture()
    saving.value = true
    let outdated = false
    try {
      await request()
    } catch (err) {
      // Someone else changed or deleted the span meanwhile (#460): the view shows it as it
      // is now, so the selection editing the outdated copy is closed.
      outdated = [409, 404].includes(errorStatus(err) ?? 0)
      throw err
    } finally {
      if (isCurrent()) {
        saving.value = false
        if (outdated) clearSelection()
      }
    }
    if (isCurrent()) clearSelection()
    return true
  }

  /** Create a span with the given tag over the current selection. Returns whether one was created. */
  const createSpan = async (tagId: string): Promise<boolean> => {
    if (!selection.value) return false

    const normalized = normalizeSelectionToStartChunk(selection.value)
    if (!normalized) return false

    return applyToSelection(() => store.createSpan({
      chunkId: normalized.chunkId,
      tagId,
      start: normalized.start,
      end: normalized.end,
      type: SpanType.pos
    }))
  }

  /**
   * Retag the span being edited. Returns whether it was retagged. A failed retag restores the
   * selection's previous tag, unless the user has moved on to another selection meanwhile.
   */
  const updateSpanTag = async (tagId: string): Promise<boolean> => {
    const sel = selection.value
    if (!sel?.editingSpanId || saving.value) return false

    // A boundary drag may have moved the selection's anchor off the chunk that holds the span.
    const spanId = sel.editingSpanId
    const ownerChunkId = sel.spanChunkId ?? sel.chunkId

    // Update visual highlight immediately
    const isCurrent = selectionGuard.capture()
    selection.value = { ...sel, tagId }

    try {
      return await applyToSelection(() => store.updateSpan(spanId, ownerChunkId, { tagId }))
    } catch (err) {
      if (isCurrent() && selection.value?.tagId === tagId) {
        selection.value = { ...selection.value, tagId: sel.tagId }
      }
      throw err
    }
  }

  const updateSpanPosition = async () => {
    if (!selection.value?.editingSpanId || saving.value) return

    const normalized = normalizeSelectionToStartChunk(selection.value)
    if (!normalized?.editingSpanId) return

    // Keep UI state consistent with the normalized anchor used for persistence.
    selection.value = normalized

    const spanId = normalized.editingSpanId
    const ownerChunkId = normalized.spanChunkId ?? normalized.chunkId

    // A start dragged into another chunk moves the span there in the same write (#436): it
    // keeps its id, provenance and AI metadata.
    await applyToSelection(() => store.updateSpan(spanId, ownerChunkId, {
      start: normalized.start,
      end: normalized.end,
      ...(ownerChunkId !== normalized.chunkId ? { chunkId: normalized.chunkId } : {})
    }))
  }

  const deleteSpan = async () => {
    if (!selection.value?.editingSpanId) return

    const spanId = selection.value.editingSpanId
    const ownerChunkId = selection.value.spanChunkId ?? selection.value.chunkId
    await applyToSelection(() => store.deleteSpan(spanId, ownerChunkId))
  }

  // ── Helpers ──

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
    saving,
    isEditing,
    hasSelection,
    positionChanged,
    spansByChunkId,
    spansVersion,

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
    getAllProjectedSpans,

    // CRUD
    applyToSelection,
    createSpan,
    updateSpanTag,
    updateSpanPosition,
    deleteSpan
  }
}
