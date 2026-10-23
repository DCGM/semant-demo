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
      <q-btn
        flat dense round
        icon="format_indent_increase"
        size="sm"
        class="view-btn"
        :class="{ 'view-btn--active': preserveWhitespace }"
        :title="preserveWhitespace ? 'Switch to compact whitespace (collapse spaces & line breaks)' : 'Switch to original whitespace (preserve spaces & line breaks)'"
        @click="emit('update:preserveWhitespace', !preserveWhitespace)"
      >
        <q-tooltip v-if="preserveWhitespace">Showing original whitespace — click to collapse</q-tooltip>
        <q-tooltip v-else>Showing collapsed whitespace — click to preserve original</q-tooltip>
      </q-btn>
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
.paper-toolbar-row {
  display: flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  position: sticky;
  top: 96px;
  z-index: 200;
  margin-top: 8px;
}

.paper-view-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 6px;
  background: #ffffff;
  border-radius: 10px;
  border: 2px solid rgb(202, 202, 202);
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.14);
}

.view-btn {
  color: #64748b;
  font-size: 0.78rem;
  border-radius: 6px;
}

.focus-tag-box {
  gap: 6px;
  padding-left: 10px;
  max-width: 360px;
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
