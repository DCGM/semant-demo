<template>
  <!-- Two flex columns of the reader row: selection checkboxes and chunk controls. -->
  <div class="chunk-gutters">
    <div
      class="chunk-checkbox-col"
      :class="{ 'is-active': selectedIds.length > 0 }"
    >
      <div
        v-for="row in rows"
        :key="row.chunkId"
        class="chunk-checkbox-item"
        :class="{ 'is-checked': selectedIds.includes(row.chunkId), 'is-hovered': textHoveredChunkId === row.chunkId }"
        :style="{ top: row.top + 'px', height: row.height + 'px' }"
        :title="selectedIds.includes(row.chunkId) ? 'Deselect chunk' : 'Select chunk'"
        @mouseenter="emit('hover', row.chunkId, false)"
        @mouseleave="emit('hover', null, false)"
        @click.stop="emit('toggleSelect', row.chunkId)"
      >
        <q-icon
          :name="selectedIds.includes(row.chunkId) ? 'check_box' : 'check_box_outline_blank'"
          size="18px"
          :color="selectedIds.includes(row.chunkId) ? 'primary' : 'grey-5'"
        />
      </div>
    </div>

    <div class="chunk-gutter-wrapper">
      <div class="chunk-gutter">
        <div
          v-for="row in rows"
          :key="row.chunkId"
          class="chunk-gutter-item"
          :class="{ 'chunk-gutter-item--text-hover': textHoveredChunkId === row.chunkId }"
          :style="{ top: row.top + 'px', height: row.height + 'px' }"
          @mouseenter="emit('hover', row.chunkId, true)"
          @mouseleave="emit('hover', null, true)"
        >
          <div
            class="chunk-bar"
            :class="inCollection(row.chunkId) ? 'chunk-bar--in' : 'chunk-bar--out'"
          />
          <div class="chunk-btn-group">
            <template v-if="inCollection(row.chunkId)">
              <q-btn
                v-if="canEditMembership"
                flat dense round
                icon="remove_circle_outline"
                color="negative"
                size="sm"
                class="chunk-toggle-btn"
                :loading="loadingChunkId === row.chunkId"
                title="Remove from collection"
                @click.stop="emit('remove', row.chunkId)"
              />
            </template>
            <template v-else>
              <q-btn
                v-if="canEditMembership"
                flat dense round
                icon="add_circle_outline"
                color="positive"
                size="sm"
                class="chunk-toggle-btn"
                :loading="loadingChunkId === row.chunkId"
                title="Add to collection"
                @click.stop="emit('add', row.chunkId)"
              />
              <q-btn
                flat dense round
                icon="visibility_off"
                color="grey"
                size="sm"
                class="chunk-toggle-btn chunk-hide-btn"
                title="Hide chunk"
                @click.stop="emit('hide', row.chunkId)"
              />
            </template>
          </div>
          <span class="chunk-order-label">
            <span class="chunk-order-num">{{ row.order + 1 }}</span>
            <span class="chunk-order-total">/ {{ totalChunks ?? '?' }}</span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CollectionChunk } from 'src/generated/api'
import type { ChunkRow } from './useReaderGutters'

// The chunk gutter left of the reader text: a selection checkbox, the chunk's order and
// collection membership, and add/remove/hide buttons for each displayed chunk.
const props = defineProps<{
  rows: ChunkRow[]
  chunks: CollectionChunk[]
  selectedIds: string[]
  /** The chunk under the mouse in the text; its controls are shown. */
  textHoveredChunkId: string | null
  canEditMembership: boolean
  loadingChunkId: string | null
  totalChunks: number | null
}>()

const emit = defineEmits<{
  /** The mouse entered (chunk id) or left (null) a row of the checkbox (row false) or controls column. */
  hover: [chunkId: string | null, controls: boolean]
  toggleSelect: [chunkId: string]
  add: [chunkId: string]
  remove: [chunkId: string]
  hide: [chunkId: string]
}>()

const inCollection = (chunkId: string) => props.chunks.find(c => c.id === chunkId)?.inCollection ?? false
</script>

<style scoped>
.chunk-gutters {
  display: contents;
}

.chunk-checkbox-col {
  width: 22px;
  flex-shrink: 0;
  position: relative;
  background: #ffffff;
  min-height: calc(100vh - 160px);
}

.chunk-checkbox-item {
  position: absolute;
  left: 0;
  right: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 2px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s;
}

/* Show on direct hover of checkbox column, when something is selected, or when this item is checked */
.chunk-checkbox-col.is-active .chunk-checkbox-item,
.chunk-checkbox-item.is-checked,
.chunk-checkbox-item.is-hovered,
.chunk-checkbox-item:hover {
  opacity: 1;
}

.chunk-gutter-wrapper {
  width: 52px;
  flex-shrink: 0;
  position: relative;
  background: #ffffff;
  min-height: calc(100vh - 160px);
}

.chunk-gutter {
  position: relative;
  width: 100%;
  height: 100%;
}

.chunk-gutter-item {
  position: absolute;
  left: 0;
  right: 0;
  display: flex;
  align-items: flex-start;
  padding-top: 2px;
  gap: 4px;
}

.chunk-btn-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  opacity: 0;
  transition: opacity 0.15s;
  flex-shrink: 0;
  position: absolute;
  left: 5px;
  top: 30px;
  z-index: 1;
}

.chunk-gutter-item:hover .chunk-btn-group,
.chunk-gutter-item--text-hover .chunk-btn-group {
  opacity: 1;
}

.chunk-order-label {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.2;
  color: #64748b;
  white-space: nowrap;
  flex-shrink: 0;
  transition: opacity 0.15s;
  padding-top: 1px;
}

.chunk-order-num {
  font-size: 13px;
  font-weight: 600;
}

.chunk-order-total {
  font-size: 11px;
  color: #94a3b8;
}

.chunk-bar {
  width: 4px;
  border-radius: 2px;
  flex-shrink: 0;
  align-self: stretch;
  min-height: 20px;
  transition: opacity 0.15s;
}

.chunk-bar--in {
  background: #22c55e;
  opacity: 0.7;
}

.chunk-bar--out {
  background: #cbd5e1;
  opacity: 0.5;
}

.chunk-gutter-item:hover .chunk-bar {
  opacity: 1;
}

.chunk-toggle-btn {
  flex-shrink: 0;
}
</style>
