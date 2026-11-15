<template>
  <div
    ref="root"
    class="kwic"
    :class="{ 'kwic--attributes': attributes.length > 0, 'kwic--scrolled': scrolled }"
    data-testid="kwic"
    @scroll.passive="onScroll"
  >
    <p :id="helpId" class="sr-only">
      Arrow keys move between rows, Enter shows the annotation in its document, Space checks the row.
    </p>
    <div
      class="kwic__grid"
      :class="{ 'kwic__grid--attribute': attributes.length > 0 }"
      :style="attributes.length ? { '--kwic-attributes': attributes.length } : undefined"
      role="grid"
      aria-label="Annotations in context"
      :aria-rowcount="rows.length + 1"
      :aria-describedby="helpId"
      :aria-busy="loading ? 'true' : undefined"
      @keydown="onKeydown"
    >
      <div class="kwic__row kwic__row--head" role="row">
        <div class="kwic__cell kwic__check" role="columnheader">
          <q-checkbox
            dense
            size="sm"
            :model-value="pageSelection"
            :disable="!rows.length"
            aria-label="Check all rows on this page"
            @update:model-value="value => emit('select-page', !!value)"
          />
        </div>
        <div
          v-for="column in TEXT_COLUMNS"
          :key="column.field"
          class="kwic__cell kwic__head"
          :class="column.class"
          role="columnheader"
          :aria-sort="ariaSort(column.sort)"
          :data-testid="`kwic-head-${column.id}`"
        >
          <HeaderControls
            :label="column.label"
            :sortable="column.sort !== null"
            :sort-state="sortState(column.sort)"
            :sort-disabled="ranked"
            :not-sortable-hint="column.sort === null ? NOT_SORTABLE_YET : undefined"
            :filter-label="filterLabel(column.field)"
            :filter-active="filterActive(column.field)"
            :filter-disabled="textFilterDisabled"
            :filter-hint="textFilterDisabled ? 'The text is ranked by meaning, not matched as words' : undefined"
            :testid="column.id"
            @sort="sortBy(column.sort)"
            @filter="emit('filter', column.field)"
          />
        </div>
        <div
          v-for="attribute in attributes"
          :key="attribute.id"
          class="kwic__cell kwic__attribute"
          role="columnheader"
          :title="`${attribute.name} (${NOT_SORTABLE_YET.toLowerCase()})`"
          data-testid="kwic-attribute-head"
        >
          {{ attribute.name }}
        </div>
        <div class="kwic__cell kwic__meta kwic__head" role="columnheader">{{ rankStart !== null ? 'Rank · tag · status' : 'Tag · status' }}</div>
        <div
          v-for="column in DOCUMENT_COLUMNS"
          :key="column.field"
          class="kwic__cell kwic__head"
          :class="column.class"
          role="columnheader"
          :aria-sort="ariaSort(column.sort)"
          :data-testid="`kwic-head-${column.id}`"
        >
          <HeaderControls
            :label="column.label"
            sortable
            :sort-state="sortState(column.sort)"
            :sort-disabled="ranked"
            :filter-label="filterLabel(column.field)"
            :filter-active="filterActive(column.field)"
            :testid="column.id"
            @sort="sortBy(column.sort)"
            @filter="emit('filter', column.field)"
          />
        </div>
      </div>

      <div
        v-for="(row, index) in rows"
        :key="row.id"
        :ref="el => setRowEl(row.id, el as HTMLElement | null)"
        class="kwic__row"
        :class="{
          'kwic__row--focused': row.id === focusedId,
          'kwic__row--selected': selected.has(row.id),
          'kwic__row--rejected': row.type === SpanType.neg
        }"
        role="row"
        :aria-selected="selected.has(row.id) ? 'true' : 'false'"
        :aria-current="row.id === focusedId ? 'true' : undefined"
        :tabindex="index === activeIndex ? 0 : -1"
        :data-annotation-id="row.id"
        data-testid="kwic-row"
        @click="emit('open', row)"
        @focus="activeIndex = index"
      >
        <q-menu v-if="similar" context-menu touch-position data-testid="kwic-row-menu">
          <q-list dense style="min-width: 180px">
            <q-item v-close-popup clickable data-testid="kwic-row-open" @click="emit('open', row)">
              <q-item-section avatar><q-icon name="menu_book" /></q-item-section>
              <q-item-section>Show in document</q-item-section>
            </q-item>
            <q-item v-close-popup clickable data-testid="kwic-row-similar" @click="emit('similar', row)">
              <q-item-section avatar><q-icon name="join_inner" /></q-item-section>
              <q-item-section>Find similar</q-item-section>
            </q-item>
          </q-list>
        </q-menu>
        <div class="kwic__cell kwic__check" role="gridcell" @click.stop>
          <q-checkbox
            dense
            size="sm"
            tabindex="-1"
            :model-value="selected.has(row.id)"
            :aria-label="`Check ${rowLabel(row)}`"
            @update:model-value="value => emit('toggle', row.id, !!value)"
          />
        </div>
        <!-- One cell under the three text headers, a row of its own: the annotation centered,
             the left context right before it and the right context right after it, so the row
             reads as continuous text (#665). -->
        <div class="kwic__text" role="gridcell" aria-colspan="3" data-testid="kwic-text">
          <span class="kwic__left"><span dir="ltr" class="kwic__ltr"><template v-for="(part, i) in marked(lineText(row.leftContext, true), inContext)" :key="i"><mark v-if="part.match" class="kwic__match">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span></span>
          <span class="kwic__key" :title="row.text ?? undefined">
            <span v-if="row.text !== null && row.text !== undefined" class="kwic__key-text"><template v-for="(part, i) in marked(lineText(row.text), inText)" :key="i"><mark v-if="part.match" class="kwic__match">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span>
            <span v-else class="kwic__missing">{{ missingText(row) }}</span>
          </span>
          <span class="kwic__right"><template v-for="(part, i) in marked(lineText(row.rightContext), inContext)" :key="i"><mark v-if="part.match" class="kwic__match">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span>
        </div>
        <div
          v-for="attribute in attributes"
          :key="attribute.id"
          class="kwic__cell kwic__attribute"
          role="gridcell"
          :data-attribute-id="attribute.id"
          data-testid="kwic-attribute"
          @click.stop
        >
          <q-btn
            v-if="!cannotAssign(attribute, row)"
            flat
            dense
            no-caps
            tabindex="-1"
            class="kwic__attribute-button"
            :loading="pending.has(row.id)"
            :aria-label="`${attribute.name} of ${rowLabel(row)}: ${heldLabel(attribute, row)}. Change`"
            data-testid="kwic-attribute-edit"
          >
            <AttributeValueChips :attribute="attribute" :ids="row.attributes?.[attribute.id]" empty-label="Assign…" line />
            <q-menu
              anchor="bottom left"
              self="top left"
              :model-value="openPicker === pickerKey(row, attribute)"
              @update:model-value="(open: boolean) => setPicker(pickerKey(row, attribute), open)"
            >
              <AttributeValuePicker
                :attribute="attribute"
                :current="row.attributes?.[attribute.id] ?? []"
                :busy="pending.has(row.id)"
                @change="change => emit('assign', row, attribute, change, ok => picked(row, attribute, ok))"
              />
            </q-menu>
          </q-btn>
          <span v-else :title="cannotAssign(attribute, row) ?? undefined">
            <AttributeValueChips
              v-if="row.attributes?.[attribute.id]?.length"
              :attribute="attribute"
              :ids="row.attributes[attribute.id]"
              :inapplicable="!applies(attribute, row)"
              line
            />
            <span v-else class="kwic__missing" aria-hidden="true">–</span>
            <span class="sr-only">{{ cannotAssign(attribute, row) }}</span>
          </span>
        </div>
        <div class="kwic__cell kwic__meta" role="gridcell">
          <span v-if="rankStart !== null" class="kwic__rank" data-testid="kwic-rank">#{{ rankStart + index }}</span>
          <span class="kwic__tag" :title="tagName(row)">
            <span class="kwic__tag-dot" :style="{ backgroundColor: tagColor(row) }" aria-hidden="true" />
            {{ tagName(row) }}
          </span>
          <span class="kwic__status" :class="`kwic__status--${row.type}`">{{ statusLabel(row.type) }}</span>
        </div>
        <div class="kwic__cell kwic__source" role="gridcell" :title="sourceLabel(row)">
          <span v-if="row.documentAvailable" class="kwic__title">{{ row.documentTitle || 'Untitled document' }}</span>
          <span v-else class="kwic__missing">Source unavailable</span>
        </div>
        <div class="kwic__cell kwic__year" role="gridcell">
          <template v-if="row.documentAvailable">{{ row.documentYear ?? 'n.d.' }}</template>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
/** The fields a column header's filter button brings up (#665): the text search in the
 * annotation or its context (#663 scopes; left and right context are one field), the source or
 * the publication years. */
export type FilterField = 'annotation' | 'context' | 'source' | 'year'
</script>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { QBtn, QCheckbox, QIcon, QItem, QItemSection, QList, QMenu, ClosePopup as vClosePopup } from 'quasar'
import {
  AnnotationSort, Cardinality, RetrievalMode, SpanType, TextScope, TextStatus, type AnnotationListRow, type Attribute, type Tag
} from 'src/generated/api'
import type { ConcordanceFilters } from './concordanceStore'
import HeaderControls, { type SortState } from './KwicHeaderControls.vue'
import { markMatches, queryWords, type TextPart } from './textMatches'
import AttributeValueChips from 'src/features/attributes/AttributeValueChips.vue'
import AttributeValuePicker from 'src/features/attributes/AttributeValuePicker.vue'
import { applies, cannotAssign, heldName, heldValues, type AssignChange } from 'src/features/attributes/assignment'

const props = withDefaults(defineProps<{
  rows: AnnotationListRow[]
  tags: Tag[]
  selected: Set<string>
  /** The row whose source context is open. */
  focusedId?: string | null
  loading?: boolean
  /** The attributes whose values are shown in columns of their own and assigned there (#331,
   * #537), in this order. */
  attributes?: Attribute[]
  /** Annotations with an assignment under way. */
  pending?: Set<string>
  /** The lexical query whose matches are marked (#663), and where it searches. */
  query?: string
  queryScope?: TextScope
  /** The rank of the first row, in a ranked result (#664); null shows no ranks. */
  rankStart?: number | null
  /** Rows offer Find similar in their context menu (#664). */
  similar?: boolean
  /** The query: its sort and the filters the column headers show as active (#665). */
  filters?: ConcordanceFilters | null
}>(), {
  focusedId: null,
  loading: false,
  attributes: () => [],
  pending: () => new Set(),
  query: '',
  queryScope: TextScope.annotation,
  rankStart: null,
  similar: false,
  filters: null
})

const emit = defineEmits<{
  /** Show the row's annotation in its document (row click, Enter). */
  open: [row: AnnotationListRow]
  /** List the annotations most similar to the row's (its context menu, #664). */
  similar: [row: AnnotationListRow]
  /** Check or uncheck one row (its checkbox, Space); separate from opening. */
  toggle: [id: string, value: boolean]
  'select-page': [value: boolean]
  /** Assign values of a shown attribute to the row's annotation; `done` says whether it was saved. */
  assign: [row: AnnotationListRow, attribute: Attribute, change: AssignChange, done:(ok: boolean) => void]
  /** Order the whole result by a column (its header): the first activation ascending, the next
   * one of the same column descending, and so on. */
  sort: [sort: AnnotationSort, descending: boolean]
  /** Show the filter of a column (its header's filter button). */
  filter: [field: FilterField]
}>()

// The column headers (#665). Left and right context sort by their nearest words in #666.
const NOT_SORTABLE_YET = 'Not sortable yet'
const TEXT_COLUMNS: { id: string, label: string, field: FilterField, sort: AnnotationSort | null, class: string }[] = [
  { id: 'left', label: 'Left context', field: 'context', sort: null, class: 'kwic__left' },
  { id: 'annotation', label: 'Annotation', field: 'annotation', sort: AnnotationSort.text, class: 'kwic__key' },
  { id: 'right', label: 'Right context', field: 'context', sort: null, class: 'kwic__right' }
]
const DOCUMENT_COLUMNS: { id: string, label: string, field: FilterField, sort: AnnotationSort, class: string }[] = [
  { id: 'source', label: 'Source', field: 'source', sort: AnnotationSort.document, class: 'kwic__source' },
  { id: 'year', label: 'Year', field: 'year', sort: AnnotationSort.year, class: 'kwic__year' }
]

const ranked = computed(() => !!props.filters && props.filters.mode !== RetrievalMode.lexical)
const textFilterDisabled = computed(() => props.filters?.mode === RetrievalMode.semantic)

function sortState (sort: AnnotationSort | null): SortState {
  const f = props.filters
  if (!f || sort === null || ranked.value || f.sort !== sort) return null
  return f.descending ? 'descending' : 'ascending'
}

function ariaSort (sort: AnnotationSort | null): 'ascending' | 'descending' | 'none' | undefined {
  if (sort === null) return undefined
  return sortState(sort) ?? 'none'
}

function sortBy (sort: AnnotationSort | null) {
  if (sort === null || ranked.value) return
  emit('sort', sort, sortState(sort) === 'ascending')
}

const FILTER_LABELS: Record<FilterField, string> = {
  annotation: 'Filter by words in the annotation',
  context: 'Filter by words in the context',
  source: 'Filter by source',
  year: 'Filter by publication year'
}

function filterActive (field: FilterField): boolean {
  const f = props.filters
  if (!f) return false
  if (field === 'source') return f.documentIds.length > 0
  if (field === 'year') return f.documentFilters.yearMin != null || f.documentFilters.yearMax != null
  if (!f.text.trim() || f.mode === RetrievalMode.semantic || f.mode === RetrievalMode.hybrid) return false
  return f.textScope === TextScope.both ||
    f.textScope === (field === 'annotation' ? TextScope.annotation : TextScope.context)
}

function filterLabel (field: FilterField): string {
  return filterActive(field) ? `${FILTER_LABELS[field]} (active)` : FILTER_LABELS[field]
}

// Scrolled sideways (attribute columns): each row's text sticks next to the checkbox as its
// annotation alone, so the attribute columns scroll in beside it.
const scrolled = ref(false)
function onScroll (event: Event) {
  scrolled.value = (event.target as HTMLElement).scrollLeft > 0
}

const helpId = `kwic-help-${Math.random().toString(36).slice(2, 8)}`

// Lexical matches, marked only in the fields the query searched.
const words = computed(() => queryWords(props.query))
const inText = computed(() => props.queryScope !== TextScope.context)
const inContext = computed(() => props.queryScope !== TextScope.annotation)
function marked (text: string | null | undefined, searched: boolean): TextPart[] {
  return markMatches(text ?? '', searched ? words.value : [])
}

/** A context or annotation as one line of the row: line breaks as spaces; `endKept`: its trailing spaces (before
 * the annotation) as no-break spaces, which neither collapse at the line end nor move to the far
 * side of the right-to-left cell the left context is cut in. */
function lineText (text: string | null | undefined, endKept = false): string {
  const line = (text ?? '').replace(/[\n\r\t\f\v\u2028\u2029]/g, ' ')
  return endKept ? line.replace(/\s+$/, spaces => '\u00a0'.repeat(spaces.length)) : line
}
const tagsById = computed(() => new Map(props.tags.map(t => [t.id, t])))

const pageSelection = computed<boolean | null>(() => {
  const checked = props.rows.filter(r => props.selected.has(r.id)).length
  if (!checked) return false
  return checked === props.rows.length ? true : null
})

function tagName (row: AnnotationListRow): string {
  return (row.tagId && tagsById.value.get(row.tagId)?.name) || 'Unknown tag'
}

function tagColor (row: AnnotationListRow): string {
  return (row.tagId && tagsById.value.get(row.tagId)?.color) || '#9e9e9e'
}

function statusLabel (type: SpanType | null | undefined): string {
  if (type === SpanType.pos) return 'Confirmed'
  if (type === SpanType.auto) return 'Proposal'
  if (type === SpanType.neg) return 'Rejected'
  return 'Unknown status'
}

function missingText (row: AnnotationListRow): string {
  if (row.textStatus === TextStatus.failed) return 'Text could not be read'
  if (row.textStatus === TextStatus.invalid) return 'Range does not fit the text'
  return 'Text not available yet'
}

function sourceLabel (row: AnnotationListRow): string {
  if (!row.documentAvailable) return 'Source unavailable'
  return `${row.documentTitle || 'Untitled document'}, ${row.documentYear ?? 'no year'}`
}

function rowLabel (row: AnnotationListRow): string {
  const text = row.text ?? missingText(row)
  return `${text} (${tagName(row)}, ${statusLabel(row.type)}, ${sourceLabel(row)})`
}

// The open value picker (one at a time, of one row's one attribute). Choosing one value of a
// single-valued attribute is a complete choice: its picker closes once the assignment is saved,
// and stays open on a failure so its message can be acted on. A multi-valued one stays open for
// further choices.
const openPicker = ref<string | null>(null)
const pickerKey = (row: AnnotationListRow, attribute: Attribute) => `${row.id}\n${attribute.id}`
function setPicker (key: string, open: boolean) {
  if (open) openPicker.value = key
  else if (openPicker.value === key) openPicker.value = null
}
function picked (row: AnnotationListRow, attribute: Attribute, ok: boolean) {
  if (ok && attribute.cardinality === Cardinality.single) setPicker(pickerKey(row, attribute), false)
}

function heldLabel (attribute: Attribute, row: AnnotationListRow): string {
  const held = heldValues(attribute, row.attributes?.[attribute.id])
  return held.length ? held.map(heldName).join(', ') : 'not assigned'
}

// Keyboard: one row is in the tab order; the arrow keys move it.
const activeIndex = ref(0)
const rowEls = new Map<string, HTMLElement>()
function setRowEl (id: string, el: HTMLElement | null) {
  if (el) rowEls.set(id, el)
  else rowEls.delete(id)
}

watch(() => props.rows, (rows) => {
  const focused = rows.findIndex(r => r.id === props.focusedId)
  activeIndex.value = focused >= 0 ? focused : Math.min(activeIndex.value, Math.max(0, rows.length - 1))
})

function focusRow (index: number) {
  const row = props.rows[index]
  if (!row) return
  activeIndex.value = index
  // Into view vertically only: a list scrolled sideways keeps its scroll (the row is wider).
  void nextTick(() => {
    const el = rowEls.get(row.id)
    el?.focus({ preventScroll: true })
    el?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  })
}

function onKeydown (event: KeyboardEvent) {
  const index = activeIndex.value
  const row = props.rows[index]
  if (!row || (event.target as HTMLElement).getAttribute('role') !== 'row') return
  const moves: Record<string, number> = {
    ArrowDown: index + 1,
    ArrowUp: index - 1,
    Home: 0,
    End: props.rows.length - 1,
    PageDown: index + 10,
    PageUp: index - 10
  }
  if (event.key in moves) {
    event.preventDefault()
    focusRow(Math.max(0, Math.min(props.rows.length - 1, moves[event.key])))
  } else if (event.key === 'Enter') {
    event.preventDefault()
    emit('open', row)
  } else if (event.key === ' ') {
    event.preventDefault()
    emit('toggle', row.id, !props.selected.has(row.id))
  }
}

/** Scrolls the row into view and gives it keyboard focus. */
function reveal (id: string) {
  const index = props.rows.findIndex(r => r.id === id)
  if (index < 0) return
  activeIndex.value = index
  void nextTick(() => {
    const el = rowEls.get(id)
    el?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
    el?.focus({ preventScroll: true })
  })
}

// A wrapped annotation's box keeps the width it was given, not that of its longest line, which
// would leave a gap before the right context and push the annotation off center. So each wrapped
// annotation gets the width of its longest line, measured after rendering and on every resize
// (all widths reset, then all measured, then all set: one layout pass, not one per row).
const root = ref<HTMLElement | null>(null)
let fitFrame = 0
function fitWrappedKeys () {
  fitFrame = 0
  const keys = Array.from(root.value?.querySelectorAll<HTMLElement>('.kwic__text .kwic__key') ?? [])
  for (const key of keys) key.style.width = ''
  const widths = keys.map(key => {
    const lines = Array.from(key.firstElementChild?.getClientRects() ?? [])
    if (lines.length < 2) return null
    return Math.ceil(Math.max(...lines.map(r => r.width))) + 1
  })
  keys.forEach((key, i) => { if (widths[i] !== null) key.style.width = `${widths[i]}px` })
}
function scheduleFit () {
  if (!fitFrame && typeof requestAnimationFrame !== 'undefined') fitFrame = requestAnimationFrame(fitWrappedKeys)
}
let resizes: ResizeObserver | null = null
onMounted(() => {
  scheduleFit()
  if (typeof ResizeObserver !== 'undefined' && root.value) {
    resizes = new ResizeObserver(scheduleFit)
    resizes.observe(root.value)
  }
})
onBeforeUnmount(() => {
  resizes?.disconnect()
  if (fitFrame) cancelAnimationFrame(fitFrame)
})
watch(() => [props.rows, props.query, props.queryScope, props.attributes.length], () => { void nextTick(scheduleFit) })

defineExpose({ reveal })
</script>

<style scoped>
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.kwic {
  /* The columns follow the space the list has (it narrows when the sidebar opens). */
  container-type: inline-size;
}

/* Attribute columns get at most their share of a budget, so several of them leave the context
   readable; once the list is narrower than the minimums it scrolls sideways (#537). */
.kwic--attributes {
  /* Also the containing block of the cells' screen-reader texts, which would widen the page. */
  position: relative;
  overflow-x: auto;
}

/* check | left context | annotation | right context | [attributes] | tag · status | source | year.
   The context columns share the text area equally, so the annotation header is centered over
   it, as each row's annotation is (#665). */
.kwic__grid {
  --kwic-context-min: 0px;
  /* The annotation column never collapses below its header's name and controls (cut). */
  --kwic-key-min: 6.5rem;
  --kwic-text:
    minmax(var(--kwic-context-min), 1fr) minmax(var(--kwic-key-min), auto) minmax(var(--kwic-context-min), 1fr);
  display: grid;
  grid-template-columns: 2rem var(--kwic-text) fit-content(9rem) fit-content(13rem) auto;
  font-size: 0.9rem;
}

/* With attribute columns (their count in --kwic-attributes) after the right context. */
.kwic__grid--attribute {
  --kwic-context-min: 8rem;
  --kwic-attribute-min: 6rem;
  --kwic-attribute-max: min(14rem, 30rem / var(--kwic-attributes));
  grid-template-columns:
    2rem var(--kwic-text)
    repeat(var(--kwic-attributes), fit-content(max(var(--kwic-attribute-min), var(--kwic-attribute-max))))
    fit-content(9rem) fit-content(13rem) auto;
}

.kwic__attribute {
  font-size: 0.78rem;
}

/* Minimum widths, so the values stay identifiable (the list scrolls instead). */
.kwic__grid--attribute .kwic__cell.kwic__attribute {
  min-width: var(--kwic-attribute-min);
}

/* Opaque rows, for the sticky cells to inherit. Without specificity of its own (:where), so the
   hover, selected and focused backgrounds below still win; the header's hover must win over
   its own `none` below, so it keeps the full specificity. */
:where(.kwic__grid--attribute) .kwic__row,
.kwic__grid--attribute .kwic__row--head:hover {
  background: #fff;
}

/* The row's checkbox and annotation stay in view while the attribute columns scroll under: the
   whole text cell sticks (a sticky box stays within its parent's box, so it is the row's grid item,
   not the annotation inside it), shrunk to the annotation once the list is scrolled. */
.kwic__grid--attribute .kwic__check,
.kwic__grid--attribute .kwic__row--head .kwic__key,
.kwic__grid--attribute .kwic__text {
  position: sticky;
  z-index: 1;
  background: inherit;
}

.kwic__grid--attribute .kwic__check {
  left: 0;
}

.kwic__grid--attribute .kwic__row--head .kwic__key,
.kwic__grid--attribute .kwic__text {
  left: 2rem;
}

.kwic--scrolled .kwic__text {
  justify-self: start;
}

.kwic--scrolled .kwic__text .kwic__left,
.kwic--scrolled .kwic__text .kwic__right {
  display: none;
}

.kwic--scrolled .kwic__text .kwic__key {
  max-width: min(14rem, 60vw);
}

/* They cover the row's own marks, so they draw their part of them. */
.kwic__grid--attribute .kwic__row--focused .kwic__check {
  box-shadow: inset 3px 0 0 var(--q-primary);
}

.kwic__grid--attribute .kwic__row:focus-visible .kwic__check {
  box-shadow: inset 2px 2px 0 var(--q-primary), inset 0 -2px 0 var(--q-primary);
}

.kwic__grid--attribute .kwic__row:focus-visible .kwic__text {
  box-shadow: inset 0 2px 0 var(--q-primary), inset 0 -2px 0 var(--q-primary);
}

.kwic__attribute-button {
  max-width: 100%;
  min-height: 0;
  padding: 0 2px;
  font-weight: 400;
}

.kwic__row {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: subgrid;
  align-items: center;
  min-height: 2rem;
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  cursor: pointer;
  outline: none;
}

.kwic__row:hover {
  background: #f5f7fa;
}

.kwic__row:focus-visible {
  box-shadow: inset 0 0 0 2px var(--q-primary);
}

.kwic__row--selected {
  background: #eef4fd;
}

.kwic__row--focused {
  background: #fff8d6;
  box-shadow: inset 3px 0 0 var(--q-primary);
}

.kwic__row--head {
  cursor: default;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(0, 0, 0, 0.6);
  border-bottom: 1px solid rgba(0, 0, 0, 0.2);
}

.kwic__row--head:hover {
  background: none;
}

.kwic__cell {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  padding: 2px 4px;
}

.kwic__row--head .kwic__left {
  text-align: right;
}

.kwic__row--head .kwic__key {
  text-align: center;
}

/* The text cell: the annotation between two context boxes that share the rest of the width
   equally, so the annotation is centered whatever its length; the contexts run right up to it
   (no gap or padding) and are cut at their outer ends only. */
.kwic__text {
  grid-column: 2 / span 3;
  display: flex;
  align-items: baseline;
  min-width: 0;
  overflow: hidden;
  padding: 7px 4px;
  line-height: 1.25;
  background: inherit;
}

.kwic__text .kwic__left,
.kwic__text .kwic__right {
  flex: 1 1 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  /* Spaces kept as in the text (`lineText`), also those next to the annotation. */
  white-space: pre;
  color: #444;
}

/* Cut at its start, so the words next to the annotation stay visible. */
.kwic__text .kwic__left {
  direction: rtl;
  text-align: right;
}

.kwic__ltr {
  direction: ltr;
}

/* At most 60 % of the text, so some context shows on both sides; longer annotations wrap to a
   second line and are cut after it (the full text is in the sidebar and the title). */
.kwic__text .kwic__key {
  flex: 0 1 auto;
  max-width: 60%;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  /* Its own spaces kept too (an annotation may start or end with one); wraps at them, in lines
     of even length, and gets the width of its longest line (`fitWrappedKeys`). */
  white-space: pre-wrap;
  text-wrap: balance;
  overflow-wrap: anywhere;
  font-weight: 600;
  color: #1f2a37;
}

.kwic__key-text {
  padding: 1px 0;
  border-radius: 2px;
  background: rgba(255, 213, 79, 0.35);
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}

/* A lexical match: underlined, distinct from the annotation's own highlight. */
.kwic__match {
  background: none;
  color: inherit;
  font-weight: 700;
  text-decoration: underline;
  text-decoration-color: var(--q-primary);
  text-decoration-thickness: 2px;
  text-underline-offset: 2px;
}

.kwic__row--rejected .kwic__key-text {
  text-decoration: line-through;
  text-decoration-color: rgba(0, 0, 0, 0.45);
}

.kwic__missing {
  font-style: italic;
  font-weight: 400;
  color: rgba(0, 0, 0, 0.55);
}

.kwic__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
}

.kwic__row--head .kwic__meta {
  font-size: inherit;
}

.kwic__rank {
  margin-right: 6px;
  font-variant-numeric: tabular-nums;
  color: rgba(0, 0, 0, 0.65);
}

.kwic__tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kwic__tag-dot {
  flex: 0 0 auto;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.kwic__status {
  flex: 0 0 auto;
  padding: 0 5px;
  border-radius: 3px;
  border: 1px solid currentColor;
  font-size: 0.7rem;
  line-height: 1.4;
}

.kwic__status--pos {
  color: #1b5e20;
}

.kwic__status--auto {
  color: #8a5300;
  border-style: dashed;
}

.kwic__status--neg {
  color: #8e1b1b;
}

.kwic__row:not(.kwic__row--head) .kwic__source,
.kwic__row:not(.kwic__row--head) .kwic__year {
  font-size: 0.78rem;
  color: rgba(0, 0, 0, 0.7);
}

.kwic__year {
  font-variant-numeric: tabular-nums;
}

/* Secondary columns give way first when the list narrows: zero wide, their values still read
   by assistive technology; their headers' controls are hidden (the toolbar has them). */
@container (max-width: 900px) {
  .kwic__grid {
    grid-template-columns: 2rem var(--kwic-text) 0 fit-content(9rem) auto;
  }
  .kwic__grid--attribute {
    --kwic-context-min: 6rem;
    --kwic-attribute-max: min(10rem, 20rem / var(--kwic-attributes));
    grid-template-columns:
      2rem var(--kwic-text)
      repeat(var(--kwic-attributes), fit-content(max(var(--kwic-attribute-min), var(--kwic-attribute-max))))
      0 fit-content(9rem) auto;
  }
  .kwic__meta {
    padding: 0;
  }
  .kwic__row--head .kwic__meta {
    visibility: hidden;
  }
}

@container (max-width: 560px) {
  .kwic__grid {
    grid-template-columns: 2rem var(--kwic-text) 0 0 0;
    font-size: 0.85rem;
  }
  .kwic__grid--attribute {
    --kwic-context-min: 4rem;
    --kwic-key-min: 5.5rem;
    --kwic-attribute-min: 5rem;
    --kwic-attribute-max: 7rem;
    grid-template-columns:
      2rem var(--kwic-text)
      repeat(var(--kwic-attributes), fit-content(max(var(--kwic-attribute-min), var(--kwic-attribute-max))))
      0 0 0;
  }
  .kwic__source,
  .kwic__year {
    padding: 0;
  }
  .kwic__row--head .kwic__source,
  .kwic__row--head .kwic__year {
    visibility: hidden;
  }
}
</style>
