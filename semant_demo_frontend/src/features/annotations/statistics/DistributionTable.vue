<template>
  <table class="distribution-table" :data-testid="testId">
    <caption class="sr-only">{{ caption }}</caption>
    <thead class="sr-only">
      <tr>
        <th scope="col">{{ title }}</th>
        <td aria-hidden="true" />
        <th scope="col">Annotations</th>
        <th scope="col">Share</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in rows" :key="row.key" :class="`distribution-table__${row.kind}`">
        <th scope="row" class="distribution-table__label">
          <button
            v-if="row.drill"
            type="button"
            class="distribution-table__link"
            :title="`${row.label}: list its ${formatCount(row.count)} annotations`"
            :data-testid="`${testId}-show-${row.key}`"
            @click="emit('drill', row.drill)"
          ><span class="distribution-table__text">{{ row.label }}</span></button>
          <span
            v-else class="distribution-table__text"
            :title="row.kind === 'missing' ? 'The annotation list has no filter for a missing value' : row.label"
          >{{ row.label }}</span>
        </th>
        <td class="distribution-table__bar-cell" aria-hidden="true">
          <span class="distribution-table__bar">
            <span class="distribution-table__fill" :style="{ width: `${barWidth(row)}%` }" />
          </span>
        </td>
        <td class="distribution-table__count">{{ formatCount(row.count) }}</td>
        <td class="distribution-table__share">{{ formatShare(row.share) }}</td>
      </tr>
    </tbody>
  </table>
</template>

<script setup lang="ts">
/**
 * Rows of one distribution (#818) as a table, one line each: the label (a button listing its
 * annotations when it has a drill-down; a long one is shortened, in full in its tooltip), a bar
 * scaled to the largest row right beside it, the count and the share of the named denominator. One accessible element: the bars are decoration of the numbers beside them.
 */
import { computed } from 'vue'
import type { ConcordanceFilters } from '../concordance/concordanceStore'
import { formatCount, formatShare, type DistributionRow } from './statistics'

const props = defineProps<{
  rows: DistributionRow[]
  title: string
  caption: string
  testId: string
}>()
const emit = defineEmits<{ drill: [change: Partial<ConcordanceFilters>] }>()

const largest = computed(() => Math.max(1, ...props.rows.map(r => r.count)))
const barWidth = (row: DistributionRow) => (row.count / largest.value) * 100
</script>

<style scoped>
.distribution-table {
  border-collapse: collapse;
  width: 100%;
  font-size: 0.875rem;
}

.distribution-table td,
.distribution-table th {
  padding: 3px 0;
  vertical-align: middle;
  border-bottom: 1px solid #f1f4f8;
}

.distribution-table__label {
  font-weight: 400;
  text-align: left;
  white-space: nowrap;
  width: 1%;
  padding-right: 12px !important;
}

/* As wide as the label needs, at most this; the bar takes the rest. */
.distribution-table__text {
  display: block;
  max-width: var(--label-width, 14rem);
  overflow: hidden;
  text-overflow: ellipsis;
}

.distribution-table__bar-cell {
  width: 100%;
  min-width: 60px;
}

.distribution-table__count,
.distribution-table__share {
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  padding-left: 12px !important;
}

.distribution-table__share {
  color: #4a5568;
  min-width: 4.5em;
}

.distribution-table__link {
  background: none;
  border: 0;
  padding: 0;
  font: inherit;
  max-width: 100%;
  color: var(--q-primary);
  cursor: pointer;
  text-align: left;
}

.distribution-table__link:hover,
.distribution-table__link:focus-visible {
  text-decoration: underline;
}

.distribution-table__bar {
  display: block;
  height: 10px;
  background: #edf2f7;
  border-radius: 2px;
}

.distribution-table__fill {
  display: block;
  height: 100%;
  background: #3b6ea8;
  border-radius: 2px;
}

.distribution-table__missing .distribution-table__label {
  font-style: italic;
}

.distribution-table__missing .distribution-table__fill {
  background: #a0aec0;
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
