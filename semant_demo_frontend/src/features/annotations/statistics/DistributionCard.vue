<template>
  <q-card flat bordered class="distribution" :data-testid="`statistics-${dimension}`">
    <q-card-section class="distribution__head">
      <h3 class="distribution__title">{{ title }}</h3>
      <span v-if="facet" class="distribution__values">{{ valueCount }}</span>
    </q-card-section>
    <q-card-section class="q-pt-none">
      <p v-if="!facet" class="distribution__note" :data-testid="`statistics-${dimension}-unavailable`">
        Not available for this query: too many source documents to count. Narrow the query to see it.
      </p>
      <p v-else-if="!rows.length" class="distribution__note">No annotations.</p>
      <template v-else>
        <DistributionTable
          :rows="shown"
          :title="title"
          :caption="`Annotations per ${title.toLowerCase()}, ${denominator}`"
          :test-id="`statistics-${dimension}`"
          @drill="change => emit('drill', change)"
        />
        <q-btn
          v-if="hidden > 0"
          flat dense no-caps color="primary" icon-right="chevron_right" class="distribution__all"
          :label="`All ${rows.length} rows`"
          :data-testid="`statistics-${dimension}-all`"
          @click="emit('open')"
        />
      </template>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
/**
 * One distribution of the annotation statistics (#818) in the overview grid: its first
 * `CARD_ROWS` rows (the Missing row always shown), the rest in its detail (`open`), so every card
 * stays short whatever the number of values.
 */
import { computed } from 'vue'
import { QBtn, QCard, QCardSection } from 'quasar'
import type { Facet } from 'src/generated/api'
import type { ConcordanceFilters } from '../concordance/concordanceStore'
import DistributionTable from './DistributionTable.vue'
import { CARD_ROWS, DIMENSION_LABELS, defaultOrder, distributionRows, orderedRows, type Dimension, type Labels } from './statistics'

const props = defineProps<{
  dimension: Dimension
  /** Null: the server could not count this dimension. */
  facet: Facet | null
  filters: ConcordanceFilters
  labels: Labels
  denominator: string
  drillable: boolean
}>()
const emit = defineEmits<{ drill: [change: Partial<ConcordanceFilters>], open: [] }>()

const title = computed(() => DIMENSION_LABELS[props.dimension])
const rows = computed(() => (props.facet
  ? orderedRows(distributionRows(props.facet, props.dimension, props.labels, props.filters, props.drillable), props.dimension, defaultOrder(props.dimension))
  : []))
const shown = computed(() => {
  const values = rows.value.filter(r => r.kind === 'value')
  const missing = rows.value.filter(r => r.kind === 'missing')
  return [...values.slice(0, CARD_ROWS), ...missing]
})
const hidden = computed(() => rows.value.length - shown.value.length)
const valueCount = computed(() => {
  const f = props.facet
  const n = f?.distinct ?? f?.values.length ?? 0
  return `${n} ${n === 1 ? 'value' : 'values'}`
})
</script>

<style scoped>
.distribution__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding-bottom: 4px;
}

.distribution__title {
  font-size: 0.95rem;
  font-weight: 600;
  line-height: 1.4;
  margin: 0;
}

.distribution__values,
.distribution__note {
  color: #4a5568;
  font-size: 0.8rem;
  margin: 0;
}

.distribution__all {
  margin-top: 4px;
  margin-left: -6px;
}
</style>
