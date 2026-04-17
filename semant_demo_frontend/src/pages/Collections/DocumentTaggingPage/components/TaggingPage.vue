<template>
  <q-page class="">
    <div class="row q-col-gutter-lg">
      <div class="col-12 col-md-8 left-pane">
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
          :hovered-annotation-marker="hoveredAnnotationMarker"
          :is-collection-updating="isChunkCollectionUpdating(chunk.chunkId)"
          @selection-change="handleSelectionChange"
          @toggle-collection="toggleChunkInCollection"
          @span-hover-start="startHoverFromAnnotationMarker"
          @span-hover-end="stopHoverFromAnnotationMarker"
        />

        <q-card v-if="!chunks.length" class="bg-grey-2">
          <q-card-section class="text-center text-grey-7 q-py-xl">
            <q-icon name="description" size="48px" class="q-mb-sm" />
            <div>No chunk is available for annotation.</div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-4">
        <div class="right-pane">
          <div v-if="globalSelection" class="floating-tag-menu">
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

          <div class="floating-suggestions-panel">
            <q-btn
              v-if="!showAutoSuggestionsMenu"
              color="primary"
              class="full-width"
              label="Automaticky navrhnout anotace"
              no-caps
              unelevated
              @click="showAutoSuggestionsMenu = true"
            />

            <AutoAnnotationSuggestionsMenu
              v-else
              :available-tags="availableTags"
              @start-suggestions="handleStartSuggestions"
              @cancel-suggestions="showAutoSuggestionsMenu = false"
            />
          </div>

          <AnnotationTagRail
            :markers="annotationMarkers"
            :available-tags="availableTags"
            :layout-trigger="railLayoutTrigger"
            :hovered-marker="hoveredAnnotationMarker"
            @marker-click="selectSpanFromAnnotationMarker"
            @marker-hover-start="startHoverFromAnnotationMarker"
            @marker-hover-end="stopHoverFromAnnotationMarker"
          />
        </div>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { SpanType } from 'src/generated/api/models/SpanType'
import ChunkExpansionItem from './ChunkExpansionItem.vue'
import AnnotationTagRail from './AnnotationTagRail.vue'
import AutoAnnotationSuggestionsMenu from './AutoAnnotationSuggestionsMenu.vue'
import TagOptionsMenu from './TagOptionsMenu.vue'
import { useTaggingPageState } from '../composables/useTaggingPageState'

interface Props {
  collectionId: string
  documentId: string
}

const props = defineProps<Props>()
const showAutoSuggestionsMenu = ref(false)

const {
  chunks,
  annotationMarkers,
  hoveredAnnotationMarker,
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
  startAutoAnnotationSuggestions,
  handleSelectionChange,
  selectSpanFromAnnotationMarker,
  startHoverFromAnnotationMarker,
  stopHoverFromAnnotationMarker,
  getChunkSelection,
  getDisplayedTagSpans,
  getTagsForCollection
} = useTaggingPageState()

const isAutoSelection = computed(() => {
  return (
    !!globalSelection.value?.editingId &&
    globalSelection.value.spanType === SpanType.auto
  )
})

const railLayoutTrigger = computed(() => {
  return [
    !!globalSelection.value,
    globalSelection.value?.editingId || '',
    isAutoSelection.value,
    showAutoSuggestionsMenu.value
  ].join('|')
})

const handleStartSuggestions = async (selectedTagIds: string[]) => {
  await startAutoAnnotationSuggestions(selectedTagIds)
  showAutoSuggestionsMenu.value = false
}

onMounted(async () => {
  await loadChunks(props.documentId, props.collectionId)
  await getTagsForCollection(props.collectionId)
})
</script>

<style scoped>
.left-pane {
  position: relative;
}

.right-pane {
  position: relative;
  height: stretch;
}

.floating-tag-menu {
  position: absolute;
  z-index: 30;
  top: 0;
  left: 0;
  right: 0;
  height: -webkit-fill-available;
  background: white;
}

.floating-suggestions-panel {
  position: sticky;
  z-index: 29;
  top: 0;
  left: 0;
  right: 0;
  /* height: -webkit-fill-available; */
  /* background: white; */
}

.floating-suggestions-panel :deep(.suggestions-card) {
  margin-top: 0;
}

@media (max-width: 1023px) {
  .floating-tag-menu {
    position: static;
    width: 100%;
    margin-top: 12px;
  }

  .floating-suggestions-panel {
    position: static;
    padding: 0;
    margin-top: 12px;
  }
}
</style>
