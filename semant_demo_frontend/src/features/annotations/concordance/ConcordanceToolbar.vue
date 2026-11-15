<template>
  <div class="concordance-toolbar" data-testid="concordance-toolbar">
    <q-select
      :model-value="filters.tagIds"
      :options="tagOptions"
      multiple
      emit-value
      map-options
      use-chips
      clearable
      dense
      outlined
      options-dense
      label="Tags"
      class="concordance-toolbar__tags"
      data-testid="concordance-tags"
      @update:model-value="value => emit('change', { tagIds: value ?? [] })"
    >
      <template #option="{ itemProps, opt, selected, toggleOption }">
        <q-item v-bind="itemProps">
          <q-item-section side>
            <q-checkbox dense :model-value="selected" @update:model-value="toggleOption(opt)" />
          </q-item-section>
          <q-item-section>
            <q-item-label>
              <span class="concordance-toolbar__dot" :style="{ backgroundColor: opt.color }" aria-hidden="true" />
              {{ opt.label }}
            </q-item-label>
          </q-item-section>
        </q-item>
      </template>
    </q-select>

    <div class="concordance-toolbar__status" role="group" aria-label="Status">
      <q-checkbox
        v-for="option in statusOptions"
        :key="option.value"
        dense
        :model-value="filters.types.includes(option.value)"
        :label="option.label"
        :disable="filters.types.length === 1 && filters.types.includes(option.value)"
        :data-testid="`concordance-status-${option.value}`"
        @update:model-value="value => toggleType(option.value, !!value)"
      >
        <q-tooltip v-if="option.hint">{{ option.hint }}</q-tooltip>
      </q-checkbox>
    </div>

    <div class="concordance-toolbar__search" role="group" aria-label="Text search">
      <q-select
        :model-value="filters.mode"
        :options="modeOptions"
        emit-value
        map-options
        dense
        outlined
        options-dense
        label="Find by"
        class="concordance-toolbar__mode"
        data-testid="concordance-mode"
        @update:model-value="value => emit('change', modeChange(value))"
      />
      <q-input
        ref="textInput"
        :model-value="filters.text"
        dense
        outlined
        clearable
        debounce="400"
        :label="textLabel"
        :hint="textHint"
        hide-hint
        hide-bottom-space
        class="concordance-toolbar__text"
        data-testid="concordance-text"
        @update:model-value="value => emit('change', { text: String(value ?? '') })"
      >
        <template #prepend><q-icon name="search" /></template>
      </q-input>
      <q-select
        v-if="filters.mode !== RetrievalMode.semantic"
        :model-value="filters.textScope"
        :options="scopeOptions"
        emit-value
        map-options
        dense
        outlined
        options-dense
        label="Search in"
        class="concordance-toolbar__scope"
        data-testid="concordance-text-scope"
        @update:model-value="value => emit('change', { textScope: value })"
      />
      <q-select
        v-if="ranked"
        :model-value="filters.k"
        :options="TOP_K_OPTIONS"
        dense
        outlined
        options-dense
        label="Top"
        class="concordance-toolbar__k"
        data-testid="concordance-k"
        @update:model-value="value => emit('change', { k: value })"
      >
        <q-tooltip>How many annotations to rank at most</q-tooltip>
      </q-select>
      <q-checkbox
        v-if="filters.mode === RetrievalMode.similar"
        dense
        :model-value="filters.includeSource"
        label="Include source"
        data-testid="concordance-include-source"
        @update:model-value="value => emit('change', { includeSource: !!value })"
      />
    </div>

    <q-select
      ref="sourcesSelect"
      :model-value="filters.documentIds"
      :options="filteredDocumentOptions"
      multiple
      emit-value
      map-options
      use-input
      clearable
      dense
      outlined
      options-dense
      input-debounce="0"
      label="Sources"
      class="concordance-toolbar__sources"
      :display-value="sourcesLabel"
      hide-bottom-space
      :error="!!documentsError"
      :error-message="documentsError ?? undefined"
      data-testid="concordance-sources"
      @filter="filterDocuments"
      @update:model-value="value => emit('change', { documentIds: value ?? [] })"
    />

    <q-select
      v-if="attributes.length"
      :model-value="attributeFilter"
      :options="filteredAttributeOptions"
      multiple
      emit-value
      map-options
      use-input
      clearable
      dense
      outlined
      options-dense
      input-debounce="0"
      label="Attributes"
      class="concordance-toolbar__attributes"
      :display-value="attributesLabel"
      data-testid="concordance-attributes"
      @filter="filterAttributes"
      @update:model-value="setAttributeFilter"
    >
      <template #option="{ itemProps, opt, selected, toggleOption }">
        <q-item v-bind="itemProps">
          <q-item-section side>
            <q-checkbox dense :model-value="selected" @update:model-value="toggleOption(opt)" />
          </q-item-section>
          <q-item-section>
            <q-item-label :class="{ 'text-italic': opt.unassigned }">{{ opt.label }}</q-item-label>
          </q-item-section>
        </q-item>
      </template>
      <q-tooltip>Values of one attribute match any of them; different attributes must all match</q-tooltip>
    </q-select>

    <div class="concordance-toolbar__years" role="group" aria-label="Publication years">
      <q-input
        ref="yearInput"
        :model-value="filters.documentFilters.yearMin ?? ''"
        dense
        outlined
        type="number"
        debounce="500"
        label="From year"
        class="concordance-toolbar__year"
        data-testid="concordance-year-from"
        @update:model-value="value => setDocumentFilters({ yearMin: toYear(value) })"
      />
      <q-input
        :model-value="filters.documentFilters.yearMax ?? ''"
        dense
        outlined
        type="number"
        debounce="500"
        label="To year"
        class="concordance-toolbar__year"
        data-testid="concordance-year-to"
        @update:model-value="value => setDocumentFilters({ yearMax: toYear(value) })"
      />
    </div>

    <q-btn
      outline
      dense
      no-caps
      color="primary"
      icon="tune"
      :label="documentFilterCount ? `Document filters (${documentFilterCount})` : 'Document filters'"
      class="concordance-toolbar__document-filters"
      data-testid="concordance-document-filters"
    >
      <q-menu anchor="bottom left" self="top left" class="concordance-toolbar__menu">
        <div class="concordance-toolbar__document-form" data-testid="concordance-document-form">
          <p class="concordance-toolbar__menu-hint">
            The same document filters as in Search and the corpus overview: annotations in documents that match
            every kind, and any of several values of one kind.
          </p>
          <q-input
            v-model="titleDraft"
            dense
            outlined
            clearable
            maxlength="100"
            label="Title contains"
            hint="Enter adds it; several titles match any of them. Each word inside a title word, in any order; ignores case, not diacritics."
            :error="!!titleError"
            :error-message="titleError ?? undefined"
            data-testid="concordance-title"
            @keydown.enter.prevent="addTitle"
          >
            <template #append>
              <q-btn flat dense round icon="add" aria-label="Add title filter" :disable="!titleDraft?.trim()" @click="addTitle" />
            </template>
          </q-input>
          <q-select
            :model-value="filters.documentFilters.libraries ?? []"
            :options="libraryOptions"
            multiple
            emit-value
            map-options
            use-chips
            clearable
            dense
            outlined
            options-dense
            label="Source library"
            :disable="!libraryOptions.length"
            :hint="libraryOptions.length ? 'Any of the selected libraries' : 'The annotated documents record no library'"
            data-testid="concordance-libraries"
            @update:model-value="value => setDocumentFilters({ libraries: value ?? [] })"
          />
          <q-select
            :model-value="filters.documentFilters.languages ?? []"
            :options="languageOptions"
            multiple
            emit-value
            map-options
            use-chips
            clearable
            dense
            outlined
            options-dense
            label="Document language"
            :disable="!languageOptions.length"
            :hint="languageOptions.length ? 'Any of the selected languages' : 'The annotated documents record no language'"
            data-testid="concordance-languages"
            @update:model-value="value => setDocumentFilters({ languages: value ?? [] })"
          />
        </div>
      </q-menu>
    </q-btn>

    <q-select
      :model-value="filters.sort"
      :options="sortOptions"
      emit-value
      map-options
      dense
      outlined
      options-dense
      label="Sort by"
      :disable="ranked"
      :display-value="ranked ? 'Relevance' : undefined"
      class="concordance-toolbar__sort"
      data-testid="concordance-sort"
      @update:model-value="value => emit('change', { sort: value, descending: false })"
    >
      <q-tooltip v-if="ranked">Ranked results are in order of relevance</q-tooltip>
    </q-select>
    <q-btn
      v-if="!ranked"
      flat
      dense
      round
      :icon="filters.descending ? 'arrow_downward' : 'arrow_upward'"
      :aria-label="filters.descending ? 'Descending; sort ascending' : 'Ascending; sort descending'"
      :aria-pressed="filters.descending ? 'true' : 'false'"
      data-testid="concordance-sort-direction"
      @click="emit('change', { descending: !filters.descending })"
    >
      <q-tooltip>{{ filters.descending ? 'Descending' : 'Ascending' }}</q-tooltip>
    </q-btn>

    <q-select
      v-if="attributes.length"
      :model-value="shownIds"
      :options="shownAttributeOptions"
      multiple
      emit-value
      map-options
      clearable
      dense
      outlined
      options-dense
      label="Show attributes"
      :display-value="shownLabel"
      class="concordance-toolbar__show-attribute"
      data-testid="concordance-show-attribute"
      @update:model-value="value => emit('show-attributes', value ?? [])"
    >
      <!-- The option carries role and state (itemProps); its checkbox only shows them. -->
      <template #option="{ itemProps, opt, selected, toggleOption }">
        <q-item v-bind="itemProps">
          <q-item-section side>
            <q-checkbox
              dense
              tabindex="-1"
              aria-hidden="true"
              :model-value="selected"
              @update:model-value="toggleOption(opt)"
            />
          </q-item-section>
          <q-item-section>
            <q-item-label>{{ opt.label }}</q-item-label>
          </q-item-section>
        </q-item>
      </template>
      <q-tooltip>Shows each chosen attribute's values in a column of their own, where they can be assigned</q-tooltip>
    </q-select>

  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { QBtn, QCheckbox, QIcon, QInput, QItem, QItemLabel, QItemSection, QMenu, QSelect, QTooltip } from 'quasar'
import {
  AnnotationSort, RetrievalMode, SpanType, TextScope, type AnnotatedDocument, type Attribute, type DocumentFilters, type Tag
} from 'src/generated/api'
import { orderedValues, valueName } from 'src/features/attributes/attributeForm'
import { languageLabel, libraryLabel } from 'src/features/analytics/corpusOverview'
import { TOP_K_OPTIONS, modeChange, type ConcordanceFilters } from './concordanceStore'
import type { FilterField } from './ConcordanceTable.vue'
import { MODE_LABELS, SCOPE_LABELS, modeHintText, titleProblem } from './filterChips'

const props = defineProps<{
  filters: ConcordanceFilters
  tags: Tag[]
  documents: AnnotatedDocument[]
  documentsError?: string | null
  /** The collection's attribute definitions (#331), retired ones included. */
  attributes?: Attribute[]
  /** The attributes shown in columns of their own. */
  shownAttributeIds?: string[]
}>()

const emit = defineEmits<{
  change: [change: Partial<ConcordanceFilters>]
  'show-attributes': [attributeIds: string[]]
}>()

const attributes = computed(() => props.attributes ?? [])

const textInput = ref<InstanceType<typeof QInput> | null>(null)
const sourcesSelect = ref<InstanceType<typeof QSelect> | null>(null)
const yearInput = ref<InstanceType<typeof QInput> | null>(null)

/** Brings the filter of a table column to the user (its header's filter button, #665): the text
 * search scoped to the annotation or its context (a scope that already searches the field is
 * kept), the source picker or the year range. */
function openFilter (field: FilterField) {
  if (field === 'source') {
    sourcesSelect.value?.$el.scrollIntoView?.({ block: 'nearest' })
    sourcesSelect.value?.focus()
    sourcesSelect.value?.showPopup()
    return
  }
  const input = field === 'year' ? yearInput.value : textInput.value
  if (field !== 'year') {
    const scope = field === 'annotation' ? TextScope.annotation : TextScope.context
    if (props.filters.textScope !== scope && props.filters.textScope !== TextScope.both) emit('change', { textScope: scope })
  }
  input?.$el.scrollIntoView?.({ block: 'nearest' })
  void nextTick(() => input?.focus())
}

defineExpose({ openFilter })

const tagOptions = computed(() => props.tags.map(t => ({ label: t.name, value: t.id, color: t.color })))

const statusOptions = [
  { value: SpanType.pos, label: 'Confirmed', hint: 'Manual or approved annotations' },
  { value: SpanType.auto, label: 'Proposals', hint: 'Automatic proposals not yet reviewed' },
  { value: SpanType.neg, label: 'Rejected', hint: 'Rejected proposals, kept as negative examples' }
]

const sortOptions = [
  { value: AnnotationSort.document, label: 'Document' },
  { value: AnnotationSort.year, label: 'Year' },
  { value: AnnotationSort.text, label: 'Annotated text' }
]

const scopeOptions = Object.values(TextScope).map(value => ({ value, label: SCOPE_LABELS[value] }))
const scopeLabel = computed(() => props.filters.textScope === TextScope.annotation ? 'Annotated text'
  : props.filters.textScope === TextScope.context ? 'Context text' : 'Annotation or context text')
const ranked = computed(() => props.filters.mode !== RetrievalMode.lexical)
// Find similar is entered from an annotation; the selector only shows it while it is active.
const modeOptions = computed(() => Object.values(RetrievalMode)
  .filter(value => value !== RetrievalMode.similar || props.filters.mode === RetrievalMode.similar)
  .map(value => ({ value, label: MODE_LABELS[value], disable: value === RetrievalMode.similar })))
const textLabel = computed(() => props.filters.mode === RetrievalMode.semantic ? 'Meaning of'
  : props.filters.mode === RetrievalMode.hybrid ? 'Meaning and words of' : scopeLabel.value)
const textHint = computed(() => modeHintText(props.filters.mode, props.filters.textScope))

function setDocumentFilters (change: Partial<DocumentFilters>) {
  emit('change', { documentFilters: { ...props.filters.documentFilters, ...change } })
}

const documentFilterCount = computed(() => {
  const f = props.filters.documentFilters
  return (f.titleContains?.length ?? 0) + (f.libraries?.length ?? 0) + (f.languages?.length ?? 0)
})

const titleDraft = ref<string | null>(null)
const titleError = ref<string | null>(null)
function addTitle () {
  const text = titleDraft.value?.trim()
  if (!text) return
  const titles = props.filters.documentFilters.titleContains ?? []
  titleError.value = titleProblem(text, titles)
  if (titleError.value) return
  if (!titles.includes(text)) setDocumentFilters({ titleContains: [...titles, text] })
  titleDraft.value = null
}

/** The stored values of the annotated documents, with how many annotations each has. */
function valueOptions (key: 'library' | 'language', label: (value: string) => string) {
  const counts = new Map<string, number>()
  for (const d of props.documents) {
    const value = d[key]
    if (value) counts.set(value, (counts.get(value) ?? 0) + d.count)
  }
  return [...counts].sort(([a], [b]) => label(a).localeCompare(label(b)))
    .map(([value, count]) => ({ value, label: `${label(value)} (${count})` }))
}
const libraryOptions = computed(() => valueOptions('library', libraryLabel))
const languageOptions = computed(() => valueOptions('language', languageLabel))

function toggleType (type: SpanType, value: boolean) {
  const types = value ? [...props.filters.types, type] : props.filters.types.filter(t => t !== type)
  if (types.length) emit('change', { types: statusOptions.map(o => o.value).filter(t => types.includes(t)) })
}

function toYear (value: string | number | null): number | null {
  const year = Number(value)
  return value === null || value === '' || !Number.isInteger(year) ? null : year
}

function documentLabel (d: AnnotatedDocument): string {
  if (!d.available) return `Unavailable source (${d.count})`
  return `${d.title || 'Untitled document'}${d.year ? `, ${d.year}` : ''} (${d.count})`
}

const documentOptions = computed(() => props.documents.map(d => ({ label: documentLabel(d), value: d.id })))
const documentNeedle = ref('')
const filteredDocumentOptions = computed(() => {
  const needle = documentNeedle.value.toLocaleLowerCase()
  return needle ? documentOptions.value.filter(o => o.label.toLocaleLowerCase().includes(needle)) : documentOptions.value
})

function filterDocuments (value: string, update: (fn: () => void) => void) {
  update(() => { documentNeedle.value = value })
}

const sourcesLabel = computed(() => {
  const count = props.filters.documentIds.length
  return count ? `${count} selected` : ''
})

// Attribute filter options: `v:<attribute id>:<value id>` for a value, `u:<attribute id>` for
// "not assigned"; one select edits both filter lists.
const attributeOptions = computed(() => attributes.value.flatMap(a => {
  const name = a.retired ? `${a.name} (retired)` : a.name
  return [
    ...orderedValues(a).map(v => ({
      label: `${name}: ${valueName(v)}${v.retired ? ' (retired)' : ''}`, value: `v:${a.id}:${v.id}`, unassigned: false
    })),
    { label: `${name}: not assigned`, value: `u:${a.id}`, unassigned: true }
  ]
}))
const attributeNeedle = ref('')
const filteredAttributeOptions = computed(() => {
  const needle = attributeNeedle.value.toLocaleLowerCase()
  return needle ? attributeOptions.value.filter(o => o.label.toLocaleLowerCase().includes(needle)) : attributeOptions.value
})
function filterAttributes (value: string, update: (fn: () => void) => void) {
  update(() => { attributeNeedle.value = value })
}
const attributeFilter = computed(() => [
  ...props.filters.attributeValues.map(v => `v:${v}`),
  ...props.filters.attributeUnassigned.map(a => `u:${a}`)
])
function setAttributeFilter (value: string[] | null) {
  const list = value ?? []
  emit('change', {
    attributeValues: list.filter(v => v.startsWith('v:')).map(v => v.slice(2)),
    attributeUnassigned: list.filter(v => v.startsWith('u:')).map(v => v.slice(2))
  })
}
const attributesLabel = computed(() => {
  const count = attributeFilter.value.length
  return count ? `${count} selected` : ''
})

const shownAttributeOptions = computed(() => attributes.value.map(a => ({
  label: a.retired ? `${a.name} (retired)` : a.name, value: a.id
})))
// Only attributes that still exist count as shown.
const shownIds = computed(() => {
  const ids = new Set(props.shownAttributeIds ?? [])
  return attributes.value.filter(a => ids.has(a.id)).map(a => a.id)
})
// The shown attributes by name, in the columns' order (cut short when they do not fit).
const shownLabel = computed(() => {
  const ids = new Set(shownIds.value)
  return shownAttributeOptions.value.filter(o => ids.has(o.value)).map(o => o.label).join(', ')
})
</script>

<style scoped>
.concordance-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.concordance-toolbar__tags {
  flex: 1 1 220px;
  max-width: 360px;
}

.concordance-toolbar__search {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  flex: 1 1 420px;
  max-width: 760px;
  gap: 6px;
}

.concordance-toolbar__text {
  flex: 1 1 180px;
  min-width: 0;
}

.concordance-toolbar__scope {
  width: 130px;
}

.concordance-toolbar__document-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: min(360px, calc(100vw - 32px));
  padding: 12px;
}

.concordance-toolbar__menu-hint {
  margin: 0;
  font-size: 0.8rem;
  color: rgba(0, 0, 0, 0.65);
}

.concordance-toolbar__sources {
  flex: 1 1 180px;
  max-width: 280px;
}

.concordance-toolbar__attributes {
  flex: 1 1 180px;
  max-width: 280px;
}

.concordance-toolbar__show-attribute {
  width: 180px;
}

/* One line, cut short, whatever the number of names. */
.concordance-toolbar__show-attribute :deep(.q-field__native) {
  flex-wrap: nowrap;
}

.concordance-toolbar__show-attribute :deep(.q-field__native > span) {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.concordance-toolbar__status {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}

.concordance-toolbar__years {
  display: flex;
  gap: 6px;
}

.concordance-toolbar__year {
  width: 104px;
}

.concordance-toolbar__sort {
  width: 160px;
}

.concordance-toolbar__mode {
  flex: 0 1 170px;
  min-width: 120px;
}

.concordance-toolbar__k {
  width: 84px;
}

.concordance-toolbar__dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  margin-right: 6px;
}
</style>
