<template>
  <div class="document-distributions" :class="{ 'document-distributions--stale': loading }" :aria-busy="loading">
    <q-card flat bordered class="dimension-card dimension-card--wide" data-testid="corpus-years">
      <q-card-section>
        <h2 class="dimension-card__title">Publication year</h2>
        <template v-if="distributions.publicationYear.available">
          <p class="dimension-card__coverage">{{ coverageText(distributions.publicationYear.unknownCount ?? 0, 'a publication year') }}</p>
          <PublicationTimeline
            v-if="distributions.publicationYear.years?.length"
            :distribution="distributions.publicationYear"
            @apply-period="(period) => emit('applyPeriod', period)"
            @view="(view) => (timelineView = view)"
          />
          <p v-else class="dimension-card__note">No document of these has a valid publication year.</p>
        </template>
        <p v-else class="dimension-card__unavailable" role="note">{{ unavailableText('publication years') }}</p>
      </q-card-section>
    </q-card>

    <q-card flat bordered class="dimension-card dimension-card--wide" data-testid="corpus-heatmap">
      <q-card-section>
        <h2 class="dimension-card__title">Publication period × source library</h2>
        <template v-if="distributions.libraries.available && distributions.publicationYear.available">
          <p class="dimension-card__note">
            Which libraries the documents of each period come from, in raw document counts. Counted on request, for the
            same documents as the rest of the page.
          </p>
          <q-btn
            v-if="!showHeatmap" outline no-caps color="primary" icon="grid_on" label="Show documents per library and period"
            data-testid="heatmap-show" @click="showHeatmap = true"
          />
          <LibraryHeatmap
            v-else-if="distributions.publicationYear.years?.length && timelineView"
            :filters="distributions.filters" :chunk-filters="distributions.chunkFilters" :view="timelineView"
          />
          <p v-else class="dimension-card__note">No document of these has a valid publication year.</p>
        </template>
        <p v-else class="dimension-card__unavailable" role="note">
          {{ unavailableText(distributions.libraries.available ? 'publication years' : 'source libraries') }}
        </p>
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

<script setup lang="ts">
/**
 * The document charts of one `CorpusDistributions` answer (#254, #361): the publication
 * timeline, the period × library heatmap (counted when asked for) and the library and language
 * bars, each with its table and unknown/unavailable values. Shown by the Corpus overview and by
 * Explore Visualizations (#618). Zooming and panning stay in the charts; "Apply … as filter"
 * is emitted, and the page decides what it changes.
 */
import { computed, ref, shallowRef } from 'vue'
import type { CategoryDistribution, CorpusDistributions } from 'src/generated/api'
import VegaChart from 'src/shared/visualization/VegaChart.vue'
import LibraryHeatmap from './LibraryHeatmap.vue'
import PublicationTimeline from './PublicationTimeline.vue'
import { categoryBarSpec, categoryRows, coverage, languageLabel, libraryLabel } from './corpusOverview'
import type { YearWindow } from './timeline'

const props = defineProps<{
  distributions: CorpusDistributions
  /** Newer counts are being loaded: the shown ones are dimmed. */
  loading?: boolean
}>()
const emit = defineEmits<{ applyPeriod: [period: YearWindow] }>()

const numberFormat = new Intl.NumberFormat('en')
const formatCount = (n: number) => numberFormat.format(n)

const total = computed(() => props.distributions.totalDocuments)

/** The timeline's shown window and bin width; the heatmap shows the same periods. */
const timelineView = shallowRef<{ window: YearWindow, width: number } | null>(null)
/** The heatmap is counted only once asked for; it then stays shown for other filters. */
const showHeatmap = ref(false)

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
  const data = props.distributions
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
</script>

<style scoped lang="scss">
.document-distributions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.document-distributions--stale {
  opacity: 0.55;
  transition: opacity 0.2s;
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
  .document-distributions {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
