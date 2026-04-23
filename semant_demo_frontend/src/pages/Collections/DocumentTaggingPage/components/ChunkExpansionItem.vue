<template>
  <div ref="rootEl">
    <q-card flat bordered class="q-mb-lg">
    <q-expansion-item
      ref="expansionRef"
      v-model="isExpanded"
      :default-opened="inUserCollection"
      expand-separator
      switch-toggle-side
      :header-class="[
        'chunk-expansion-header',
        inUserCollection ? '' : 'bg-grey-2 text-grey-8'
      ]"
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
          <q-item-label v-if="discoveredTopic" caption class="text-blue-8">
            Topic: {{ discoveredTopic }}
          </q-item-label>
          <!-- <q-item-label caption lines="2">
            {{ chunkPreview }}
          </q-item-label> -->
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
          :external-hovered-marker="hoveredAnnotationMarker"
          @selection-change="onSelectionChange"
          @span-hover-start="onSpanHoverStart"
          @span-hover-end="onSpanHoverEnd"
        />
      </q-card-section>
    </q-expansion-item>
    </q-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
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

interface HoveredSpanMarker {
  spanId: string | null
  tagId: string
  spanType?: TagSpan['type'] | null
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
  discoveredTopic?: string | null
  hoveredAnnotationMarker: HoveredSpanMarker | null
  isCollectionUpdating: boolean
}

const props = defineProps<Props>()

const rootEl = ref<HTMLElement | null>(null)
const expansionRef = ref()
const isExpanded = ref(props.inUserCollection)

const emit = defineEmits<{
  selectionChange: [payload: SelectionPayload]
  toggleCollection: [chunkId: string, inUserCollection: boolean]
  spanHoverStart: [marker: HoveredSpanMarker]
  spanHoverEnd: []
  expansionChange: [chunkId: string, expanded: boolean]
}>()

watch(isExpanded, (expanded) => {
  emit('expansionChange', props.chunkId, expanded)
})

const chunkIdShort = computed(() => props.chunkId.slice(0, 8))

const onSelectionChange = (payload: SelectionPayload) => {
  emit('selectionChange', payload)
}

const onToggleCollection = () => {
  emit('toggleCollection', props.chunkId, props.inUserCollection)
}

const onSpanHoverStart = (marker: HoveredSpanMarker) => {
  emit('spanHoverStart', marker)
}

const onSpanHoverEnd = () => {
  emit('spanHoverEnd')
}

const scrollToSpan = async (
  spanId: string | null | undefined,
  startIndex?: number
): Promise<boolean> => {
  if (!spanId && startIndex === undefined) return false

  isExpanded.value = true
  await nextTick()

  let target: HTMLElement | null = null

  if (spanId) {
    const escapedSpanId =
      typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
        ? CSS.escape(spanId)
        : spanId

    target = rootEl.value?.querySelector(
      `.text-segment[data-span-ids~="${escapedSpanId}"]`
    ) as HTMLElement | null
  }

  // Selected/editing span can be removed from segment tag IDs in annotator rendering.
  // Fallback to locating segment by current selection start index.
  if (!target && startIndex !== undefined) {
    const segments = Array.from(
      rootEl.value?.querySelectorAll('.text-segment') || []
    ) as HTMLElement[]

    target =
      segments.find((segment) => {
        const start = Number(segment.dataset.start)
        const end = Number(segment.dataset.end)
        if (Number.isNaN(start) || Number.isNaN(end)) return false
        return startIndex >= start && startIndex < end
      }) || null
  }

  if (!target) return false

  target.scrollIntoView({
    behavior: 'smooth',
    block: 'center',
    inline: 'nearest'
  })

  return true
}

defineExpose({
  scrollToSpan
})
</script>

<style scoped>
:deep(.chunk-expansion-header) {
  user-select: none;
}
</style>
