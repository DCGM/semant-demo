<template>
  <q-card flat bordered class="attribute-distribution" :data-testid="`statistics-attribute-${attribute.id}`">
    <q-card-section class="attribute-distribution__head">
      <h3 class="attribute-distribution__title">{{ attribute.name }}</h3>
      <span class="attribute-distribution__values">{{ multiValued ? 'multiple values' : 'single value' }}</span>
    </q-card-section>
    <q-card-section class="q-pt-none">
      <p v-if="!distribution" class="attribute-distribution__note" data-testid="statistics-attribute-unavailable">
        Not available for this query.
      </p>
      <template v-else>
        <p class="attribute-distribution__summary" data-testid="statistics-attribute-summary">
          <strong>{{ formatCount(distribution.withValue) }}</strong> of {{ formatCount(distribution.eligible) }}
          confirmed {{ distribution.eligible === 1 ? 'annotation' : 'annotations' }} with a value ·
          <strong>{{ formatCount(distribution.assignments) }}</strong>
          {{ distribution.assignments === 1 ? 'assignment' : 'assignments' }}
        </p>
        <p v-if="distribution.eligible === 0" class="attribute-distribution__note">
          No confirmed annotation of a tag this attribute applies to matches the query.
        </p>
        <template v-else>
          <DistributionTable
            :rows="shown"
            :title="attribute.name"
            :caption="`Confirmed annotations per value of ${attribute.name}, ${denominator}`"
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
          <p class="attribute-distribution__note">
            Shares are {{ denominator }}.<template v-if="multiValued">
              A multi-valued annotation counts once under each of its values, so the values can add up to more
              than the annotations with a value.
            </template>
            <template v-if="includeRetained">
              Includes {{ formatCount(distribution.retained) }} stored
              {{ distribution.retained === 1 ? 'value' : 'values' }} on annotations whose tag the attribute no longer
              applies to: a different population from the accepted classifications.
            </template>
          </p>
        </template>
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
import { computed, ref } from 'vue'
import { QBtn, QCard, QCardSection } from 'quasar'
import { Cardinality, type Attribute } from 'src/generated/api'
import DistributionTable from './DistributionTable.vue'
import { CARD_ROWS, formatCount, type AttributeDistribution } from './statistics'
import type { ConcordanceFilters } from '../concordance/concordanceStore'

const props = defineProps<{
  attribute: Attribute
  /** Null: the server gave no accepted-value statistics for the attribute. */
  distribution: AttributeDistribution | null
  includeRetained: boolean
}>()
const emit = defineEmits<{ drill: [change: Partial<ConcordanceFilters>] }>()

const multiValued = computed(() => props.attribute.cardinality === Cardinality.multi)
const expanded = ref(false)
const valueRows = computed(() => props.distribution?.rows.filter(r => r.kind === 'value').length ?? 0)
const shown = computed(() => {
  const rows = props.distribution?.rows ?? []
  const values = rows.filter(r => r.kind === 'value')
  const missing = rows.filter(r => r.kind === 'missing')
  return [...(expanded.value ? values : values.slice(0, CARD_ROWS)), ...missing]
})
const hidden = computed(() => valueRows.value - Math.min(valueRows.value, CARD_ROWS))
const denominator = 'of the confirmed annotations the attribute applies to'
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

.attribute-distribution__values,
.attribute-distribution__note,
.attribute-distribution__summary {
  color: #4a5568;
  font-size: 0.8rem;
  margin: 0 0 6px;
}

.attribute-distribution__all {
  margin-left: -6px;
}
</style>
