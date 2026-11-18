<template>
  <div class="concordance-toolbar" data-testid="concordance-toolbar">
    <div class="concordance-toolbar__row">
      <!-- A phone shows only this summary until the filters are asked for. -->
      <div v-if="phone" class="concordance-toolbar__phone-bar">
        <q-btn
          outline
          dense
          no-caps
          color="primary"
          icon="filter_list"
          :label="activeCount ? `Filters (${activeCount})` : 'Filters'"
          class="concordance-toolbar__phone-toggle"
          aria-controls="concordance-filter-form"
          :aria-expanded="formOpen ? 'true' : 'false'"
          data-testid="concordance-filters-toggle"
          @click="formOpen = !formOpen"
        >
          <q-icon :name="formOpen ? 'expand_less' : 'expand_more'" right />
        </q-btn>
        <span v-if="!formOpen && queryText" class="concordance-toolbar__summary" data-testid="concordance-summary">{{ queryText }}</span>
      </div>

      <div v-show="formVisible" id="concordance-filter-form" class="concordance-toolbar__primary">
        <q-select
          :model-value="filters.tagIds"
          :options="tagOptions"
          multiple
          emit-value
          map-options
          clearable
          dense
          outlined
          options-dense
          hide-bottom-space
          label="Tags"
          :display-value="tagsLabel"
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
              <q-item-section v-if="opt.count != null" side>
                <span class="concordance-toolbar__count" data-testid="concordance-tag-count">{{ opt.count }}</span>
              </q-item-section>
            </q-item>
          </template>
        </q-select>

        <!-- One segmented control: any combination of the statuses, at least one. -->
        <q-btn-group outline class="concordance-toolbar__status" role="group" aria-label="Status">
          <q-btn
            v-for="option in statusOptions"
            :key="option.value"
            dense
            no-caps
            :unelevated="statusActive(option.value)"
            :outline="!statusActive(option.value)"
            :color="statusActive(option.value) ? 'primary' : 'grey-8'"
            :icon="statusActive(option.value) ? 'check' : undefined"
            :label="option.label"
            :aria-pressed="statusActive(option.value) ? 'true' : 'false'"
            :disable="filters.types.length === 1 && statusActive(option.value)"
            :data-testid="`concordance-status-${option.value}`"
            @click="toggleType(option.value, !statusActive(option.value))"
          >
            <span v-if="statusCount(option.value) != null" class="concordance-toolbar__count" :data-testid="`concordance-status-count-${option.value}`">{{ statusCount(option.value) }}</span>
            <q-tooltip v-if="option.hint">{{ option.hint }}</q-tooltip>
          </q-btn>
        </q-btn-group>

        <div class="concordance-toolbar__search" role="group" aria-label="Text search">
          <q-input
            ref="textInput"
            :model-value="filters.text"
            dense
            outlined
            clearable
            debounce="400"
            label="Contains words"
            hide-bottom-space
            class="concordance-toolbar__text"
            data-testid="concordance-text"
            @update:model-value="value => emit('change', { text: String(value ?? '') })"
          >
            <template #prepend><q-icon name="search" /></template>
            <template #append>
              <q-btn
                flat
                round
                dense
                size="sm"
                icon="help_outline"
                aria-label="How the text is matched"
                data-testid="concordance-text-help"
              >
                <q-popup-proxy>
                  <p class="concordance-toolbar__help">{{ textHint }}</p>
                </q-popup-proxy>
              </q-btn>
            </template>
          </q-input>
          <q-select
            :model-value="filters.textScope"
            :options="scopeOptions"
            emit-value
            map-options
            dense
            outlined
            options-dense
            hide-bottom-space
            label="Search in"
            class="concordance-toolbar__scope"
            data-testid="concordance-text-scope"
            @update:model-value="value => emit('change', { textScope: value })"
          />
          <q-input
            :model-value="filters.similarity"
            dense
            outlined
            clearable
            debounce="400"
            label="Similar meaning"
            hide-bottom-space
            class="concordance-toolbar__text"
            data-testid="concordance-similarity"
            @update:model-value="value => emit('change', { similarity: String(value ?? '') })"
          >
            <template #prepend><q-icon name="auto_awesome" /></template>
            <template #append>
              <q-btn
                flat
                round
                dense
                size="sm"
                icon="help_outline"
                aria-label="How the similarity text ranks"
                data-testid="concordance-similarity-help"
              >
                <q-popup-proxy>
                  <p class="concordance-toolbar__help">{{ similarityHint }}</p>
                </q-popup-proxy>
              </q-btn>
            </template>
          </q-input>
          <q-checkbox
            v-if="filters.mode === RetrievalMode.similar"
            dense
            :model-value="filters.includeSource"
            label="Include source"
            data-testid="concordance-include-source"
            @update:model-value="value => emit('change', { includeSource: !!value })"
          />
        </div>

        <q-btn
          outline
          dense
          no-caps
          color="primary"
          :icon="moreOpen ? 'expand_less' : 'tune'"
          :label="moreFilterCount ? `More filters (${moreFilterCount})` : 'More filters'"
          class="concordance-toolbar__more-button"
          aria-controls="concordance-more-filters"
          :aria-expanded="moreOpen ? 'true' : 'false'"
          data-testid="concordance-more-filters"
          @click="toggleMore"
        >
          <q-tooltip>Sources, years, document title, library, language and attributes</q-tooltip>
        </q-btn>
      </div>

      <div
        v-if="attributes.length"
        class="concordance-toolbar__display"
        role="group"
        aria-label="Display settings, they do not limit the results"
        data-testid="concordance-display"
      >
        <span class="concordance-toolbar__group-label">Display<q-tooltip>Display settings change how the results are shown, not which annotations match</q-tooltip></span>
        <q-select
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
    </div>

    <!-- Always one line high, so the counts arriving later do not move the list. -->
    <p v-show="formVisible" class="concordance-toolbar__population" data-testid="concordance-facets-note">
      <template v-if="!facets" />
      <template v-else-if="facets.population === 'top_k'">Counts are of these {{ facets.k }} results.</template>
      <template v-else>Counts show how many annotations each choice gives; a filter does not narrow its own counts.</template>
    </p>

    <div
      v-show="formVisible && moreOpen"
      id="concordance-more-filters"
      ref="morePanel"
      class="concordance-toolbar__more"
      role="group"
      aria-label="More filters"
      data-testid="concordance-more-panel"
    >
      <div class="concordance-toolbar__more-section" data-testid="concordance-document-form">
        <p class="concordance-toolbar__more-title">Documents</p>
        <div class="concordance-toolbar__more-fields">
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
          <div class="concordance-toolbar__years" role="group" aria-label="Publication years" :title="yearHint ?? undefined">
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
          <p v-if="yearHint" class="concordance-toolbar__rule" data-testid="concordance-year-hint">{{ yearHint }}</p>
          <q-input
            v-model="titleDraft"
            dense
            outlined
            clearable
            maxlength="100"
            hide-bottom-space
            label="Title contains"
            :error="!!titleError"
            :error-message="titleError ?? undefined"
            class="concordance-toolbar__title"
            data-testid="concordance-title"
            @keydown.enter.prevent="addTitle"
          >
            <template #append>
              <q-btn flat dense round icon="add" aria-label="Add title filter" :disable="!titleDraft?.trim()" @click="addTitle" />
              <q-btn flat round dense size="sm" icon="help_outline" aria-label="How titles are matched" data-testid="concordance-title-help">
                <q-popup-proxy>
                  <p class="concordance-toolbar__help">
                    Enter adds it; several titles match any of them. Each word inside a title word, in any order;
                    ignores case, not diacritics.
                  </p>
                </q-popup-proxy>
              </q-btn>
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
            hide-bottom-space
            :label="libraryOptions.length ? 'Source library' : 'Source library (none recorded)'"
            :disable="!libraryOptions.length"
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
            hide-bottom-space
            :label="languageOptions.length ? 'Document language' : 'Document language (none recorded)'"
            :disable="!languageOptions.length"
            data-testid="concordance-languages"
            @update:model-value="value => setDocumentFilters({ languages: value ?? [] })"
          />
        </div>
      </div>
      <div v-if="attributes.length" class="concordance-toolbar__more-section">
        <p class="concordance-toolbar__more-title">Attributes</p>
        <div class="concordance-toolbar__more-fields">
          <q-select
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
            hide-bottom-space
            label="Attributes"
            class="concordance-toolbar__attributes"
            aria-describedby="concordance-attribute-rule"
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
                  <q-item-label v-if="opt.inapplicable" caption>{{ opt.inapplicable }} on annotations it no longer applies to</q-item-label>
                </q-item-section>
                <q-item-section v-if="opt.count != null" side>
                  <span class="concordance-toolbar__count" data-testid="concordance-attribute-count">{{ opt.count }}</span>
                </q-item-section>
              </q-item>
            </template>
          </q-select>
          <p id="concordance-attribute-rule" class="concordance-toolbar__rule" data-testid="concordance-attribute-rule">
            Values of one attribute match <strong>any</strong> of them (OR); different attributes must <strong>all</strong> match (AND).
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import {
  QBtn, QBtnGroup, QCheckbox, QIcon, QInput, QItem, QItemLabel, QItemSection, QPopupProxy, QSelect, QTooltip, useQuasar
} from 'quasar'
import {
  RetrievalMode, SpanType, TextScope, type AnnotatedDocument, type AnnotationFacets, type Attribute, type DocumentFilters, type Tag
} from 'src/generated/api'
import { orderedValues, valueName } from 'src/features/attributes/attributeForm'
import { languageLabel, libraryLabel } from 'src/features/analytics/corpusOverview'
import { type ConcordanceFilters } from './concordanceStore'
import type { FilterField } from './ConcordanceTable.vue'
import { SCOPE_LABELS, concordanceChips, scopeHintText, similarityHintText, titleProblem } from './filterChips'

const props = defineProps<{
  filters: ConcordanceFilters
  tags: Tag[]
  documents: AnnotatedDocument[]
  documentsError?: string | null
  /** How many annotations each choice gives (#667); none until read or when reading failed. */
  facets?: AnnotationFacets | null
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
const morePanel = ref<HTMLElement | null>(null)

const $q = useQuasar()
/** A phone shows the whole filter form only when asked for; the entered values stay meanwhile. */
const phone = computed(() => $q.screen.lt.sm)
const formOpen = ref(false)
const formVisible = computed(() => !phone.value || formOpen.value)

/** The secondary filters live in an inline panel under the primary row, closed until asked for. */
const moreOpen = ref(false)

function focusPanel () {
  const target = morePanel.value?.querySelector<HTMLElement>('input:not([disabled]), [tabindex="0"]')
  target?.focus()
}

function toggleMore () {
  moreOpen.value = !moreOpen.value
  if (moreOpen.value) void nextTick(focusPanel)
}

/** Brings the filter of a table column to the user (its header's filter button, #665): the text
 * search scoped to exactly that field (annotation or context, also from *Both*, as the header
 * promises), the source picker or the year range. */
function openFilter (field: FilterField) {
  formOpen.value = true
  if (field === 'source' || field === 'year') moreOpen.value = true
  if (field === 'source') {
    void nextTick(() => {
      sourcesSelect.value?.$el.scrollIntoView?.({ block: 'nearest' })
      sourcesSelect.value?.focus()
      sourcesSelect.value?.showPopup()
    })
    return
  }
  const input = field === 'year' ? yearInput.value : textInput.value
  if (field !== 'year') {
    const scope = field === 'annotation' ? TextScope.annotation : TextScope.context
    if (props.filters.textScope !== scope) emit('change', { textScope: scope })
  }
  void nextTick(() => {
    input?.$el.scrollIntoView?.({ block: 'nearest' })
    input?.focus()
  })
}

defineExpose({ openFilter })

/** The counted values of a facet by value, with the facet's missing count; null while not read. */
function facetOf (name: string) {
  const facet = props.facets?.facets.find(f => f.facet === name)
  return facet ? { ...facet, byValue: new Map(facet.values.map(v => [v.value, v])) } : null
}
/** Annotations the choice gives; 0 when the facet counted none with it. Null when not counted. */
function countOf (name: string, value: string): number | null {
  const facet = facetOf(name)
  return facet ? facet.byValue.get(value)?.count ?? 0 : null
}

const tagFacet = computed(() => facetOf('tag'))
const tagOptions = computed(() => props.tags.map(t => ({
  label: t.name, value: t.id, color: t.color, count: tagFacet.value ? tagFacet.value.byValue.get(t.id)?.count ?? 0 : null
})))
const statusCount = (type: SpanType) => countOf('type', type)
const yearHint = computed(() => {
  const facet = facetOf('year')
  if (!facet) return null
  const years = facet.values.map(v => Number(v.value)).sort((a, b) => a - b)
  const range = years.length ? `${years[0]}\u2013${years[years.length - 1]}` : 'no year recorded'
  return `Annotations from ${range}${facet.missing ? `; ${facet.missing} without a year` : ''}`
})
/** The chosen tags in a line of their own, however many: the first name and how many more. */
const tagsLabel = computed(() => {
  const names = props.filters.tagIds.map(id => props.tags.find(t => t.id === id)?.name ?? 'Unknown tag')
  return names.length > 1 ? `${names[0]} +${names.length - 1}` : (names[0] ?? '')
})

const activeCount = computed(() =>
  concordanceChips(props.filters, props.tags, props.documents, attributes.value).length)
const queryText = computed(() => props.filters.text.trim() ? `\u201c${props.filters.text.trim()}\u201d` : '')
const statusActive = (type: SpanType) => props.filters.types.includes(type)

const statusOptions = [
  { value: SpanType.pos, label: 'Confirmed', hint: 'Created by hand or confirmed proposals' },
  { value: SpanType.auto, label: 'Proposals', hint: 'Automatic proposals not yet reviewed' },
  { value: SpanType.neg, label: 'Rejected', hint: 'Rejected proposals, kept as negative examples' }
]

const scopeOptions = Object.values(TextScope).map(value => ({ value, label: SCOPE_LABELS[value] }))
const textHint = computed(() => scopeHintText(props.filters.textScope))
const similarityHint = computed(() => similarityHintText())

function setDocumentFilters (change: Partial<DocumentFilters>) {
  emit('change', { documentFilters: { ...props.filters.documentFilters, ...change } })
}

/** The active filters inside the panel, one per value, as the chips list them. */
const moreFilterCount = computed(() => {
  const f = props.filters
  const d = f.documentFilters
  return f.documentIds.length + f.attributeValues.length + f.attributeUnassigned.length +
    (d.yearMin != null ? 1 : 0) + (d.yearMax != null ? 1 : 0) +
    (d.titleContains?.length ?? 0) + (d.libraries?.length ?? 0) + (d.languages?.length ?? 0)
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
  // The choices are those of the documents; their counts, when read, are those of the whole query
  // without this filter (#667), 0 for a choice nothing matches now.
  const facet = facetOf(key)
  if (facet) for (const value of counts.keys()) counts.set(value, facet.byValue.get(value)?.count ?? 0)
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

/** The annotations of the document under the whole query without the source filter (#667) when
 * read: 0 when none, the choice's own count when the facet left the document out (it lists the
 * documents with most annotations only). */
function documentCount (d: AnnotatedDocument): number {
  const facet = facetOf('document')
  if (!facet) return d.count
  return facet.byValue.get(d.id)?.count ?? (facet.truncated ? d.count : 0)
}

function documentLabel (d: AnnotatedDocument): string {
  const count = documentCount(d)
  if (!d.available) return `Unavailable source (${count})`
  return `${d.title || 'Untitled document'}${d.year ? `, ${d.year}` : ''} (${count})`
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
  const facet = facetOf(`attribute:${a.id}`)
  return [
    ...orderedValues(a).map(v => {
      const found = facet?.byValue.get(v.id)
      return {
        label: `${name}: ${valueName(v)}${v.retired ? ' (retired)' : ''}`,
        value: `v:${a.id}:${v.id}`,
        unassigned: false,
        count: facet ? found?.count ?? 0 : null,
        inapplicable: found?.inapplicable ?? 0
      }
    }),
    { label: `${name}: not assigned`, value: `u:${a.id}`, unassigned: true, count: facet ? facet.missing : null, inapplicable: 0 }
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
/* The layout follows the width of the toolbar's own container, not the viewport: the sidebars
 * take width from the list. */
.concordance-toolbar {
  container: concordance-toolbar / inline-size;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.concordance-toolbar__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

/* The controls take part in the row directly; the wrapper only shows and hides them. */
.concordance-toolbar__primary {
  display: contents;
}

.concordance-toolbar__count {
  margin-left: 6px;
  font-size: 0.85em;
  opacity: 0.75;
  font-variant-numeric: tabular-nums;
}

.concordance-toolbar__population {
  margin: 0;
  min-height: 1.3em;
  font-size: 0.85em;
  opacity: 0.75;
}

.concordance-toolbar__tags {
  flex: 0 1 190px;
  min-width: 130px;
}

.concordance-toolbar__status {
  flex: 0 0 auto;
}

.concordance-toolbar__status :deep(.q-btn) {
  min-height: 40px;
  padding: 0 12px;
}

/* The check mark and the label stay on one line, whatever the width. */
.concordance-toolbar__status :deep(.q-btn__content) {
  flex-wrap: nowrap;
  white-space: nowrap;
}

.concordance-toolbar__more-button {
  min-height: 40px;
  flex: 0 0 auto;
}

.concordance-toolbar__search {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  flex: 1 1 380px;
  min-width: 0;
  gap: 8px;
}

.concordance-toolbar__text {
  flex: 1 1 180px;
  min-width: 0;
}

.concordance-toolbar__scope {
  flex: 0 1 140px;
  min-width: 110px;
}

.concordance-toolbar__help {
  max-width: 320px;
  margin: 0;
  padding: 10px 12px;
  font-size: 0.85rem;
}

/* Display settings: apart from the filters, to the right where there is room. */
.concordance-toolbar__display {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  padding-left: 12px;
  border-left: 1px solid rgba(0, 0, 0, 0.18);
}

.concordance-toolbar__group-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(0, 0, 0, 0.6);
}

.concordance-toolbar__show-attribute {
  width: 190px;
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

.concordance-toolbar__phone-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  order: -2;
}

.concordance-toolbar__phone-toggle {
  min-height: 40px;
}

.concordance-toolbar__summary {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: rgba(0, 0, 0, 0.7);
}

.concordance-toolbar__more {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  padding: 8px 12px 12px;
  border: 1px solid rgba(0, 0, 0, 0.18);
  border-radius: 4px;
}

.concordance-toolbar__more-section {
  flex: 1 1 320px;
  min-width: 0;
}

.concordance-toolbar__more-title {
  margin: 0 0 6px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(0, 0, 0, 0.6);
}

.concordance-toolbar__more-fields {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px 12px;
}

.concordance-toolbar__more-fields > .q-field {
  flex: 1 1 220px;
  max-width: 340px;
}

.concordance-toolbar__rule {
  flex: 1 1 100%;
  margin: 0;
  font-size: 0.8rem;
  color: rgba(0, 0, 0, 0.7);
}

.concordance-toolbar__years {
  display: flex;
  gap: 8px;
}

.concordance-toolbar__year {
  width: 104px;
}

.concordance-toolbar__dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  margin-right: 6px;
}

/* Too narrow for one row: the text search gets a row of its own, below the other controls. */
@container concordance-toolbar (max-width: 899px) {
  .concordance-toolbar__search {
    order: 10;
    flex-basis: 100%;
  }
}

@media (max-width: 599px) {
  /* Next to the Filters button, the select taking the rest of the row. */
  .concordance-toolbar__display {
    order: -1;
    padding-left: 0;
    border-left: 0;
    flex: 1 1 0;
    min-width: 150px;
    margin-left: 0;
  }

  .concordance-toolbar__group-label {
    display: none;
  }

  .concordance-toolbar__show-attribute {
    flex: 1 1 0;
    width: auto;
    min-width: 0;
  }

  .concordance-toolbar__tags,
  .concordance-toolbar__status,
  .concordance-toolbar__more-button {
    flex: 1 1 100%;
  }

  .concordance-toolbar__status :deep(.q-btn) {
    flex: 1 1 auto;
    padding: 0 8px;
  }

  .concordance-toolbar__more-fields > .q-field,
  .concordance-toolbar__more-section {
    flex-basis: 100%;
    max-width: none;
  }
}
</style>
