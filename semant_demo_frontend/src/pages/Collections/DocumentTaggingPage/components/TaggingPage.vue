<template>
  <q-page class="">
    <div class="row q-col-gutter-lg">
      <div class="col-12 col-md-8">
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

        <q-card v-if="!chunks.length" class="bg-grey-2">
          <q-card-section class="text-center text-grey-7 q-py-xl">
            <q-icon name="description" size="48px" class="q-mb-sm" />
            <div>No chunk is available for annotation.</div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-4">
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

        <AutoAnnotationSuggestionsMenu
          :available-tags="availableTags"
          @start-suggestions="handleStartSuggestions"
        />
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { SpanType } from 'src/generated/api'
import ChunkExpansionItem from './ChunkExpansionItem.vue'
import AutoAnnotationSuggestionsMenu from './AutoAnnotationSuggestionsMenu.vue'
import TagOptionsMenu from './TagOptionsMenu.vue'
import { useTaggingPageState } from '../composables/useTaggingPageState'

interface Props {
  collectionId: string
  documentId: string
}

const props = defineProps<Props>()

const {
  chunks,
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

const isAutoSelection = computed(() => {
  return (
    !!globalSelection.value?.editingId &&
    globalSelection.value.spanType === SpanType.auto
  )
})

const handleStartSuggestions = (selectedTagIds: string[]) => {
  // Placeholder for future backend call.
  console.log('Automatic suggestions start for tags:', selectedTagIds)
}

onMounted(async () => {
  await loadChunks(props.documentId, props.collectionId)
  await getTagsForCollection(props.collectionId)
})
</script>
