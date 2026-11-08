<template>
  <div class="ranked-charts" :class="{ 'ranked-charts--stale': loading }" :aria-busy="loading">
    <div class="ranked-charts__scope" data-testid="charts-scope">
      <div class="text-subtitle1">
        <strong data-testid="charts-total">{{ fmt(counts.totalCount) }}</strong>
        {{ unitNoun(unit, counts.totalCount) }} counted: the {{ unit === 'documents' ? 'ranked documents' : 'ranked passages' }} of
        this search, not the whole corpus.
      </div>
      <ul class="ranked-charts__facts text-caption text-grey-8">
        <li data-testid="charts-ranking">
          Ranked by {{ methodLabel }}<template v-if="vectorName"> ({{ vectorName }})</template>.
          <template v-if="counts.ranking.bounded">
            <strong>Bounded:</strong> only the best {{ fmt(counts.inputCount) }} by relevance were retrieved (the retrieval
            limit is {{ fmt(counts.ranking.retrievalLimit) }}); more {{ unit }} may match, so these counts are not those of
            every match.
          </template>
          <template v-else>Every matching {{ unitNoun(unit, 1) }} was retrieved (within the retrieval limit of {{ fmt(counts.ranking.retrievalLimit) }}).</template>
        </li>
        <li v-if="unit === 'passages'" data-testid="charts-distinct-documents">
          Each passage is counted once, with the publication year, library and language of its document: the
          {{ fmt(counts.totalCount) }} passages come from {{ fmt(counts.distinctDocuments) }} distinct
          {{ unitNoun('documents', counts.distinctDocuments) }}, so a document with several passages counts several times.
        </li>
        <li v-else>Each document is counted once, however many of its passages matched.</li>
        <li v-if="counts.missingCount" data-testid="charts-missing">
          {{ fmt(counts.missingCount) }} of the {{ fmt(counts.inputCount) }} ranked {{ unitNoun(unit, counts.inputCount) }}
          {{ counts.missingCount === 1 ? 'is' : 'are' }} not counted: deleted, or no longer matching the search's filters.
        </li>
      </ul>
    </div>

    <div v-if="counts.totalCount === 0" class="ranked-charts__status" role="status" data-testid="charts-empty">
      <q-icon name="search_off" size="2.5em" />
      <div class="q-mt-sm text-subtitle1">{{ counts.inputCount ? 'None of the ranked results could be counted.' : 'No results match this search.' }}</div>
      <div class="text-caption">Try other words, or remove some of the filters above.</div>
    </div>

    <div v-else class="ranked-charts__grid">
      <q-card flat bordered class="dimension-card dimension-card--wide" data-testid="results-years">
        <q-card-section>
          <h2 class="dimension-card__title">Publication year</h2>
          <template v-if="counts.publicationYear.available">
            <p class="dimension-card__coverage">{{ coverageText(counts.publicationYear.unknownCount ?? 0, 'a publication year') }}</p>
            <PublicationTimeline
              v-if="counts.publicationYear.years?.length"
              :distribution="counts.publicationYear"
              :unit="unit"
              inspectable
              @apply-period="(period) => emit('applyPeriod', period)"
              @inspect="inspectYears"
            />
            <template v-else>
              <p class="dimension-card__note">None of these results has a valid publication year.</p>
              <q-btn dense flat no-caps color="primary" label="Inspect them" data-testid="timeline-inspect-unknown" @click="inspectYears(null)" />
            </template>
          </template>
          <p v-else class="dimension-card__unavailable" role="note">{{ unavailableText('publication years') }}</p>
        </q-card-section>
      </q-card>

      <q-card v-for="dimension in categories" :key="dimension.key" flat bordered class="dimension-card" :data-testid="`results-${dimension.key}`">
        <q-card-section>
          <h2 class="dimension-card__title">{{ dimension.title }}</h2>
          <template v-if="dimension.distribution.available">
            <p class="dimension-card__coverage">{{ coverageText(dimension.distribution.unknownCount ?? 0, dimension.subject) }}</p>
            <p v-if="dimension.note" class="dimension-card__note">{{ dimension.note }}</p>
            <VegaChart :spec="dimension.spec" :label="`Bar chart of ${unit} per ${dimension.axis.toLowerCase()}; the table below lists the same counts.`" />
            <q-markup-table flat dense separator="horizontal" class="count-table">
              <caption class="sr-only">{{ unitNoun(unit, 2, true) }} per {{ dimension.axis.toLowerCase() }}</caption>
              <thead>
                <tr>
                  <th scope="col" class="text-left">{{ dimension.axis }}</th>
                  <th scope="col" class="text-right">{{ unitNoun(unit, 2, true) }}</th>
                  <th scope="col" class="text-right"><span class="sr-only">Inspect</span></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in dimension.rows" :key="row.key" :class="`count-table__${row.kind}`">
                  <th scope="row" class="text-left text-weight-regular">
                    {{ row.label }}<code v-if="row.kind === 'value' && row.label !== row.key" class="sr-only"> {{ row.key }}</code>
                  </th>
                  <td class="text-right">{{ fmt(row.count) }}</td>
                  <td class="text-right">
                    <q-btn
                      v-if="row.count > 0" dense flat no-caps color="primary" label="Inspect"
                      :aria-label="`Inspect the ${fmt(row.count)} ${unitNoun(unit, row.count)}: ${row.label}`"
                      :data-testid="`inspect-${dimension.key}-${row.kind === 'value' ? row.key : row.kind}`"
                      @click="emit('inspect', { dimension: dimension.dimension, value: inspectValue(row) })"
                    />
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
          </template>
          <p v-else class="dimension-card__unavailable" role="note">{{ unavailableText(dimension.subjectPlural) }}</p>
        </q-card-section>
      </q-card>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * The charts of a text query's ranked results (#620): one `RankedResultsDistributions` answer,
 * counted in the unit of the results mode (documents, or passages with their distinct source
 * documents), with the ranking that produced them and whether its retrieval limit cut it.
 * Every category with results can be inspected (`inspect`: the page shows those results of the
 * same ranking); a timeline period can also be applied as a filter, which is a new search.
 */
import { computed } from 'vue'
import type { CategoryDistribution, RankedResultsDistributions } from 'src/generated/api'
import VegaChart from 'src/shared/visualization/VegaChart.vue'
import PublicationTimeline from 'src/features/analytics/PublicationTimeline.vue'
import { categoryBarSpec, categoryRows, coverage, languageLabel, libraryLabel, type CategoryRow } from 'src/features/analytics/corpusOverview'
import { unitNoun, type YearWindow } from 'src/features/analytics/timeline'
import { INSPECT_OTHER, INSPECT_UNKNOWN, type InspectDimension, type Inspection } from './criteria'

const props = defineProps<{
  counts: RankedResultsDistributions
  /** Display name of the ranking's search vector. */
  vectorName?: string | null
  /** Newer counts are being loaded: the shown ones are dimmed. */
  loading?: boolean
}>()
const emit = defineEmits<{
  inspect: [inspection: Inspection]
  applyPeriod: [period: YearWindow]
}>()

const numberFormat = new Intl.NumberFormat('en')
const fmt = (n: number) => numberFormat.format(n)

const unit = computed(() => (props.counts.unit === 'documents' ? 'documents' : 'passages'))
const METHODS: Record<string, string> = {
  text: 'keyword search',
  hybrid: 'hybrid search (keywords and meaning)',
  vector: 'semantic search'
}
const methodLabel = computed(() => METHODS[props.counts.ranking.type] ?? `${props.counts.ranking.type} search`)

const categories = computed(() => {
  const dimension = (key: string, dim: InspectDimension, title: string, axis: string, subject: string, subjectPlural: string,
    distribution: CategoryDistribution, label: (v: string) => string, note?: string) => {
    const rows = categoryRows(distribution, label)
    return { key, dimension: dim, title, axis, subject, subjectPlural, note, distribution, rows, spec: categoryBarSpec(rows, axis, unit.value) }
  }
  return [
    dimension('libraries', 'library', 'Source library', 'Library', 'a source library', 'source libraries', props.counts.libraries, libraryLabel),
    dimension('languages', 'language', 'Document language', 'Language', 'a document language', 'document languages', props.counts.languages, languageLabel,
      unit.value === 'passages'
        ? 'The language recorded in the bibliographic metadata of each passage\'s document, not the language of the passage itself.'
        : 'The language recorded in the bibliographic metadata of each document, not detected from its text.')
  ]
})

const inspectValue = (row: CategoryRow) => (row.kind === 'value' ? row.key : row.kind === 'other' ? INSPECT_OTHER : INSPECT_UNKNOWN)

function inspectYears (years: YearWindow | null) {
  const value = years === null ? INSPECT_UNKNOWN : years.start === years.end ? `${years.start}` : `${years.start}-${years.end}`
  emit('inspect', { dimension: 'year', value })
}

function coverageText (unknown: number, subject: string): string {
  const total = props.counts.totalCount
  const c = coverage(unknown, total)
  return `${fmt(c.known)} of ${fmt(total)} ${unitNoun(unit.value, total)} (${c.percent} %) have ${subject}; ${fmt(c.unknown)} unknown.`
}

function unavailableText (subjectPlural: string): string {
  return `Not available: this corpus database does not record ${subjectPlural} in a form that can be counted, ` +
    `so the ${unit.value} are not broken down by them (this is not a count of zero).`
}
</script>

<style scoped lang="scss">
.ranked-charts--stale {
  opacity: 0.55;
  transition: opacity 0.2s;
}

.ranked-charts__scope {
  margin-bottom: 16px;
  max-width: 90ch;
}

.ranked-charts__facts {
  margin: 4px 0 0;
  padding-left: 1.2em;
}

.ranked-charts__status {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 16px;
  text-align: center;
  color: #4a5568;
}

.ranked-charts__grid {
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

.count-table {
  margin-top: 8px;
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
  .ranked-charts__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
