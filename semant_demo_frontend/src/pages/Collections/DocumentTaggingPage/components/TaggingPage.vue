<template>
  <q-page class="">
    <div class="row q-col-gutter-lg">
      <div ref="contentPaneRef" class="col-12 col-md-8 left-pane">
        <ChunkExpansionItem
          v-for="chunk in chunks"
          :key="chunk.chunkId"
          :chunk-id="chunk.chunkId"
          :chunk-text="chunk.textChunk"
          :in-user-collection="chunk.inUserCollection"
          :tag-spans="getDisplayedTagSpans(chunk.chunkId)"
          :available-tags="availableTags"
          :is-processing="pageLoading"
          :snap-to-words="useWordSnapping"
          :selection="getChunkSelection(chunk.chunkId)"
          :show-selection-start-handle="
            selectionBoundaryChunkIds.startChunkId === chunk.chunkId
          "
          :show-selection-end-handle="
            selectionBoundaryChunkIds.endChunkId === chunk.chunkId
          "
          :selection-start-boundary="globalSelectionBoundaries.startBoundary"
          :selection-end-boundary="globalSelectionBoundaries.endBoundary"
          :editing-span-id="globalSelection?.editingId || null"
          :is-collection-updating="isChunkCollectionUpdating(chunk.chunkId)"
          @selection-change="handleSelectionChange"
          @toggle-collection="toggleChunkInCollection"
        />

        <div
          v-if="globalSelection && menuPosition"
          class="floating-tag-menu"
          :style="{
            top: `${menuPosition.top}px`,
            left: `${menuPosition.left}px`
          }"
        >
          <TagOptionsMenu
            :global-selection="globalSelection"
            :page-loading="pageLoading"
            :is-auto-selection="isAutoSelection"
            :available-tags="availableTags"
            @tag-click="handleTagClick"
            @clear-selection="clearSelection"
            @save-edited-tag="saveEditedTag"
            @delete-edited-tag="deleteEditedTag"
            @approve-auto-span="approveSelectedAutoSpan"
            @decline-auto-span="declineSelectedAutoSpan"
          />
        </div>

        <q-card v-if="!chunks.length" class="bg-grey-2">
          <q-card-section class="text-center text-grey-7 q-py-xl">
            <q-icon name="description" size="48px" class="q-mb-sm" />
            <div>No chunk is available for annotation.</div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-4">
        <AnnotationTagRail
          :markers="annotationMarkers"
          :available-tags="availableTags"
        />
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { SpanType } from 'src/generated/api/models/SpanType'
import ChunkExpansionItem from './ChunkExpansionItem.vue'
import AnnotationTagRail from './AnnotationTagRail.vue'
import TagOptionsMenu from './TagOptionsMenu.vue'
import { useTaggingPageState } from '../composables/useTaggingPageState'

interface Props {
  collectionId: string
  documentId: string
}

const props = defineProps<Props>()

const {
  chunks,
  annotationMarkers,
  pageLoading,
  globalSelection,
  useWordSnapping,
  selectionBoundaryChunkIds,
  globalSelectionBoundaries,
  isChunkCollectionUpdating,
  toggleChunkInCollection,
  availableTags,
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
} = useTaggingPageState()

const contentPaneRef = ref<HTMLElement | null>(null)
const menuPosition = ref<{ top: number; left: number } | null>(null)
let menuRafId: number | null = null

const isAutoSelection = computed(() => {
  return (
    !!globalSelection.value?.editingId &&
    globalSelection.value.spanType === SpanType.auto
  )
})

const scheduleMenuPositionSync = () => {
  if (menuRafId !== null) return
  menuRafId = window.requestAnimationFrame(() => {
    menuRafId = null
    syncMenuPosition()
  })
}

const syncMenuPosition = () => {
  const pane = contentPaneRef.value
  const selection = globalSelection.value
  if (!pane || !selection) {
    menuPosition.value = null
    return
  }

  const selector = `.text-segment[data-chunk-id="${selection.chunkId}"][data-start="${selection.start}"]`
  const segment = document.querySelector(selector) as HTMLElement | null
  if (!segment) {
    menuPosition.value = null
    return
  }

  const paneRect = pane.getBoundingClientRect()
  const segmentRect = segment.getBoundingClientRect()

  const menuWidth = 380
  const rawLeft = segmentRect.left - paneRect.left + segmentRect.width + 12
  const maxLeft = Math.max(0, paneRect.width - menuWidth)
  const left = Math.min(Math.max(0, rawLeft), maxLeft)
  const top = segmentRect.top - paneRect.top + segmentRect.height + 8

  menuPosition.value = { top, left }
}

watch(
  () => [globalSelection.value, chunks.value],
  async () => {
    await nextTick()
    scheduleMenuPositionSync()
  },
  { deep: true, immediate: true }
)

onMounted(async () => {
  window.addEventListener('scroll', scheduleMenuPositionSync, true)
  window.addEventListener('resize', scheduleMenuPositionSync)
  await loadChunks(props.documentId, props.collectionId)
  await getTagsForCollection(props.collectionId)
  scheduleMenuPositionSync()
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', scheduleMenuPositionSync, true)
  window.removeEventListener('resize', scheduleMenuPositionSync)
  if (menuRafId !== null) {
    window.cancelAnimationFrame(menuRafId)
    menuRafId = null
  }
})
</script>

<style scoped>
.left-pane {
  position: relative;
}

.floating-tag-menu {
  position: absolute;
  z-index: 12;
  width: min(380px, calc(100% - 8px));
}
</style>
