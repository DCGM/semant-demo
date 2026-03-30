<template>
  <q-page class="q-pa-md">
    <div class="row justify-between items-center q-mb-md q-col-gutter-md">
      <!-- <div class="col-auto">
        <span class="text-h5">Text Tagging</span>
      </div> -->
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

    <div class="row q-col-gutter-lg">
      <div class="col-12 col-md-8">
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
            :snap-to-words="useWordSnapping"
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
      </div>

      <div class="col-12 col-md-4">
        <q-card
          class="menu-card"
          :class="globalSelection ? 'bg-blue-grey-1' : 'bg-grey-2'"
        >
          <q-card-section>
            <div class="text-h6">
              {{ globalSelection?.editingId ? 'Edit Tag' : 'Global Selection' }}
            </div>
            <div
              v-if="globalSelection"
              class="text-caption text-grey-7 q-mt-xs"
            >
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
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import ChunkTagAnnotator from './components/ChunkTagAnnotator.vue'
import { useTaggingPageState } from './composables/useTaggingPageState'

const {
  chunks,
  pageLoading,
  globalSelection,
  useWordSnapping,
  selectionBoundaryChunkIds,
  globalSelectionBoundaries,
  availableTags,
  loadChunks,
  clearSelection,
  handleTagClick,
  saveEditedTag,
  deleteEditedTag,
  handleSelectionChange,
  getChunkSelection,
  getDisplayedTagSpans
} = useTaggingPageState()

onMounted(async () => {
  await loadChunks()
})
</script>

<style scoped>
.menu-card {
  position: sticky;
  top: calc(64px + 12px);
}
</style>
