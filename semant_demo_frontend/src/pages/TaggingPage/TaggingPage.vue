<template>
  <q-page class="q-pa-md">
    <div class="row justify-between items-center q-mb-md q-col-gutter-md">
      <div class="col-auto">
        <span class="text-h5">Text Tagging</span>
      </div>
      <div class="col-auto">
        <q-btn
          icon="refresh"
          color="primary"
          outline
          label="Reload Chunks"
          :loading="pageLoading"
          @click="loadChunks"
        />
      </div>
    </div>

    <q-card
      class="q-mb-lg"
      :class="globalSelection ? 'bg-blue-grey-1' : 'bg-grey-2'"
    >
      <q-card-section>
        <div class="text-h6">
          {{ globalSelection?.editingId ? 'Edit Tag' : 'Global Selection' }}
        </div>
        <div v-if="globalSelection" class="text-caption text-grey-7 q-mt-xs">
          Chunk: {{ globalSelection.chunkId }} | Range:
          {{ globalSelection.start }}-{{ globalSelection.end }}
        </div>
        <div v-else class="text-caption text-grey-7 q-mt-xs">
          Select text in any chunk to annotate it here.
        </div>
      </q-card-section>

      <q-separator />

      <q-card-section>
        <div class="text-subtitle1 text-weight-bold q-mb-sm">
          {{ globalSelection?.editingId ? 'Tag Type' : 'Assign Tag' }}
        </div>
        <div class="row q-gutter-sm">
          <q-btn
            v-for="tag in availableTags"
            :key="tag.tagUuid"
            :label="tag.tagName"
            :icon="tag.tagPictogram"
            :disable="!globalSelection || pageLoading"
            :style="{
              backgroundColor: tag.tagColor,
              color: '#fff',
              opacity:
                globalSelection?.editingId &&
                globalSelection.tagId !== tag.tagUuid
                  ? 0.4
                  : 1
            }"
            @click="handleTagClick(tag.tagUuid)"
          >
            <q-icon
              v-if="
                globalSelection?.editingId &&
                globalSelection.tagId === tag.tagUuid
              "
              name="check"
              class="q-ml-xs"
            />
          </q-btn>
        </div>
      </q-card-section>

      <q-card-actions
        class="q-pa-md bg-grey-3 row justify-between items-center"
      >
        <q-btn
          v-if="globalSelection?.editingId"
          flat
          icon="delete"
          label="Remove Tag"
          color="negative"
          :loading="pageLoading"
          @click="deleteEditedTag"
        />
        <div v-else></div>

        <div class="row q-gutter-sm">
          <q-btn
            flat
            label="Cancel"
            color="grey-8"
            @click="clearSelection"
            :disable="!globalSelection || pageLoading"
          />
          <q-btn
            v-if="globalSelection?.editingId"
            label="Save Changes"
            color="primary"
            :loading="pageLoading"
            @click="saveEditedTag"
          />
        </div>
      </q-card-actions>
    </q-card>

    <q-card
      v-for="chunk in chunks"
      :key="chunk.id"
      flat
      bordered
      class="q-mb-lg"
    >
      <ChunkTagAnnotator
        :chunk-id="chunk.id"
        :chunk-text="chunk.text"
        :tag-spans="getDisplayedTagSpans(chunk.id)"
        :available-tags="availableTags"
        :is-processing="pageLoading"
        :selection="getChunkSelection(chunk.id)"
        :show-selection-start-handle="selectionBoundaryChunkIds.startChunkId === chunk.id"
        :show-selection-end-handle="selectionBoundaryChunkIds.endChunkId === chunk.id"
        :selection-start-boundary="globalSelectionBoundaries.startBoundary"
        :selection-end-boundary="globalSelectionBoundaries.endBoundary"
        :editing-span-id="globalSelection?.editingId || null"
        @selection-change="handleSelectionChange"
      />
    </q-card>

    <q-card v-if="!chunks.length" class="bg-grey-2">
      <q-card-section class="text-center text-grey-7 q-py-xl">
        <q-icon name="description" size="48px" class="q-mb-sm" />
        <div>No chunk is available for annotation.</div>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { TagSpan } from 'src/generated/api'
import ChunkTagAnnotator from './components/ChunkTagAnnotator.vue'
import { useTagging } from './composables/useTagging'

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

const handleSelectionChange = (payload: SelectionPayload) => {
  if (payload.startBoundary && payload.endBoundary) {
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
        globalSelectionBoundaries.value.startBoundary || payload.startBoundary
      const anchorEnd =
        globalSelectionBoundaries.value.endBoundary || payload.endBoundary

      if (payload.dragHandle === 'end') {
        if (compareBoundaries(payload.endBoundary, anchorStart) <= 0) {
          return
        }
      }

      if (payload.dragHandle === 'start') {
        if (compareBoundaries(payload.startBoundary, anchorEnd) >= 0) {
          return
        }
      }
    }

    const normalizedSelection = normalizeCrossChunkSelection(
      payload.startBoundary,
      payload.endBoundary
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

  for (let sourceIndex = 0; sourceIndex <= targetChunkIndex; sourceIndex += 1) {
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

onMounted(async () => {
  await loadChunks()
})
</script>
