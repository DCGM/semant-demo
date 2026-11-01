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

    <q-input
      :model-value="filters.text"
      dense
      outlined
      clearable
      debounce="400"
      label="Annotated text"
      class="concordance-toolbar__text"
      data-testid="concordance-text"
      @update:model-value="value => emit('change', { text: String(value ?? '') })"
    >
      <template #prepend><q-icon name="search" /></template>
    </q-input>

    <q-select
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
        :model-value="filters.yearFrom ?? ''"
        dense
        outlined
        type="number"
        debounce="500"
        label="From year"
        class="concordance-toolbar__year"
        data-testid="concordance-year-from"
        @update:model-value="value => emit('change', { yearFrom: toYear(value) })"
      />
      <q-input
        :model-value="filters.yearTo ?? ''"
        dense
        outlined
        type="number"
        debounce="500"
        label="To year"
        class="concordance-toolbar__year"
        data-testid="concordance-year-to"
        @update:model-value="value => emit('change', { yearTo: toYear(value) })"
      />
    </div>

    <q-select
      :model-value="filters.sort"
      :options="sortOptions"
      emit-value
      map-options
      dense
      outlined
      options-dense
      label="Sort by"
      class="concordance-toolbar__sort"
      data-testid="concordance-sort"
      @update:model-value="value => emit('change', { sort: value })"
    />

    <q-select
      v-if="attributes.length"
      :model-value="shownAttributeId"
      :options="shownAttributeOptions"
      emit-value
      map-options
      clearable
      dense
      outlined
      options-dense
      label="Show attribute"
      class="concordance-toolbar__show-attribute"
      data-testid="concordance-show-attribute"
      @update:model-value="value => emit('show-attribute', value ?? null)"
    >
      <q-tooltip>Shows the attribute's values in a column of their own, where they can be assigned</q-tooltip>
    </q-select>

    <q-btn
      flat
      dense
      no-caps
      color="primary"
      icon="filter_alt_off"
      label="Reset"
      :disable="!filtersChanged"
      @click="emit('reset')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { QBtn, QCheckbox, QIcon, QInput, QItem, QItemLabel, QItemSection, QSelect, QTooltip } from 'quasar'
import { AnnotationSort, SpanType, type AnnotatedDocument, type Attribute, type Tag } from 'src/generated/api'
import { orderedValues, valueName } from 'src/features/attributes/attributeForm'
import { defaultFilters, type ConcordanceFilters } from './concordanceStore'

const props = defineProps<{
  filters: ConcordanceFilters
  tags: Tag[]
  documents: AnnotatedDocument[]
  documentsError?: string | null
  /** The collection's attribute definitions (#331), retired ones included. */
  attributes?: Attribute[]
  /** The attribute shown in a column of its own. */
  shownAttributeId?: string | null
}>()

const emit = defineEmits<{
  change: [change: Partial<ConcordanceFilters>]
  reset: []
  'show-attribute': [attributeId: string | null]
}>()

const attributes = computed(() => props.attributes ?? [])

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

const filtersChanged = computed(() => JSON.stringify(props.filters) !== JSON.stringify(defaultFilters()))
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

.concordance-toolbar__text {
  flex: 1 1 200px;
  max-width: 320px;
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

.concordance-toolbar__dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  margin-right: 6px;
}
</style>
