import { computed, ref } from 'vue'
import type { TagSpan } from 'src/generated/api'
import { useTagging } from './useTagging'
import { snapToWordBoundary } from '../utils'

interface SelectionState {
  start: number
  end: number
  editingId?: string
  tagId?: string
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

export function useTaggingPageState() {
  const {
    chunks,
    isProcessing,
    getFewChunks,
    fetchTagSpansForChunk,
    fetchTagSpansMapForChunks,
    createTagSpan,
    updateTagSpan,
    deleteTagSpan
  } = useTagging()

  const tagSpansByChunkId = ref<Record<string, TagSpan[]>>({})
  const isPreloading = ref(false)
  const globalSelection = ref<GlobalSelection | null>(null)
  const useWordSnapping = ref(true)

  const pageLoading = computed(() => isProcessing.value || isPreloading.value)

  const chunkIndexById = computed(() => {
    return chunks.value.reduce<Record<string, number>>((acc, chunk, index) => {
      acc[chunk.id] = index
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
      remaining > chunks.value[endChunkIndex].text.length
    ) {
      remaining -= chunks.value[endChunkIndex].text.length
      endChunkIndex += 1
    }

    if (endChunkIndex >= chunks.value.length) {
      endChunkIndex = chunks.value.length - 1
    }

    return {
      startChunkId,
      endChunkId: chunks.value[endChunkIndex]?.id || startChunkId
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
      remaining > chunks.value[endChunkIndex].text.length
    ) {
      remaining -= chunks.value[endChunkIndex].text.length
      endChunkIndex += 1
    }

    if (endChunkIndex >= chunks.value.length) {
      endChunkIndex = chunks.value.length - 1
      remaining = chunks.value[endChunkIndex].text.length
    }

    return {
      startBoundary: {
        chunkId: startChunkId,
        index: globalSelection.value.start
      },
      endBoundary: {
        chunkId: chunks.value[endChunkIndex].id,
        index: remaining
      }
    }
  })

  const availableTags = ref([
    {
      tagName: 'Reproduktory',
      tagShorthand: 'repr',
      tagColor: '#e91e63',
      tagPictogram: 'square',
      tagDefinition: 'Reproduktory je věc, která produkuje zvuk',
      tagExamples: ['repráky'],
      collectionName: 'repraky_collection',
      tagUuid: '01f490ee-5b1b-46b4-b0e9-73476fa9c123'
    },
    {
      tagName: 'Prezident',
      tagShorthand: 'p',
      tagColor: '#4caf50',
      tagPictogram: 'circle',
      tagDefinition: 'Hlava statu',
      tagExamples: ['EU Cesko'],
      collectionName: 'MojeKolekce',
      tagUuid: '025a38bf-81cf-41c3-aa10-74e24f362bb9'
    }
  ])

  const preloadAllChunkSpans = async () => {
    const missingChunkIds = chunks.value
      .map((chunk) => chunk.id)
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

  const loadChunks = async () => {
    await getFewChunks()
    tagSpansByChunkId.value = {}
    await preloadAllChunkSpans()
  }

  const handleCreateTagSpan = async (payload: CreatePayload) => {
    await createTagSpan({
      span: {
        chunkId: payload.chunkId,
        tagId: payload.tagId,
        start: payload.start,
        end: payload.end
      }
    })
    await refreshChunkSpans(payload.chunkId)
  }

  const handleUpdateTagSpan = async (payload: UpdatePayload) => {
    await updateTagSpan({
      spanId: payload.spanId,
      tagSpan: {
        tagId: payload.tagId,
        start: payload.start,
        end: payload.end
      }
    })
    await refreshChunkSpans(payload.chunkId)
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

    let end = chunks.value[firstIndex].text.length
    for (let idx = firstIndex + 1; idx < secondIndex; idx += 1) {
      end += chunks.value[idx].text.length
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
            chunks.value[chunkIndex].text
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

  const handleTagClick = async (tagId: string) => {
    if (!globalSelection.value) return

    if (globalSelection.value.editingId) {
      globalSelection.value = {
        ...globalSelection.value,
        tagId
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
    if (!globalSelection.value?.editingId || !globalSelection.value.tagId) return

    await handleUpdateTagSpan({
      chunkId: globalSelection.value.chunkId,
      spanId: globalSelection.value.editingId,
      tagId: globalSelection.value.tagId,
      start: globalSelection.value.start,
      end: globalSelection.value.end
    })
    clearSelection()
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
      offsetFromBase += chunks.value[idx].text.length
    }

    const targetChunkLength = chunks.value[targetChunkIndex].text.length
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
      tagId: globalSelection.value.tagId
    }
  }

  const getDisplayedTagSpans = (targetChunkId: string): DisplayedTagSpan[] => {
    const targetChunkIndex = chunkIndexById.value[targetChunkId]
    if (targetChunkIndex === undefined) {
      return []
    }

    const targetChunkLength = chunks.value[targetChunkIndex].text.length
    const displayed: DisplayedTagSpan[] = []

    for (
      let sourceIndex = 0;
      sourceIndex <= targetChunkIndex;
      sourceIndex += 1
    ) {
      const sourceChunk = chunks.value[sourceIndex]
      const sourceSpans = tagSpansByChunkId.value[sourceChunk.id] || []
      if (!sourceSpans.length) continue

      let offsetFromSourceToTarget = 0
      for (let idx = sourceIndex; idx < targetChunkIndex; idx += 1) {
        offsetFromSourceToTarget += chunks.value[idx].text.length
      }

      for (const span of sourceSpans) {
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
    pageLoading,
    globalSelection,
    useWordSnapping,
    selectionBoundaryChunkIds,
    globalSelectionBoundaries,
    availableTags,
    loadChunks,
    clearSelection,
    handleTagClick,
    saveEditedTag,
    deleteEditedTag,
    handleSelectionChange,
    getChunkSelection,
    getDisplayedTagSpans
  }
}
