<template>
  <div class="scoped-document-charts">
    <div class="scoped-document-charts__scope" data-testid="charts-scope">
      <div v-if="collectionName !== null" class="text-subtitle1">
        <strong data-testid="charts-total">{{ formatCount(distributions.totalDocuments) }}</strong>
        {{ distributions.totalDocuments === 1 ? 'document' : 'documents' }} of collection
        <strong data-testid="charts-collection-name">{{ collectionName }}</strong>{{ filtered ? (distributions.totalDocuments === 1 ? ' matches' : ' match') + ' the applied filters' : '' }}.
      </div>
      <div v-else class="text-subtitle1">
        <strong data-testid="charts-total">{{ formatCount(distributions.totalDocuments) }}</strong>
        {{ distributions.totalDocuments === 1 ? 'document matches' : 'documents match' }}
        {{ filtered ? 'the applied filters' : '(the whole searchable corpus)' }}.
      </div>
      <p class="text-caption text-grey-8 q-mb-none">
        <template v-if="collectionName !== null">
          Every chart counts distinct documents of the collection: all documents added to it, also those without a
          passage in it, counted in the corpus database, not the loaded results or a sample.
        </template>
        <template v-else>
          Every chart counts distinct documents: all that match, counted in the corpus database, not the loaded results
          or a sample.
        </template>
        <template v-if="perDimension">
          A document matches the passage filters when, for each of them, at least one of its passages has a chosen value;
          different filters may be met by different passages.
          <template v-if="collectionName !== null">All passages of each document count, not only those in the collection.</template>
        </template>
      </p>
    </div>
    <div v-if="loading" class="scoped-document-charts__updating" role="status" aria-live="polite">
      <q-spinner size="20px" color="primary" />
      <span>{{ slow ? 'Counting the matching documents takes longer than usual…' : 'Counting the matching documents…' }}</span>
    </div>
    <div v-if="distributions.totalDocuments === 0" class="scoped-document-charts__empty" role="status" data-testid="charts-empty">
      <template v-if="collectionName !== null && !filtered">
        <q-icon name="folder_open" size="2.5em" />
        <div class="q-mt-sm text-subtitle1">This collection has no documents.</div>
        <div class="text-caption">{{ emptyHint }}</div>
      </template>
      <template v-else>
        <q-icon name="search_off" size="2.5em" />
        <div class="q-mt-sm text-subtitle1">{{ collectionName !== null ? 'No documents of this collection match these filters.' : 'No documents match these filters.' }}</div>
        <div class="text-caption">Remove some of the filters above.</div>
      </template>
    </div>
    <DocumentDistributions
      v-else :distributions="distributions" :loading="loading"
      :unit-label="collectionName !== null ? 'collection documents' : 'documents'" :opens-explore="opensExplore"
      @apply-filter="(filter) => emit('applyFilter', filter)"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * Document charts with what they count (#618, #768, #795): the total and scope line, the unit
 * and the passage-filter note, the empty states, and the charts (`DocumentDistributions`).
 * Shared by Explore Visualizations and the collection Overview tab. The scope, filters and
 * collection are those of the counts themselves (their echoed `filters`/`chunkFilters`); the
 * page passes `collectionName` only for counts whose `scope` is a user collection, and checks
 * that they are of the population it shows. A clicked category is emitted as `applyFilter`.
 */
import { computed } from 'vue'
import type { CorpusDistributions } from 'src/generated/api'
import DocumentDistributions from './DocumentDistributions.vue'
import { hasChunkFilters, isUnfiltered, type ChartFilter } from './corpusOverview'

const props = withDefaults(defineProps<{
  distributions: CorpusDistributions
  /** Newer counts are being loaded; the shown ones stay meanwhile. */
  loading?: boolean
  slow?: boolean
  /** The counted collection's name, or null for the searchable corpus. */
  collectionName?: string | null
  /** What to do about an empty collection, where these charts are shown. */
  emptyHint?: string
  /** A clicked category opens Explore with it (the collection page) instead of filtering here. */
  opensExplore?: boolean
}>(), { loading: false, slow: false, collectionName: null, emptyHint: '', opensExplore: false })
const emit = defineEmits<{ applyFilter: [filter: ChartFilter] }>()

const numberFormat = new Intl.NumberFormat('en')
const formatCount = (n: number) => numberFormat.format(n)

const perDimension = computed(() => hasChunkFilters(props.distributions.chunkFilters))
const filtered = computed(() => !isUnfiltered(props.distributions.filters) || perDimension.value)
</script>

<style scoped>
.scoped-document-charts__scope {
  margin-bottom: 16px;
  max-width: 80ch;
}

.scoped-document-charts__updating {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  color: #4a5568;
}

.scoped-document-charts__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 160px;
  padding: 32px 16px;
  text-align: center;
  color: #4a5568;
}
</style>
