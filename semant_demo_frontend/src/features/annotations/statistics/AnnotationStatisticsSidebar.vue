<template>
  <section class="statistics-sidebar" :class="{ 'statistics-sidebar--stale': loading }" aria-label="Statistics" data-testid="statistics-sidebar" :aria-busy="loading ? 'true' : 'false'">
    <div v-if="error" class="statistics-sidebar__state text-negative" role="alert" data-testid="statistics-sidebar-error">
      {{ error }}
      <q-btn flat dense no-caps color="primary" label="Retry" data-testid="statistics-sidebar-retry" @click="load" />
    </div>

    <p v-else-if="!statistics" class="statistics-sidebar__state text-grey-8" data-testid="statistics-sidebar-loading">
      <q-spinner v-if="loading" color="primary" size="1.2em" aria-label="Loading statistics" /> Counting…
    </p>

    <template v-else>
      <p class="statistics-sidebar__summary" data-testid="statistics-sidebar-summary">
        <strong data-testid="statistics-sidebar-total">{{ formatCount(summary.total) }}</strong>
        {{ summary.total === 1 ? 'annotation' : 'annotations' }}{{ summary.topK ? ` in the top ${summary.k} by similarity` : '' }}
        in <strong data-testid="statistics-sidebar-documents">{{ summary.documents == null ? '—' : formatCount(summary.documents) }}</strong>
        {{ summary.documents == null ? 'source documents (not available for this query)' : summary.documents === 1 ? 'source document' : 'source documents' }}
        <span class="text-grey-8">· {{ statuses }} · shares {{ summary.denominator }}</span>
      </p>
      <p v-if="summary.topK" class="statistics-sidebar__warning" data-testid="statistics-sidebar-top-k">
        Only the {{ summary.k }} most similar annotations are counted, not every match.
      </p>

      <q-btn
        flat dense no-caps color="primary" icon="open_in_full" label="Open statistics" class="statistics-sidebar__open"
        data-testid="statistics-sidebar-open" @click="emit('open', null)"
      />

      <p v-if="summary.total === 0" class="statistics-sidebar__state text-grey-8" data-testid="statistics-sidebar-empty">
        No annotations match the filters.
      </p>
      <template v-else>
        <div v-for="block in blocks" :key="block.dimension" class="statistics-sidebar__block" :data-testid="`statistics-sidebar-${block.dimension}`">
          <h3 class="statistics-sidebar__title">{{ block.title }}</h3>
          <p v-if="!block.facet" class="statistics-sidebar__note" :data-testid="`statistics-sidebar-${block.dimension}-unavailable`">
            Not available for this query: too many source documents to count.
          </p>
          <p v-else-if="!block.rows.length" class="statistics-sidebar__note">No annotations.</p>
          <template v-else>
            <DistributionTable
              :rows="block.shown"
              :title="block.title"
              :caption="`Annotations per ${block.title.toLowerCase()}, ${summary.denominator}`"
              :test-id="`statistics-sidebar-table-${block.dimension}`"
              @drill="change => emit('drill', change)"
            />
            <q-btn
              v-if="block.hidden > 0"
              flat dense no-caps color="primary" icon-right="chevron_right" class="statistics-sidebar__all"
              :label="`All ${block.rows.length} rows`"
              :data-testid="`statistics-sidebar-${block.dimension}-all`"
              @click="emit('open', block.dimension)"
            />
          </template>
        </div>

        <!-- Accepted attribute values (#819): confirmed annotations of the tags each attribute applies to. -->
        <div v-if="attributeBlocks.length" class="statistics-sidebar__attributes" data-testid="statistics-sidebar-attributes">
          <h3 class="statistics-sidebar__group">Accepted attribute values</h3>
          <div
            v-for="block in attributeBlocks" :key="block.attribute.id"
            class="statistics-sidebar__block" :data-testid="`statistics-sidebar-attribute-${block.attribute.id}`"
          >
            <h4 class="statistics-sidebar__title">{{ block.attribute.name }}</h4>
            <p v-if="!block.distribution" class="statistics-sidebar__note" :data-testid="`statistics-sidebar-attribute-${block.attribute.id}-unavailable`">
              Not available for this query.
            </p>
            <p v-else-if="block.distribution.eligible === 0" class="statistics-sidebar__note">
              No confirmed annotation of a tag this attribute applies to.
            </p>
            <template v-else>
              <p class="statistics-sidebar__note" :data-testid="`statistics-sidebar-attribute-${block.attribute.id}-summary`">
                {{ formatCount(block.distribution.withValue) }} of {{ formatCount(block.distribution.eligible) }}
                confirmed {{ block.distribution.eligible === 1 ? 'annotation' : 'annotations' }} with a value
              </p>
              <DistributionTable
                :rows="block.shown"
                :title="block.attribute.name"
                :caption="`Confirmed annotations per value of ${block.attribute.name}`"
                :test-id="`statistics-sidebar-attribute-${block.attribute.id}-values`"
                @drill="change => emit('drill', change)"
              />
              <q-btn
                v-if="block.hidden > 0"
                flat dense no-caps color="primary" icon-right="chevron_right" class="statistics-sidebar__all"
                :label="`All ${block.values} values`"
                :data-testid="`statistics-sidebar-attribute-${block.attribute.id}-all`"
                @click="emit('openAttribute', block.attribute.id)"
              />
            </template>
          </div>
        </div>
      </template>
    </template>
  </section>
</template>

<script setup lang="ts">
/**
 * The compact statistics of the annotation workspace's sidebar (#680): the same request, counting
 * and rows as the Statistics view (#818), each distribution cut to its `SIDEBAR_ROWS` most frequent
 * values and the Missing row, and the accepted values of the collection's attributes (#819) cut the
 * same way, without the view's retained-value toggle. A value's label narrows the filter (`drill`) without leaving the list;
 * `open` shows the full view, of one distribution or of all; `openAttribute` the full view at one attribute. Read only while `active` (the panel is
 * shown and the sidebar open), again on every return and on each `refresh`.
 */
import { computed, watch } from 'vue'
import { QBtn, QSpinner } from 'quasar'
import type { AnnotatedDocument, Attribute, Tag } from 'src/generated/api'
import { MAX_FACET_ATTRIBUTES, type ConcordanceFilters } from '../concordance/concordanceStore'
import DistributionTable from './DistributionTable.vue'
import { useAnnotationStatistics } from './useAnnotationStatistics'
import {
  DIMENSIONS, DIMENSION_LABELS, STATUS_LABELS, STATUS_ORDER, attributeDistribution, attributeFacetName, countedAttributeIds,
  defaultOrder, distributionRows, facetOf, formatCount, isTopK, orderedRows, summaryOf, type Dimension, type DistributionRow
} from './statistics'

/** Rows of values a distribution shows here (its Missing row comes on top of them). */
const SIDEBAR_ROWS = 5

const props = defineProps<{
  collectionId: string
  filters: ConcordanceFilters
  /** The panel is shown: only then is anything read. */
  active: boolean
  /** Changes whenever annotations changed (review, undo, boundary edit, assignment). */
  refresh: number
  tags: Tag[]
  documents: AnnotatedDocument[]
  /** The collection's attributes, whose accepted values are counted as in the view (#819). */
  attributes: Attribute[]
}>()
const emit = defineEmits<{
  drill: [change: Partial<ConcordanceFilters>]
  open: [dimension: Dimension | null]
  /** The full view, scrolled to this attribute's card (its values are not a `dimension`). */
  openAttribute: [attributeId: string]
}>()

const { statistics, loading, error, load } = useAnnotationStatistics(
  computed(() => (props.active && props.collectionId) || null), computed(() => props.filters),
  computed(() => countedAttributeIds(props.attributes)))
watch(() => props.refresh, () => { if (props.active) void load() })

const summary = computed(() => summaryOf(statistics.value!))
const statuses = computed(() => STATUS_ORDER.filter(t => props.filters.types.includes(t)).map(t => STATUS_LABELS[t].toLowerCase()).join(', '))
// A category can be listed only when counted for the current query, never for a ranked top k.
const drillable = computed(() => !isTopK(statistics.value) && !loading.value)
const labels = computed(() => ({ tags: props.tags, documents: props.documents }))

const blocks = computed(() => DIMENSIONS.map((dimension: Dimension) => {
  const facet = facetOf(statistics.value, dimension)
  const rows = facet
    ? orderedRows(distributionRows(facet, dimension, labels.value, props.filters, drillable.value), dimension, defaultOrder(dimension))
    : []
  const shown = topRows(rows)
  return { dimension, title: DIMENSION_LABELS[dimension], facet, rows, shown, hidden: rows.length - shown.length }
}))

/** The attributes the request counted (as the view: the first `MAX_FACET_ATTRIBUTES`), each cut the same way. */
const attributeBlocks = computed(() => props.attributes.filter(a => !a.retired).slice(0, MAX_FACET_ATTRIBUTES).map(attribute => {
  const facet = statistics.value?.facets.find(f => f.facet === attributeFacetName(attribute.id)) ?? null
  const distribution = attributeDistribution(facet, attribute, props.filters, drillable.value, false)
  const rows = distribution?.rows ?? []
  const shown = topRows(rows)
  const values = rows.filter(r => r.kind === 'value').length
  return { attribute, distribution, shown, values, hidden: rows.length - shown.length }
}))

/** The `SIDEBAR_ROWS` most frequent values, in the distribution's display order, and its Missing row. */
function topRows (rows: DistributionRow[]): DistributionRow[] {
  const values = rows.filter(r => r.kind === 'value')
  const top = new Set([...values].sort((a, b) => b.count - a.count).slice(0, SIDEBAR_ROWS).map(r => r.key))
  return rows.filter(r => r.kind === 'missing' || top.has(r.key))
}
</script>

<style scoped>
.statistics-sidebar--stale {
  opacity: 0.5;
  transition: opacity 0.15s;
}

.statistics-sidebar {
  padding: 8px 12px;
  --label-width: 9rem;
}

.statistics-sidebar__summary {
  font-size: 0.875rem;
  margin: 0 0 4px;
}

.statistics-sidebar__warning {
  background: #fffbeb;
  border-left: 3px solid #d69e2e;
  padding: 6px 10px;
  margin: 0 0 8px;
  font-size: 0.8rem;
}

.statistics-sidebar__state {
  padding: 12px 0;
}

.statistics-sidebar__open {
  margin: 0 0 8px -6px;
}

.statistics-sidebar__block {
  margin-bottom: 14px;
}

.statistics-sidebar__title {
  font-size: 0.95rem;
  font-weight: 600;
  line-height: 1.4;
  margin: 0 0 2px;
}

.statistics-sidebar__note {
  color: #4a5568;
  font-size: 0.8rem;
  margin: 0;
}

.statistics-sidebar__attributes {
  border-top: 1px solid #e2e8f0;
  padding-top: 10px;
}

.statistics-sidebar__group {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 8px;
}

.statistics-sidebar__all {
  margin-left: -6px;
}
</style>
