<template>
  <div class="passage-charts">
    <q-banner v-if="languagesFailed" rounded class="bg-red-1 text-negative" role="alert" data-testid="passage-charts-error">
      <template v-slot:avatar>
        <q-icon name="error_outline" color="negative" />
      </template>
      The passages of this collection could not be counted.
      <template v-slot:action>
        <q-btn flat color="negative" label="Try again" data-testid="passage-charts-retry" @click="languagesQuery.refetch()" />
      </template>
    </q-banner>
    <div v-else-if="!languagesShown" class="passage-charts__loading" role="status" data-testid="passage-charts-loading">
      <q-spinner color="primary" size="2.5em" />
      <div class="q-mt-sm">Counting the passages of the collection…</div>
    </div>
    <template v-else>
      <div class="passage-charts__scope" data-testid="passage-charts-scope">
        <div class="text-subtitle1">
          <strong data-testid="passage-charts-total">{{ formatCount(languagesShown.totalPassages) }}</strong>
          {{ languagesShown.totalPassages === 1 ? 'passage' : 'passages' }} included in collection
          <strong>{{ collectionName }}</strong>.
        </div>
        <p class="text-caption text-grey-8 q-mb-none">
          Every chart counts the passages added to the collection, not all passages of its documents, counted in the
          corpus database. The charts are not clickable.
        </p>
      </div>
      <div v-if="languagesShown.totalPassages === 0" class="passage-charts__empty" role="status" data-testid="passage-charts-empty">
        <q-icon name="folder_open" size="2.5em" />
        <div class="q-mt-sm text-subtitle1">This collection has no passages.</div>
        <div class="text-caption">{{ emptyHint }}</div>
      </div>
      <div v-else class="passage-charts__grid">
        <q-card flat bordered class="dimension-card" data-testid="passage-languages">
          <q-card-section>
            <h2 class="dimension-card__title">Passage language</h2>
            <template v-if="languagesShown.languages?.available">
              <p class="dimension-card__coverage">{{ languageCoverage }}</p>
              <p class="dimension-card__note">
                The language detected in the passage text, not the document's bibliographic language.
              </p>
              <CategoryChart :rows="languageRowsShown" axis="Language" unit="passages" test-id="passage-languages" />
            </template>
            <p v-else class="dimension-card__unavailable" role="note">
              This corpus database does not record the language of passages.
            </p>
          </q-card-section>
        </q-card>

        <q-card flat bordered class="dimension-card" data-testid="passage-classification">
          <q-card-section>
            <h2 class="dimension-card__title">Passage classification</h2>
            <q-banner v-if="filtersQuery.isError.value && !options.length" rounded class="bg-red-1 text-negative" role="alert" data-testid="passage-dimensions-error">
              The classifications could not be loaded.
              <template v-slot:action>
                <q-btn flat color="negative" label="Try again" data-testid="passage-dimensions-retry" @click="filtersQuery.refetch()" />
              </template>
            </q-banner>
            <div v-else-if="!options.length && filtersQuery.isFetching.value" class="passage-charts__loading passage-charts__loading--small" role="status">
              <q-spinner color="primary" size="1.5em" />
            </div>
            <p v-else-if="!options.length" class="dimension-card__unavailable" role="note" data-testid="passage-dimensions-none">
              No passage classification is configured.
            </p>
            <template v-else>
              <q-select
                v-model="chosen"
                :options="options"
                emit-value map-options dense outlined
                label="Classification"
                class="passage-charts__dimension"
                data-testid="passage-dimension"
              />
              <q-banner v-if="classificationFailed" rounded class="bg-red-1 text-negative q-mt-sm" role="alert" data-testid="passage-classification-error">
                This classification of the passages could not be counted.
                <template v-slot:action>
                  <q-btn flat color="negative" label="Try again" data-testid="passage-classification-retry" @click="classificationQuery.refetch()" />
                </template>
              </q-banner>
              <div v-else-if="!classificationShown" class="passage-charts__loading passage-charts__loading--small" role="status" data-testid="passage-classification-loading">
                <q-spinner color="primary" size="1.5em" />
                <div class="q-mt-sm">Counting the passages by {{ dimensionLabel.toLowerCase() }}…</div>
              </div>
              <p v-else-if="!classificationShown.chart" class="dimension-card__unavailable q-mt-sm" role="note">
                This corpus database does not record this classification of passages.
              </p>
              <template v-else>
                <p class="dimension-card__coverage q-mt-sm" data-testid="passage-classification-occurring">
                  {{ classificationShown.chart.occurring }} of {{ classificationShown.chart.configured }}
                  {{ classificationShown.chart.configured === 1 ? 'value occurs' : 'values occur' }} in this collection.
                </p>
                <p class="dimension-card__note">
                  A passage can have several values, so the bars can add up to more than the passages.
                  <template v-if="classificationShown.chart.approximate">
                    Some passages hold a value that is not configured, so "Without a value" is approximate.
                  </template>
                </p>
                <CategoryChart
                  :rows="classificationShown.chart.rows" :axis="dimensionLabel" unit="passages" test-id="passage-classification"
                />
              </template>
            </template>
          </q-card-section>
        </q-card>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * The charts of a collection's included passages on its Overview tab (#807, 622c of #622): their
 * total, their detected language and one classification picked in a selector (`subject_domain`
 * first), each a `CategoryChart` of passages, not clickable. The languages and the
 * classification are separate reads (`useCollectionPassageCharts`): choosing another
 * classification asks for that one alone, and a failed classification leaves the language chart
 * in place. The reverse does not hold: when the total cannot be counted (also when counting it
 * again on a later visit fails), the card shows that error alone, as the statistics do, since
 * counts that could not be confirmed are not shown as current. Only answers that say they are of
 * this collection are shown; a failed load, or a complete answer of another scope, shows its
 * error with Try again, never zeros.
 */
import { computed, ref, toRef, watch } from 'vue'
import CategoryChart from 'src/features/analytics/CategoryChart.vue'
import { useSearchFilters } from 'src/features/search/useSearchFilters'
import type { CollectionPassages } from 'src/generated/api'
import { classificationChart, classificationFilters, dimensionOptions, languageRows, ofCollection } from './passageCharts'
import { useCollectionPassageClassification, useCollectionPassageLanguages } from './useCollectionPassageCharts'
import type { PassageDimension } from './useUserCollectionsRepository'

const props = defineProps<{
  collectionId: string
  collectionName: string
  /** The collection itself has loaded: nothing is counted before. */
  enabled: boolean
  emptyHint: string
}>()

const numberFormat = new Intl.NumberFormat('en')
const formatCount = (n: number) => numberFormat.format(n)

const collectionId = toRef(props, 'collectionId')
const enabled = toRef(props, 'enabled')

// A retry in progress shows the loading state, not the error it may clear.
function states (query: { data: { value: CollectionPassages | undefined }, isFetching: { value: boolean }, isError: { value: boolean } },
  fits: (p: CollectionPassages) => boolean) {
  const failed = computed(() => {
    const d = query.data.value
    return enabled.value && !query.isFetching.value && (query.isError.value || (!!d && !fits(d)))
  })
  const shown = computed(() => {
    const d = query.data.value
    return enabled.value && !failed.value && d && fits(d) ? d : null
  })
  return { failed, shown }
}

const languagesQuery = useCollectionPassageLanguages(collectionId, enabled)
const languages = states(languagesQuery, p => ofCollection(p, collectionId.value) && !!p.languages)
const languagesFailed = languages.failed
const languagesShown = languages.shown
const languageRowsShown = computed(() => languagesShown.value ? languageRows(languagesShown.value) : [])
const languageCoverage = computed(() => {
  const p = languagesShown.value
  const unknown = p?.languages?.unknownCount ?? 0
  if (!p || !unknown) return 'Every passage has a detected language.'
  return `${formatCount(unknown)} of ${formatCount(p.totalPassages)} ${p.totalPassages === 1 ? 'passage has' : 'passages have'} no detected language (Unknown).`
})

// The classifications offered are those the search filters configure, as the backend counts them.
const filtersQuery = useSearchFilters()
const filters = computed(() => filtersQuery.data.value?.filters ?? [])
const options = computed(() => dimensionOptions(filters.value))
const chosen = ref<PassageDimension | null>(null)
// Another collection starts again with the first classification (set here: when it was chosen
// already, the fallback below would not change, and the selector would show nothing).
watch(collectionId, () => { chosen.value = options.value[0]?.value ?? null })
const dimension = computed<PassageDimension | null>(() =>
  options.value.some(o => o.value === chosen.value) ? chosen.value : options.value[0]?.value ?? null)
watch(dimension, (value) => { if (chosen.value !== value) chosen.value = value }, { immediate: true })
const dimensionLabel = computed(() => options.value.find(o => o.value === dimension.value)?.label ?? 'Classification')

// Only once the collection has passages: an empty collection has no chart to show.
const classificationEnabled = computed(() => !!languagesShown.value && languagesShown.value.totalPassages > 0)
const classificationQuery = useCollectionPassageClassification(collectionId, dimension, classificationEnabled)
const classification = states(classificationQuery, p => ofCollection(p, collectionId.value) &&
  p.classification?.dimension === dimension.value)
const classificationFailed = computed(() => classificationEnabled.value && classification.failed.value)
const classificationShown = computed(() => {
  const p = classification.shown.value
  if (!classificationEnabled.value || !p?.classification) return null
  const filter = dimension.value ? classificationFilters(filters.value).get(dimension.value) : undefined
  return { chart: classificationChart(p.classification, filter) }
})
</script>

<style scoped>
.passage-charts__scope {
  margin-bottom: 16px;
  max-width: 80ch;
}

.passage-charts__loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 16px;
  color: #4a5568;
}

.passage-charts__loading--small {
  padding: 16px;
}

.passage-charts__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 160px;
  padding: 32px 16px;
  text-align: center;
  color: #4a5568;
}

.passage-charts__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.passage-charts__dimension {
  max-width: 360px;
}

.dimension-card {
  border-radius: 12px;
  min-width: 0;
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

@media (max-width: 1023px) {
  .passage-charts__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
