<template>
  <q-page class="">
    <div class="row q-col-gutter-lg">
      <div class="col-12 col-md-8 left-pane">
        <ChunkExpansionItem
          v-for="chunk in chunks"
          :key="chunk.chunkId"
          :ref="(el) => setChunkItemRef(chunk.chunkId, el)"
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
          @expansion-change="handleChunkExpansionChange"
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
              @approve-auto-span="handleApproveAutoSpan"
              @decline-auto-span="handleDeclineAutoSpan"
            />
          </div>

          <div class="floating-suggestions-panel">
            <div class="sticky">
              <q-btn
                v-if="!showAutoSuggestionsMenu"
                color="primary"
                class="full-width"
                label="Automatically suggest annotations"
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

              <q-btn
                color="negative"
                class="full-width q-mt-sm"
                label="DEBUG: Remove all chunks from collection"
                no-caps
                outline
                :loading="isBulkCollectionUpdating"
                :disable="pageLoading"
                @click="removeAllChunksFromCollection"
              />
            </div>

            <AnnotationTagRail
              :markers="visibleAnnotationMarkers"
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
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
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

interface ChunkExpansionItemExposed {
  scrollToSpan: (
    spanId: string | null | undefined,
    startIndex?: number
  ) => Promise<boolean>
}

const props = defineProps<Props>()
const showAutoSuggestionsMenu = ref(false)
const chunkItemRefs = ref<Record<string, ChunkExpansionItemExposed | null>>({})
const railLayoutVersion = ref(0)
const expandedChunks = ref<Record<string, boolean>>({})

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
  isBulkCollectionUpdating,
  toggleChunkInCollection,
  removeAllChunksFromCollection,
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
    showAutoSuggestionsMenu.value,
    railLayoutVersion.value
  ].join('|')
})

const visibleAnnotationMarkers = computed(() => {
  return annotationMarkers.value.filter(
    (marker) => expandedChunks.value[marker.chunkId] !== false
  )
})

watch(
  chunks,
  (nextChunks) => {
    const nextExpanded: Record<string, boolean> = {}

    for (const chunk of nextChunks) {
      nextExpanded[chunk.chunkId] =
        expandedChunks.value[chunk.chunkId] ?? chunk.inUserCollection
    }

    expandedChunks.value = nextExpanded
  },
  { immediate: true }
)

const handleChunkExpansionChange = (chunkId: string, expanded: boolean) => {
  expandedChunks.value[chunkId] = expanded

  if (!expanded) {
    window.setTimeout(() => {
      railLayoutVersion.value += 1
    }, 0)
    return
  }

  railLayoutVersion.value += 1
}

const setChunkItemRef = (chunkId: string, el: unknown) => {
  chunkItemRefs.value[chunkId] =
    (el as ChunkExpansionItemExposed | null) || null
}

const scrollToSpan = async (spanId: string | null | undefined) => {
  if (!spanId && globalSelection.value?.start === undefined) return

  await nextTick()

  const selectedChunkId = globalSelection.value?.chunkId
  const selectedStartIndex = globalSelection.value?.start

  if (selectedChunkId) {
    const chunkRef = chunkItemRefs.value[selectedChunkId]
    const scrolled = await chunkRef?.scrollToSpan(spanId, selectedStartIndex)
    if (scrolled) return
  }

  // Fallback: try all chunk refs if selected chunk ref is temporarily unavailable.
  for (const chunkRef of Object.values(chunkItemRefs.value)) {
    const scrolled = await chunkRef?.scrollToSpan(spanId, selectedStartIndex)
    if (scrolled) return
  }
}

const handleStartSuggestions = async (selectedTagIds: string[]) => {
  const nextSpanId = await startAutoAnnotationSuggestions(selectedTagIds)
  showAutoSuggestionsMenu.value = false
  await scrollToSpan(nextSpanId)
}

const handleApproveAutoSpan = async () => {
  const nextSpanId = await approveSelectedAutoSpan()
  await scrollToSpan(nextSpanId)
}

const handleDeclineAutoSpan = async () => {
  const nextSpanId = await declineSelectedAutoSpan()
  await scrollToSpan(nextSpanId)
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
  /* position: sticky; */
  z-index: 29;
  top: 0;
  left: 0;
  right: 0;
  height: -webkit-fill-available;
  /* background: white; */
}

.sticky {
  position: sticky;
  top: 100px;
  z-index: 29;
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
