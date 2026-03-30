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
        :tag-spans="tagSpansByChunkId[chunk.id] || []"
        :available-tags="availableTags"
        :is-processing="pageLoading"
        :selection="getChunkSelection(chunk.id)"
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
  if (!globalSelection.value || globalSelection.value.chunkId !== chunkId) {
    return null
  }

  return {
    start: globalSelection.value.start,
    end: globalSelection.value.end,
    editingId: globalSelection.value.editingId,
    tagId: globalSelection.value.tagId
  }
}

onMounted(async () => {
  await loadChunks()
})
</script>
