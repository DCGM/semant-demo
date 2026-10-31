<template>
  <div class="kwic" data-testid="kwic">
    <p :id="helpId" class="sr-only">
      Arrow keys move between rows, Enter shows the annotation in its document, Space checks the row.
    </p>
    <div
      class="kwic__grid"
      :class="{ 'kwic__grid--attribute': !!attribute }"
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
        <div v-if="attribute" class="kwic__cell kwic__attribute" role="columnheader" :title="attribute.name">
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
        <div v-if="attribute" class="kwic__cell kwic__attribute" role="gridcell" data-testid="kwic-attribute" @click.stop>
          <q-btn
            v-if="!cannotAssign(attribute, row)"
            flat
            dense
            no-caps
            tabindex="-1"
            class="kwic__attribute-button"
            :loading="pending.has(row.id)"
            :aria-label="`${attribute.name} of ${rowLabel(row)}: ${heldLabel(row)}. Change`"
            data-testid="kwic-attribute-edit"
          >
            <AttributeValueChips :attribute="attribute" :ids="row.attributes?.[attribute.id]" empty-label="Assign…" line />
            <q-menu anchor="bottom left" self="top left">
              <AttributeValuePicker
                :attribute="attribute"
                :current="row.attributes?.[attribute.id] ?? []"
                :busy="pending.has(row.id)"
                @change="change => emit('assign', row, attribute!, change)"
              />
            </q-menu>
          </q-btn>
          <span v-else :title="cannotAssign(attribute, row) ?? undefined">
            <AttributeValueChips
              v-if="row.attributes?.[attribute.id]?.length"
              :attribute="attribute"
              :ids="row.attributes[attribute.id]"
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
import { SpanType, TextStatus, type AnnotationListRow, type Attribute, type Tag } from 'src/generated/api'
import AttributeValueChips from 'src/features/attributes/AttributeValueChips.vue'
import AttributeValuePicker from 'src/features/attributes/AttributeValuePicker.vue'
import { cannotAssign, heldName, heldValues, type AssignChange } from 'src/features/attributes/assignment'

const props = withDefaults(defineProps<{
  rows: AnnotationListRow[]
  tags: Tag[]
  selected: Set<string>
  /** The row whose source context is open. */
  focusedId?: string | null
  loading?: boolean
  /** The attribute whose values are shown in a column of their own and assigned there (#331). */
  attribute?: Attribute | null
  /** Annotations with an assignment under way. */
  pending?: Set<string>
}>(), {
  focusedId: null,
  loading: false,
  attribute: null,
  pending: () => new Set()
})

const emit = defineEmits<{
  /** Show the row's annotation in its document (row click, Enter). */
  open: [row: AnnotationListRow]
  /** Check or uncheck one row (its checkbox, Space); separate from opening. */
  toggle: [id: string, value: boolean]
  'select-page': [value: boolean]
  /** Assign values of the shown attribute to the row's annotation. */
  assign: [row: AnnotationListRow, attribute: Attribute, change: AssignChange]
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

function heldLabel (row: AnnotationListRow): string {
  const attribute = props.attribute
  const held = attribute ? heldValues(attribute, row.attributes?.[attribute.id]) : []
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
  void nextTick(() => rowEls.get(row.id)?.focus())
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

.kwic__grid {
  display: grid;
  /* check | left context | annotation | right context | tag · status | source */
  grid-template-columns: 2rem minmax(0, 1fr) fit-content(24%) minmax(0, 1fr) fit-content(9rem) fit-content(13rem);
  font-size: 0.9rem;
}

/* With an attribute column after the right context. */
.kwic__grid--attribute {
  grid-template-columns: 2rem minmax(0, 1fr) fit-content(24%) minmax(0, 1fr) fit-content(14rem) fit-content(9rem) fit-content(13rem);
}

.kwic__attribute {
  font-size: 0.78rem;
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
    grid-template-columns: 2rem minmax(0, 1fr) fit-content(24%) minmax(0, 1fr) fit-content(10rem) 0 fit-content(9rem);
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
    grid-template-columns: 2rem minmax(0, 1fr) fit-content(30%) minmax(0, 1fr) fit-content(7rem) 0 0;
  }
  .kwic__source {
    padding: 0;
  }
}
</style>
