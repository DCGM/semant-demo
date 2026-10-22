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
      :loading="loading"
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
                @remove="load(withoutFilter(overview.filters, group.key, chip.value))"
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

      <div v-else class="corpus-overview__grid" :class="{ 'corpus-overview__grid--stale': loading }" :aria-busy="loading">
        <q-card flat bordered class="dimension-card dimension-card--wide" data-testid="corpus-years">
          <q-card-section>
            <h2 class="dimension-card__title">Publication year</h2>
            <template v-if="overview.publicationYear.available">
              <p class="dimension-card__coverage">{{ coverageText(overview.publicationYear.unknownCount ?? 0, 'a publication year') }}</p>
              <PublicationTimeline
                v-if="overview.publicationYear.years?.length"
                :distribution="overview.publicationYear"
                @apply-period="applyPeriod"
              />
              <p v-else class="dimension-card__note">No document of these has a valid publication year.</p>
            </template>
            <p v-else class="dimension-card__unavailable" role="note">{{ unavailableText('publication years') }}</p>
          </q-card-section>
        </q-card>

        <q-card
          v-for="dimension in categories"
          :key="dimension.key"
          flat
          bordered
          class="dimension-card"
          :data-testid="`corpus-${dimension.key}`"
        >
          <q-card-section>
            <h2 class="dimension-card__title">{{ dimension.title }}</h2>
            <template v-if="dimension.distribution.available">
              <p class="dimension-card__coverage">{{ coverageText(dimension.distribution.unknownCount ?? 0, dimension.subject) }}</p>
              <p v-if="dimension.note" class="dimension-card__note">{{ dimension.note }}</p>
              <VegaChart :spec="dimension.spec" :label="`Bar chart of documents per ${dimension.axis.toLowerCase()}; the table below lists the same counts.`" />
              <q-expansion-item dense dense-toggle switch-toggle-side :label="`Table: documents per ${dimension.axis.toLowerCase()}`" class="dimension-card__table">
                <q-markup-table flat dense separator="horizontal" class="count-table">
                  <caption class="sr-only">Documents per {{ dimension.axis.toLowerCase() }}</caption>
                  <thead>
                    <tr>
                      <th scope="col" class="text-left">{{ dimension.axis }}</th>
                      <th scope="col" class="text-left">Stored value</th>
                      <th scope="col" class="text-right">Documents</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in dimension.rows" :key="row.key" :class="`count-table__${row.kind}`">
                      <th scope="row" class="text-left text-weight-regular">{{ row.label }}</th>
                      <td class="text-left"><code v-if="row.kind === 'value'">{{ row.key }}</code><span v-else>—</span></td>
                      <td class="text-right">{{ formatCount(row.count) }}</td>
                    </tr>
                  </tbody>
                </q-markup-table>
              </q-expansion-item>
            </template>
            <p v-else class="dimension-card__unavailable" role="note">{{ unavailableText(dimension.subjectPlural) }}</p>
          </q-card-section>
        </q-card>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import type { CategoryDistribution } from 'src/generated/api'
import VegaChart from 'src/shared/visualization/VegaChart.vue'
import CorpusFilters from './CorpusFilters.vue'
import PublicationTimeline from './PublicationTimeline.vue'
import {
  categoryBarSpec, categoryRows, coverage, filterGroups, isUnfiltered, languageLabel, libraryLabel, withoutFilter
} from './corpusOverview'
import type { YearWindow } from './timeline'
import { useCorpusOverview } from './useCorpusOverview'

const { distributions: overview, corpus, filters, loading, slow, error, invalid, load, retry } = useCorpusOverview()

/** The counts shown are of filtered documents (their own filters, not the ones being requested). */
const filtered = computed(() => overview.value ? !isUnfiltered(overview.value.filters) : false)
const groups = computed(() => overview.value ? filterGroups(overview.value.filters) : [])

const numberFormat = new Intl.NumberFormat('en')
const formatCount = (n: number) => numberFormat.format(n)

const total = computed(() => overview.value?.totalDocuments ?? 0)

/** Restricts the counted documents to a period of the timeline, keeping the other filters. */
function applyPeriod (period: YearWindow) {
  if (overview.value) void load({ ...overview.value.filters, yearMin: period.start, yearMax: period.end })
}

interface CategoryDimension {
  key: string
  title: string
  axis: string
  subject: string
  subjectPlural: string
  note?: string
  distribution: CategoryDistribution
  rows: ReturnType<typeof categoryRows>
  spec: ReturnType<typeof categoryBarSpec>
}

const categories = computed<CategoryDimension[]>(() => {
  const data = overview.value
  if (!data) return []
  const dimension = (key: string, title: string, axis: string, subject: string, subjectPlural: string,
    distribution: CategoryDistribution, label: (v: string) => string, note?: string): CategoryDimension => {
    const rows = categoryRows(distribution, label)
    return { key, title, axis, subject, subjectPlural, note, distribution, rows, spec: categoryBarSpec(rows, axis) }
  }
  return [
    dimension('libraries', 'Source library', 'Library', 'a source library', 'source libraries', data.libraries, libraryLabel),
    dimension('languages', 'Document language', 'Language', 'a language', 'document languages', data.languages, languageLabel,
      'The language recorded in the bibliographic metadata of each document, not detected from its text.')
  ]
})

function coverageText (unknown: number, subject: string): string {
  const c = coverage(unknown, total.value)
  return `${formatCount(c.known)} of ${formatCount(total.value)} documents (${c.percent} %) have ${subject}; ` +
    `${formatCount(c.unknown)} unknown.`
}

function unavailableText (subjectPlural: string): string {
  return `Not available: this corpus database does not record ${subjectPlural} in a form that can be counted, ` +
    'so documents are not broken down by them (this is not a count of zero).'
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

.corpus-overview__summary--stale,
.corpus-overview__grid--stale {
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

.corpus-overview__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.dimension-card {
  border-radius: 12px;
  min-width: 0;
}

.dimension-card--wide {
  grid-column: 1 / -1;
}

.dimension-card__title {
  font-size: 1.15rem;
  font-weight: 600;
  line-height: 1.3;
  margin: 0 0 4px;
}

.dimension-card__coverage,
.dimension-card__note {
  color: #4a5568;
  margin: 0 0 8px;
}

.dimension-card__note {
  font-size: 0.85rem;
}

.dimension-card__unavailable {
  background: #fff8e1;
  border-radius: 8px;
  padding: 12px;
  margin: 8px 0 0;
}

.dimension-card__table {
  margin-top: 8px;
}

.count-table {
  max-width: 560px;
}

.count-table__other th,
.count-table__unknown th {
  font-style: italic;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

@media (max-width: 1023px) {
  .corpus-overview__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 599px) {
  .corpus-overview {
    padding: 16px;
  }
}
</style>
