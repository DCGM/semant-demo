<template>
  <q-card flat bordered class="attribute-distribution" :data-testid="`statistics-attribute-${attribute.id}`">
    <q-card-section class="attribute-distribution__head">
      <h3 class="attribute-distribution__title">{{ attribute.name }}</h3>
      <q-icon name="info_outline" size="16px" class="attribute-distribution__info" tabindex="0" aria-label="How values are counted">
        <q-tooltip max-width="320px">
          Confirmed annotations whose tag the attribute applies to; shares are of those annotations.
          <template v-if="multiValued">An annotation with several values counts under each, so values can add up to more than the annotations.</template>
        </q-tooltip>
      </q-icon>
    </q-card-section>
    <q-card-section class="q-pt-none">
      <p v-if="!distribution" class="attribute-distribution__note" data-testid="statistics-attribute-unavailable">
        Not available for this query.
      </p>
      <p v-else-if="distribution.eligible === 0" class="attribute-distribution__note">
        No confirmed annotation of a tag this attribute applies to matches the query.
      </p>
      <template v-else>
        <p class="attribute-distribution__summary" data-testid="statistics-attribute-summary">
          <strong>{{ formatCount(distribution.withValue) }}</strong> of {{ formatCount(distribution.eligible) }}
          {{ distribution.eligible === 1 ? 'annotation' : 'annotations' }} with a value<template v-if="multiValued">
            · <strong>{{ formatCount(distribution.assignments) }}</strong>
            {{ distribution.assignments === 1 ? 'assignment' : 'assignments' }}</template>
        </p>
        <DistributionTable
          :rows="shown"
          :title="attribute.name"
          :caption="`Confirmed annotations per value of ${attribute.name}`"
          :test-id="`statistics-attribute-${attribute.id}-values`"
          @drill="change => emit('drill', change)"
        />
        <q-btn
          v-if="hidden > 0 || expanded"
          flat dense no-caps color="primary" class="attribute-distribution__all"
          :icon-right="expanded ? 'expand_less' : 'chevron_right'"
          :label="expanded ? 'Fewer values' : `All ${valueRows} values`"
          :data-testid="`statistics-attribute-${attribute.id}-all`"
          @click="expanded = !expanded"
        />
        <q-checkbox
          v-if="retained > 0"
          v-model="includeRetained"
          dense size="sm" class="attribute-distribution__retained"
          :label="`Include ${retained} retained`"
          data-testid="statistics-include-retained"
        >
          <q-tooltip max-width="320px">
            Values kept on annotations whose tag the attribute no longer applies to. They are not current
            classifications, so this shows a different population; clicking a value then lists all its holders.
          </q-tooltip>
        </q-checkbox>
      </template>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
/**
 * One attribute's accepted-value distribution (#819): the confirmed annotations of the query whose
 * tag the attribute applies to, counted per value, with the annotations that have a value and the
 * assignments beside each other, and the annotations without one as a Not assigned row. The
 * retained values of annotations the attribute no longer applies to (#500) join the counts only when
 * `includeRetained` asks, and then say so; each value leads to the list of exactly the counted annotations.
 */
import { computed, ref, watch } from 'vue'
import { QBtn, QCard, QCardSection, QCheckbox, QIcon, QTooltip } from 'quasar'
import { Cardinality, type Attribute, type Facet } from 'src/generated/api'
import DistributionTable from './DistributionTable.vue'
import { CARD_ROWS, attributeDistribution, formatCount, type AttributeDistribution } from './statistics'
import type { ConcordanceFilters } from '../concordance/concordanceStore'

const props = defineProps<{
  attribute: Attribute
  /** The attribute's facet; null: the server gave no accepted-value statistics for it. */
  facet: Facet | null
  filters: ConcordanceFilters
  drillable: boolean
}>()
const emit = defineEmits<{ drill: [change: Partial<ConcordanceFilters>] }>()

const includeRetained = ref(false)
const distribution = computed<AttributeDistribution | null>(() =>
  attributeDistribution(props.facet, props.attribute, props.filters, props.drillable, includeRetained.value))
const retained = computed(() => distribution.value?.retained ?? 0)
watch(retained, (n) => { if (!n) includeRetained.value = false })
const multiValued = computed(() => props.attribute.cardinality === Cardinality.multi)
const expanded = ref(false)
const valueRows = computed(() => distribution.value?.rows.filter(r => r.kind === 'value').length ?? 0)
const shown = computed(() => {
  const rows = distribution.value?.rows ?? []
  const values = rows.filter(r => r.kind === 'value')
  const missing = rows.filter(r => r.kind === 'missing')
  return [...(expanded.value ? values : values.slice(0, CARD_ROWS)), ...missing]
})
const hidden = computed(() => valueRows.value - Math.min(valueRows.value, CARD_ROWS))
</script>

<style scoped>
.attribute-distribution__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding-bottom: 4px;
}

.attribute-distribution__title {
  font-size: 0.95rem;
  font-weight: 600;
  line-height: 1.4;
  margin: 0;
}

.attribute-distribution__note,
.attribute-distribution__summary {
  color: #4a5568;
  font-size: 0.8rem;
  margin: 0 0 6px;
}

.attribute-distribution__info {
  color: #718096;
  cursor: help;
}

.attribute-distribution__retained {
  display: flex;
  margin-top: 6px;
  font-size: 0.8rem;
}

.attribute-distribution__all {
  margin-left: -6px;
}
</style>
