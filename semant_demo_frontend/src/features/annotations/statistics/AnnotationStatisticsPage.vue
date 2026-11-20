<template>
  <q-page class="annotation-statistics q-px-md q-pb-lg" data-testid="annotation-statistics">
    <section class="statistics-scope q-mb-md" aria-labelledby="statistics-scope-title">
      <h2 id="statistics-scope-title" class="statistics-scope__title">Scope</h2>
      <p class="statistics-scope__text" data-testid="statistics-scope">
        {{ scopeText }}
        <router-link :to="{ name: 'collectionAnnotations' }">Change the query in Annotations</router-link>.
      </p>
      <div class="statistics-scope__status" role="group" aria-label="Status counted">
        <span class="statistics-scope__label">Status counted:</span>
        <q-checkbox
          v-for="status in STATUS_ORDER"
          :key="status"
          dense
          :model-value="store.filters.types.includes(status)"
          :label="STATUS_LABELS[status]"
          :disable="store.filters.types.length === 1 && store.filters.types.includes(status)"
          :data-testid="`statistics-status-${status}`"
          class="q-mr-md"
          @update:model-value="(on: boolean) => toggleStatus(status, on)"
        />
      </div>
      <ConcordanceFilterChips
        :filters="store.filters"
        :tags="tags"
        :documents="store.documents"
        :attributes="attributesStore.attributes"
        class="q-mt-xs"
        @change="store.setFilters"
        @reset="store.resetFilters"
      />
    </section>

    <q-linear-progress v-if="loading" indeterminate color="primary" class="q-mb-sm" aria-label="Loading statistics" />

    <q-banner v-if="error" dense rounded class="bg-red-1 text-negative q-mb-md" data-testid="statistics-error">
      {{ error }}
      <template #action>
        <q-btn flat dense no-caps color="negative" label="Retry" @click="load" />
      </template>
    </q-banner>

    <template v-else-if="statistics">
      <q-banner v-if="topK" dense rounded class="bg-amber-1 q-mb-md" data-testid="statistics-top-k">
        These counts are of the top {{ statistics.k }} annotations ranked by similarity, not of every
        match in the collection. Listing one category would rank again and give other annotations, so
        it is not offered here; clear the similarity ranking to count and list every match.
      </q-banner>

      <section class="statistics-summary q-mb-md" aria-label="Summary" data-testid="statistics-summary">
        <div class="statistics-summary__item">
          <div class="statistics-summary__value" data-testid="statistics-total">{{ formatCount(total) }}</div>
          <div class="statistics-summary__label">{{ total === 1 ? 'annotation' : 'annotations' }}{{ topK ? ` in the top ${statistics.k}` : '' }}</div>
        </div>
        <div class="statistics-summary__item">
          <div class="statistics-summary__value" data-testid="statistics-documents">
            {{ documents == null ? '—' : formatCount(documents) }}
          </div>
          <div class="statistics-summary__label">
            {{ documents == null ? 'source documents: not available for this query' : `distinct source ${documents === 1 ? 'document' : 'documents'}` }}
          </div>
        </div>
        <div v-for="status in statusCounts" :key="status.key" class="statistics-summary__item">
          <div class="statistics-summary__value">{{ formatCount(status.count) }}</div>
          <div class="statistics-summary__label">{{ status.label.toLowerCase() }} ({{ formatShare(status.share) }})</div>
        </div>
      </section>

      <p v-if="total === 0" class="statistics-empty" data-testid="statistics-empty">
        No annotations match this query.
      </p>
      <div v-else class="statistics-grid">
        <DistributionCard
          v-for="dimension in DIMENSIONS"
          :key="dimension"
          :dimension="dimension"
          :facet="facetOf(statistics, dimension)"
          :filters="store.filters"
          :labels="labels"
          :denominator="denominator"
          :drillable="!topK"
          @drill="drill"
        />
      </div>
    </template>
  </q-page>
</template>

<script setup lang="ts">
/**
 * The statistics of the collection's annotation workspace query (#818): how the annotations the
 * Annotations tab lists are distributed by status, tag, year, source, library and language. It
 * shares that query (`concordanceStore`), so changing the scope here changes the list too; each
 * category leads to the list with exactly its annotations, other filters kept.
 */
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { QBanner, QBtn, QCheckbox, QLinearProgress, QPage } from 'quasar'
import type { SpanType } from 'src/generated/api'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import { useAttributesStore } from 'src/features/attributes/attributesStore'
import ConcordanceFilterChips from '../concordance/ConcordanceFilterChips.vue'
import { useConcordanceStore, type ConcordanceFilters } from '../concordance/concordanceStore'
import { concordanceChips } from '../concordance/filterChips'
import DistributionCard from './DistributionCard.vue'
import {
  DIMENSIONS, STATUS_LABELS, STATUS_ORDER, denominatorText, distributionRows, facetOf, formatCount, formatShare, isTopK
} from './statistics'
import { useAnnotationStatistics } from './useAnnotationStatistics'

const route = useRoute()
const router = useRouter()
const store = useConcordanceStore()
const tagsStore = useTagsStore()
const attributesStore = useAttributesStore()
const { tags } = storeToRefs(tagsStore)

const collectionId = computed(() => typeof route.params.collectionId === 'string' ? route.params.collectionId : '')

watch(collectionId, (id) => {
  if (!id) return
  store.enter(id)
  void tagsStore.fetchTagsByCollection(id)
  void attributesStore.load(id)
  // Titles of the source documents.
  void store.loadDocuments()
}, { immediate: true })

const workspaceCollection = computed(() => (store.collectionId === collectionId.value ? store.collectionId : null))
const filters = computed(() => store.filters)
const { statistics, loading, error, load } = useAnnotationStatistics(workspaceCollection, filters)

const topK = computed(() => isTopK(statistics.value))
const typeFacet = computed(() => facetOf(statistics.value, 'type'))
const total = computed(() => typeFacet.value?.total ?? statistics.value?.facets[0]?.total ?? 0)
const documents = computed(() => facetOf(statistics.value, 'document')?.distinct ?? null)
const denominator = computed(() => (statistics.value ? denominatorText(statistics.value, total.value) : ''))
const labels = computed(() => ({ tags: tags.value, documents: store.documents }))
const statusCounts = computed(() => (typeFacet.value ? distributionRows(typeFacet.value, 'type', labels.value, store.filters, false) : []))

const scopeText = computed(() => {
  const chips = concordanceChips(store.filters, tags.value, store.documents, attributesStore.attributes)
  return chips.length
    ? 'The annotations matching the query of the Annotations tab (filters below).'
    : 'Every annotation of the collection with the statuses below: the Annotations tab has no other filters.'
})

function toggleStatus (status: SpanType, on: boolean) {
  const types = on ? [...store.filters.types, status] : store.filters.types.filter(t => t !== status)
  if (types.length) void store.setFilters({ types: STATUS_ORDER.filter(t => types.includes(t)) })
}

/** Lists exactly a category's annotations: the shared query narrowed to it, then the list. */
async function drill (change: Partial<ConcordanceFilters>) {
  void store.setFilters(change)
  await router.push({ name: 'collectionAnnotations', params: { collectionId: collectionId.value } })
}
</script>

<style scoped>
.statistics-scope__title {
  font-size: 1.1rem;
  font-weight: 600;
  line-height: 1.4;
  margin: 0 0 4px;
}

.statistics-scope__text {
  margin: 0 0 4px;
}

.statistics-scope__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.statistics-scope__label {
  font-weight: 500;
  margin-right: 8px;
}

.statistics-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 32px;
}

.statistics-summary__value {
  font-size: 1.5rem;
  font-weight: 600;
  line-height: 1.2;
}

.statistics-summary__label {
  color: #4a5568;
  font-size: 0.85rem;
}

.statistics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 420px), 1fr));
  gap: 16px;
}

.statistics-empty {
  color: #4a5568;
}
</style>
