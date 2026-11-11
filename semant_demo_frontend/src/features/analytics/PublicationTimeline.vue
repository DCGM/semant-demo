<template>
  <div class="timeline" data-testid="corpus-timeline">
    <p v-if="hiddenText" class="timeline__outside" data-testid="timeline-outside">
      <q-icon name="visibility_off" size="18px" class="q-mr-xs" />
      <span>Not shown: {{ hiddenText }}.</span>
      <q-btn
        v-if="!isFull" flat dense no-caps color="primary" label="Show full range" class="q-ml-xs"
        data-testid="timeline-show-full" @click="showFull"
      />
    </p>

    <div class="timeline__toolbar" role="toolbar" aria-label="Publication timeline view">
      <span class="timeline__window" data-testid="timeline-window" aria-live="polite">
        {{ windowLabel }} · {{ binsName(width) }}
      </span>
      <div class="timeline__buttons">
        <q-btn dense flat round icon="chevron_left" aria-label="Show earlier years" :disable="atStart" @click="pan(-1)">
          <q-tooltip>Earlier years</q-tooltip>
        </q-btn>
        <q-btn dense flat round icon="zoom_in" aria-label="Zoom in" :disable="!canZoomIn" data-testid="timeline-zoom-in" @click="zoom(0.5)">
          <q-tooltip>Zoom in</q-tooltip>
        </q-btn>
        <q-btn dense flat round icon="zoom_out" aria-label="Zoom out" :disable="isFull" data-testid="timeline-zoom-out" @click="zoom(2)">
          <q-tooltip>Zoom out</q-tooltip>
        </q-btn>
        <q-btn dense flat round icon="chevron_right" aria-label="Show later years" :disable="atEnd" @click="pan(1)">
          <q-tooltip>Later years</q-tooltip>
        </q-btn>
        <q-btn dense flat no-caps color="primary" label="Reset zoom" :disable="isMain" data-testid="timeline-reset" @click="reset" />
        <q-btn dense flat no-caps color="primary" label="Full range" :disable="isFull" data-testid="timeline-full" @click="showFull" />
      </div>
      <q-btn
        dense outline no-caps color="primary" icon="filter_alt" :label="`Apply ${periodLabel} as filter`"
        data-testid="timeline-apply-period" @click="emit('applyPeriod', period)"
      />
    </div>
    <p class="timeline__hint">
      Click a bar to filter by its years; drag across the chart to zoom into a period. Zooming changes only this chart;
      <template v-if="searches">a filter starts a new search, whose results and counts may differ from these.</template>
      <template v-else>a filter restricts every count on the page.</template>
    </p>

    <div @pointerup="zoomToSelection">
      <VegaChart
        :spec="spec"
        :signals="['period']"
        :clickable="isFilterableBin"
        :label="`Bar chart of ${unit} per ${widthName(width)} from ${windowLabel}; the table below lists the same counts.`"
        @signal="onSignal"
        @item-click="(datum) => emit('applyPeriod', binYears(Number(datum.start)))"
      />
    </div>

    <q-expansion-item
      dense dense-toggle switch-toggle-side class="timeline__table"
      :label="`Show data table (${unit} per ${widthName(width)}, ${windowLabel})`"
      data-testid="timeline-table"
    >
      <q-markup-table flat dense separator="horizontal" class="count-table">
        <caption class="sr-only">{{ unitNoun(unit, 2, true) }} per {{ widthName(width) }} of publication, {{ windowLabel }}</caption>
        <thead>
          <tr>
            <th scope="col" class="text-left">Publication years</th>
            <th scope="col" class="text-right">{{ unitNoun(unit, 2, true) }}</th>
            <th scope="col" class="text-right"><span class="sr-only">Filter</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.key" :class="`count-table__${row.kind}`">
            <th scope="row" class="text-left text-weight-regular">
              {{ row.label }}<span v-if="row.note" class="text-grey-7"> — {{ row.note }}</span>
            </th>
            <td class="text-right">{{ formatCount(row.count) }}</td>
            <td class="text-right">
              <q-btn
                v-if="row.kind === 'bin' && row.count > 0" dense flat no-caps color="primary" label="Filter"
                :aria-label="`Filter by the years ${row.label}`"
                :data-testid="`timeline-filter-${row.key}`" @click="emit('applyPeriod', binYears(Number(row.key.slice(4))))"
              />
            </td>
          </tr>
          <tr class="count-table__unknown">
            <th scope="row" class="text-left text-weight-regular">Unknown or invalid year</th>
            <td class="text-right">{{ formatCount(distribution.unknownCount ?? 0) }}</td>
            <td />
          </tr>
        </tbody>
      </q-markup-table>
    </q-expansion-item>
  </div>
</template>

<script setup lang="ts">
/**
 * The publication-year chart of the corpus overview (#361): opens on the main range, names
 * the documents outside the visible window, and zooms or pans without asking the server
 * (`timeline.ts`). Only "Apply … as filter" changes the counted documents, through the page.
 */
import { computed, shallowRef, watch } from 'vue'
import type { PublicationYearCounts } from 'src/generated/api'
import VegaChart from 'src/shared/visualization/VegaChart.vue'
import {
  alignWindow, binWidthFor, binsName, fullRange, mainRange, outside, panWindow, selectedWindow, timelineBins,
  timelineRows, timelineSpec, unitNoun, widthName, zoomWindow, MIN_SPAN, type CountUnit, type Outside, type YearWindow
} from './timeline'

const props = withDefaults(defineProps<{
  distribution: PublicationYearCounts
  /** What is counted (#620: a search's Passages results count passages). */
  unit?: CountUnit
  /** A filter starts a new search (a text query's charts), said in the hint. */
  searches?: boolean
}>(), { unit: 'documents', searches: false })
const emit = defineEmits<{
  /** These years (inclusive) as the publication-year filter: the shown period or a clicked bin. */
  applyPeriod: [period: YearWindow]
  /** The shown window and bin width, whenever they change (other views follow the timeline). */
  view: [view: { window: YearWindow, width: number }]
}>()

const numberFormat = new Intl.NumberFormat('en')
const formatCount = (n: number) => numberFormat.format(n)
const currentYear = new Date().getFullYear()

const years = computed(() => props.distribution.years ?? [])
const main = computed(() => mainRange(years.value))
const full = computed(() => fullRange(years.value))

/** The window asked for (by zooming, panning or selecting); shown widened to whole bins. */
const view = shallowRef<YearWindow>({ start: 0, end: 0 })
let selection: YearWindow | null = null

// A new population (other filters) opens on its own main range.
watch(main, (range) => { if (range) view.value = range }, { immediate: true })

const width = computed(() => binWidthFor(view.value))
const shown = computed(() => alignWindow(view.value, width.value))
const bins = computed(() => timelineBins(years.value, shown.value, width.value))
const out = computed(() => outside(years.value, shown.value))
const rows = computed(() => timelineRows(bins.value, width.value, out.value, props.unit))
const spec = computed(() => timelineSpec(bins.value, width.value, shown.value, props.unit))
/** A bin with counts can be applied as a filter (a click on its bar or its table row). */
const isFilterableBin = (datum: Record<string, unknown>) => Number(datum.count) > 0 && typeof datum.endExclusive === 'number'

/** The years of the bin starting at `start`: the whole bin, as counted, within valid years. */
function binYears (start: number): YearWindow {
  const bin = bins.value.find(b => b.start === start)
  const end = bin ? bin.endExclusive - 1 : start
  return { start: Math.max(1, start), end: Math.min(currentYear, end) }
}

watch([shown, width], () => emit('view', { window: shown.value, width: width.value }), { immediate: true })

const same = (a: YearWindow | null, b: YearWindow | null) => !!a && !!b && a.start === b.start && a.end === b.end
const covers = (a: YearWindow, b: YearWindow | null) => !!b && a.start <= b.start && a.end >= b.end
const isMain = computed(() => same(view.value, main.value))
const isFull = computed(() => covers(shown.value, full.value))
const atStart = computed(() => !full.value || shown.value.start <= full.value.start)
const atEnd = computed(() => !full.value || shown.value.end >= full.value.end)
const canZoomIn = computed(() => view.value.end - view.value.start + 1 > MIN_SPAN)

const windowLabel = computed(() => `${shown.value.start}–${shown.value.end}`)

/** The shown years as a publication-year filter: whole years from 1 to the current year. */
const period = computed<YearWindow>(() => ({
  start: Math.max(1, shown.value.start),
  end: Math.min(currentYear, shown.value.end)
}))
const periodLabel = computed(() => period.value.start === period.value.end
  ? `${period.value.start}`
  : `${period.value.start}–${period.value.end}`)

const hiddenText = computed(() => {
  const describe = (o: Outside, where: string) => {
    if (!o.count) return null
    const named = o.years.length ? ` (${o.years.length === 1 ? 'year' : 'years'} ${o.years.join(', ')})` : ''
    return `${formatCount(o.count)} ${unitNoun(props.unit, o.count)} ${where}${named}`
  }
  return [describe(out.value.before, `before ${shown.value.start}`), describe(out.value.after, `after ${shown.value.end}`)]
    .filter(Boolean).join('; ')
})

function zoom (factor: number) {
  if (full.value) view.value = zoomWindow(view.value, factor, full.value)
}

function pan (direction: -1 | 1) {
  if (full.value) view.value = panWindow(view.value, direction, full.value)
}

function reset () {
  if (main.value) view.value = main.value
}

function showFull () {
  if (full.value) view.value = full.value
}

/** The period being dragged across the chart; applied as the view when the drag ends. */
function onSignal (_name: string, value: unknown) {
  const range = (value as { start?: [number, number] } | null)?.start
  selection = range ? selectedWindow(range[0], range[1]) : null
}

function zoomToSelection () {
  if (!selection || !full.value) return
  view.value = zoomWindow(selection, 1, full.value)
  selection = null
}
</script>

<style scoped lang="scss">
.timeline__outside {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  background: #e3f2fd;
  border-radius: 8px;
  padding: 4px 12px;
  margin: 0 0 8px;
}

.timeline__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
}

.timeline__window {
  font-weight: 600;
  min-width: 12ch;
}

.timeline__buttons {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
}

.timeline__hint {
  color: #4a5568;
  font-size: 0.85rem;
  margin: 4px 0 8px;
}

.timeline__table {
  margin-top: 8px;
}

.count-table {
  max-width: 560px;
}

/* Long gap labels wrap, so the Inspect column stays inside a phone-wide card. */
.count-table :deep(th),
.count-table :deep(td) {
  white-space: normal;
}

.count-table__gap th,
.count-table__before th,
.count-table__after th,
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
</style>
