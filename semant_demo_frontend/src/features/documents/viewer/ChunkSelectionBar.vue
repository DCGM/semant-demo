<template>
  <!-- Bulk selection action bar -->
  <Teleport to="body">
    <div v-if="count > 0" class="bulk-action-bar">
      <span class="bulk-count">{{ count }} selected</span>
      <q-btn
        flat dense no-caps
        label="All visible"
        size="md"
        color="grey-4"
        title="Select all visible chunks"
        @click="emit('selectVisible')"
      />
      <q-btn
        flat dense no-caps
        label="Not in collection"
        size="md"
        color="grey-4"
        title="Select all chunks not yet in the collection"
        @click="emit('selectNotInCollection')"
      />
      <div class="bulk-spacer" />
      <q-btn
        v-if="canAdd"
        flat dense no-caps
        icon="add_circle_outline"
        label="Add"
        color="positive"
        :loading="loading"
        title="Add selected chunks to collection"
        @click="emit('add')"
      />
      <q-btn
        v-if="canRemove"
        flat dense no-caps
        icon="remove_circle_outline"
        label="Remove"
        color="negative"
        :loading="loading"
        title="Remove selected chunks from collection"
        @click="emit('remove')"
      />
      <q-btn
        flat dense round
        icon="close"
        size="md"
        color="grey-4"
        title="Clear selection"
        @click="emit('clear')"
      />
    </div>
  </Teleport>
</template>

<script setup lang="ts">
// Actions for the chunks selected in the chunk gutter, shown while any is selected.
defineProps<{
  count: number
  canAdd: boolean
  canRemove: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  selectVisible: []
  selectNotInCollection: []
  add: []
  remove: []
  clear: []
}>()
</script>

<style scoped>
.bulk-action-bar {
  position: fixed;
  bottom: 28px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  background: #1c2636;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.28);
  /* Above the drawers (3000), below the annotation popover (5000) and dialogs (6000). */
  z-index: 4000;
  white-space: nowrap;
}

.bulk-count {
  font-size: 0.92rem;
  font-weight: 600;
  padding: 0 10px;
  color: #f1f5f9;
}

.bulk-spacer {
  min-width: 12px;
  flex: 1;
}
</style>
