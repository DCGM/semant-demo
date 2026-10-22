<template>
  <q-form class="corpus-filters" data-testid="corpus-filters" aria-label="Document filters" @submit="apply">
    <h2 class="corpus-filters__title">Filter documents</h2>
    <div class="corpus-filters__fields">
      <fieldset class="corpus-filters__years">
        <legend class="sr-only">Publication year</legend>
        <q-input
          v-model="yearMin" label="Year from" dense outlined inputmode="numeric" maxlength="4"
          :rules="[validYear]" lazy-rules hide-bottom-space data-testid="filter-year-min"
        />
        <q-input
          v-model="yearMax" label="Year to" dense outlined inputmode="numeric" maxlength="4"
          :rules="[validYear]" lazy-rules hide-bottom-space data-testid="filter-year-max"
        />
        <p class="corpus-filters__hint">Publication years, both included; documents without a year do not match.</p>
      </fieldset>
      <q-input
        v-model="title" label="Title contains" dense outlined clearable maxlength="100"
        :rules="[validTitle]" lazy-rules
        hint="Enter adds it; several titles match any of them. Each word inside a title word, in any order; ignores case, not diacritics (skola ≠ škola)."
        data-testid="filter-title"
      />
      <q-select
        :model-value="[]" :options="libraryOptions" label="Source library" multiple emit-value map-options
        dense outlined options-dense :disable="!librariesAvailable"
        :hint="librariesAvailable ? 'Applied when chosen; any of the selected libraries.' : 'Not available: this corpus database does not record libraries.'"
        data-testid="filter-libraries" @update:model-value="(values: string[]) => toggle('libraries', values)"
      >
        <template #option="{ itemProps, opt }">
          <q-item v-bind="itemProps" :aria-selected="String(chosen('libraries', opt.value))">
            <q-item-section side><q-icon v-bind="checkbox(chosen('libraries', opt.value))" /></q-item-section>
            <q-item-section>{{ opt.label }}</q-item-section>
          </q-item>
        </template>
      </q-select>
      <q-select
        :model-value="[]" :options="languageOptions" label="Document language" multiple emit-value map-options
        dense outlined options-dense :disable="!languagesAvailable"
        hint="Applied when chosen; matches language values by word, ignoring case (ces also matches CES)."
        data-testid="filter-languages" @update:model-value="(values: string[]) => toggle('languages', values)"
      >
        <template #option="{ itemProps, opt }">
          <q-item v-bind="itemProps" :aria-selected="String(chosen('languages', opt.value))">
            <q-item-section side><q-icon v-bind="checkbox(chosen('languages', opt.value))" /></q-item-section>
            <q-item-section>{{ opt.label }}</q-item-section>
          </q-item>
        </template>
      </q-select>
    </div>
    <div class="corpus-filters__actions">
      <q-btn type="submit" color="primary" unelevated label="Apply" icon="filter_alt" :loading="loading" data-testid="filter-apply" />
      <q-btn flat color="primary" label="Clear all" :disable="!hasFilters" data-testid="filter-clear" @click="clear" />
    </div>
  </q-form>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CategoryDistribution, DocumentFilters } from 'src/generated/api'
import { isUnfiltered, languageLabel, libraryLabel } from './corpusOverview'

/**
 * The filter form of the corpus overview (#361). The year fields are a draft until Apply (or
 * Enter); a title is added to the applied titles by Apply (or Enter) and the field is emptied;
 * a library or language is applied as soon as it is chosen or unchosen. Every change emits the
 * complete filters, built on the applied ones. The applied values are shown by the page, not in
 * these fields; the choices of library and language are the values of the whole corpus.
 */
const props = defineProps<{
  applied: DocumentFilters
  libraries?: CategoryDistribution
  languages?: CategoryDistribution
  loading?: boolean
}>()

const emit = defineEmits<{ apply: [filters: DocumentFilters] }>()

const currentYear = new Date().getFullYear()
const MAX_TITLES = 10
const MAX_TITLE_WORDS = 5
const TITLE_WORD = /[\p{L}\p{N}]+/gu

const yearMin = ref<string | null>(null)
const yearMax = ref<string | null>(null)
const title = ref<string | null>(null)

// The year fields show the applied range again whenever it changes (Apply, a removed chip,
// a period applied from the timeline, Clear all).
watch(() => [props.applied.yearMin, props.applied.yearMax], ([min, max]) => {
  yearMin.value = min != null ? String(min) : null
  yearMax.value = max != null ? String(max) : null
}, { immediate: true })

const options = (distribution: CategoryDistribution | undefined, label: (value: string) => string) =>
  (distribution?.values ?? []).map(v => ({ value: v.value, label: label(v.value) }))

const libraryOptions = computed(() => options(props.libraries, libraryLabel))
const languageOptions = computed(() => options(props.languages, languageLabel))
const librariesAvailable = computed(() => props.libraries?.available === true)
const languagesAvailable = computed(() => props.languages?.available === true)

/** A year field is a plain text field (no step buttons); empty means no bound. */
const year = (value: string | null) => (value?.trim() ? Number(value.trim()) : undefined)

/** Checked before Apply (the form submits only when every rule passes); the server checks again. */
function validYear (value: string | null): true | string {
  const text = value?.trim() ?? ''
  if (!text) return true
  if (!/^\d+$/.test(text) || Number(text) < 1) return 'Enter a whole year'
  return Number(text) <= currentYear || `At most ${currentYear}`
}

/** The server's title rules, checked before a title is added. */
function validTitle (value: string | null): true | string {
  const text = value?.trim() ?? ''
  if (!text) return true
  if (/[*?]/.test(text)) return 'Wildcards (* or ?) are not supported; enter whole or partial words'
  const words = (text.match(TITLE_WORD) ?? []).filter(w => w.length >= 2)
  if (!words.length) return 'Enter at least one word of two or more letters or digits'
  if (new Set(words.map(w => w.toLowerCase())).size > MAX_TITLE_WORDS) return `At most ${MAX_TITLE_WORDS} words`
  return (props.applied.titleContains?.length ?? 0) < MAX_TITLES || `At most ${MAX_TITLES} titles`
}

const hasFilters = computed(() => !isUnfiltered(props.applied) || !!yearMin.value?.trim() ||
  !!yearMax.value?.trim() || !!title.value?.trim())

function apply () {
  const text = title.value?.trim()
  emit('apply', {
    ...props.applied,
    yearMin: year(yearMin.value),
    yearMax: year(yearMax.value),
    titleContains: text ? [...(props.applied.titleContains ?? []), text] : props.applied.titleContains
  })
  title.value = null
}

type ListKey = 'libraries' | 'languages'

const chosen = (key: ListKey, value: string) => (props.applied[key] ?? []).includes(value)
const checkbox = (on: boolean) => ({ name: on ? 'check_box' : 'check_box_outline_blank', color: on ? 'primary' : undefined })

/**
 * The selects hold no value of their own (their field stays empty; the page shows the applied
 * values), so a click on an option reports just that option: it is added to or removed from
 * the applied values, which are applied at once.
 */
function toggle (key: ListKey, clicked: string[]) {
  let values = [...(props.applied[key] ?? [])]
  for (const value of clicked) values = values.includes(value) ? values.filter(v => v !== value) : [...values, value]
  emit('apply', { ...props.applied, [key]: values })
}

function clear () {
  title.value = null
  emit('apply', {})
}
</script>

<style scoped lang="scss">
.corpus-filters {
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 12px;
  padding: 12px 16px 16px;
  margin-bottom: 20px;
}

.corpus-filters__title {
  font-size: 1.15rem;
  font-weight: 600;
  line-height: 1.3;
  margin: 0 0 8px;
}

.corpus-filters__fields {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(0, 1.4fr));
  gap: 12px 16px;
  align-items: start;
}

.corpus-filters__years {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 8px;
  border: 0;
  margin: 0;
  padding: 0;
  min-width: 0;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.corpus-filters__hint {
  grid-column: 1 / -1;
  color: rgba(0, 0, 0, 0.54);
  font-size: 11px;
  line-height: 1.3;
  margin: 4px 0 0;
}

.corpus-filters__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

@media (max-width: 1023px) {
  .corpus-filters__fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 599px) {
  .corpus-filters__fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
