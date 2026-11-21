<template>
  <section class="annotation-statistics" aria-label="Statistics" data-testid="annotation-statistics">
    <q-linear-progress v-if="loading" indeterminate color="primary" class="q-mb-sm" aria-label="Loading statistics" />

    <div v-if="error" class="annotation-statistics__state text-negative" role="alert" data-testid="statistics-error">
      {{ error }}
      <q-btn flat dense no-caps color="primary" label="Retry" @click="load" />
    </div>

    <template v-else-if="statistics">
      <p class="annotation-statistics__summary" data-testid="statistics-summary">
        <strong data-testid="statistics-total">{{ formatCount(total) }}</strong>
        {{ total === 1 ? 'annotation' : 'annotations' }}{{ topK ? ` in the top ${statistics.k} by similarity` : '' }}
        in
        <strong data-testid="statistics-documents">{{ documents == null ? '—' : formatCount(documents) }}</strong>
        {{ documents == null ? 'source documents (not available for this query)' : documents === 1 ? 'source document' : 'source documents' }}.
        <span class="text-grey-8">Shares are {{ denominator }}.</span>
      </p>
      <p v-if="topK" class="annotation-statistics__warning" data-testid="statistics-top-k">
        Only the {{ statistics.k }} most similar annotations are counted, not every match. Listing one
        category would rank again, so it is not offered; clear the similarity ranking to count every match.
      </p>

      <p v-if="total === 0" class="annotation-statistics__state text-grey-8" data-testid="statistics-empty">
        No annotations match the filters.
      </p>

      <!-- One distribution in full. -->
      <div v-else-if="dimension" class="annotation-statistics__detail" :data-testid="`statistics-detail-${dimension}`">
        <div class="annotation-statistics__detail-head">
          <q-btn
            flat dense no-caps color="primary" icon="arrow_back" label="All statistics"
            data-testid="statistics-back" @click="emit('dimension', null)"
          />
          <h3 class="annotation-statistics__detail-title">{{ DIMENSION_LABELS[dimension] }}</h3>
          <q-space />
          <q-btn-toggle
            v-model="order"
            dense no-caps unelevated toggle-color="primary" color="grey-2" text-color="dark"
            aria-label="Order"
            :options="[{ value: 'count', label: 'Most annotations' }, { value: 'value', label: dimension === 'year' ? 'By year' : 'By name' }]"
          />
        </div>
        <p v-if="!detailFacet" class="annotation-statistics__state text-grey-8" :data-testid="`statistics-${dimension}-unavailable`">
          Not available for this query: too many source documents to count. Narrow the query to see it.
        </p>
        <template v-else>
          <DistributionTable
            :rows="detailRows"
            :title="DIMENSION_LABELS[dimension]"
            :caption="`Annotations per ${DIMENSION_LABELS[dimension].toLowerCase()}, ${denominator}`"
            :test-id="`statistics-${dimension}`"
            class="annotation-statistics__detail-table"
            @drill="change => emit('drill', change)"
          />
          <p v-if="truncatedBy" class="annotation-statistics__note">
            {{ formatCount(truncatedBy) }} more source documents with fewer annotations are not listed.
          </p>
        </template>
      </div>

      <div v-else class="annotation-statistics__grid">
        <DistributionCard
          v-for="d in DIMENSIONS"
          :key="d"
          :dimension="d"
          :facet="facetOf(statistics, d)"
          :filters="filters"
          :labels="labels"
          :denominator="denominator"
          :drillable="!topK"
          @drill="change => emit('drill', change)"
          @open="emit('dimension', d)"
        />
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
/**
 * The statistics view of the annotation workspace (#818): the annotations the current filters
 * select, counted by status, tag, year, source, library and language instead of listed. The page
 * keeps the toolbar and filter chips above it, so the scope is the list's query. A category's label
 * emits `drill` with the filter change that lists exactly its annotations; `dimension` shows one
 * distribution in full (`dimension` events open and close it).
 */
import { computed, ref, toRef, watch } from 'vue'
import { QBtn, QBtnToggle, QLinearProgress, QSpace } from 'quasar'
import type { AnnotatedDocument, Tag } from 'src/generated/api'
import type { ConcordanceFilters } from '../concordance/concordanceStore'
import DistributionCard from './DistributionCard.vue'
import DistributionTable from './DistributionTable.vue'
import {
  DIMENSIONS, DIMENSION_LABELS, defaultOrder, denominatorText, distributionRows, facetOf, formatCount, isTopK, orderedRows,
  type Dimension, type RowOrder
} from './statistics'
import { useAnnotationStatistics } from './useAnnotationStatistics'

const props = defineProps<{
  filters: ConcordanceFilters
  collectionId: string
  tags: Tag[]
  documents: AnnotatedDocument[]
  /** The distribution shown in full; null for all of them. */
  dimension: Dimension | null
}>()
const emit = defineEmits<{ drill: [change: Partial<ConcordanceFilters>], dimension: [dimension: Dimension | null] }>()

const collection = computed(() => props.collectionId || null)
const { statistics, loading, error, load } = useAnnotationStatistics(collection, toRef(props, 'filters'))

const topK = computed(() => isTopK(statistics.value))
const total = computed(() => statistics.value?.facets[0]?.total ?? 0)
const documents = computed(() => facetOf(statistics.value, 'document')?.distinct ?? null)
const denominator = computed(() => (statistics.value ? denominatorText(statistics.value, total.value) : ''))
const labels = computed(() => ({ tags: props.tags, documents: props.documents }))

const order = ref<RowOrder>('count')
watch(() => props.dimension, (d) => { if (d) order.value = defaultOrder(d) }, { immediate: true })
const detailFacet = computed(() => (props.dimension ? facetOf(statistics.value, props.dimension) : null))
const detailRows = computed(() => {
  const d = props.dimension
  if (!d || !detailFacet.value) return []
  return orderedRows(distributionRows(detailFacet.value, d, labels.value, props.filters, !topK.value), d, order.value)
})
const truncatedBy = computed(() => {
  const f = detailFacet.value
  return f?.truncated && f.distinct != null ? f.distinct - f.values.length : 0
})
</script>

<style scoped>
.annotation-statistics__summary {
  margin: 4px 0 12px;
}

.annotation-statistics__warning {
  background: #fffbeb;
  border-left: 3px solid #d69e2e;
  padding: 6px 10px;
  margin: 0 0 12px;
  font-size: 0.875rem;
}

.annotation-statistics__state {
  padding: 24px 0;
}

.annotation-statistics__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
  gap: 12px;
  align-items: start;
}

.annotation-statistics__detail {
  max-width: 760px;
}

.annotation-statistics__detail-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.annotation-statistics__detail-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 0;
}

.annotation-statistics__note {
  color: #4a5568;
  font-size: 0.85rem;
  margin: 8px 0 0;
}
</style>
