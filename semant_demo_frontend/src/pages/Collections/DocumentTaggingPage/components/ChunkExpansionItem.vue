<template>
  <q-card flat bordered class="q-mb-lg">
    <q-expansion-item
      :default-opened="inUserCollection"
      expand-separator
      switch-toggle-side
      :header-class="inUserCollection ? '' : 'bg-grey-2 text-grey-8'"
      :caption="
        inUserCollection
          ? 'Chunk is in selected collection'
          : 'Chunk is not in selected collection'
      "
    >
      <template #header>
        <q-item-section avatar>
          <q-icon
            :name="inUserCollection ? 'task_alt' : 'remove_circle_outline'"
            :color="inUserCollection ? 'positive' : 'grey-7'"
          />
        </q-item-section>

        <q-item-section>
          <q-item-label class="text-weight-medium">
            Chunk {{ chunkIdShort }}
          </q-item-label>
          <q-item-label caption lines="2">
            {{ chunkPreview }}
          </q-item-label>
        </q-item-section>

        <q-item-section side>
          <q-btn
            dense
            flat
            round
            :icon="inUserCollection ? 'remove_circle' : 'add_circle'"
            :color="inUserCollection ? 'negative' : 'positive'"
            :loading="isCollectionUpdating"
            :disable="isCollectionUpdating || isProcessing"
            @click.stop="onToggleCollection"
          >
            <q-tooltip>
              {{
                inUserCollection
                  ? 'Remove chunk from collection'
                  : 'Add chunk to collection'
              }}
            </q-tooltip>
          </q-btn>
        </q-item-section>
      </template>

      <q-card-section>
        <ChunkTagAnnotator
          :chunk-id="chunkId"
          :chunk-text="chunkText"
          :tag-spans="tagSpans"
          :available-tags="availableTags"
          :is-processing="isProcessing"
          :snap-to-words="snapToWords"
          :selection="selection"
          :show-selection-start-handle="showSelectionStartHandle"
          :show-selection-end-handle="showSelectionEndHandle"
          :selection-start-boundary="selectionStartBoundary"
          :selection-end-boundary="selectionEndBoundary"
          :editing-span-id="editingSpanId"
          @selection-change="onSelectionChange"
        />
      </q-card-section>
    </q-expansion-item>
  </q-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { TagSpan } from 'src/generated/api/models/TagSpan'
import ChunkTagAnnotator, { AvailableTag } from './ChunkTagAnnotator.vue'

interface SelectionBoundary {
  chunkId: string
  index: number
}

interface SelectionState {
  start: number
  end: number
  editingId?: string
  tagId?: string
  spanType?: TagSpan['type']
}

interface SelectionPayload {
  chunkId: string
  selection: SelectionState | null
  startBoundary?: SelectionBoundary
  endBoundary?: SelectionBoundary
  source?: 'mouse' | 'drag'
  dragHandle?: 'start' | 'end'
}

interface Props {
  chunkId: string
  chunkText: string
  inUserCollection: boolean
  tagSpans: TagSpan[]
  availableTags: AvailableTag[]
  isProcessing: boolean
  snapToWords: boolean
  selection: SelectionState | null
  showSelectionStartHandle: boolean
  showSelectionEndHandle: boolean
  selectionStartBoundary: SelectionBoundary | null
  selectionEndBoundary: SelectionBoundary | null
  editingSpanId: string | null
  isCollectionUpdating: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  selectionChange: [payload: SelectionPayload]
  toggleCollection: [chunkId: string, inUserCollection: boolean]
}>()

const chunkPreview = computed(() => {
  const text = props.chunkText.replace(/\s+/g, ' ').trim()
  if (text.length <= 120) return text
  return `${text.slice(0, 117)}...`
})

const chunkIdShort = computed(() => props.chunkId.slice(0, 8))

const onSelectionChange = (payload: SelectionPayload) => {
  emit('selectionChange', payload)
}

const onToggleCollection = () => {
  emit('toggleCollection', props.chunkId, props.inUserCollection)
}
</script>

<style scoped>
:deep(.chunk-expansion-header) {
  user-select: none;
}
</style>
