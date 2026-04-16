import { computed, ref } from 'vue'
import { useTagging } from './useTagging'
import { snapToWordBoundary } from '../utils'
import { TagSpan } from 'src/generated/api/models/TagSpan'
import { SpanType } from 'src/generated/api/models/SpanType'

interface SelectionState {
  start: number
  end: number
  editingId?: string
  tagId?: string
  spanType?: TagSpan['type']
}

interface DisplayedTagSpan extends TagSpan {
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

export function useTaggingPageState() {
  const {
    documentDetail,
    availableTags,
    isProcessing,
    getDocumentDetail,
    addChunkToCollection,
    removeChunkFromCollection,
    fetchTagSpansForChunk,
    fetchTagSpansMapForChunks,
    createTagSpan,
    updateTagSpan,
    deleteTagSpan,
    getTagsForCollection
  } = useTagging()

  const tagSpansByChunkId = ref<Record<string, TagSpan[]>>({})
  const isPreloading = ref(false)
  const collectionActionChunkId = ref<string | null>(null)
  const currentDocumentId = ref<string | null>(null)
  const currentCollectionId = ref<string | null>(null)
  const globalSelection = ref<GlobalSelection | null>(null)
  const useWordSnapping = ref(true)

  const pageLoading = computed(() => isProcessing.value || isPreloading.value)

  const chunks = computed<TaggingChunk[]>(() => {
    return (
      documentDetail.value?.chunks.map((chunk) => ({
        chunkId: chunk.id,
        textChunk: chunk.text,
        inUserCollection: chunk.inUserCollection
      })) ?? []
    )
  })

  const chunkIndexById = computed(() => {
    return chunks.value.reduce<Record<string, number>>(
      (acc, chunk, index) => {
        acc[chunk.chunkId] = index
        return acc
      },
      {}
    )
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

      await getDocumentDetail(currentDocumentId.value, currentCollectionId.value)
    } finally {
      collectionActionChunkId.value = null
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
  ) => {
    if (!globalSelection.value?.editingId) return
    if (globalSelection.value.spanType !== SpanType.auto) return

    await updateTagSpan({
      spanId: globalSelection.value.editingId,
      tagSpan: {
        type: nextType
      }
    })
    await refreshChunkSpans(globalSelection.value.chunkId)
    clearSelection()
  }

  const approveSelectedAutoSpan = async () => {
    await updateSelectedAutoSpanType(SpanType.pos)
  }

  const declineSelectedAutoSpan = async () => {
    await updateSelectedAutoSpanType(SpanType.neg)
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
    availableTags,
    pageLoading,
    globalSelection,
    useWordSnapping,
    selectionBoundaryChunkIds,
    globalSelectionBoundaries,
    isChunkCollectionUpdating,
    toggleChunkInCollection,
    loadChunks,
    clearSelection,
    handleTagClick,
    saveEditedTag,
    deleteEditedTag,
    approveSelectedAutoSpan,
    declineSelectedAutoSpan,
    handleSelectionChange,
    getChunkSelection,
    getDisplayedTagSpans,
    getTagsForCollection
  }
}
