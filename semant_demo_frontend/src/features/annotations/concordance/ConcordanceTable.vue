<template>
  <div
    class="kwic"
    :class="{ 'kwic--attributes': attributes.length > 0, 'kwic--scrolled': scrolled, 'kwic--phone': phone }"
    data-testid="kwic"
    @scroll.passive="onScroll"
    @copy="onCopy"
  >
    <p :id="helpId" class="sr-only">
      Arrow keys move between rows, Enter shows the annotation in its document, Space checks the row,
      the context menu key or Shift+F10 opens the row's actions and the filters of its values.
      Alt+C confirms and Alt+R rejects the row, Alt+Down and Alt+Up show the next or previous one.
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
          :key="column.id"
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
        <div class="kwic__cell kwic__review kwic__head" role="columnheader"><span :class="{ 'sr-only': phone }">Status</span></div>
        <div class="kwic__cell kwic__meta kwic__head" role="columnheader">{{ rankStart !== null ? 'Rank · tag' : 'Tag' }}</div>
        <div
          v-for="column in DOCUMENT_COLUMNS"
          :key="column.id"
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
          'kwic__row--menu': row.id === menuOpen,
          'kwic__row--selected': selected.has(row.id),
          'kwic__row--rejected': row.type === SpanType.neg,
          'kwic__row--unmatched': unmatched.has(row.id)
        }"
        :title="unmatched.has(row.id) ? 'No longer matches the filters; it leaves the list when the list is read again' : undefined"
        role="row"
        :aria-selected="selected.has(row.id) ? 'true' : 'false'"
        :aria-current="row.id === focusedId ? 'true' : undefined"
        :tabindex="index === activeIndex ? 0 : -1"
        :data-annotation-id="row.id"
        data-testid="kwic-row"
        @click="onRowClick(row, $event)"
        @contextmenu="prepareMenu(row)"
        v-touch-hold:500="() => onHold(row)"
        @focus="activeIndex = index"
      >
        <!-- The row's actions and the filters of its values (#665): right click (with the words
             selected in its text), the context menu key or Shift+F10, or its menu button; on a phone a
             long press (`onHold`). -->
        <q-menu
          v-if="hasMenu"
          :ref="(el: unknown) => setMenu(row.id, el as QMenu | null)"
          :context-menu="!phone"
          :no-parent-event="phone"
          :touch-position="!phone"
          :anchor="phone ? 'bottom right' : undefined"
          :self="phone ? 'top right' : undefined"
          data-testid="kwic-row-menu"
          :persistent="pressHeld"
          @before-show="onMenuOpening(row)"
          @before-hide="onMenuClosing(row)"
          @hide="onMenuHide(row)"
        >
          <q-list dense class="kwic__menu" :class="{ 'kwic__menu--phone': phone }">
            <q-item clickable data-testid="kwic-row-open" @click="menuAction(row, () => emit('open', row))">
              <q-item-section avatar><q-icon name="menu_book" /></q-item-section>
              <q-item-section>Show in document</q-item-section>
            </q-item>
            <q-item v-if="similar" clickable data-testid="kwic-row-similar" @click="menuAction(row, () => emit('similar', row))">
              <q-item-section avatar><q-icon name="join_inner" /></q-item-section>
              <q-item-section>Find similar</q-item-section>
            </q-item>
            <template v-for="group in menuGroups(row)" :key="group.key">
              <q-separator />
              <q-item-label header class="kwic__menu-group" :data-testid="`kwic-refine-group-${group.key}`">
                <span class="kwic__menu-label">{{ group.label }}</span>
                <span v-if="group.caption" class="kwic__menu-caption">{{ group.caption }}</span>
              </q-item-label>
              <q-item
                v-for="action in group.actions"
                :key="action.key"
                clickable
                :data-testid="`kwic-refine-${action.key}`"
                @click="menuAction(row, () => emit('refine', action.change))"
              >
                <q-item-section avatar><q-icon :name="action.icon" /></q-item-section>
                <q-item-section>{{ action.label }}</q-item-section>
              </q-item>
            </template>
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
            <template v-if="row.text !== null && row.text !== undefined">
              <!-- Read as one text: the halves are flex items, which assistive technology would
                   announce apart ("Jan N ovák"). -->
              <span class="sr-only kwic__key-label">{{ lineText(row.text) }}</span>
              <span v-for="(half, h) in halves(row.text)" :key="h" :class="h ? 'kwic__key-tail' : 'kwic__key-head'" aria-hidden="true"><span dir="ltr" class="kwic__ltr"><template v-for="(part, i) in half" :key="i"><mark v-if="part.match" class="kwic__match">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span></span>
            </template>
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
        <!-- The status as an icon (#690); on a hovered or keyboard-focused row of a desktop its two
             review buttons take its place, the current state pressed, and while the review is
             saved a spinner does. All three share one place in a column of fixed width, so nothing
             moves. A click there never opens or checks the row, nor moves focus. -->
        <div
          class="kwic__cell kwic__review"
          :class="{ 'kwic__review--saving': saving.has(row.id) }"
          role="gridcell"
          :aria-busy="saving.has(row.id) ? 'true' : undefined"
          data-testid="kwic-review"
          @click.stop
        >
          <span
            class="kwic__status"
            :class="`kwic__status--${row.type}`"
            :title="statusLabel(row.type)"
            data-testid="kwic-status"
          ><q-icon :name="statusIcon(row.type)" size="1.15rem" aria-hidden="true" /><span class="sr-only">{{ statusLabel(row.type) }}</span></span>
          <span v-if="!phone" class="kwic__decide" role="group" :aria-label="`Review ${rowLabel(row)}`">
            <q-btn
              v-for="decision in DECISIONS"
              :key="decision.action"
              flat
              round
              dense
              size="sm"
              tabindex="-1"
              :icon="decision.icon"
              class="kwic__decision"
              :class="[`kwic__decision--${decision.action}`, { 'kwic__decision--pressed': row.type === decision.state }]"
              :aria-pressed="row.type === decision.state ? 'true' : 'false'"
              :aria-label="row.type === decision.state ? decision.done : decision.verb"
              :aria-keyshortcuts="decision.keys"
              :data-testid="`kwic-${decision.action}`"
              @mousedown.prevent
              @click.stop="decideRow(row, decision.action)"
            >
              <q-tooltip :delay="400">{{ row.type === decision.state ? decision.done : decision.verb }} ({{ decision.keys }})</q-tooltip>
            </q-btn>
          </span>
          <q-spinner v-if="saving.has(row.id)" class="kwic__status-spinner" size="1.1rem" aria-label="Saving" />
        </div>
        <div class="kwic__cell kwic__meta" role="gridcell">
          <span v-if="rankStart !== null" class="kwic__rank" data-testid="kwic-rank">#{{ rankStart + index }}</span>
          <span class="kwic__tag" :title="tagName(row)">
            <span class="kwic__tag-dot" :style="{ backgroundColor: tagColor(row) }" aria-hidden="true" />
            {{ tagName(row) }}
          </span>
          <!-- Reviewed here and out of the filters now: dimmed until the query is read again (#690);
               the summary line counts these rows. -->
          <span v-if="unmatched.has(row.id)" class="sr-only">No longer matches the filters</span>
          <q-btn
            v-if="hasMenu"
            flat
            round
            dense
            size="xs"
            icon="more_vert"
            tabindex="-1"
            class="kwic__more"
            :aria-label="`Actions and filters for ${rowLabel(row)}`"
            title="Actions and filters (context menu key or Shift+F10)"
            data-testid="kwic-row-more"
            @click.stop="event => openMenu(row, event)"
          />
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

/** A review decision made in a row (#690): the two states it can be put in. */
export type RowDecision = 'approve' | 'reject'
</script>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { QBtn, QCheckbox, QIcon, QItem, QItemLabel, QItemSection, QList, QMenu, QSeparator, QSpinner, QTooltip, TouchHold as vTouchHold, useQuasar } from 'quasar'
import {
  AnnotationSort, Cardinality, RetrievalMode, SpanType, TextScope, TextStatus, type AnnotationListRow, type Attribute, type Tag
} from 'src/generated/api'
import type { ConcordanceFilters } from './concordanceStore'
import { rowFilterGroups, wordFilterGroup, type CellFilterGroup } from './cellFilters'
import HeaderControls, { type SortState } from './KwicHeaderControls.vue'
import { markMatches, queryWords, splitParts, type TextPart } from './textMatches'
import AttributeValueChips from 'src/features/attributes/AttributeValueChips.vue'
import AttributeValuePicker from 'src/features/attributes/AttributeValuePicker.vue'
import { applies, cannotAssign, heldName, heldValues, type AssignChange } from 'src/features/attributes/assignment'
import { prefersReducedMotion } from 'src/features/documents/contextScroll'
import { scrollRowIntoView } from './rowScroll'

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
  /** Annotations whose review is being saved (#690). */
  saving?: Set<string>
  /** Rows a review took out of the filters; they stay, marked, until the list is read again (#690). */
  unmatched?: Set<string>
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
  saving: () => new Set(),
  unmatched: () => new Set(),
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
  /** Change the query by a filter of a row's value or of the words selected in its text (its menu). */
  refine: [change: Partial<ConcordanceFilters>]
  /** Confirm or reject this row's annotation (its review buttons, Alt+C / Alt+R on the focused row,
   * #690); `done` says whether it is now in that state. */
  review: [row: AnnotationListRow, action: RowDecision, done: (ok: boolean) => void]
  /** Open the first row of the next page or the last one of the previous page (Alt+↓ / Alt+↑ at
   * the page's end); `done` gets the row opened, or null. */
  step: [direction: 1 | -1, done: (row: AnnotationListRow | null) => void]
}>()

// Inline review (#690 phase B): the two states a row can be put in, as its buttons and keys.
const DECISIONS: { action: RowDecision, state: SpanType, icon: string, verb: string, done: string, keys: string }[] = [
  { action: 'approve', state: SpanType.pos, icon: 'check', verb: 'Confirm', done: 'Confirmed', keys: 'Alt+C' },
  { action: 'reject', state: SpanType.neg, icon: 'block', verb: 'Reject', done: 'Rejected', keys: 'Alt+R' }
]

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

/** The annotation in its two halves (`splitParts`), its matches marked. */
function halves (text: string): [TextPart[], TextPart[]] {
  return splitParts(marked(lineText(text), inText.value))
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

function statusIcon (type: SpanType | null | undefined): string {
  if (type === SpanType.pos) return 'check'
  if (type === SpanType.neg) return 'block'
  return 'question_mark'
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
  const away = props.unmatched.has(row.id) ? ', no longer matches the filters' : ''
  return `${text} (${tagName(row)}, ${statusLabel(row.type)}${away}, ${sourceLabel(row)})`
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
  void nextTick(() => {
    const el = rowEls.get(row.id)
    if (!el) return
    el.focus({ preventScroll: true })
    scrollRowIntoView(el)
  })
}

/** A write is being saved, or a menu or dialog is open: no review decision is taken. */
function decisionsBlocked (): boolean {
  return props.saving.size > 0 || !!document.querySelector('.q-menu, .q-dialog')
}

/** A button's decision needs no follow-up: focus is not moved by it. */
function ignoreDone (): void { /* nothing to do */ }

/** A row's review button: acts on that row only, at the version it shows. Focus stays where it is
 * (the press does not take it) and a text selection is left alone: the click of a drag that
 * selects text goes to the row, never to the button, which needs both press and release. */
function decideRow (row: AnnotationListRow, action: RowDecision) {
  if (decisionsBlocked()) return
  emit('review', row, action, ignoreDone)
}

/**
 * Review keys of the focused row (#690): Alt+C / Alt+R confirm / reject it and, once it is in
 * that state, move focus to the next row; Alt+↓ / Alt+↑ move focus to the next / previous row and
 * open it in the sidebar, across the page's end. Matched by `event.code` (macOS Option+C types "ç").
 * Returns whether the key was one of them.
 */
function onReviewKey (event: KeyboardEvent, row: AnnotationListRow, index: number): boolean {
  if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return false
  const decision = DECISIONS.find(d => d.keys === `Alt+${event.code.replace(/^Key/, '')}`)
  const direction = event.code === 'ArrowDown' ? 1 : event.code === 'ArrowUp' ? -1 : 0
  if (!decision && !direction) return false
  event.preventDefault()
  if (decision) {
    if (event.repeat || decisionsBlocked()) return true
    emit('review', row, decision.action, ok => {
      const at = props.rows.findIndex(r => r.id === row.id)
      // Only when focus is still on the row decided.
      if (ok && at >= 0 && activeIndex.value === at && rowEls.get(row.id) === document.activeElement) focusRow(at + 1)
    })
    return true
  }
  if (props.loading) return true
  const next = props.rows[index + direction]
  if (next) {
    focusRow(index + direction)
    emit('open', next)
  } else {
    emit('step', direction as 1 | -1, opened => { if (opened) focusRowById(opened.id) })
  }
  return true
}

function focusRowById (id: string) {
  const index = props.rows.findIndex(r => r.id === id)
  if (index >= 0) focusRow(index)
}

function onKeydown (event: KeyboardEvent) {
  const index = activeIndex.value
  const row = props.rows[index]
  if (!row || (event.target as HTMLElement).getAttribute('role') !== 'row') return
  if (onReviewKey(event, row, index)) return
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
  } else if (event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey)) {
    // The platform's context menu keys. Firefox also shows its own menu on Shift+F10 (Shift bypasses
    // a page's context menu there, which cannot be prevented); kept as the standard key (#665).
    event.preventDefault()
    openMenu(row)
  }
}

// The row menus (#665): the row's actions, the filters of its values and, when it was opened with
// words selected in the row's text, the filter by them.
const hasMenu = computed(() => props.similar || !!props.filters)
const menus = new Map<string, QMenu>()
function setMenu (id: string, menu: QMenu | null) {
  if (menu) menus.set(id, menu)
  else menus.delete(id)
}

/** The words selected in a row's text when its menu was opened, and the field(s) they are in. */
const selectedWords = ref<{ rowId: string, text: string, scope: TextScope } | null>(null)

/** Notes what the menu of `row` is opened for (before it opens: right click, key, button). */
function prepareMenu (row: AnnotationListRow) {
  selectedWords.value = null
  const cell = rowEls.get(row.id)?.querySelector('.kwic__text')
  const selection = window.getSelection()
  if (!cell || !selection || selection.isCollapsed || !selection.rangeCount) return
  const range = selection.getRangeAt(0)
  if (!cell.contains(range.startContainer) || !cell.contains(range.endContainer)) return
  const parts = selectedParts(range, cell)
  // The fields with a selected word (a selected space next to the annotation does not count).
  const fields = new Set(parts.filter(p => /[\p{L}\p{N}]/u.test(p.text))
    .map(p => p.node.parentElement?.closest('.kwic__key') ? 'annotation' : 'context'))
  if (!fields.size) return
  const scope = fields.size > 1 ? TextScope.both : fields.has('annotation') ? TextScope.annotation : TextScope.context
  selectedWords.value = { rowId: row.id, text: parts.map(p => p.text).join(''), scope }
}

function openMenu (row: AnnotationListRow, event?: Event) {
  prepareMenu(row)
  menus.get(row.id)?.show(event)
}

/** Does what an item of the row's menu does, after closing the menu (a filter changes the menu's
 * items, and an item removed before `v-close-popup` acts would leave it open). Nothing while the
 * long press that opened the menu is being released: the browser may report it as a click on the
 * item under the finger. */
function menuAction (row: AnnotationListRow, action: () => void) {
  if (pressHeld.value) return
  menus.get(row.id)?.hide()
  action()
}

/** A long press opened the menu and its finger is still down: on a phone the menu is not under it,
 * and the browser may report its release as a tap outside, which would close the menu. */
const pressHeld = ref(false)

function onMenuOpening (row: AnnotationListRow) {
  menuOpen.value = row.id
}

/** On a phone a long press opens the menu (Quasar's context menu would place it at the finger, and
 * narrow it at the viewport's edge until it scrolls sideways): as wide as the row, under or above it. */
const $q = useQuasar()
// A phone, not a narrow window of a desktop browser (which keeps the right click).
const phone = computed(() => $q.platform.is.mobile === true && $q.screen.lt.sm)
function onHold (row: AnnotationListRow) {
  if (!phone.value) return
  pressHeld.value = true
  // The menu takes taps outside again a moment after the finger is lifted.
  const release = () => setTimeout(() => { pressHeld.value = false }, 400)
  document.addEventListener('touchend', release, { once: true, capture: true })
  document.addEventListener('touchcancel', release, { once: true, capture: true })
  openMenu(row)
}

function onMenuClosing (row: AnnotationListRow) {
  if (menuOpen.value !== row.id) return
  menuOpen.value = null
  menuClosed = { rowId: row.id, at: Date.now() }
}

function onMenuHide (row: AnnotationListRow) {
  if (selectedWords.value?.rowId === row.id) selectedWords.value = null
}

function menuGroups (row: AnnotationListRow): CellFilterGroup[] {
  const f = props.filters
  if (!f) return []
  const words = selectedWords.value?.rowId === row.id
    ? wordFilterGroup(selectedWords.value.text, selectedWords.value.scope, f)
    : null
  const groups = rowFilterGroups(row, f, { tagName: tagName(row), attributes: props.attributes })
  return words ? [words, ...groups] : groups
}

/** The row whose menu is shown, and the last one closed: a long press opens the menu on touch
 * screens, and lifting the finger may then click the row. */
const menuOpen = ref<string | null>(null)
let menuClosed: { rowId: string, at: number } | null = null
// A menu of a row the new page no longer has went with it, without closing.
watch(() => props.rows, rows => {
  if (menuOpen.value && !rows.some(r => r.id === menuOpen.value)) menuOpen.value = null
})

/** A click opens the row, unless it ended selecting text in it (the selection is kept) or the long
 * press that opened its menu. */
function onRowClick (row: AnnotationListRow, event: MouseEvent) {
  if (menuOpen.value || (menuClosed?.rowId === row.id && Date.now() - menuClosed.at < 400)) return
  const selection = window.getSelection()
  const el = event.currentTarget as HTMLElement
  if (selection && !selection.isCollapsed && selection.rangeCount && selection.getRangeAt(0).intersectsNode(el)) return
  emit('open', row)
}

// The open row follows the sidebar (Next, the advance after a review, #704): when it changes to a
// row of this page, the list scrolls it into view below the page's header (`scrollRowIntoView`).
// Keyboard focus stays where it is, e.g. on the sidebar's button.
watch(() => props.focusedId, (id) => {
  if (!id || !props.rows.some(r => r.id === id)) return
  activeIndex.value = props.rows.findIndex(r => r.id === id)
  void nextTick(() => {
    const el = rowEls.get(id)
    if (el) scrollRowIntoView(el, prefersReducedMotion() ? 'auto' : 'smooth')
  })
})

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

/**
 * Copies the selected text as it is in the source. A cut annotation's two halves are flex items,
 * which the browser's plain text would separate by line breaks, and the contexts end in no-break
 * spaces (`lineText`). So for a selection that touches an annotation, the text is joined from the
 * selected text nodes: nothing between the parts of one row's text cell, a line break between
 * cells, no-break spaces as spaces; screen-reader-only text is left out. Other selections copy as
 * the browser does.
 */
function onCopy (event: ClipboardEvent) {
  const selection = window.getSelection()
  const list = event.currentTarget as HTMLElement
  if (!selection || selection.isCollapsed || !selection.rangeCount || !event.clipboardData) return
  const range = selection.getRangeAt(0)
  if (!Array.from(list.querySelectorAll('.kwic__key')).some(key => range.intersectsNode(key))) return
  let text = ''
  let lastCell: Element | null = null
  for (const { node, text: part } of selectedParts(range, range.commonAncestorContainer)) {
    const cell = node.parentElement?.closest('[role="gridcell"], [role="columnheader"]') ?? null
    if (text && cell !== lastCell) text += '\n'
    text += part
    lastCell = cell
  }
  event.clipboardData.setData('text/plain', text)
  event.preventDefault()
}

/** The selected text of the text nodes under `root`, in order, as the source has it: no-break
 * spaces as spaces; screen-reader texts and hidden decorations are left out, but not the
 * annotation's halves (their screen-reader copy is the one left out). */
function selectedParts (range: Range, root: Node): { node: Node, text: string }[] {
  const parts: { node: Node, text: string }[] = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  for (let node = walker.currentNode.nodeType === Node.TEXT_NODE ? walker.currentNode : walker.nextNode(); node; node = walker.nextNode()) {
    if (!range.intersectsNode(node) ||
      node.parentElement?.closest('.sr-only, [aria-hidden="true"]:not(.kwic__key-head, .kwic__key-tail)')) continue
    const value = node.textContent ?? ''
    const part = value.slice(node === range.startContainer ? range.startOffset : 0,
      node === range.endContainer ? range.endOffset : value.length)
    if (part) parts.push({ node, text: part.replace(/\u00a0/g, ' ') })
  }
  return parts
}

defineExpose({ reveal, focusRowById })
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
  /* The status column: wide enough for the two review buttons, which take the icon's place. */
  --kwic-status: 4.25rem;
  --kwic-text:
    minmax(var(--kwic-context-min), 1fr) minmax(var(--kwic-key-min), auto) minmax(var(--kwic-context-min), 1fr);
  display: grid;
  grid-template-columns: 2rem var(--kwic-text) var(--kwic-status) fit-content(9rem) fit-content(13rem) auto;
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
    var(--kwic-status) fit-content(9rem) fit-content(13rem) auto;
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

.kwic__grid--attribute .kwic__row--menu .kwic__check,
.kwic__grid--attribute .kwic__row:focus-visible .kwic__check {
  box-shadow: inset 2px 2px 0 var(--q-primary), inset 0 -2px 0 var(--q-primary);
}

/* The row whose menu is open is marked like a focused one, so the menu's row stays recognizable
   (on a phone the menu is under or above it, not at the finger). */
.kwic__row.kwic__row--menu {
  background: #eef4fd;
  box-shadow: inset 0 0 0 2px var(--q-primary);
}

/* The text cell is opaque (it may stick), so it draws its part of the focus ring, also on a
   checked or open row. */
.kwic__row--menu .kwic__text,
.kwic__row:focus-visible .kwic__text {
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
  /* A row scrolled into view clears the fixed app header: `scrollRowIntoView` measures it and
     sets the top margin; this is the fallback before the first measurement. */
  scroll-margin-top: 4.5rem;
  scroll-margin-bottom: 0.5rem;
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

/* The annotation, highlighted, on one line of at most 60 % of the text, so some context shows on
   both sides. A longer one is cut in the middle: its first half shows its start (cut at its end,
   with an ellipsis), its second half its end (cut at its start). Each half gets half the room and
   gives what it does not need to the other (basis 0, at most its text), so only an annotation
   that does not fit is cut, and the words next to both contexts stay visible. The full text is in
   the sidebar and the title. */
.kwic__text .kwic__key {
  flex: 0 1 auto;
  max-width: 60%;
  min-width: 0;
  display: flex;
  overflow: hidden;
  /* Its own spaces kept too (an annotation may start or end with one). */
  white-space: pre;
  border-radius: 2px;
  background: rgba(255, 213, 79, 0.35);
  font-weight: 600;
  color: #1f2a37;
}

.kwic__key-head,
.kwic__key-tail {
  flex: 1 1 0;
  min-width: 0;
  max-width: max-content;
  overflow: hidden;
}

.kwic__key-head {
  text-overflow: ellipsis;
}

/* Cut at its start, like the left context. */
.kwic__key-tail {
  direction: rtl;
  text-overflow: clip;
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

.kwic__row--rejected .kwic__key-head,
.kwic__row--rejected .kwic__key-tail {
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
  /* The dot and the first letters stay when the column is narrow (the status does not shrink). */
  min-width: 3.25em;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kwic__tag-dot {
  flex: 0 0 auto;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

/* The row menu fits a phone's width: long values are cut, never scrolled sideways. */
.kwic__menu {
  min-width: min(260px, calc(100vw - 16px));
  max-width: min(360px, calc(100vw - 16px));
}

/* On a phone as wide as its content, never wider than the list (its 16 px gutters), at the held
   row's right edge. */
.kwic__menu--phone {
  min-width: min(220px, calc(100vw - 32px));
  max-width: calc(100vw - 32px);
}

/* A group of the row menu: the field and the row's value, cut to one line, and what it does. */
.kwic__menu-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 16px 2px;
}

.kwic__menu-label {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.kwic__menu-caption {
  font-size: 0.72rem;
  line-height: 1.3;
  color: rgba(0, 0, 0, 0.6);
}

/* The row's menu button: over the row's right end (it takes no column), shown on the hovered or
   keyboard-focused row, on touch screens also on the open one (a long press opens the menu too). */
.kwic__row {
  position: relative;
}

.kwic__more {
  position: absolute;
  right: 2px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
  color: rgba(0, 0, 0, 0.65);
  background: #fff;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.12);
  visibility: hidden;
}

.kwic__row:hover .kwic__more,
.kwic__row:focus-visible .kwic__more {
  visibility: visible;
}

@media (hover: none) {
  .kwic__row--focused .kwic__more {
    visibility: visible;
  }
}

.kwic__status--pos {
  color: #2e7d32;
}

.kwic__status--auto {
  color: #b26a00;
}

.kwic__status--neg {
  color: #c62828;
}

/* The status cell (#690): the icon, the review buttons and the spinner in one place, one shown at
   a time (`visibility`, so the cell keeps its size). */
.kwic__review {
  display: grid;
  place-items: center;
  overflow: visible;
  padding: 0 2px;
}

.kwic__review > * {
  grid-area: 1 / 1;
}

.kwic__row--head .kwic__review {
  overflow: hidden;
  text-align: center;
}

.kwic__status {
  display: inline-flex;
}

.kwic__decide {
  display: inline-flex;
  gap: 2px;
  visibility: hidden;
  user-select: none;
}

.kwic__decision {
  color: rgba(0, 0, 0, 0.6);
}

.kwic__decision--approve:hover,
.kwic__decision--approve.kwic__decision--pressed {
  color: #2e7d32;
}

.kwic__decision--reject:hover,
.kwic__decision--reject.kwic__decision--pressed {
  color: #c62828;
}

.kwic__decision--pressed {
  background: currentColor;
}

/* The icon of the pressed button on its own color (the background above is the text color). */
.kwic__decision--pressed :deep(.q-icon) {
  color: #fff;
}

@media (hover: hover) {
  .kwic__row:hover .kwic__decide {
    visibility: visible;
  }
  .kwic__row:hover .kwic__status {
    visibility: hidden;
  }
}

.kwic__row:focus-visible .kwic__decide {
  visibility: visible;
}

.kwic__row:focus-visible .kwic__status {
  visibility: hidden;
}

/* Saving: the spinner alone, also without hover or focus. */
.kwic__review--saving .kwic__status,
.kwic__row .kwic__review--saving .kwic__decide {
  visibility: hidden;
}

.kwic__status-spinner {
  color: var(--q-primary);
}

.kwic--phone .kwic__grid {
  --kwic-status: 2rem;
}

/* Reviewed out of the filters (#690): still there, but visibly no longer part of the result. */
.kwic__row--unmatched .kwic__text,
.kwic__row--unmatched .kwic__source,
.kwic__row--unmatched .kwic__year {
  opacity: 0.5;
}

.kwic__row:not(.kwic__row--head) .kwic__source,
.kwic__row:not(.kwic__row--head) .kwic__year {
  font-size: 0.78rem;
  color: rgba(0, 0, 0, 0.7);
}

.kwic__year {
  font-variant-numeric: tabular-nums;
}

/* When the list narrows, Source and Year give way first (zero wide, their values still read by
   assistive technology, their headers' controls hidden: the toolbar sorts and filters by them).
   The annotation, its tag, status and shown attribute values stay: they are what is reviewed
   (#665 review). Several attribute columns scroll sideways instead. */
@container (max-width: 900px) {
  .kwic__grid {
    grid-template-columns: 2rem var(--kwic-text) var(--kwic-status) fit-content(9rem) 0 0;
  }
  .kwic__grid--attribute {
    --kwic-context-min: 6rem;
    --kwic-attribute-max: min(10rem, 20rem / var(--kwic-attributes));
    grid-template-columns:
      2rem var(--kwic-text)
      repeat(var(--kwic-attributes), fit-content(max(var(--kwic-attribute-min), var(--kwic-attribute-max))))
      var(--kwic-status) fit-content(9rem) 0 0;
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

/* On a phone the tag name is cut first; the text keeps the rest. */
@container (max-width: 560px) {
  .kwic__grid {
    grid-template-columns: 2rem var(--kwic-text) var(--kwic-status) fit-content(9rem) 0 0;
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
      var(--kwic-status) fit-content(9rem) 0 0;
  }
  .kwic__meta {
    gap: 4px;
  }
}
</style>
