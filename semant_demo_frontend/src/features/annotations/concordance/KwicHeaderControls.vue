<template>
  <span class="kwic-head">
    <button
      v-if="sortable"
      type="button"
      class="kwic-head__sort"
      :class="{ 'kwic-head__sort--active': sortState !== null }"
      :disabled="sortDisabled"
      :aria-label="sortLabel"
      :data-testid="`kwic-sort-${testid}`"
      @click="emit('sort')"
    >
      <span class="kwic-head__label">{{ label }}</span>
      <q-icon
        :name="sortState === 'descending' ? 'arrow_downward' : 'arrow_upward'"
        size="14px"
        class="kwic-head__arrow"
        aria-hidden="true"
      />
      <q-tooltip v-if="sortDisabled">Ranked results are in order of relevance</q-tooltip>
      <q-tooltip v-else-if="sortHint">{{ sortHint }}</q-tooltip>
    </button>
    <span v-else class="kwic-head__label" :title="notSortableHint">{{ label }}</span>
    <q-btn
      v-if="filterable"
      flat
      dense
      round
      size="xs"
      :icon="filterActive ? 'filter_alt' : 'filter_list'"
      :color="filterActive ? 'primary' : undefined"
      :disable="filterDisabled"
      :aria-label="filterLabel"
      class="kwic-head__filter"
      :data-testid="`kwic-filter-${testid}`"
      @click="emit('filter')"
    >
      <q-tooltip>{{ filterHint ?? filterLabel }}</q-tooltip>
    </q-btn>
  </span>
</template>

<script lang="ts">
/** The order a sortable column is in, or null when the result is sorted by another one. */
export type SortState = 'ascending' | 'descending' | null
</script>

<script setup lang="ts">
import { computed } from 'vue'
import { QBtn, QIcon, QTooltip } from 'quasar'

/** A KWIC column header (#665): its sort button, or its name when it cannot be sorted, and the
 * button that brings up its filter. */
const props = withDefaults(defineProps<{
  label: string
  sortable?: boolean
  sortState?: SortState
  sortDisabled?: boolean
  /** How the column sorts (e.g. "nearest word first"), shown on hover. */
  sortHint?: string
  notSortableHint?: string
  /** Shows the filter button (attribute columns filter in their cells, #665). */
  filterable?: boolean
  filterLabel?: string
  filterActive?: boolean
  filterDisabled?: boolean
  filterHint?: string
  testid: string
}>(), {
  sortable: false,
  sortState: null,
  sortDisabled: false,
  sortHint: undefined,
  notSortableHint: undefined,
  filterable: true,
  filterLabel: '',
  filterActive: false,
  filterDisabled: false,
  filterHint: undefined
})

const emit = defineEmits<{ sort: [], filter: [] }>()

const sortLabel = computed(() => {
  if (props.sortState === 'ascending') return `${props.label}, sorted ascending; sort descending`
  if (props.sortState === 'descending') return `${props.label}, sorted descending; sort ascending`
  return `Sort by ${props.label.toLowerCase()}`
})
</script>

<style scoped>
.kwic-head {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  max-width: 100%;
  min-width: 0;
}

.kwic-head__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kwic-head__sort {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  padding: 1px 2px;
  border: 0;
  border-radius: 3px;
  background: none;
  font: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
  color: inherit;
  cursor: pointer;
}

.kwic-head__sort:hover:not(:disabled) {
  background: rgba(0, 0, 0, 0.06);
}

.kwic-head__sort:focus-visible {
  outline: 2px solid var(--q-primary);
  outline-offset: 0;
}

.kwic-head__sort:disabled {
  cursor: default;
}

/* Only the active column shows its direction; the others show where sorting would start, faintly. */
.kwic-head__arrow {
  opacity: 0;
}

.kwic-head__sort:not(:disabled):hover .kwic-head__arrow,
.kwic-head__sort:focus-visible .kwic-head__arrow {
  opacity: 0.4;
}

.kwic-head__sort--active {
  color: var(--q-primary);
}

.kwic-head__sort--active .kwic-head__arrow,
.kwic-head__sort--active:hover .kwic-head__arrow {
  opacity: 1;
}

.kwic-head__filter {
  flex: 0 0 auto;
  opacity: 0.55;
}

.kwic-head__filter.text-primary,
.kwic-head__filter:hover,
.kwic-head__filter:focus-visible {
  opacity: 1;
}
</style>
