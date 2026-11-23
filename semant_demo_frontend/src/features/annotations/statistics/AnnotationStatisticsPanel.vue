<template>
  <section class="annotation-statistics" :class="{ 'annotation-statistics--stale': stale }" aria-label="Statistics" data-testid="annotation-statistics" :aria-busy="stale ? 'true' : 'false'">
    <div v-if="error" class="annotation-statistics__state text-negative" role="alert" data-testid="statistics-error">
      {{ error }}
      <q-btn flat dense no-caps color="primary" label="Retry" @click="emit('retry')" />
    </div>

    <template v-else-if="statistics">
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

      <!-- Columns filled top to bottom in a fixed order: each distribution as tall as its rows, never
           stretched by a neighbour, and no column of empty space beside one. -->
      <div v-else class="annotation-statistics__grid">
        <DistributionCard
          v-for="d in DIMENSIONS"
          :key="d"
          :dimension="d"
          :facet="facetOf(statistics, d)"
          :filters="filters"
          :labels="labels"
          :denominator="denominator"
          :drillable="drillable"
          @drill="change => emit('drill', change)"
          @open="emit('dimension', d)"
        />
      </div>

      <!-- Accepted attribute values (#819): their own population, so apart from the distributions above. -->
      <section v-if="!dimension && attributeCards.length" class="annotation-statistics__attributes" data-testid="statistics-attributes">
        <h3 class="annotation-statistics__detail-title">Accepted attribute values</h3>
        <p v-if="countedAttributes.length > attributeCards.length" class="annotation-statistics__note" data-testid="statistics-attributes-capped">
          Showing the first {{ attributeCards.length }} of {{ countedAttributes.length }} attributes.
        </p>
        <div class="annotation-statistics__grid">
          <AttributeDistributionCard
            v-for="c in attributeCards"
            :key="c.attribute.id"
            :attribute="c.attribute"
            :facet="c.facet"
            :filters="filters"
            :drillable="drillable"
            @drill="change => emit('drill', change)"
          />
        </div>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
/**
 * The statistics view of the annotation workspace (#818): the annotations the current filters
 * select, counted by status, tag, year, source, library and language instead of listed. The page
 * reads the statistics (`useAnnotationStatistics`) and keeps the toolbar, filter chips and the
 * summary line above this view, so the scope is the list's query. A category's label
 * emits `drill` with the filter change that lists exactly its annotations; `dimension` shows one
 * distribution in full (`dimension` events open and close it).
 */
import { computed, ref, watch } from 'vue'
import { QBtn, QBtnToggle, QSpace } from 'quasar'
import type { AnnotatedDocument, AnnotationFacets, Attribute, Tag } from 'src/generated/api'
import type { ConcordanceFilters } from '../concordance/concordanceStore'
import AttributeDistributionCard from './AttributeDistributionCard.vue'
import { MAX_FACET_ATTRIBUTES } from '../concordance/concordanceStore'
import DistributionCard from './DistributionCard.vue'
import DistributionTable from './DistributionTable.vue'
import {
  DIMENSIONS, DIMENSION_LABELS, attributeFacetName, defaultOrder, denominatorText, distributionRows, facetOf, formatCount, isTopK, orderedRows,
  type Dimension, type RowOrder
} from './statistics'

const props = defineProps<{
  filters: ConcordanceFilters
  statistics: AnnotationFacets | null
  error: string | null
  /** A newer query is being counted: the counts shown are of the previous one, dimmed until then. */
  stale?: boolean
  tags: Tag[]
  documents: AnnotatedDocument[]
  /** The collection's attributes, whose accepted values are counted (#819). */
  attributes?: Attribute[]
  /** The distribution shown in full; null for all of them. */
  dimension: Dimension | null
}>()
const emit = defineEmits<{ drill: [change: Partial<ConcordanceFilters>], dimension: [dimension: Dimension | null], retry: [] }>()

const statistics = computed(() => props.statistics)
const topK = computed(() => isTopK(props.statistics))
const total = computed(() => props.statistics?.facets[0]?.total ?? 0)
/** A category can be listed only when its count is of the current query: never for a ranked top k
 * (a narrower query would rank again), nor while a newer query is counted (the counts shown are of
 * the previous one, the filter change would be of the new one). */
const drillable = computed(() => !topK.value && !props.stale)
const denominator = computed(() => (props.statistics ? denominatorText(props.statistics, total.value) : ''))
const labels = computed(() => ({ tags: props.tags, documents: props.documents }))

const countedAttributes = computed(() => (props.attributes ?? []).filter(a => !a.retired))
/** Only the attributes the request asked for (`MAX_FACET_ATTRIBUTES`): the others are not counted, not failed. */
const attributeCards = computed(() => countedAttributes.value.slice(0, MAX_FACET_ATTRIBUTES).map(attribute => ({
  attribute,
  facet: props.statistics?.facets.find(f => f.facet === attributeFacetName(attribute.id)) ?? null
})))

const order = ref<RowOrder>('count')
watch(() => props.dimension, (d) => { if (d) order.value = defaultOrder(d) }, { immediate: true })
const detailFacet = computed(() => (props.dimension ? facetOf(props.statistics, props.dimension) : null))
const detailRows = computed(() => {
  const d = props.dimension
  if (!d || !detailFacet.value) return []
  return orderedRows(distributionRows(detailFacet.value, d, labels.value, props.filters, drillable.value), d, order.value)
})
const truncatedBy = computed(() => {
  const f = detailFacet.value
  return f?.truncated && f.distinct != null ? f.distinct - f.values.length : 0
})
</script>

<style scoped>
.annotation-statistics--stale {
  opacity: 0.5;
  transition: opacity 0.15s;
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
  columns: 3 440px;
  column-gap: 12px;
}

.annotation-statistics__grid > * {
  break-inside: avoid;
  margin-bottom: 12px;
}

.annotation-statistics__attributes {
  margin-top: 16px;
}

.annotation-statistics__detail {
  max-width: 1100px;
  --label-width: 28rem;
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
