<template>
  <div ref="rootEl">
    <q-card flat class="q-mb-sm relative-position" :bordered="true">
      <!-- Persistent Absolute Buttons on Top Right -->
      <div
        class="absolute-top-right row items-center q-pa-xs q-gutter-md floating-buttons"
      >
        <div
          v-if="chunkOrder !== null && chunkTotal > 0 && isExpanded"
          class="chunk-order-indicator text-caption text-grey-8"
        >
          {{ chunkOrder }} / {{ chunkTotal }}
        </div>

        <!-- Collection Button: Visible ONLY when open -->
        <q-btn
          v-if="isExpanded"
          dense
          flat
          round
          :icon="inUserCollection ? 'check' : 'add'"
          size="sm"
          :color="inUserCollection ? 'positive' : 'grey-9'"
          :loading="isCollectionUpdating"
          :disable="isCollectionUpdating || isProcessing"
          @click.stop="onToggleCollection"
        >
          <q-tooltip>
            {{
              inUserCollection
                ? 'In collection, click to remove'
                : 'Not in collection, click to add'
            }}
          </q-tooltip>
        </q-btn>

        <!-- Open/Close Toggle Button: Always visible -->
        <q-btn
          dense
          flat
          round
          color="grey-7"
          :icon="isExpanded ? 'expand_less' : 'expand_more'"
          @click.stop="isExpanded = !isExpanded"
        >
          <q-tooltip>{{ isExpanded ? 'Collapse' : 'Expand' }}</q-tooltip>
        </q-btn>
      </div>

      <q-expansion-item
        ref="expansionRef"
        v-model="isExpanded"
        hide-expand-icon
        :header-class="isExpanded ? 'chunk-header-open' : 'chunk-header-closed'"
      >
        <!-- MINIMAL CLOSED HEADER -->
        <template #header>
          <!--
            Shows ONLY the chunk ID. Left icons, captions, and
            collection status are completely removed.
          -->
          <q-item-section>
            <q-item-label
              class="text-weight-medium flex items-center q-gutter-sm"
            >
              <q-btn
                dense
                flat
                round
                @click.stop="() => {}"
                :color="inUserCollection ? 'grey-7' : 'grey-7'"
                :icon="inUserCollection ? 'check' : 'remove'"
                size="xs"
                ><q-tooltip>
                  {{ inUserCollection ? 'In collection' : 'Not in collection' }}
                </q-tooltip></q-btn
              >
              <span>{{ chunkTextShort }}</span>

              <div
                v-if="chunkOrder !== null && chunkTotal > 0 && !isExpanded"
                class="chunk-order-indicator q-ml-auto q-mr-sm text-caption text-grey-8"
              >
                {{ chunkOrder }} / {{ chunkTotal }}
              </div>
              <span class="text-weight-regular text-grey-7"
                >{{ chunkAnnotationsCount }}
                {{
                  chunkAnnotationsCount === 1 ? 'annotation' : 'annotations'
                }}</span
              >
            </q-item-label>
          </q-item-section>
        </template>

        <!-- EXPANDED CONTENT AREA -->
        <q-card-section class="q-pa-none">
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
            @selection-end="onSelectionEnd"
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
  chunkOrder: number | null
  chunkTotal: number
  chunkText: string
  inUserCollection: boolean
  isExpanded: boolean
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
const isExpanded = ref(props.isExpanded)
const isSyncingExpanded = ref(false)

const emit = defineEmits<{
  selectionChange: [payload: SelectionPayload]
  toggleCollection: [chunkId: string, inUserCollection: boolean]
  spanHoverStart: [marker: HoveredSpanMarker]
  spanHoverEnd: []
  expansionChange: [chunkId: string, expanded: boolean]
  selectionEnd: []
}>()

watch(
  () => props.isExpanded,
  (nextExpanded) => {
    isSyncingExpanded.value = true
    isExpanded.value = nextExpanded
    nextTick(() => {
      isSyncingExpanded.value = false
    })
  },
  { immediate: true }
)

watch(isExpanded, (expanded) => {
  if (isSyncingExpanded.value) return
  emit('expansionChange', props.chunkId, expanded)
})

const chunkTextShort = computed(() => {
  const maxLength = 60
  if (props.chunkText.length <= maxLength) return props.chunkText
  return props.chunkText.slice(0, maxLength) + '...'
})

const chunkAnnotationsCount = computed(() => {
  return props.tagSpans.length
})

const onSelectionChange = (payload: SelectionPayload) => {
  emit('selectionChange', payload)
}

const onSelectionEnd = () => {
  emit('selectionEnd')
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
/*
  When opened: the header totally collapses and disappears (0 height)
  leaving just the annotator component and the floating absolute buttons.
*/
:deep(.chunk-header-open) {
  min-height: 0 !important;
  height: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
  border: none !important;
  overflow: hidden !important;
  opacity: 0 !important;
  pointer-events: none;
}

/*
  When closed: Show basic header bar with sufficient right padding
  so the chunk ID doesn't overlap the absolute expand button.
*/
:deep(.chunk-header-closed) {
  min-height: 40px !important;
  padding: 8px 50px 8px 4px !important;
}

.floating-buttons {
  z-index: 100;
}

.chunk-order-indicator {
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 4px;
  padding: 1px 6px;
  line-height: 1.3;
}
</style>
