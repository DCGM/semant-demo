<template>
  <q-page class="">
    <div class="row q-col-gutter-lg">
      <div class="col-12 col-md-8 left-pane">
        <div class="left-pane-grid">
          <div class="chunks-column">
            <ChunkExpansionItem
              v-for="chunk in chunks"
              :key="chunk.chunkId"
              :ref="(el) => setChunkItemRef(chunk.chunkId, el)"
              :chunk-id="chunk.chunkId"
              :chunk-text="chunk.textChunk"
              :in-user-collection="chunk.inUserCollection"
              :tag-spans="getVisibleTagSpans(chunk.chunkId)"
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
              :discovered-topic="discoveredTopicByChunkId[chunk.chunkId] || null"
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

          <div class="rails-column">
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

      <div class="col-12 col-md-4">
        <div class="right-pane">
          <div class="right-panel-tools">
            <div class="tools-stack">
              <q-btn
                color="secondary"
                class="full-width"
                label="Document info"
                icon="info"
                no-caps
                unelevated
                size="md"
                :outline="activeTool !== 'info'"
                @click="setActiveTool('info')"
              />

              <q-btn
                color="primary"
                class="full-width"
                label="Suggest annotations"
                icon="lightbulb"
                no-caps
                unelevated
                size="md"
                :outline="activeTool !== 'suggest'"
                @click="setActiveTool('suggest')"
              />

              <q-btn
                color="dark"
                class="full-width"
                label="Manage tags"
                icon="label"
                no-caps
                unelevated
                size="md"
                :outline="activeTool !== 'catalog'"
                @click="setActiveTool('catalog')"
              />

              <q-btn
                color="accent"
                class="full-width"
                label="Tag selection"
                icon="sell"
                no-caps
                unelevated
                size="md"
                :outline="activeTool !== 'tags'"
                :disable="!globalSelection"
                @click="setActiveTool('tags')"
              />
            </div>

            <div class="tools-menu">
              <DocumentMetadataCard
                v-if="activeTool === 'info'"
                :document="documentDetail?.document ?? null"
                @close="setActiveTool(null)"
              />

              <AutoAnnotationSuggestionsMenu
                v-else-if="activeTool === 'suggest'"
                :available-tags="availableTags"
                :is-loading="isSuggestingAnnotations"
                :collection-id="props.collectionId"
                @start-suggestions="handleStartSuggestions"
                @cancel-suggestions="setActiveTool(null)"
                @close="setActiveTool(null)"
              />

              <TagCatalogMenu
                v-else-if="activeTool === 'catalog'"
                :available-tags="availableTags"
                :collection-id="props.collectionId"
                :hidden-tag-ids="[...hiddenTagIds]"
                :tag-counts="tagCounts"
                @toggle-tag-visibility="toggleTagVisibility"
                @show-all="showAllTags"
                @hide-all="hideAllTags"
                @solo-tag="soloTag"
                @close="setActiveTool(null)"
              />

              <TagOptionsMenu
                v-else-if="activeTool === 'tags' && globalSelection"
                :global-selection="globalSelection"
                :debug="DEBUG"
                :page-loading="pageLoading"
                :is-auto-selection="isAutoSelection"
                :available-tags="availableTags"
                :probable-tags="probableTagSuggestions"
                :is-loading-probable-tags="isLoadingProbableTags"
                :collection-id="props.collectionId"
                @tag-click="handleTagClick"
                @clear-selection="clearSelection"
                @save-edited-tag="saveEditedTag"
                @delete-edited-tag="deleteEditedTag"
                @approve-auto-span="handleApproveAutoSpan"
                @decline-auto-span="handleDeclineAutoSpan"
                @close="setActiveTool(null)"
              />
            </div>
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
import DocumentMetadataCard from './DocumentMetadataCard.vue'
import TagCatalogMenu from './TagCatalogMenu.vue'
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
const isSuggestingAnnotations = ref(false)
const chunkItemRefs = ref<Record<string, ChunkExpansionItemExposed | null>>({})
const railLayoutVersion = ref(0)
const expandedChunks = ref<Record<string, boolean>>({})
const activeTool = ref<'info' | 'suggest' | 'catalog' | 'tags' | null>(null)
const hiddenTagIds = ref<Set<string>>(new Set())

const {
  DEBUG,
  documentDetail,
  chunks,
  annotationMarkers,
  hoveredAnnotationMarker,
  pageLoading,
  globalSelection,
  useWordSnapping,
  probableTagSuggestions,
  isLoadingProbableTags,
  selectionBoundaryChunkIds,
  globalSelectionBoundaries,
  isChunkCollectionUpdating,
  toggleChunkInCollection,
  availableTags,
  discoveredTopicByChunkId,
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
  return globalSelection.value?.spanType === SpanType.auto
})

const railLayoutTrigger = computed(() => {
  return [
    !!globalSelection.value,
    globalSelection.value?.editingId || '',
    isAutoSelection.value,
    activeTool.value || '',
    railLayoutVersion.value
  ].join('|')
})

const visibleAnnotationMarkers = computed(() => {
  return annotationMarkers.value.filter(
    (marker) =>
      expandedChunks.value[marker.chunkId] !== false &&
      !hiddenTagIds.value.has(marker.tagId)
  )
})

const tagCounts = computed<Record<string, number>>(() => {
  return annotationMarkers.value.reduce<Record<string, number>>((acc, marker) => {
    acc[marker.tagId] = (acc[marker.tagId] || 0) + 1
    return acc
  }, {})
})

const getVisibleTagSpans = (chunkId: string) => {
  return getDisplayedTagSpans(chunkId).filter(
    (span) => !hiddenTagIds.value.has(span.tagId)
  )
}

const toggleTagVisibility = (tagId: string) => {
  const next = new Set(hiddenTagIds.value)
  if (next.has(tagId)) {
    next.delete(tagId)
  } else {
    next.add(tagId)
  }
  hiddenTagIds.value = next
}

const showAllTags = () => {
  hiddenTagIds.value = new Set()
}

const hideAllTags = () => {
  const next = new Set<string>()
  for (const tag of availableTags.value) {
    if (tag.tagUuid) {
      next.add(tag.tagUuid)
    }
  }
  hiddenTagIds.value = next
}

const soloTag = (tagId: string) => {
  const allTagIds = availableTags.value
    .map((tag) => tag.tagUuid)
    .filter((id): id is string => !!id)

  const isSoloed =
    allTagIds.length > 0 &&
    hiddenTagIds.value.size === allTagIds.length - 1 &&
    !hiddenTagIds.value.has(tagId)

  if (isSoloed) {
    hiddenTagIds.value = new Set()
    return
  }

  hiddenTagIds.value = new Set(allTagIds.filter((id) => id !== tagId))
}

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

watch(
  () => globalSelection.value,
  (nextSelection) => {
    if (nextSelection) {
      activeTool.value = 'tags'
      return
    }

    if (activeTool.value === 'tags') {
      activeTool.value = null
    }
  }
)

const setActiveTool = (
  tool: 'info' | 'suggest' | 'catalog' | 'tags' | null
) => {
  activeTool.value = tool
}

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
  isSuggestingAnnotations.value = true
  try {
    const nextSpanId = await startAutoAnnotationSuggestions(selectedTagIds)
    activeTool.value = null
    await scrollToSpan(nextSpanId)
  } finally {
    isSuggestingAnnotations.value = false
  }
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

.left-pane-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 140px;
  gap: 16px;
  align-items: start;
}

.chunks-column {
  min-width: 0;
}

.rails-column {
  position: relative;
}

.right-pane {
  position: relative;
  min-height: 100%;
}

.right-panel-tools {
  position: sticky;
  top: 80px;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tools-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: white;
  padding: 12px;
  border-radius: 4px;
  /* box-shadow: 0 12px 24px rgba(0, 0, 0, 0.06); */
  border: 1px solid rgba(0, 0, 0, 0.12);
}

.tools-menu :deep(.right-panel-menu) {
  background: #f5f5f5;
  border-radius: 16px;
  box-shadow: 0 14px 24px rgba(0, 0, 0, 0.08);
}

.tools-menu :deep(.right-panel-menu-section) {
  background: white;
  border-radius: 12px;
  padding: 12px;
}

@media (max-width: 1023px) {
  .left-pane-grid {
    grid-template-columns: 1fr;
  }

  .rails-column {
    order: 2;
  }

  .right-panel-tools {
    position: static;
  }
}
</style>
