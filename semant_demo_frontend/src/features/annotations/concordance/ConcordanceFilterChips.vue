<template>
  <div v-if="chips.length" class="filter-chips" role="group" aria-label="Active filters" data-testid="concordance-chips">
    <span class="filter-chips__label">Filters:</span>
    <q-chip
      v-for="chip in chips"
      :key="chip.key"
      removable
      dense
      :clickable="!!chip.opens"
      :icon="chip.opens ? 'join_inner' : undefined"
      :color="chip.opens ? 'amber-2' : 'blue-1'"
      text-color="dark"
      class="filter-chips__chip"
      :title="chip.opens ? 'Show this annotation' : undefined"
      :remove-aria-label="chip.opens ? `Stop finding annotations similar to ${chip.label}` : `Remove filter ${chip.group}: ${chip.label}`"
      :data-testid="`concordance-chip-${chip.key}`"
      @click="chip.opens && emit('open', chip.opens)"
      @remove="emit('change', chip.remove)"
    >
      <span class="filter-chips__group">{{ chip.group }}:</span>
      <span class="filter-chips__value" :title="chip.label">{{ chip.label }}</span>
    </q-chip>
    <q-btn
      flat
      dense
      no-caps
      color="primary"
      label="Reset filters"
      data-testid="concordance-chips-reset"
      @click="emit('reset')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QBtn, QChip } from 'quasar'
import type { AnnotatedDocument, AnnotationListRow, Attribute, Tag } from 'src/generated/api'
import type { ConcordanceFilters } from './concordanceStore'
import { concordanceChips } from './filterChips'

/** The concordance's active filters as removable chips, with a reset of all (#663); the source
 * of Find similar as a reference chip that opens it (#664). */
const props = defineProps<{
  filters: ConcordanceFilters
  tags: Tag[]
  documents: AnnotatedDocument[]
  attributes?: Attribute[]
}>()

const emit = defineEmits<{
  change: [change: Partial<ConcordanceFilters>]
  reset: []
  open: [row: AnnotationListRow]
}>()

const chips = computed(() => concordanceChips(props.filters, props.tags, props.documents, props.attributes ?? []))
</script>

<style scoped>
.filter-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 4px;
}

.filter-chips__label {
  font-size: 0.8rem;
  color: rgba(0, 0, 0, 0.65);
  margin-right: 2px;
}

.filter-chips__chip {
  max-width: 100%;
}

.filter-chips__group {
  margin-right: 4px;
  color: rgba(0, 0, 0, 0.65);
}

.filter-chips__value {
  max-width: 18rem;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
