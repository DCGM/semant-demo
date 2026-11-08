<template>
  <section class="explore-visualizations" aria-label="Visualizations" data-testid="explore-visualizations">
    <div v-if="availability === 'textQuery'" class="explore-visualizations__status" role="status" data-testid="charts-text-query">
      <q-icon name="insights" size="2.5em" />
      <div class="q-mt-sm text-subtitle1">Charts of search results are not available yet.</div>
      <div class="text-caption">
        With a text query, charts will describe only the retrieved results, not the whole corpus. Remove the text query
        to chart every document that matches the filters.
      </div>
    </div>

    <div v-else-if="availability === 'passages'" class="explore-visualizations__status" role="status" data-testid="charts-passages">
      <q-icon name="insights" size="2.5em" />
      <div class="q-mt-sm text-subtitle1">Passages cannot be charted by filters alone.</div>
      <div class="text-caption">Browsing passages without a text query is not available. Documents charts the documents these filters match.</div>
      <q-btn outline no-caps color="primary" class="q-mt-md" label="Chart the documents" data-testid="charts-show-documents" @click="emit('showDocuments')" />
    </div>

    <div v-else-if="availability === 'collection'" class="explore-visualizations__status" role="status" data-testid="charts-collection">
      <q-icon name="folder_off" size="2.5em" />
      <div class="q-mt-sm text-subtitle1">Charts of a collection are not available yet.</div>
      <div class="text-caption">Charts count the documents of the public corpus. Remove the collection from the search to chart them.</div>
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
      <DocumentDistributions v-else :distributions="distributions" :loading="loading" @apply-period="(period) => emit('applyPeriod', period)" />
    </template>
  </section>
</template>

<script setup lang="ts">
/**
 * The Visualizations view of Explore (#618): the charts of the documents matching the applied
 * criteria, or why there are none for them (`chartsAvailability`). The page owns the counts
 * (`useExploreCharts`) and the criteria; a timeline period applied as a filter is emitted.
 */
import { computed } from 'vue'
import type { CorpusDistributions } from 'src/generated/api'
import DocumentDistributions from 'src/features/analytics/DocumentDistributions.vue'
import { hasChunkFilters, isUnfiltered } from 'src/features/analytics/corpusOverview'
import type { YearWindow } from 'src/features/analytics/timeline'
import type { ChartsAvailability } from './useExploreCharts'

const props = defineProps<{
  availability: ChartsAvailability
  distributions: CorpusDistributions | null
  loading: boolean
  slow: boolean
  error: string | null
  /** The request was refused as invalid: trying again cannot help. */
  invalid: boolean
}>()
const emit = defineEmits<{
  retry: []
  applyPeriod: [period: YearWindow]
  showDocuments: []
}>()

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
