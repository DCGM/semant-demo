<template>
  <div class="library-heatmap" data-testid="heatmap">
    <div v-if="error" class="library-heatmap__status" role="alert">
      <q-icon name="error" color="negative" size="24px" />
      <span>{{ error }}</span>
      <q-btn outline color="primary" label="Retry" icon="refresh" :loading="loading" @click="load" />
    </div>

    <div v-else-if="!data" class="library-heatmap__status" role="status" aria-live="polite">
      <q-spinner size="24px" color="primary" />
      <span>Counting the documents per library and period…</span>
    </div>

    <p v-else-if="!data.available" class="library-heatmap__unavailable" role="note">
      Not available: this corpus database does not record
      {{ data.unavailableProperty === 'library' ? 'source libraries' : 'publication years' }} in a form that can be counted.
    </p>

    <template v-else>
      <div v-if="loading" class="library-heatmap__status" role="status" aria-live="polite">
        <q-spinner size="20px" color="primary" />
        <span>Counting the documents per library and period…</span>
      </div>
      <div :class="{ 'library-heatmap--stale': loading }" :aria-busy="loading">
        <p class="library-heatmap__note" data-testid="heatmap-note">
          {{ view.window.start }}–{{ view.window.end }} in {{ binsName(view.width) }}, as in the timeline above; the colour
          is the number of documents (blank: none).
          <template v-if="notShown">{{ notShown }}</template>
        </p>
        <VegaChart
          :spec="spec"
          :label="`Heatmap of documents per source library and ${widthName(view.width)} from ${view.window.start} to ${view.window.end}; the table below lists the same counts.`"
        />
        <q-expansion-item
          dense dense-toggle switch-toggle-side class="library-heatmap__table"
          :label="`Table: documents per library and period (${binsName(view.width)})`"
        >
          <div class="library-heatmap__scroll">
            <q-markup-table flat dense separator="cell" class="heatmap-table">
              <caption class="sr-only">Documents per source library and {{ widthName(view.width) }} of publication</caption>
              <thead>
                <tr>
                  <th scope="col" class="text-left">Publication years</th>
                  <th v-for="row in rows" :key="row.key" scope="col" class="text-right">{{ row.label }}</th>
                  <th scope="col" class="text-right">All</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="period in tableRows" :key="period.key" :class="`heatmap-table__${period.kind}`">
                  <th scope="row" class="text-left text-weight-regular">
                    {{ period.label }}<span v-if="period.note" class="text-grey-7"> — {{ period.note }}</span>
                  </th>
                  <td v-for="(count, i) in period.counts" :key="rows[i].key" class="text-right">{{ formatCount(count) }}</td>
                  <td class="text-right">{{ formatCount(period.total) }}</td>
                </tr>
                <tr class="heatmap-table__summary">
                  <th scope="row" class="text-left text-weight-regular">Outside {{ view.window.start }}–{{ view.window.end }}</th>
                  <td v-for="(count, i) in outsideCounts" :key="rows[i].key" class="text-right">{{ formatCount(count) }}</td>
                  <td class="text-right">{{ formatCount(sum(outsideCounts)) }}</td>
                </tr>
                <tr class="heatmap-table__summary">
                  <th scope="row" class="text-left text-weight-regular">Unknown or invalid year</th>
                  <td v-for="row in data.rows" :key="row.library ?? 'rest'" class="text-right">{{ formatCount(row.unknownYearCount) }}</td>
                  <td class="text-right">{{ formatCount(sum((data.rows ?? []).map(r => r.unknownYearCount))) }}</td>
                </tr>
                <tr class="heatmap-table__total">
                  <th scope="row" class="text-left">All documents</th>
                  <td v-for="row in data.rows" :key="row.library ?? 'rest'" class="text-right">{{ formatCount(row.totalDocuments) }}</td>
                  <td class="text-right">{{ formatCount(data.totalDocuments) }}</td>
                </tr>
              </tbody>
            </q-markup-table>
          </div>
        </q-expansion-item>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * Publication period × source library (#361): loaded on request (it costs about as much as the
 * other counts again) and again whenever the counted documents change; the periods follow the
 * timeline's view (`view`), which needs no request. A newer request replaces an older one,
 * whose late answer is ignored; leaving aborts the request in flight.
 */
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import type { DocumentFilters, LibraryYearDistribution } from 'src/generated/api'
import { apiErrorMessage, isAbortError, useApi } from 'src/shared/api'
import VegaChart from 'src/shared/visualization/VegaChart.vue'
import { heatmapRows, heatmapSpec, heatmapTableRows } from './libraryHeatmap'
import { binsName, widthName, type YearWindow } from './timeline'

const props = defineProps<{
  /** The filters of the counts shown on the page. */
  filters: DocumentFilters
  /** The timeline's shown window and bin width. */
  view: { window: YearWindow, width: number }
}>()

const api = useApi().default
const data = shallowRef<LibraryYearDistribution | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
let controller: AbortController | null = null

const numberFormat = new Intl.NumberFormat('en')
const formatCount = (n: number) => numberFormat.format(n)
const sum = (counts: number[]) => counts.reduce((a, b) => a + b, 0)

async function load () {
  controller?.abort()
  const current = new AbortController()
  controller = current
  loading.value = true
  error.value = null
  try {
    const result = await api.corpusLibraryYearsApiAnalyticsCorpusLibraryYearsPost(
      { corpusDistributionsRequest: { filters: props.filters } }, { signal: current.signal })
    if (controller !== current) return
    data.value = result
  } catch (e) {
    if (controller !== current || isAbortError(e)) return
    console.error('Loading the library × period counts failed', e)
    const message = await apiErrorMessage(e, 'The documents per library and period could not be counted.')
    if (controller !== current) return
    data.value = null
    error.value = message
  } finally {
    if (controller === current) {
      controller = null
      loading.value = false
    }
  }
}

watch(() => props.filters, load, { immediate: true })
onBeforeUnmount(() => {
  controller?.abort()
  controller = null
})

const rows = computed(() => heatmapRows(data.value?.rows ?? [], props.view.window, props.view.width))
const tableRows = computed(() => heatmapTableRows(rows.value, props.view.width))
const spec = computed(() => heatmapSpec(rows.value, props.view.width, props.view.window))

/** Per row: documents with a valid year outside the shown window. */
const outsideCounts = computed(() => (data.value?.rows ?? []).map((row, i) =>
  sum(row.years.map(y => y.count)) - sum(rows.value[i]?.bins.map(b => b.count) ?? [])))

const notShown = computed(() => {
  const outside = sum(outsideCounts.value)
  const unknown = sum((data.value?.rows ?? []).map(r => r.unknownYearCount))
  const parts = [
    outside ? `${formatCount(outside)} outside these years` : '',
    unknown ? `${formatCount(unknown)} without a valid year` : ''
  ].filter(Boolean)
  return parts.length ? `Not shown: ${parts.join(', ')} (see the table).` : ''
})
</script>

<style scoped lang="scss">
.library-heatmap__status {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
  color: #4a5568;
}

.library-heatmap__unavailable {
  background: #fff8e1;
  border-radius: 8px;
  padding: 12px;
  margin: 8px 0 0;
}

.library-heatmap__note {
  color: #4a5568;
  font-size: 0.85rem;
  margin: 0 0 8px;
}

.library-heatmap--stale {
  opacity: 0.55;
  transition: opacity 0.2s;
}

.library-heatmap__table {
  margin-top: 8px;
}

.library-heatmap__scroll {
  overflow-x: auto;
  max-width: 100%;
}

.heatmap-table {
  min-width: max-content;
}

.heatmap-table__gap th,
.heatmap-table__summary th {
  font-style: italic;
}

.heatmap-table__total th,
.heatmap-table__total td {
  font-weight: 600;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
