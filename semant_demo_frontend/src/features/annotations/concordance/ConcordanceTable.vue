<template>
  <div class="kwic" :class="{ 'kwic--attributes': attributes.length > 0 }" data-testid="kwic">
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
        <div class="kwic__cell kwic__left" role="columnheader">Left context</div>
        <div class="kwic__cell kwic__key" role="columnheader">Annotation</div>
        <div class="kwic__cell kwic__right" role="columnheader">Right context</div>
        <div
          v-for="attribute in attributes"
          :key="attribute.id"
          class="kwic__cell kwic__attribute"
          role="columnheader"
          :title="attribute.name"
          data-testid="kwic-attribute-head"
        >
          {{ attribute.name }}
        </div>
        <div class="kwic__cell kwic__meta" role="columnheader">Tag · status</div>
        <div class="kwic__cell kwic__source" role="columnheader">Source</div>
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
        <div class="kwic__cell kwic__left" role="gridcell">
          <span dir="ltr" class="kwic__ltr">{{ row.leftContext ?? '' }}</span>
        </div>
        <div class="kwic__cell kwic__key" role="gridcell" :title="row.text ?? undefined">
          <span v-if="row.text !== null && row.text !== undefined" class="kwic__key-text">{{ row.text }}</span>
          <span v-else class="kwic__missing">{{ missingText(row) }}</span>
        </div>
        <div class="kwic__cell kwic__right" role="gridcell">{{ row.rightContext ?? '' }}</div>
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
          <span class="kwic__tag" :title="tagName(row)">
            <span class="kwic__tag-dot" :style="{ backgroundColor: tagColor(row) }" aria-hidden="true" />
            {{ tagName(row) }}
          </span>
          <span class="kwic__status" :class="`kwic__status--${row.type}`">{{ statusLabel(row.type) }}</span>
        </div>
        <div class="kwic__cell kwic__source" role="gridcell" :title="sourceLabel(row)">
          <template v-if="row.documentAvailable">
            <span class="kwic__title">{{ row.documentTitle || 'Untitled document' }}</span>
            <span class="kwic__year">{{ row.documentYear ?? 'n.d.' }}</span>
          </template>
          <span v-else class="kwic__missing">Source unavailable</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { QBtn, QCheckbox, QMenu } from 'quasar'
import { Cardinality, SpanType, TextStatus, type AnnotationListRow, type Attribute, type Tag } from 'src/generated/api'
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
}>(), {
  focusedId: null,
  loading: false,
  attributes: () => [],
  pending: () => new Set()
})

const emit = defineEmits<{
  /** Show the row's annotation in its document (row click, Enter). */
  open: [row: AnnotationListRow]
  /** Check or uncheck one row (its checkbox, Space); separate from opening. */
  toggle: [id: string, value: boolean]
  'select-page': [value: boolean]
  /** Assign values of a shown attribute to the row's annotation; `done` says whether it was saved. */
  assign: [row: AnnotationListRow, attribute: Attribute, change: AssignChange, done:(ok: boolean) => void]
}>()

const helpId = `kwic-help-${Math.random().toString(36).slice(2, 8)}`
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

.kwic__grid {
  display: grid;
  /* check | left context | annotation | right context | tag · status | source */
  grid-template-columns: 2rem minmax(0, 1fr) fit-content(24%) minmax(0, 1fr) fit-content(9rem) fit-content(13rem);
  font-size: 0.9rem;
}

/* With attribute columns (their count in --kwic-attributes) after the right context. */
.kwic__grid--attribute {
  --kwic-context-min: 8rem;
  --kwic-key-min: 8rem;
  --kwic-attribute-min: 6rem;
  --kwic-attribute-max: min(14rem, 30rem / var(--kwic-attributes));
  grid-template-columns:
    2rem minmax(var(--kwic-context-min), 1fr) fit-content(24%) minmax(var(--kwic-context-min), 1fr)
    repeat(var(--kwic-attributes), fit-content(max(var(--kwic-attribute-min), var(--kwic-attribute-max))))
    fit-content(9rem) fit-content(13rem);
}

.kwic__attribute {
  font-size: 0.78rem;
}

/* Minimum widths, so the annotation and the values stay identifiable (the list scrolls instead). */
.kwic__grid--attribute .kwic__cell.kwic__attribute {
  min-width: var(--kwic-attribute-min);
}

.kwic__grid--attribute .kwic__cell.kwic__key {
  min-width: var(--kwic-key-min);
}

/* Opaque rows, for the sticky cells to inherit. Without specificity of its own (:where), so the
   hover, selected and focused backgrounds below still win; the header's hover must win over
   its own `none` below, so it keeps the full specificity. */
:where(.kwic__grid--attribute) .kwic__row,
.kwic__grid--attribute .kwic__row--head:hover {
  background: #fff;
}

/* The row's checkbox and annotation stay in view while the attribute columns scroll under. */
.kwic__grid--attribute .kwic__check,
.kwic__grid--attribute .kwic__key {
  position: sticky;
  z-index: 1;
  background: inherit;
}

.kwic__grid--attribute .kwic__check {
  left: 0;
}

.kwic__grid--attribute .kwic__key {
  left: 2rem;
}

/* They cover the row's own marks, so they draw their part of them. */
.kwic__grid--attribute .kwic__row--focused .kwic__check {
  box-shadow: inset 3px 0 0 var(--q-primary);
}

.kwic__grid--attribute .kwic__row:focus-visible .kwic__check {
  box-shadow: inset 2px 2px 0 var(--q-primary), inset 0 -2px 0 var(--q-primary);
}

.kwic__grid--attribute .kwic__row:focus-visible .kwic__key {
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

/* Left context is cut at its start, so the words next to the annotation stay visible. */
.kwic__row:not(.kwic__row--head) .kwic__left {
  direction: rtl;
  text-align: right;
  color: #444;
}

.kwic__ltr {
  direction: ltr;
}

.kwic__key {
  font-weight: 600;
  color: #1f2a37;
  padding: 2px 2px;
}

.kwic__key-text {
  padding: 1px 4px;
  border-radius: 2px;
  background: rgba(255, 213, 79, 0.35);
}

.kwic__row--rejected .kwic__key-text {
  text-decoration: line-through;
  text-decoration-color: rgba(0, 0, 0, 0.45);
}

.kwic__right {
  color: #444;
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

.kwic__source {
  font-size: 0.78rem;
  color: rgba(0, 0, 0, 0.7);
}

.kwic__year {
  margin-left: 6px;
  font-variant-numeric: tabular-nums;
}

/* Secondary columns give way first when the list narrows. */
@container (max-width: 900px) {
  .kwic__grid {
    grid-template-columns: 2rem minmax(0, 1fr) fit-content(28%) minmax(0, 1fr) 0 fit-content(9rem);
  }
  .kwic__grid--attribute {
    --kwic-context-min: 6rem;
    --kwic-key-min: 6rem;
    --kwic-attribute-max: min(10rem, 20rem / var(--kwic-attributes));
    grid-template-columns:
      2rem minmax(var(--kwic-context-min), 1fr) fit-content(24%) minmax(var(--kwic-context-min), 1fr)
      repeat(var(--kwic-attributes), fit-content(max(var(--kwic-attribute-min), var(--kwic-attribute-max))))
      0 fit-content(9rem);
  }
  /* Zero width, still read by assistive technology. */
  .kwic__meta {
    padding: 0;
  }
}

@container (max-width: 560px) {
  .kwic__grid {
    grid-template-columns: 2rem minmax(0, 1fr) fit-content(40%) minmax(0, 1fr) 0 0;
    font-size: 0.85rem;
  }
  .kwic__grid--attribute {
    --kwic-context-min: 4rem;
    --kwic-key-min: 6rem;
    --kwic-attribute-min: 5rem;
    --kwic-attribute-max: 7rem;
    grid-template-columns:
      2rem minmax(var(--kwic-context-min), 1fr) fit-content(30%) minmax(var(--kwic-context-min), 1fr)
      repeat(var(--kwic-attributes), fit-content(max(var(--kwic-attribute-min), var(--kwic-attribute-max))))
      0 0;
  }
  .kwic__source {
    padding: 0;
  }
}
</style>
