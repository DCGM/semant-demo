<template>
  <section class="explore-visualizations" aria-label="Visualizations" data-testid="explore-visualizations">
    <template v-if="availability === 'ranked'">
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

    <div v-else-if="availability === 'collection'" class="explore-visualizations__status" role="status" data-testid="charts-collection">
      <q-icon name="folder_off" size="2.5em" />
      <div class="q-mt-sm text-subtitle1">Charts of a whole collection are not available yet.</div>
      <div class="text-caption">
        Without a text query, charts count the documents of the public corpus. Remove the collection from the search to
        chart them, or enter a text query to chart the collection's search results.
      </div>
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

    <div v-else-if="!distributions" class="explore-visualizations__status" role="status" data-testid="charts-loading">
      <q-spinner color="primary" size="2.5em" />
      <div class="q-mt-sm">{{ slow ? 'Counting the matching documents takes longer than usual…' : 'Counting the matching documents…' }}</div>
    </div>

    <template v-else>
      <div class="explore-visualizations__scope" data-testid="charts-scope">
        <div class="text-subtitle1">
          <strong data-testid="charts-total">{{ formatCount(distributions.totalDocuments) }}</strong>
          {{ distributions.totalDocuments === 1 ? 'document matches' : 'documents match' }}
          {{ filtered ? 'the applied filters' : '(the whole searchable corpus)' }}.
        </div>
        <p class="text-caption text-grey-8 q-mb-none">
          Every chart counts distinct documents: all that match, counted in the corpus database, not the loaded results
          or a sample.
          <template v-if="perDimension">
            A document matches the passage filters when, for each of them, at least one of its passages has a chosen value;
            different filters may be met by different passages.
          </template>
        </p>
      </div>
      <div v-if="loading" class="explore-visualizations__updating" role="status" aria-live="polite">
        <q-spinner size="20px" color="primary" />
        <span>{{ slow ? 'Counting the matching documents takes longer than usual…' : 'Counting the matching documents…' }}</span>
      </div>
      <div v-if="distributions.totalDocuments === 0" class="explore-visualizations__status" role="status" data-testid="charts-empty">
        <q-icon name="search_off" size="2.5em" />
        <div class="q-mt-sm text-subtitle1">No documents match these filters.</div>
        <div class="text-caption">Remove some of the filters above.</div>
      </div>
      <DocumentDistributions v-else :distributions="distributions" :loading="loading" @apply-filter="(filter) => emit('applyFilter', filter)" />
    </template>
  </section>
</template>

<script setup lang="ts">
/**
 * The Visualizations view of Explore (#618, #620): the charts of the documents matching the
 * applied criteria, of a text query's ranked results (`RankedResultCharts`), or why there are
 * none for them (`chartsAvailability`). The page owns the counts (`useExploreCharts`,
 * `useResultCharts`), the search and the criteria; a clicked chart category (or the shown
 * period) is emitted as a filter, which the page applies (a new search or count).
 */
import { computed } from 'vue'
import type { CorpusDistributions } from 'src/generated/api'
import RankedResultCharts from './RankedResultCharts.vue'
import type { RankedChartsState } from './useResultCharts'
import DocumentDistributions from 'src/features/analytics/DocumentDistributions.vue'
import { hasChunkFilters, isUnfiltered } from 'src/features/analytics/corpusOverview'
import type { ChartFilter } from 'src/features/analytics/corpusOverview'
import type { ChartsAvailability } from './useExploreCharts'

const props = defineProps<{
  availability: ChartsAvailability
  distributions: CorpusDistributions | null
  loading: boolean
  slow: boolean
  error: string | null
  /** The request was refused as invalid: trying again cannot help. */
  invalid: boolean
  /** A text query's charts: its search and the counts of its ranking. */
  ranked?: RankedChartsState
}>()
const emit = defineEmits<{
  retry: []
  retryRanked: []
  retrySearch: []
  applyFilter: [filter: ChartFilter]
  showDocuments: []
}>()

const NOTHING_RANKED: RankedChartsState = { searching: false, searchError: null, counts: null, slow: false, error: null, invalid: false, vectorName: null }
const ranked = computed(() => props.ranked ?? NOTHING_RANKED)

const numberFormat = new Intl.NumberFormat('en')
const formatCount = (n: number) => numberFormat.format(n)

// From the counts' own (echoed) filters, not the ones being requested.
const perDimension = computed(() => hasChunkFilters(props.distributions?.chunkFilters))
const filtered = computed(() => !!props.distributions && (!isUnfiltered(props.distributions.filters) || perDimension.value))
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

.explore-visualizations__scope {
  margin-bottom: 16px;
  max-width: 80ch;
}

.explore-visualizations__updating {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  color: #4a5568;
}
</style>
