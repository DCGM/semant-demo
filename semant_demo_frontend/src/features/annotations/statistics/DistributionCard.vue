<template>
  <q-card flat bordered class="distribution" :data-testid="`statistics-${dimension}`">
    <q-card-section class="q-pb-xs">
      <h3 class="distribution__title">{{ title }}</h3>
      <p class="distribution__denominator">
        Annotations per {{ title.toLowerCase() }}; shares {{ denominator }}.
      </p>
    </q-card-section>
    <q-card-section v-if="unavailable" class="q-pt-none">
      <p class="distribution__unavailable" :data-testid="`statistics-${dimension}-unavailable`">
        Not available for this query: too many source documents to count. Narrow the query to see it.
      </p>
    </q-card-section>
    <q-card-section v-else-if="!rows.length" class="q-pt-none">
      <p class="distribution__empty">No annotations.</p>
    </q-card-section>
    <q-card-section v-else class="q-pt-none">
      <VegaChart
        :spec="spec"
        :label="`Bar chart of annotations per ${title.toLowerCase()}; the table lists the same counts.`"
        :clickable="drillable ? acceptsDatum : undefined"
        @item-click="(datum) => openRow(String(datum.key))"
      />
      <p v-if="rows.length > CHART_ROWS" class="distribution__note">
        The chart shows the first {{ CHART_ROWS }} of {{ rows.length }} rows; the table lists all of them.
      </p>
      <p v-if="truncatedBy" class="distribution__note">
        {{ formatCount(truncatedBy) }} more source documents with fewer annotations are not listed.
      </p>
      <q-expansion-item
        dense dense-toggle switch-toggle-side class="distribution__table"
        :label="`Show data table (${rows.length} ${rows.length === 1 ? 'row' : 'rows'})`"
        :data-testid="`statistics-${dimension}-table`"
      >
        <q-markup-table flat dense separator="horizontal" class="count-table">
          <caption class="sr-only">Annotations per {{ title.toLowerCase() }}, {{ denominator }}</caption>
          <thead>
            <tr>
              <th scope="col" class="text-left">{{ title }}</th>
              <th scope="col" class="text-right">Annotations</th>
              <th scope="col" class="text-right">Share</th>
              <th v-if="drillable" scope="col" class="text-right"><span class="sr-only">List</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.key" :class="`count-table__${row.kind}`">
              <th scope="row" class="text-left text-weight-regular">{{ row.label }}</th>
              <td class="text-right">{{ formatCount(row.count) }}</td>
              <td class="text-right">{{ formatShare(row.share) }}</td>
              <td v-if="drillable" class="text-right">
                <q-btn
                  v-if="row.drill" dense flat no-caps color="primary" label="Show"
                  :aria-label="`Show the ${formatCount(row.count)} annotations of ${row.label} in the annotation list`"
                  :data-testid="`statistics-${dimension}-show-${row.key}`"
                  @click="openRow(row.key)"
                />
                <span v-else class="text-grey-7" title="The annotation list has no filter for a missing value">—</span>
              </td>
            </tr>
          </tbody>
        </q-markup-table>
      </q-expansion-item>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
/**
 * One distribution of the annotation statistics (#818): bars of its first rows and a table of all
 * of them with counts and shares of the named denominator. With `drillable`, a bar or a row's Show
 * button emits `drill` with the filter change that lists exactly that row's annotations; Missing
 * rows have none.
 */
import { computed } from 'vue'
import { QBtn, QCard, QCardSection, QExpansionItem, QMarkupTable } from 'quasar'
import type { Facet } from 'src/generated/api'
import VegaChart from 'src/shared/visualization/VegaChart.vue'
import type { ConcordanceFilters } from '../concordance/concordanceStore'
import { CHART_ROWS, DIMENSION_LABELS, distributionRows, distributionSpec, formatCount, formatShare, type Dimension, type DistributionRow, type Labels } from './statistics'

const props = defineProps<{
  dimension: Dimension
  /** Null: the server could not count this dimension. */
  facet: Facet | null
  filters: ConcordanceFilters
  labels: Labels
  denominator: string
  drillable: boolean
}>()
const emit = defineEmits<{ drill: [change: Partial<ConcordanceFilters>, row: DistributionRow] }>()

const title = computed(() => DIMENSION_LABELS[props.dimension])
const unavailable = computed(() => !props.facet)
const rows = computed(() => (props.facet ? distributionRows(props.facet, props.dimension, props.labels, props.filters, props.drillable) : []))
const spec = computed(() => distributionSpec(rows.value, title.value, props.drillable))
const truncatedBy = computed(() => {
  const f = props.facet
  return f?.truncated && f.distinct != null ? f.distinct - f.values.length : 0
})

const acceptsDatum = (datum: Record<string, unknown>) => !!rows.value.find(r => r.key === datum.key)?.drill

function openRow (key: string) {
  const row = rows.value.find(r => r.key === key)
  if (row?.drill) emit('drill', row.drill, row)
}
</script>

<style scoped>
.distribution__title {
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.4;
  margin: 0;
}

.distribution__denominator,
.distribution__note,
.distribution__unavailable,
.distribution__empty {
  color: #4a5568;
  font-size: 0.85rem;
  margin: 2px 0 0;
}

.distribution__table {
  margin-top: 8px;
}

.count-table :deep(th),
.count-table :deep(td) {
  white-space: normal;
}

.count-table__missing th {
  font-style: italic;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
