<template>
  <div
    v-if="filters.similarTo"
    class="similar-source q-pa-xs q-mb-sm"
    role="region"
    aria-label="Find similar source"
    data-testid="similar-source"
  >
    <q-icon name="join_inner" size="sm" class="similar-source__icon" />
    <div class="similar-source__text">
      <span class="text-weight-medium">Source:</span>
      <span class="similar-source__quote" :title="filters.similarTo.text ?? undefined" data-testid="similar-source-text">{{ label }}</span>
      <span class="text-grey-8" data-testid="similar-source-status">
        {{ filters.includeSource ? '· ranked with the matches' : '· not one of the ranked matches' }}
      </span>
    </div>
    <q-btn
      flat
      dense
      no-caps
      color="primary"
      icon="visibility"
      label="Show source"
      data-testid="similar-source-show"
      @click="emit('open', filters.similarTo)"
    />
    <q-checkbox
      dense
      :model-value="filters.includeSource"
      label="Include in ranking"
      data-testid="similar-source-include"
      @update:model-value="value => emit('change', { includeSource: !!value })"
    />
    <q-btn
      v-if="hasPrevious"
      flat
      dense
      no-caps
      color="primary"
      icon="arrow_back"
      label="Back to previous view"
      data-testid="similar-source-back"
      @click="emit('back')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QBtn, QCheckbox, QIcon } from 'quasar'
import type { AnnotationListRow } from 'src/generated/api'
import type { ConcordanceFilters } from './concordanceStore'
import { sourceLabel } from './filterChips'

/** The source of Find similar, pinned above the results for the whole session (#691): it stays named
 * and reachable whether or not it is ranked, and the query before Find similar can be returned to. */
const props = defineProps<{
  filters: ConcordanceFilters
  hasPrevious: boolean
}>()

const emit = defineEmits<{
  open: [row: AnnotationListRow]
  change: [change: Partial<ConcordanceFilters>]
  back: []
}>()

const label = computed(() => props.filters.similarTo ? sourceLabel(props.filters.similarTo) : '')
</script>

<style scoped>
.similar-source {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  border: 1px solid var(--q-warning, #f2c037);
  border-left-width: 4px;
  border-radius: 4px;
  background: #fff8e1;
}
.similar-source__text { flex: 1 1 14rem; min-width: 0; overflow-wrap: anywhere; }
.similar-source__quote { margin: 0 6px; }
</style>
