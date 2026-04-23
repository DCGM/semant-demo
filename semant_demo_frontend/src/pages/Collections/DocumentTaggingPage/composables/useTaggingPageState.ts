import { computed, ref } from 'vue'
import { useTagging } from './useTagging'
import { snapToWordBoundary } from '../utils'
import { TagSpan } from 'src/generated/api/models/TagSpan'
import { SpanType } from 'src/generated/api/models/SpanType'

type TagSpanWithConfidence = TagSpan & {
  confidence?: number
}

interface SelectionState {
  start: number
  end: number
  editingId?: string
  tagId?: string
  spanType?: TagSpan['type']
  confidence?: number
}

interface DisplayedTagSpan extends TagSpanWithConfidence {
  sourceStart?: number
  sourceEnd?: number
}

interface SelectionBoundary {
  chunkId: string
  index: number
}

interface GlobalSelection extends SelectionState {
  chunkId: string
}

interface CreatePayload {
  chunkId: string
  tagId: string
  start: number
  end: number
}

interface UpdatePayload {
  chunkId: string
  spanId: string
  tagId: string
  start: number
  end: number
  spanType?: TagSpan['type']
}

interface DeletePayload {
  chunkId: string
  spanId: string
}

interface SelectionPayload {
  chunkId: string
  selection: SelectionState | null
  startBoundary?: SelectionBoundary
  endBoundary?: SelectionBoundary
  source?: 'mouse' | 'drag'
  dragHandle?: 'start' | 'end'
}

interface TaggingChunk {
  chunkId: string
  textChunk: string
  inUserCollection: boolean
}

interface AnnotationMarker {
  markerId: string
  spanId: string | null
  chunkId: string
  start: number
  end: number
  spanType?: TagSpan['type']
  tagId: string
}

interface HoveredSpanMarker {
  spanId: string | null
  tagId: string
  spanType?: TagSpan['type'] | null
}

interface AutoSpanCandidate {
  chunkId: string
  span: TagSpanWithConfidence
}

const normalizeChunkId = (chunkId: string | null | undefined): string => {
  return (chunkId || '').trim().toLowerCase()
}

export function useTaggingPageState() {
  const {
    documentDetail,
    availableTags,
    collectionTags,
    discoveredTopics,
    discoveredTopicChunkIds,
    isProcessing,
    getDocumentDetail,
    addChunkToCollection,
    removeChunkFromCollection,
    fetchTagSpansForChunk,
    fetchTagSpansMapForChunks,
    createTagSpan,
    updateTagSpan,
    approveTagSpan,
    declineTagSpan,
    deleteTagSpan,
    suggestAnnotations,
    discoverTopics,
    getTagsForCollection
  } = useTagging()

  const tagSpansByChunkId = ref<Record<string, TagSpanWithConfidence[]>>({})
  const pendingAutoSuggestions = ref<AutoSpanCandidate[]>([])
  const reviewedAutoSuggestionChunkIds = ref<string[]>([])
  const isPreloading = ref(false)
  const collectionActionChunkId = ref<string | null>(null)
  const isBulkCollectionUpdating = ref(false)
  const currentDocumentId = ref<string | null>(null)
  const currentCollectionId = ref<string | null>(null)
  const globalSelection = ref<GlobalSelection | null>(null)
  const hoveredAnnotationMarker = ref<HoveredSpanMarker | null>(null)
  const useWordSnapping = ref(true)

  const pageLoading = computed(
    () =>
      isProcessing.value || isPreloading.value || isBulkCollectionUpdating.value
  )

  const chunks = computed<TaggingChunk[]>(() => {
    return (
      documentDetail.value?.chunks.map((chunk) => ({
        chunkId: chunk.id,
        textChunk: chunk.text,
        inUserCollection: chunk.inUserCollection
      })) ?? []
    )
  })

  const discoveredTopicByChunkId = computed<Record<string, string>>(() => {
    const topics = discoveredTopics.value?.topics || []
    const topicDocuments = discoveredTopics.value?.topicDocuments || []
    const chunkIds = discoveredTopicChunkIds.value

    if (!topics.length || !topicDocuments.length || !chunkIds.length) {
      return {}
    }

    const topicByChunkId: Record<string, string> = {}

    for (let chunkIndex = 0; chunkIndex < chunkIds.length; chunkIndex += 1) {
      let bestTopicName: string | null = null
      let bestScore = Number.NEGATIVE_INFINITY

      for (let topicIndex = 0; topicIndex < topics.length; topicIndex += 1) {
        const score = topicDocuments[topicIndex]?.[chunkIndex]
        if (score === undefined) continue

        if (score > bestScore) {
          bestScore = score
          bestTopicName = topics[topicIndex].name
        }
      }

      if (bestTopicName) {
        topicByChunkId[chunkIds[chunkIndex]] = bestTopicName
      }
    }

    return topicByChunkId
  })

  const annotationMarkers = computed<AnnotationMarker[]>(() => {
    return Object.entries(tagSpansByChunkId.value).flatMap(([chunkId, spans]) =>
      spans
        .filter((span) => span.type !== SpanType.neg)
        .map((span) => ({
          markerId:
            span.id ?? `${chunkId}-${span.tagId}-${span.start}-${span.end}`,
          spanId: span.id ?? null,
          chunkId,
          start: span.start,
          end: span.end,
          spanType: span.type,
          tagId: span.tagId
        }))
    )
  })

  const chunkIndexById = computed(() => {
    return chunks.value.reduce<Record<string, number>>((acc, chunk, index) => {
      acc[chunk.chunkId] = index
      return acc
    }, {})
  })

  const selectionBoundaryChunkIds = computed(() => {
    if (!globalSelection.value) {
      return {
        startChunkId: null as string | null,
        endChunkId: null as string | null
      }
    }

    const startChunkId = globalSelection.value.chunkId
    const startChunkIndex = chunkIndexById.value[startChunkId]
    if (startChunkIndex === undefined) {
      return {
        startChunkId: null,
        endChunkId: null
      }
    }

    let remaining = globalSelection.value.end
    let endChunkIndex = startChunkIndex
    while (
      endChunkIndex < chunks.value.length &&
      remaining > chunks.value[endChunkIndex].textChunk.length
    ) {
      remaining -= chunks.value[endChunkIndex].textChunk.length
      endChunkIndex += 1
    }

    if (endChunkIndex >= chunks.value.length) {
      endChunkIndex = chunks.value.length - 1
    }

    return {
      startChunkId,
      endChunkId: chunks.value[endChunkIndex]?.chunkId || startChunkId
    }
  })

  const globalSelectionBoundaries = computed(() => {
    if (!globalSelection.value) {
      return {
        startBoundary: null as SelectionBoundary | null,
        endBoundary: null as SelectionBoundary | null
      }
    }

    const startChunkId = globalSelection.value.chunkId
    const startChunkIndex = chunkIndexById.value[startChunkId]

    if (startChunkIndex === undefined) {
      return {
        startBoundary: null,
        endBoundary: null
      }
    }

    let remaining = globalSelection.value.end
    let endChunkIndex = startChunkIndex
    while (
      endChunkIndex < chunks.value.length &&
      remaining > chunks.value[endChunkIndex].textChunk.length
    ) {
      remaining -= chunks.value[endChunkIndex].textChunk.length
      endChunkIndex += 1
    }

    if (endChunkIndex >= chunks.value.length) {
      endChunkIndex = chunks.value.length - 1
      remaining = chunks.value[endChunkIndex].textChunk.length
    }

    return {
      startBoundary: {
        chunkId: startChunkId,
        index: globalSelection.value.start
      },
      endBoundary: {
        chunkId: chunks.value[endChunkIndex].chunkId,
        index: remaining
      }
    }
  })

  const preloadAllChunkSpans = async () => {
    const missingChunkIds = chunks.value
      .map((chunk) => chunk.chunkId)
      .filter((chunkId) => !tagSpansByChunkId.value[chunkId])

    if (!missingChunkIds.length) return

    isPreloading.value = true
    try {
      const loadedMap = await fetchTagSpansMapForChunks(missingChunkIds)
      tagSpansByChunkId.value = {
        ...tagSpansByChunkId.value,
        ...loadedMap
      }
    } finally {
      isPreloading.value = false
    }
  }

  const refreshChunkSpans = async (chunkId: string) => {
    const refreshedSpans = await fetchTagSpansForChunk(chunkId)
    tagSpansByChunkId.value = {
      ...tagSpansByChunkId.value,
      [chunkId]: refreshedSpans
    }
  }

  const applyAutoDecisionLocally = ({
    chunkId,
    processedSpan,
    nextType
  }: {
    chunkId: string
    processedSpan: TagSpanWithConfidence
    nextType: typeof SpanType.pos | typeof SpanType.neg
  }) => {
    const chunkSpans = tagSpansByChunkId.value[chunkId] || []

    const nextChunkSpans = chunkSpans.map((span) => {
      const matchesById = !!processedSpan.id && span.id === processedSpan.id
      const matchesByCoordinates =
        span.chunkId === processedSpan.chunkId &&
        span.tagId === processedSpan.tagId &&
        span.start === processedSpan.start &&
        span.end === processedSpan.end

      if (!matchesById && !matchesByCoordinates) {
        return span
      }

      return {
        ...span,
        type: nextType
      }
    })

    tagSpansByChunkId.value = {
      ...tagSpansByChunkId.value,
      [chunkId]: nextChunkSpans
    }
  }

  const refreshSelectedChunkSpans = async (chunkIds: string[]) => {
    const uniqueChunkIds = [...new Set(chunkIds)].filter(Boolean)
    if (!uniqueChunkIds.length) return {}

    const loadedMap = await fetchTagSpansMapForChunks(uniqueChunkIds)
    tagSpansByChunkId.value = {
      ...tagSpansByChunkId.value,
      ...loadedMap
    }

    return loadedMap
  }

  const getSortedAutoSpanCandidates = (): AutoSpanCandidate[] => {
    const inCurrentBatch = pendingAutoSuggestions.value
      .filter(({ span }) => span.type === SpanType.auto)
      .map(({ chunkId, span }) => ({ chunkId, span }))

    const candidates =
      inCurrentBatch.length > 0
        ? inCurrentBatch
        : Object.entries(tagSpansByChunkId.value).flatMap(([chunkId, spans]) =>
          spans
            .filter((span) => span.type === SpanType.auto)
            .map((span) => ({ chunkId, span }))
        )

    candidates.sort((a, b) => {
      const aConfidence = a.span.confidence ?? Number.NEGATIVE_INFINITY
      const bConfidence = b.span.confidence ?? Number.NEGATIVE_INFINITY

      if (aConfidence !== bConfidence) {
        return bConfidence - aConfidence
      }

      const aChunkIndex =
        chunkIndexById.value[a.chunkId] ?? Number.MAX_SAFE_INTEGER
      const bChunkIndex =
        chunkIndexById.value[b.chunkId] ?? Number.MAX_SAFE_INTEGER
      if (aChunkIndex !== bChunkIndex) {
        return aChunkIndex - bChunkIndex
      }

      return a.span.start - b.span.start
    })

    return candidates
  }

  const selectHighestConfidenceAutoSpan = (): string | null => {
    const nextAutoSpan = getSortedAutoSpanCandidates()[0]

    if (!nextAutoSpan) {
      clearSelection()
      return null
    }

    globalSelection.value = {
      chunkId: nextAutoSpan.chunkId,
      start: nextAutoSpan.span.start,
      end: nextAutoSpan.span.end,
      editingId: nextAutoSpan.span.id || undefined,
      tagId: nextAutoSpan.span.tagId,
      spanType: nextAutoSpan.span.type,
      confidence: nextAutoSpan.span.confidence
    }

    return nextAutoSpan.span.id || null
  }

  const findSpanOwnerChunkId = (spanId: string): string | null => {
    for (const [chunkId, spans] of Object.entries(tagSpansByChunkId.value)) {
      if (spans.some((span) => span.id === spanId)) {
        return chunkId
      }
    }
    return null
  }

  const loadChunks = async (documentId: string, collectionId: string) => {
    currentDocumentId.value = documentId
    currentCollectionId.value = collectionId
    await getDocumentDetail(documentId, collectionId)
    tagSpansByChunkId.value = {}
    pendingAutoSuggestions.value = []
    reviewedAutoSuggestionChunkIds.value = []
    await preloadAllChunkSpans()
  }

  const isChunkCollectionUpdating = (chunkId: string) => {
    return collectionActionChunkId.value === chunkId
  }

  const toggleChunkInCollection = async (
    chunkId: string,
    inUserCollection: boolean
  ) => {
    if (!currentCollectionId.value || !currentDocumentId.value) return

    collectionActionChunkId.value = chunkId
    try {
      if (inUserCollection) {
        await removeChunkFromCollection({
          chunkId,
          collectionId: currentCollectionId.value
        })
      } else {
        await addChunkToCollection({
          chunkId,
          collectionId: currentCollectionId.value
        })
      }

      await getDocumentDetail(
        currentDocumentId.value,
        currentCollectionId.value
      )
    } finally {
      collectionActionChunkId.value = null
    }
  }

  const removeAllChunksFromCollection = async () => {
    if (!currentCollectionId.value || !currentDocumentId.value) return

    const chunkIdsToRemove =
      documentDetail.value?.chunks
        .filter((chunk) => chunk.inUserCollection)
        .map((chunk) => chunk.id) ?? []

    if (!chunkIdsToRemove.length) return

    isBulkCollectionUpdating.value = true
    try {
      for (const chunkId of chunkIdsToRemove) {
        await removeChunkFromCollection({
          chunkId,
          collectionId: currentCollectionId.value
        })
      }

      await getDocumentDetail(
        currentDocumentId.value,
        currentCollectionId.value
      )
    } finally {
      isBulkCollectionUpdating.value = false
    }
  }

  const handleCreateTagSpan = async (payload: CreatePayload) => {
    await createTagSpan({
      span: {
        chunkId: payload.chunkId,
        tagId: payload.tagId,
        start: payload.start,
        end: payload.end,
        type: SpanType.pos
      }
    })
    await refreshChunkSpans(payload.chunkId)
  }

  const handleUpdateTagSpan = async (payload: UpdatePayload) => {
    const previousOwnerChunkId = findSpanOwnerChunkId(payload.spanId)

    if (previousOwnerChunkId && previousOwnerChunkId !== payload.chunkId) {
      await deleteTagSpan(payload.spanId)
      await createTagSpan({
        span: {
          chunkId: payload.chunkId,
          tagId: payload.tagId,
          start: payload.start,
          end: payload.end,
          type: payload.spanType ?? SpanType.pos
        }
      })

      await refreshSelectedChunkSpans([previousOwnerChunkId, payload.chunkId])
      return
    }

    await updateTagSpan({
      spanId: payload.spanId,
      tagSpan: {
        tagId: payload.tagId,
        start: payload.start,
        end: payload.end
        // type: payload.spanType
      }
    })

    const refreshedMap = await refreshSelectedChunkSpans([
      payload.chunkId,
      previousOwnerChunkId || ''
    ])

    const spanStillVisibleInRefreshedChunks = Object.values(refreshedMap).some(
      (spans) => spans.some((span) => span.id === payload.spanId)
    )

    if (!spanStillVisibleInRefreshedChunks) {
      await preloadAllChunkSpans()
    }
  }

  const handleDeleteTagSpan = async (payload: DeletePayload) => {
    await deleteTagSpan(payload.spanId)
    await refreshChunkSpans(payload.chunkId)
  }

  const selectSpanFromAnnotationMarker = (marker: AnnotationMarker) => {
    let ownerChunkId = marker.chunkId
    let spanMatch: TagSpan | undefined

    if (marker.spanId) {
      for (const [chunkId, spans] of Object.entries(tagSpansByChunkId.value)) {
        const matched = spans.find((span) => span.id === marker.spanId)
        if (matched) {
          ownerChunkId = chunkId
          spanMatch = matched
          break
        }
      }
    }

    if (!spanMatch) {
      spanMatch = (tagSpansByChunkId.value[marker.chunkId] || []).find(
        (span) =>
          span.start === marker.start &&
          span.end === marker.end &&
          span.tagId === marker.tagId
      )
    }

    if (!spanMatch) return

    globalSelection.value = {
      chunkId: ownerChunkId,
      start: spanMatch.start,
      end: spanMatch.end,
      editingId: spanMatch.id as string | undefined,
      tagId: spanMatch.tagId,
      spanType: spanMatch.type,
      confidence: (spanMatch as TagSpanWithConfidence).confidence
    }
  }

  const startHoverFromAnnotationMarker = (marker: HoveredSpanMarker) => {
    hoveredAnnotationMarker.value = marker
  }

  const stopHoverFromAnnotationMarker = () => {
    hoveredAnnotationMarker.value = null
  }

  const normalizeCrossChunkSelection = (
    startBoundary: SelectionBoundary,
    endBoundary: SelectionBoundary
  ): GlobalSelection | null => {
    const startChunkIndex = chunkIndexById.value[startBoundary.chunkId]
    const endChunkIndex = chunkIndexById.value[endBoundary.chunkId]

    if (startChunkIndex === undefined || endChunkIndex === undefined) {
      return null
    }

    let first = startBoundary
    let second = endBoundary
    let firstIndex = startChunkIndex
    let secondIndex = endChunkIndex

    if (
      firstIndex > secondIndex ||
      (firstIndex === secondIndex && first.index > second.index)
    ) {
      first = endBoundary
      second = startBoundary
      firstIndex = endChunkIndex
      secondIndex = startChunkIndex
    }

    if (firstIndex === secondIndex) {
      return {
        chunkId: first.chunkId,
        start: first.index,
        end: second.index
      }
    }

    let end = chunks.value[firstIndex].textChunk.length
    for (let idx = firstIndex + 1; idx < secondIndex; idx += 1) {
      end += chunks.value[idx].textChunk.length
    }
    end += second.index

    return {
      chunkId: first.chunkId,
      start: first.index,
      end
    }
  }

  const handleSelectionChange = (payload: SelectionPayload) => {
    if (payload.startBoundary && payload.endBoundary) {
      const snapBoundaryToWord = (
        boundary: SelectionBoundary,
        type: 'start' | 'end'
      ): SelectionBoundary => {
        const chunkIndex = chunkIndexById.value[boundary.chunkId]
        if (chunkIndex === undefined) return boundary

        return {
          chunkId: boundary.chunkId,
          index: snapToWordBoundary(
            boundary.index,
            type,
            chunks.value[chunkIndex].textChunk
          )
        }
      }

      const snappedStartBoundary = useWordSnapping.value
        ? snapBoundaryToWord(payload.startBoundary, 'start')
        : payload.startBoundary
      const snappedEndBoundary = useWordSnapping.value
        ? snapBoundaryToWord(payload.endBoundary, 'end')
        : payload.endBoundary

      if (payload.source === 'drag' && payload.dragHandle) {
        const compareBoundaries = (
          left: SelectionBoundary,
          right: SelectionBoundary
        ) => {
          const leftIndex = chunkIndexById.value[left.chunkId]
          const rightIndex = chunkIndexById.value[right.chunkId]
          if (leftIndex === undefined || rightIndex === undefined) return 0
          if (leftIndex !== rightIndex) return leftIndex - rightIndex
          return left.index - right.index
        }

        const anchorStart =
          globalSelectionBoundaries.value.startBoundary || snappedStartBoundary
        const anchorEnd =
          globalSelectionBoundaries.value.endBoundary || snappedEndBoundary

        if (payload.dragHandle === 'end') {
          if (compareBoundaries(snappedEndBoundary, anchorStart) <= 0) {
            return
          }
        }

        if (payload.dragHandle === 'start') {
          if (compareBoundaries(snappedStartBoundary, anchorEnd) >= 0) {
            return
          }
        }
      }

      const normalizedSelection = normalizeCrossChunkSelection(
        snappedStartBoundary,
        snappedEndBoundary
      )

      if (
        normalizedSelection &&
        payload.source === 'drag' &&
        globalSelection.value?.editingId
      ) {
        normalizedSelection.editingId = globalSelection.value.editingId
        normalizedSelection.tagId = globalSelection.value.tagId
        normalizedSelection.spanType = globalSelection.value.spanType
      }

      globalSelection.value = normalizedSelection
      return
    }

    if (!payload.selection) {
      if (globalSelection.value?.chunkId === payload.chunkId) {
        globalSelection.value = null
      }
      return
    }

    globalSelection.value = {
      chunkId: payload.chunkId,
      ...payload.selection
    }

    if (globalSelection.value?.editingId) {
      const selectedSpan = (
        tagSpansByChunkId.value[payload.chunkId] || []
      ).find((span) => span.id === globalSelection.value?.editingId)

      globalSelection.value.confidence = selectedSpan?.confidence
    }
  }

  const clearSelection = () => {
    globalSelection.value = null
  }

  const handleTagClick = async (tagId: string | null) => {
    if (!globalSelection.value) return
    if (tagId === null) return

    if (globalSelection.value.editingId) {
      globalSelection.value = {
        ...globalSelection.value,
        tagId,
        spanType: globalSelection.value.spanType ?? SpanType.pos
      }
      return
    }

    await handleCreateTagSpan({
      chunkId: globalSelection.value.chunkId,
      tagId,
      start: globalSelection.value.start,
      end: globalSelection.value.end
    })
    clearSelection()
  }

  const saveEditedTag = async () => {
    if (!globalSelection.value?.editingId || !globalSelection.value.tagId)
      return

    await handleUpdateTagSpan({
      chunkId: globalSelection.value.chunkId,
      spanId: globalSelection.value.editingId,
      tagId: globalSelection.value.tagId,
      start: globalSelection.value.start,
      end: globalSelection.value.end,
      spanType: globalSelection.value.spanType
    })
    clearSelection()
  }

  const updateSelectedAutoSpanType = async (
    nextType: typeof SpanType.pos | typeof SpanType.neg
  ): Promise<string | null> => {
    if (!globalSelection.value) return null
    if (globalSelection.value.spanType !== SpanType.auto) return null

    const currentSelection = globalSelection.value

    const selectedChunkId = currentSelection.chunkId
    const selectedSpanId = currentSelection.editingId
    const selectedSpan = (tagSpansByChunkId.value[selectedChunkId] || []).find(
      (span) => {
        if (selectedSpanId && span.id === selectedSpanId) {
          return true
        }

        // Fallback for auto suggestions that may not carry a stable span id.
        return (
          span.type === SpanType.auto &&
          span.start === currentSelection.start &&
          span.end === currentSelection.end &&
          span.tagId === currentSelection.tagId
        )
      }
    )

    if (!selectedSpan) return null

    const response =
      nextType === SpanType.pos
        ? await approveTagSpan({
          chunkID: selectedSpan.chunkId,
          tagID: selectedSpan.tagId,
          collectionID: currentCollectionId.value || '',
          start: selectedSpan.start,
          end: selectedSpan.end
        })
        : await declineTagSpan({
          chunkID: selectedSpan.chunkId,
          tagID: selectedSpan.tagId,
          collectionID: currentCollectionId.value || '',
          start: selectedSpan.start,
          end: selectedSpan.end
        })

    if (!response) {
      return selectedSpanId ?? null
    }

    pendingAutoSuggestions.value = pendingAutoSuggestions.value.filter(
      ({ span, chunkId }) => {
        const matchesById = !!selectedSpan.id && span.id === selectedSpan.id
        const matchesByCoordinates =
          normalizeChunkId(chunkId) === normalizeChunkId(selectedChunkId) &&
          span.tagId === selectedSpan.tagId &&
          span.start === selectedSpan.start &&
          span.end === selectedSpan.end

        return !matchesById && !matchesByCoordinates
      }
    )

    console.debug(
      '[auto-suggest] remaining-after-decision=',
      pendingAutoSuggestions.value.length
    )

    applyAutoDecisionLocally({
      chunkId: selectedChunkId,
      processedSpan: selectedSpan,
      nextType
    })

    if (pendingAutoSuggestions.value.length === 0) {
      await refreshSelectedChunkSpans(reviewedAutoSuggestionChunkIds.value)
      reviewedAutoSuggestionChunkIds.value = []
    }

    return selectHighestConfidenceAutoSpan()
  }

  const approveSelectedAutoSpan = async () => {
    return await updateSelectedAutoSpanType(SpanType.pos)
  }

  const declineSelectedAutoSpan = async () => {
    return await updateSelectedAutoSpanType(SpanType.neg)
  }

  const startAutoAnnotationSuggestions = async (
    selectedTagIds: string[]
  ): Promise<string | null> => {
    if (!selectedTagIds.length) return null

    const chunksForSuggestion =
      documentDetail.value?.chunks.filter((chunk) => chunk.inUserCollection) ||
      []
    if (!chunksForSuggestion.length) return null

    const allowedChunkIds = new Set(
      chunksForSuggestion.map((chunk) => normalizeChunkId(chunk.id))
    )

    const selectedTags = collectionTags.value.filter(
      (tag) => !!tag.id && selectedTagIds.includes(tag.id)
    )
    if (!selectedTags.length) return null

    const response = await suggestAnnotations({
      chunks: chunksForSuggestion,
      tags: selectedTags.map((tag) => ({
        tagName: tag.name,
        tagShorthand: tag.shorthand,
        tagColor: tag.color,
        tagPictogram: tag.pictogram,
        tagDefinition: tag.definition,
        tagExamples: tag.examples,
        collectionName: currentCollectionId.value || '',
        tagUuid: tag.id
      }))
    })

    const suggestedSpans = response.suggestions
      .filter((span) => allowedChunkIds.has(normalizeChunkId(span.chunkId)))
      .map((span) => ({
        ...span,
        type: span.type ?? SpanType.auto
      }))

    console.debug(
      '[auto-suggest] received=',
      response.suggestions.length,
      'accepted=',
      suggestedSpans.length
    )

    if (!suggestedSpans.length) {
      pendingAutoSuggestions.value = []
      reviewedAutoSuggestionChunkIds.value = []
      return null
    }

    pendingAutoSuggestions.value = suggestedSpans.map((span) => ({
      chunkId: span.chunkId,
      span
    }))

    reviewedAutoSuggestionChunkIds.value = [
      ...new Set(suggestedSpans.map((span) => span.chunkId))
    ]

    console.debug('[auto-suggest] queued=', pendingAutoSuggestions.value.length)

    const chunkIdsToMerge = [...new Set(suggestedSpans.map((s) => s.chunkId))]
    const nextByChunk = { ...tagSpansByChunkId.value }

    for (const chunkId of chunkIdsToMerge) {
      const existing = nextByChunk[chunkId] || []
      const incoming = suggestedSpans.filter((span) => span.chunkId === chunkId)
      nextByChunk[chunkId] = [...existing, ...incoming]
    }

    tagSpansByChunkId.value = nextByChunk

    return selectHighestConfidenceAutoSpan()
  }

  const discoverTopicsForCurrentDocument = async (n = 3) => {
    const chunksForDiscovery =
      documentDetail.value?.chunks.filter((chunk) => chunk.inUserCollection) ||
      []

    return await discoverTopics({
      chunks: chunksForDiscovery,
      n
    })
  }

  const deleteEditedTag = async () => {
    if (!globalSelection.value?.editingId) return

    await handleDeleteTagSpan({
      chunkId: globalSelection.value.chunkId,
      spanId: globalSelection.value.editingId
    })
    clearSelection()
  }

  const getChunkSelection = (chunkId: string): SelectionState | null => {
    if (!globalSelection.value) {
      return null
    }

    const baseChunkIndex = chunkIndexById.value[globalSelection.value.chunkId]
    const targetChunkIndex = chunkIndexById.value[chunkId]

    if (baseChunkIndex === undefined || targetChunkIndex === undefined) {
      return null
    }

    if (targetChunkIndex < baseChunkIndex) {
      return null
    }

    let offsetFromBase = 0
    for (let idx = baseChunkIndex; idx < targetChunkIndex; idx += 1) {
      offsetFromBase += chunks.value[idx].textChunk.length
    }

    const targetChunkLength = chunks.value[targetChunkIndex].textChunk.length
    const localStart = Math.max(0, globalSelection.value.start - offsetFromBase)
    const localEnd = Math.min(
      targetChunkLength,
      globalSelection.value.end - offsetFromBase
    )

    if (localEnd <= localStart) {
      return null
    }

    return {
      start: localStart,
      end: localEnd,
      editingId: globalSelection.value.editingId,
      tagId: globalSelection.value.tagId,
      spanType: globalSelection.value.spanType
    }
  }

  const getDisplayedTagSpans = (targetChunkId: string): DisplayedTagSpan[] => {
    const targetChunkIndex = chunkIndexById.value[targetChunkId]
    if (targetChunkIndex === undefined) {
      return []
    }

    const targetChunkLength = chunks.value[targetChunkIndex].textChunk.length
    const displayed: DisplayedTagSpan[] = []

    for (
      let sourceIndex = 0;
      sourceIndex <= targetChunkIndex;
      sourceIndex += 1
    ) {
      const sourceChunk = chunks.value[sourceIndex]
      const sourceSpans = tagSpansByChunkId.value[sourceChunk.chunkId] || []
      if (!sourceSpans.length) continue

      let offsetFromSourceToTarget = 0
      for (let idx = sourceIndex; idx < targetChunkIndex; idx += 1) {
        offsetFromSourceToTarget += chunks.value[idx].textChunk.length
      }

      for (const span of sourceSpans) {
        if (span.type === SpanType.neg) continue

        if (sourceIndex === targetChunkIndex) {
          displayed.push({
            ...span,
            sourceStart: span.start,
            sourceEnd: span.end
          })
          continue
        }

        const localStart = Math.max(0, span.start - offsetFromSourceToTarget)
        const localEnd = Math.min(
          targetChunkLength,
          span.end - offsetFromSourceToTarget
        )

        if (localEnd <= localStart) continue

        displayed.push({
          ...span,
          start: localStart,
          end: localEnd,
          sourceStart: span.start,
          sourceEnd: span.end
        })
      }
    }

    return displayed
  }

  return {
    chunks,
    annotationMarkers,
    hoveredAnnotationMarker,
    availableTags,
    discoveredTopics,
    discoveredTopicByChunkId,
    pageLoading,
    globalSelection,
    useWordSnapping,
    selectionBoundaryChunkIds,
    globalSelectionBoundaries,
    isChunkCollectionUpdating,
    isBulkCollectionUpdating,
    toggleChunkInCollection,
    removeAllChunksFromCollection,
    loadChunks,
    clearSelection,
    handleTagClick,
    saveEditedTag,
    deleteEditedTag,
    approveSelectedAutoSpan,
    declineSelectedAutoSpan,
    startAutoAnnotationSuggestions,
    discoverTopicsForCurrentDocument,
    handleSelectionChange,
    selectSpanFromAnnotationMarker,
    startHoverFromAnnotationMarker,
    stopHoverFromAnnotationMarker,
    getChunkSelection,
    getDisplayedTagSpans,
    getTagsForCollection
  }
}
