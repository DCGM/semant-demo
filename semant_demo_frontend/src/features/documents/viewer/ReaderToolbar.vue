<template>
  <div class="paper-toolbar-row">
    <div class="paper-view-toolbar">
      <q-btn
        flat dense round
        icon="view_sidebar"
        size="sm"
        class="view-btn"
        :class="{ 'view-btn--active': chunkGutterVisible }"
        title="Show/hide chunk gutter"
        @click="emit('update:chunkGutterVisible', !chunkGutterVisible)"
        >
        <q-tooltip v-if="chunkGutterVisible">Hide chunk gutter</q-tooltip>
        <q-tooltip v-else>Show chunk gutter</q-tooltip>
      </q-btn>
    </div>
    <div class="paper-view-toolbar">
      <WhitespaceToggle
        :model-value="preserveWhitespace"
        @update:model-value="emit('update:preserveWhitespace', $event)"
      />
    </div>
    <div class="paper-view-toolbar">
    <q-btn
      flat dense no-caps
      icon="playlist_add_check"
      label="Collection only"
      size="sm"
      :class="{ 'view-btn--active': collectionOnly }"
      class="view-btn"
      title="Show only chunks already in this collection"
      @click="emit('showCollectionOnly')"
    >
      <q-tooltip>
        Show only chunks in the collection (hide preview chunks)
      </q-tooltip>
    </q-btn>
    <q-btn
      flat dense no-caps
      icon="visibility"
      label="All chunks"
      size="sm"
      :loading="loadingAll"
      :class="{ 'view-btn--active': allChunks }"
      class="view-btn"
      title="Load and show the entire document"
      @click="emit('showAllChunks')"
    >
      <q-tooltip>
        Load and show all chunks in the document (including previews)
      </q-tooltip>
    </q-btn>
    </div>
    <!-- The tag focused in the tags panel (#479): new selections are tagged with it. -->
    <div v-if="focusedTag" class="paper-view-toolbar focus-tag-box" role="status">
      <q-icon :name="focusedTag.pictogram || 'label'" :style="{ color: focusedTag.color || '#64748b' }" size="18px" />
      <span class="focus-tag-text">Tagging with: <strong>{{ focusedTag.name }}</strong></span>
      <q-btn
        flat dense round
        icon="close"
        size="xs"
        class="view-btn"
        aria-label="Stop tagging with this tag"
        @click="emit('clearFocusedTag')"
      >
        <q-tooltip>Stop tagging with this tag (Esc)</q-tooltip>
      </q-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Tag } from 'src/generated/api'
import WhitespaceToggle from './WhitespaceToggle.vue'

// View options of the document reader: chunk gutter, whitespace and which chunks to show,
// and the tag new selections are tagged with, if one is focused.
defineProps<{
  chunkGutterVisible: boolean
  preserveWhitespace: boolean
  /** Only the collection's chunks are shown. */
  collectionOnly: boolean
  /** The whole document is shown. */
  allChunks: boolean
  loadingAll: boolean
  focusedTag: Tag | null
}>()

const emit = defineEmits<{
  'update:chunkGutterVisible': [value: boolean]
  'update:preserveWhitespace': [value: boolean]
  showCollectionOnly: []
  showAllChunks: []
  clearFocusedTag: []
}>()
</script>

<style scoped>
/* A flat group in the view's controls row (WorkspaceControls), not a floating card (#600). */
.paper-toolbar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.paper-view-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
}

/* A thin separator between the groups. */
.paper-view-toolbar + .paper-view-toolbar {
  margin-left: 4px;
  padding-left: 6px;
  border-left: 1px solid #e2e8f0;
}

.view-btn {
  color: #64748b;
  font-size: 0.78rem;
  border-radius: 6px;
}

.focus-tag-box {
  gap: 6px;
  max-width: 360px;
  min-width: 0;
}

.focus-tag-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.82rem;
  color: #334155;
}

.view-btn--active {
  color: #1d4ed8;
  background: #eff6ff;
}
</style>
