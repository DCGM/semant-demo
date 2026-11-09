<template>
  <div class="corpus-overview">
    <header class="corpus-overview__header">
      <h1 class="corpus-overview__title">Corpus overview</h1>
      <p class="corpus-overview__scope" data-testid="corpus-scope">
        All documents of the searchable semANT corpus (the public corpus that Search covers),
        not your collections or the results of a search. Every number counts
        <strong>documents</strong>, not pages, text chunks or search hits.
      </p>
    </header>

    <CorpusFilters
      v-if="corpus"
      :applied="filters"
      :libraries="corpus.libraries"
      :languages="corpus.languages"
      @apply="load"
    />

    <div v-if="error" class="corpus-overview__error" role="alert">
      <q-icon name="error" color="negative" size="24px" />
      <span>{{ error }}</span>
      <q-btn v-if="!invalid" outline color="primary" label="Retry" icon="refresh" :loading="loading" @click="retry" />
    </div>

    <div v-else-if="!overview" class="corpus-overview__loading" role="status" aria-live="polite">
      <q-spinner size="32px" color="primary" />
      <span>{{ slow ? 'Counting the corpus documents takes longer than usual…' : 'Loading the corpus overview…' }}</span>
    </div>

    <template v-else>
      <div v-if="loading" class="corpus-overview__updating" role="status" aria-live="polite">
        <q-spinner size="20px" color="primary" />
        <span>{{ slow ? 'Counting the matching documents takes longer than usual…' : 'Counting the matching documents…' }}</span>
      </div>
      <section class="corpus-overview__summary" :class="{ 'corpus-overview__summary--stale': loading }" aria-label="Corpus summary">
        <div class="summary-card">
          <div class="summary-card__label">{{ filtered ? 'Matching documents' : 'Documents in the corpus' }}</div>
          <div class="summary-card__value" data-testid="corpus-total">{{ formatCount(overview.totalDocuments) }}</div>
          <div v-if="filtered && corpus" class="summary-card__text text-grey-7" data-testid="corpus-of-total">
            of {{ formatCount(corpus.totalDocuments) }} documents in the corpus
          </div>
        </div>
        <div v-if="filtered" class="summary-card summary-card--filters" data-testid="corpus-applied">
          <div class="summary-card__label">Filters: documents match every kind, and any of several values of one kind</div>
          <div
            v-for="group in groups" :key="group.key" class="summary-card__chips" :data-testid="`corpus-applied-${group.key}`"
          >
            <span class="summary-card__group">{{ group.label }}:</span>
            <template v-for="(chip, i) in group.chips" :key="chip.value ?? chip.label">
              <span v-if="i" class="text-grey-7">or</span>
              <q-chip
                removable dense color="blue-1" text-color="dark" :label="chip.label"
                :remove-aria-label="`Remove filter ${group.label} ${chip.label}`"
                @remove="load(withoutFilter(filters, group.key, chip.value))"
              />
            </template>
          </div>
          <q-btn flat dense no-caps color="primary" label="Clear all" class="q-mt-xs" data-testid="corpus-clear-all" @click="load({})" />
        </div>
      </section>

      <p v-if="overview.totalDocuments === 0 && filtered" class="corpus-overview__empty" data-testid="corpus-no-match">
        No documents match these filters. Remove a filter or clear all of them to see more documents.
      </p>

      <p v-else-if="overview.totalDocuments === 0" class="corpus-overview__empty" data-testid="corpus-empty">
        The corpus holds no documents.
      </p>

      <DocumentDistributions v-else :distributions="overview" :loading="loading" @apply-filter="applyFilter" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import CorpusFilters from './CorpusFilters.vue'
import DocumentDistributions from './DocumentDistributions.vue'
import { filterGroups, isUnfiltered, withChartFilter, withoutFilter, type ChartFilter } from './corpusOverview'
import { useCorpusOverview } from './useCorpusOverview'

const { distributions: overview, corpus, filters, loading, slow, error, invalid, load, retry } = useCorpusOverview()

/** The counts shown are of filtered documents (their own filters, not the ones being requested). */
const filtered = computed(() => overview.value ? !isUnfiltered(overview.value.filters) : false)
const groups = computed(() => overview.value ? filterGroups(overview.value.filters) : [])

const numberFormat = new Intl.NumberFormat('en')
const formatCount = (n: number) => numberFormat.format(n)

/**
 * Restricts the counted documents to a clicked year bin, library or language, or the shown
 * period, replacing that dimension's filter and keeping the others (#620). Like a removed chip,
 * built on the filters requested last, not on the counted ones shown: a change made while
 * counting must not undo the previous one (#548).
 */
function applyFilter (filter: ChartFilter) {
  void load(withChartFilter(filters.value, filter))
}

onMounted(() => load())
</script>

<style scoped lang="scss">
.corpus-overview {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.corpus-overview__title {
  font-size: 1.75rem;
  font-weight: 600;
  line-height: 1.2;
  margin: 0 0 8px;
}

.corpus-overview__scope {
  color: #4a5568;
  max-width: 70ch;
  margin: 0 0 20px;
}

.corpus-overview__error,
.corpus-overview__loading {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 24px 0;
}

.corpus-overview__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 20px;
}

.summary-card {
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 12px;
  padding: 12px 16px;
  min-width: 200px;
}

.summary-card--filters {
  flex: 2 1 360px;
}

.summary-card__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}

.summary-card__group {
  color: #4a5568;
  margin-right: 2px;
}

.corpus-overview__updating {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  color: #4a5568;
}

.corpus-overview__summary--stale {
  opacity: 0.55;
  transition: opacity 0.2s;
}

.summary-card__label {
  color: #758195;
  font-size: 0.85rem;
}

.summary-card__value {
  font-size: 2rem;
  font-weight: 700;
  line-height: 1.2;
}

.summary-card__text {
  margin: 4px 0;
}

@media (max-width: 599px) {
  .corpus-overview {
    padding: 16px;
  }
}
</style>
