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

    <div v-if="error" class="corpus-overview__error" role="alert">
      <q-icon name="error" color="negative" size="24px" />
      <span>{{ error }}</span>
      <q-btn outline color="primary" label="Retry" icon="refresh" :loading="loading" @click="load" />
    </div>

    <div v-else-if="!overview" class="corpus-overview__loading" role="status" aria-live="polite">
      <q-spinner size="32px" color="primary" />
      <span>{{ slow ? 'Counting the corpus documents takes longer than usual…' : 'Loading the corpus overview…' }}</span>
    </div>

    <template v-else>
      <section class="corpus-overview__summary" aria-label="Corpus summary">
        <div class="summary-card">
          <div class="summary-card__label">Documents in the corpus</div>
          <div class="summary-card__value" data-testid="corpus-total">{{ formatCount(overview.totalDocuments) }}</div>
        </div>
        <div class="summary-card summary-card--freshness">
          <div class="summary-card__label">Counted</div>
          <div class="summary-card__text" data-testid="corpus-freshness">
            {{ computedAtText }}
            <span class="text-grey-7">({{ freshnessNote }})</span>
          </div>
          <q-btn flat dense no-caps color="primary" icon="refresh" label="Reload" :loading="loading" @click="load" />
        </div>
      </section>

      <p v-if="overview.totalDocuments === 0" class="corpus-overview__empty" data-testid="corpus-empty">
        The corpus holds no documents.
      </p>

      <div v-else class="corpus-overview__grid">
        <q-card flat bordered class="dimension-card dimension-card--wide" data-testid="corpus-years">
          <q-card-section>
            <h2 class="dimension-card__title">Publication year</h2>
            <template v-if="overview.publicationYear.available">
              <p class="dimension-card__coverage">{{ coverageText(overview.publicationYear.unknownCount ?? 0, 'a publication year') }}</p>
              <VegaChart
                v-if="years.length"
                :spec="yearSpec"
                label="Bar chart of documents per publication decade; the table below lists the same counts."
              />
              <q-expansion-item dense dense-toggle switch-toggle-side label="Table: documents per decade" class="dimension-card__table">
                <q-markup-table flat dense separator="horizontal" class="count-table">
                  <caption class="sr-only">Documents per publication decade</caption>
                  <thead><tr><th scope="col" class="text-left">Decade</th><th scope="col" class="text-right">Documents</th></tr></thead>
                  <tbody>
                    <tr v-for="row in years" :key="row.start">
                      <th scope="row" class="text-left text-weight-regular">{{ row.label }}</th>
                      <td class="text-right">{{ formatCount(row.count) }}</td>
                    </tr>
                    <tr class="count-table__unknown">
                      <th scope="row" class="text-left text-weight-regular">Unknown year</th>
                      <td class="text-right">{{ formatCount(overview.publicationYear.unknownCount ?? 0) }}</td>
                    </tr>
                  </tbody>
                </q-markup-table>
              </q-expansion-item>
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
import { categoryBarSpec, categoryRows, coverage, languageLabel, libraryLabel, yearHistogramSpec, yearRows } from './corpusOverview'
import { useCorpusOverview } from './useCorpusOverview'

const { overview, loading, slow, error, load } = useCorpusOverview()

const numberFormat = new Intl.NumberFormat('en')
const formatCount = (n: number) => numberFormat.format(n)

const total = computed(() => overview.value?.totalDocuments ?? 0)

const computedAtText = computed(() => overview.value
  ? overview.value.computedAt.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  : '')

const freshnessNote = computed(() => overview.value?.dataSource === 'cached_aggregation'
  ? 'a recent count, served again; recounted every few minutes'
  : 'counted now')

const years = computed(() => overview.value ? yearRows(overview.value.publicationYear) : [])
const yearSpec = computed(() => yearHistogramSpec(years.value))

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

onMounted(load)
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

.summary-card--freshness {
  flex: 1 1 280px;
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
