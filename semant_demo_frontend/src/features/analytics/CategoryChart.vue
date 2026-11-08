<template>
  <div class="category-chart">
    <p v-if="filterable && rows.some(isFilterableRow)" class="category-chart__hint">
      Click a bar to filter by its {{ axis.toLowerCase() }}{{ searches ? ': a new search, whose results and counts may differ' : '' }}.
    </p>
    <VegaChart
      :spec="spec"
      :label="`Bar chart of ${unit} per ${axis.toLowerCase()}; the data table lists the same counts.`"
      :clickable="filterable ? clickable : undefined"
      @item-click="(datum) => emit('applyFilter', String(datum.key))"
    />
    <q-expansion-item
      dense dense-toggle switch-toggle-side class="category-chart__table"
      :label="`Show data table (${unit} per ${axis.toLowerCase()})`"
      :data-testid="`${testId}-table`"
    >
      <q-markup-table flat dense separator="horizontal" class="count-table">
        <caption class="sr-only">{{ unitNoun(unit, 2, true) }} per {{ axis.toLowerCase() }}</caption>
        <thead>
          <tr>
            <th scope="col" class="text-left">{{ axis }}</th>
            <th scope="col" class="text-left">Stored value</th>
            <th scope="col" class="text-right">{{ unitNoun(unit, 2, true) }}</th>
            <th v-if="filterable" scope="col" class="text-right"><span class="sr-only">Filter</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.key" :class="`count-table__${row.kind}`">
            <th scope="row" class="text-left text-weight-regular">{{ row.label }}</th>
            <td class="text-left"><code v-if="row.kind === 'value'">{{ row.key }}</code><span v-else>—</span></td>
            <td class="text-right">{{ formatCount(row.count) }}</td>
            <td v-if="filterable" class="text-right">
              <q-btn
                v-if="isFilterableRow(row)" dense flat no-caps color="primary" label="Filter"
                :aria-label="`Filter by ${row.label}`" :data-testid="`${testId}-filter-${row.key}`"
                @click="emit('applyFilter', row.key)"
              />
            </td>
          </tr>
        </tbody>
      </q-markup-table>
    </q-expansion-item>
  </div>
</template>

<script setup lang="ts">
/**
 * One category dimension (library, language) as horizontal bars with its data table, collapsed
 * by default (#620). With `filterable`, clicking a value's bar or its table row's Filter button
 * emits `applyFilter` with the stored value; Other and Unknown have no filter and stay inert.
 */
import { computed } from 'vue'
import VegaChart from 'src/shared/visualization/VegaChart.vue'
import { categoryBarSpec, isFilterableRow, type CategoryRow, type RowKind } from './corpusOverview'
import { unitNoun, type CountUnit } from './timeline'

const props = withDefaults(defineProps<{
  rows: CategoryRow[]
  /** Axis title and the noun of a value, e.g. "Library". */
  axis: string
  unit?: CountUnit
  filterable?: boolean
  /** Applying a filter starts a new search (a text query's charts), said in the hint. */
  searches?: boolean
  /** Prefix of the test ids, e.g. `libraries`. */
  testId: string
}>(), { unit: 'documents', filterable: false, searches: false })
const emit = defineEmits<{ applyFilter: [value: string] }>()

const numberFormat = new Intl.NumberFormat('en')
const formatCount = (n: number) => numberFormat.format(n)

const spec = computed(() => categoryBarSpec(props.rows, props.axis, props.unit, props.filterable))
const clickable = (datum: Record<string, unknown>) => isFilterableRow({ kind: datum.kind as RowKind, count: Number(datum.count) })
</script>

<style scoped>
.category-chart__hint {
  color: #4a5568;
  font-size: 0.85rem;
  margin: 0 0 4px;
}

.category-chart__table {
  margin-top: 8px;
}

.count-table {
  max-width: 560px;
}

.count-table :deep(th),
.count-table :deep(td) {
  white-space: normal;
}

.count-table__other th,
.count-table__unknown th {
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
