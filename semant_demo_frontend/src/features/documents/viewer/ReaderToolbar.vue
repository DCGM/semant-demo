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
  </div>
</template>

<script setup lang="ts">
// View options of the document reader: chunk gutter, whitespace and which chunks to show.
defineProps<{
  chunkGutterVisible: boolean
  preserveWhitespace: boolean
  /** Only the collection's chunks are shown. */
  collectionOnly: boolean
  /** The whole document is shown. */
  allChunks: boolean
  loadingAll: boolean
}>()

const emit = defineEmits<{
  'update:chunkGutterVisible': [value: boolean]
  'update:preserveWhitespace': [value: boolean]
  showCollectionOnly: []
  showAllChunks: []
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

.view-btn--active {
  color: #1d4ed8;
  background: #eff6ff;
}
</style>
