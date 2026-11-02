<template>
  <!-- Recent searches under a search input (#558). Pointer presses keep the focus in the input
       (mousedown.prevent), so the list stays open while an entry is picked or removed. The
       buttons cancel their own mousedown too: QBtn otherwise moves the focus into itself on
       mouseup, which would blur the input and close the list. -->
  <q-card
    v-if="items.length"
    class="search-history"
    bordered
    flat
    data-testid="search-history"
    @mousedown.prevent
  >
    <div class="search-history__header text-caption text-grey-7">Recent searches</div>
    <ul :id="listId" role="listbox" aria-label="Recent searches" class="search-history__list">
      <li
        v-for="(item, index) in items"
        :id="optionId(index)"
        :key="item.key"
        role="option"
        :aria-selected="index === activeIndex"
        class="search-history__option"
        :class="{ 'search-history__option--active': index === activeIndex }"
        data-testid="search-history-entry"
        @click="emit('choose', index)"
        @mouseenter="emit('highlight', index)"
      >
        <q-icon name="history" size="18px" color="grey-7" class="search-history__icon" />
        <div class="search-history__text">
          <div class="search-history__query">{{ item.query }}</div>
          <div v-if="item.detail" class="search-history__detail text-caption text-grey-7">{{ item.detail }}</div>
        </div>
        <q-btn
          flat
          round
          dense
          size="sm"
          icon="close"
          tabindex="-1"
          :aria-label="`Remove from history: ${item.query}`"
          class="search-history__remove"
          data-testid="search-history-remove"
          @mousedown="keepFocus"
          @click.stop="emit('remove', index)"
        />
      </li>
    </ul>
    <q-separator />
    <div class="search-history__footer">
      <q-btn
        flat
        dense
        no-caps
        color="grey-8"
        icon="delete_sweep"
        label="Clear history"
        tabindex="-1"
        data-testid="search-history-clear"
        @mousedown="keepFocus"
        @click="emit('clear')"
      />
      <span class="text-caption text-grey-6 gt-xs">Shift+Delete removes the highlighted search</span>
    </div>
  </q-card>
</template>

<script setup lang="ts">
import { QBtn, QCard, QIcon, QSeparator } from 'quasar'
import type { SearchHistoryItem } from './history'

const props = defineProps<{
  items: SearchHistoryItem[]
  activeIndex: number
  /** Id of the listbox, referenced by the input's `aria-controls`. */
  listId: string
}>()

const emit = defineEmits<{
  choose: [index: number]
  remove: [index: number]
  highlight: [index: number]
  clear: []
}>()

/** Keeps the focus in the input when a button of the list is pressed. */
function keepFocus (event: Event) {
  event.preventDefault()
}

function optionId (index: number): string {
  return `${props.listId}-option-${index}`
}
</script>

<style scoped>
.search-history {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 10;
  margin-top: 4px;
  max-height: min(60vh, 520px);
  overflow-y: auto;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}

.search-history__header {
  padding: 6px 12px 2px;
}

.search-history__list {
  list-style: none;
  margin: 0;
  padding: 0 0 4px;
}

.search-history__option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 4px 6px 12px;
  cursor: pointer;
}

.search-history__option--active {
  background: rgba(25, 118, 210, 0.1);
}

.search-history__icon {
  flex: none;
}

.search-history__text {
  flex: 1 1 auto;
  min-width: 0;
}

.search-history__query,
.search-history__detail {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-history__remove {
  flex: none;
}

.search-history__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 8px;
}
</style>
