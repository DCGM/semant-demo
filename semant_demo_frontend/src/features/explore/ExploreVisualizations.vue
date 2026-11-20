<template>
  <section class="explore-visualizations" aria-label="Visualizations" data-testid="explore-visualizations">
    <div v-if="checking" class="explore-visualizations__status" role="status" data-testid="charts-loading">
      <q-spinner color="primary" size="2.5em" />
      <div class="q-mt-sm">Checking the collection…</div>
    </div>

    <template v-else-if="availability === 'ranked'">
      <q-banner v-if="ranked.searchError" rounded class="bg-red-1 text-negative" role="alert" data-testid="charts-search-error">
        <template v-slot:avatar>
          <q-icon name="error_outline" color="negative" />
        </template>
        Search failed: {{ ranked.searchError }}
        <template v-slot:action>
          <q-btn flat color="negative" label="Try again" data-testid="charts-search-retry" @click="emit('retrySearch')" />
        </template>
      </q-banner>
      <q-banner v-else-if="ranked.error" rounded class="bg-red-1 text-negative" role="alert" data-testid="charts-error">
        <template v-slot:avatar>
          <q-icon name="error_outline" color="negative" />
        </template>
        The search results could not be counted: {{ ranked.error }}
        <template v-if="!ranked.invalid" v-slot:action>
          <q-btn flat color="negative" label="Try again" data-testid="charts-retry" @click="emit('retryRanked')" />
        </template>
      </q-banner>
      <div v-else-if="!ranked.counts" class="explore-visualizations__status" role="status" data-testid="charts-loading">
        <q-spinner color="primary" size="2.5em" />
        <div class="q-mt-sm">{{ ranked.searching ? 'Searching…' : ranked.slow ? 'Counting the search results takes longer than usual…' : 'Counting the search results…' }}</div>
      </div>
      <RankedResultCharts
        v-else
        :counts="ranked.counts"
        :vector-name="ranked.vectorName"
        @apply-filter="(filter) => emit('applyFilter', filter)"
      />
    </template>

    <div v-else-if="availability === 'passages'" class="explore-visualizations__status" role="status" data-testid="charts-passages">
      <q-icon name="insights" size="2.5em" />
      <div class="q-mt-sm text-subtitle1">Passages cannot be charted by filters alone.</div>
      <div class="text-caption">Browsing passages without a text query is not available. Documents charts the documents these filters match.</div>
      <q-btn outline no-caps color="primary" class="q-mt-md" label="Chart the documents" data-testid="charts-show-documents" @click="emit('showDocuments')" />
    </div>

    <q-banner v-else-if="error" rounded class="bg-red-1 text-negative" role="alert" data-testid="charts-error">
      <template v-slot:avatar>
        <q-icon name="error_outline" color="negative" />
      </template>
      The documents could not be counted: {{ error }}
      <template v-if="!invalid" v-slot:action>
        <q-btn flat color="negative" label="Try again" data-testid="charts-retry" @click="emit('retry')" />
      </template>
    </q-banner>

    <div v-else-if="!shown" class="explore-visualizations__status" role="status" data-testid="charts-loading">
      <q-spinner color="primary" size="2.5em" />
      <div class="q-mt-sm">{{ slow ? 'Counting the matching documents takes longer than usual…' : 'Counting the matching documents…' }}</div>
    </div>

    <ScopedDocumentCharts
      v-else :distributions="shown" :loading="loading" :slow="slow" :collection-name="collectionName"
      empty-hint="Add documents or passages to it from the Results."
      @apply-filter="(filter) => emit('applyFilter', filter)"
    />
  </section>
</template>

<script setup lang="ts">
/**
 * The Visualizations view of Explore (#618, #620): the charts of the documents matching the
 * applied criteria (of the corpus, or of a collection's documents, #768), of a text query's
 * ranked results (`RankedResultCharts`), or why there are none for them (`chartsAvailability`).
 * What the document counts describe is taken from their answer (`scope`), never from the
 * criteria being requested; counts of another population than the one the page charts
 * (`userCollectionId`: after a change of collection or account, before they are counted again)
 * are not shown at all, not even dimmed; nor is anything while the page checks the scope it was
 * given (`checking`), whose criteria are applied but not counted yet. The page owns the counts (`useExploreCharts`,
 * `useResultCharts`), the search and the criteria; a clicked chart category (or the shown
 * period) is emitted as a filter, which the page applies (a new search or count).
 */
import { computed } from 'vue'
import type { CorpusDistributions } from 'src/generated/api'
import RankedResultCharts from './RankedResultCharts.vue'
import type { RankedChartsState } from './useResultCharts'
import ScopedDocumentCharts from 'src/features/analytics/ScopedDocumentCharts.vue'
import type { ChartFilter } from 'src/features/analytics/corpusOverview'
import type { ChartsAvailability } from './useExploreCharts'

type CollectionLabel = (id: string) => string

const props = withDefaults(defineProps<{
  availability: ChartsAvailability
  distributions: CorpusDistributions | null
  loading: boolean
  slow: boolean
  error: string | null
  /** The request was refused as invalid: trying again cannot help. */
  invalid: boolean
  /** A text query's charts: its search and the counts of its ranking. */
  ranked?: RankedChartsState
  /** The name of a collection by id (the scope of collection counts). */
  collectionLabel?: CollectionLabel
  /** The collection the page charts now (null: the searchable corpus). */
  userCollectionId?: string | null
  /**
   * The page checks the collection handed over to it: the applied criteria are not counted yet,
   * so earlier counts of the same collection are not shown under them (review of #796).
   */
  checking?: boolean
}>(), { userCollectionId: null, checking: false })
const emit = defineEmits<{
  retry: []
  retryRanked: []
  retrySearch: []
  applyFilter: [filter: ChartFilter]
  showDocuments: []
}>()

const NOTHING_RANKED: RankedChartsState = { searching: false, searchError: null, counts: null, slow: false, error: null, invalid: false, vectorName: null }
const ranked = computed(() => props.ranked ?? NOTHING_RANKED)

/** The counts, when they are of the population the page charts; else none (yet). */
const shown = computed(() => {
  const d = props.distributions
  return d && (d.userCollectionId ?? null) === props.userCollectionId ? d : null
})
/** The counted collection's name when the counts describe a collection, else null. */
const collectionName = computed(() => {
  const d = shown.value
  if (d?.scope !== 'user_collection' || !d.userCollectionId) return null
  return props.collectionLabel?.(d.userCollectionId) ?? `Collection ${d.userCollectionId}`
})
</script>

<style scoped>
.explore-visualizations__status {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 160px;
  padding: 32px 16px;
  text-align: center;
  color: #4a5568;
}
</style>
