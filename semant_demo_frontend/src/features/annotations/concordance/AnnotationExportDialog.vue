<template>
  <!-- CSV export of the workspace's annotations (#719): what to export, which column groups, the
       separator; the file is saved only once it arrived whole, and the dialog then says what it
       holds. It stays open (and cannot be dismissed) while the file is being written. -->
  <q-dialog :model-value="modelValue" :persistent="running" @update:model-value="close">
    <q-card class="annotation-export" data-testid="export-dialog">
      <q-card-section class="annotation-export__head">
        <div class="text-h6">Export annotations as CSV</div>
        <q-space />
        <q-btn flat round dense icon="close" aria-label="Close" :disable="running" @click="close(false)" />
      </q-card-section>

      <q-card-section class="annotation-export__body">
        <fieldset class="annotation-export__group" :disabled="running">
          <legend class="text-subtitle2">Annotations</legend>

          <div class="annotation-export__choice">
            <q-radio
              v-model="options.scope"
              :val="AnnotationExportScope.selection"
              :disable="!selectedCount || running"
              :label="`Selected annotations (${selectedCount})`"
              data-testid="export-scope-selection"
            />
            <div class="annotation-export__caption text-caption text-grey-8">
              <template v-if="!selectedCount">Nothing is selected.</template>
              <template v-else>
                Every selected annotation, whatever its status.
                <span v-if="hiddenSelected" class="text-orange-10" data-testid="export-hidden-selected">
                  {{ plural(hiddenSelected, 'of them is', 'of them are') }} not shown by the current filters (or no
                  longer {{ hiddenSelected === 1 ? 'exists' : 'exist' }}); {{ hiddenSelected === 1 ? 'it is' : 'they are' }}
                  exported too.
                </span>
              </template>
            </div>
          </div>

          <div class="annotation-export__choice">
            <q-radio
              v-model="options.scope"
              :val="AnnotationExportScope.filters"
              :disable="!filtersExportable || running"
              :label="ranked || needsText ? 'Current filter matches' : `Current filter matches (${total})`"
              data-testid="export-scope-filters"
            />
            <div class="annotation-export__caption text-caption text-grey-8">
              <template v-if="ranked">
                Results ranked by meaning or similarity cannot be exported yet; choose <em>Words</em> under
                <em>Find by</em> to export every match.
              </template>
              <template v-else-if="needsText">Enter a text first.</template>
              <template v-else>
                Every match on all pages, not only the rows shown.
                <span data-testid="export-filter-summary">{{ filterSummary }}</span>
              </template>
            </div>
          </div>

          <div class="annotation-export__choice">
            <q-radio
              v-model="options.scope"
              :val="AnnotationExportScope.collection"
              :disable="running"
              label="All annotations in the collection"
              data-testid="export-scope-collection"
            />
            <div class="annotation-export__caption text-caption text-grey-8">No filters; only the statuses chosen here.</div>
            <div class="annotation-export__statuses" role="group" aria-label="Statuses to export">
              <q-checkbox
                v-for="type in TYPES"
                :key="type"
                v-model="options.types"
                :val="type"
                dense
                :disable="options.scope !== AnnotationExportScope.collection || running"
                :label="statusLabel(type)"
                :data-testid="`export-status-${type}`"
              />
            </div>
            <div
              v-if="options.scope === AnnotationExportScope.collection && !options.types.length"
              class="text-caption text-negative"
              role="alert"
            >
              Choose at least one status.
            </div>
          </div>
        </fieldset>

        <fieldset class="annotation-export__group" :disabled="running">
          <legend class="text-subtitle2">Columns</legend>
          <div class="text-caption text-grey-8 q-mb-xs">
            Always included: annotation and tag ids, tag, status, annotated text with left and right context,
            document id with the start and end in the document's text, and attribute values.
          </div>
          <q-toggle
            v-model="options.documentMetadata"
            dense
            label="Document metadata (title, year, authors, library, language, …)"
            data-testid="export-document-metadata"
          />
          <q-toggle
            v-model="options.chunkMetadata"
            dense
            label="Language and classifications of the passage where the annotation starts"
            data-testid="export-chunk-metadata"
          />
          <q-toggle
            v-model="options.provenance"
            dense
            label="Provenance (who created and reviewed it, when, AI run and confidence)"
            data-testid="export-provenance"
          />
        </fieldset>

        <fieldset class="annotation-export__group" :disabled="running">
          <legend class="text-subtitle2">Separator</legend>
          <q-option-group
            v-model="options.delimiter"
            inline
            dense
            :options="DELIMITERS"
            :disable="running"
            data-testid="export-delimiter"
          />
        </fieldset>
      </q-card-section>

      <q-card-section class="annotation-export__status q-pt-none" aria-live="polite">
        <div v-if="error" class="text-negative" role="alert" data-testid="export-error">{{ error }}</div>
        <div v-else-if="result" class="annotation-export__result" role="status" data-testid="export-result">
          <q-icon name="task_alt" color="positive" size="1.2em" aria-hidden="true" />
          <span>{{ resultText(result) }}</span>
        </div>
        <div v-else-if="running" class="text-grey-8" role="status">
          <q-spinner size="1.1em" color="primary" /> Writing the file…
        </div>
        <div v-else class="text-grey-8" data-testid="export-target">{{ targetText }}</div>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat no-caps color="primary" label="Close" :disable="running" @click="close(false)" />
        <q-btn
          unelevated
          no-caps
          color="primary"
          icon="download"
          label="Download CSV"
          :loading="running"
          :disable="!canExport"
          data-testid="export-download"
          @click="download"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  QBtn, QCard, QCardActions, QCardSection, QCheckbox, QDialog, QIcon, QOptionGroup, QRadio, QSpace, QSpinner, QToggle
} from 'quasar'
import { AnnotationExportScope, CsvDelimiter, SpanType, type AnnotationCounts } from 'src/generated/api'
import { countAnnotations } from 'src/features/annotations/annotationCounts'
import { plural } from 'src/shared/plural'
import type { ConcordanceFilters } from './concordanceStore'
import {
  defaultExportOptions, downloadExport, exportFailure, exportRequest, resultText, STATUS_NAMES,
  type ExportOptions, type ExportResult
} from './annotationExport'

const props = defineProps<{
  modelValue: boolean
  collectionId: string
  filters: ConcordanceFilters
  /** The active filters in words ("Tag: Osoba · Status: Rejected"). */
  filterSummary: string
  selectedIds: Set<string>
  /** Selected annotations the current filters do not show; null while unknown. */
  hiddenSelected: number | null
  /** Matches of the current filters. */
  total: number
  /** The results are a ranked top k (#664): not exportable as filter matches yet. */
  ranked: boolean
  /** A ranked mode waits for its text. */
  needsText: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const TYPES = [SpanType.pos, SpanType.auto, SpanType.neg]
const DELIMITERS = [
  { value: CsvDelimiter.comma, label: 'Comma (,)' },
  { value: CsvDelimiter.semicolon, label: 'Semicolon (;) for Excel with Czech or other European regional settings' }
]

const options = ref<ExportOptions>(defaultExportOptions(AnnotationExportScope.collection))
const counts = ref<AnnotationCounts | null>(null)
const running = ref(false)
const error = ref<string | null>(null)
const result = ref<ExportResult | null>(null)
let controller: AbortController | null = null

const selectedCount = computed(() => props.selectedIds.size)
const filtersExportable = computed(() => !props.ranked && !props.needsText)

function statusLabel (type: SpanType): string {
  const n = counts.value && { [SpanType.pos]: counts.value.approved, [SpanType.auto]: counts.value.suggestions, [SpanType.neg]: counts.value.rejected }[type]
  return n == null ? STATUS_NAMES[type] : `${STATUS_NAMES[type]} (${n})`
}

const canExport = computed(() => {
  if (running.value) return false
  switch (options.value.scope) {
    case AnnotationExportScope.selection: return selectedCount.value > 0
    case AnnotationExportScope.filters: return filtersExportable.value
    default: return options.value.types.length > 0
  }
})

/** The count the file will hold, as known before the export. */
const targetText = computed(() => {
  switch (options.value.scope) {
    case AnnotationExportScope.selection:
      return `Exports ${plural(selectedCount.value, 'selected annotation')}.`
    case AnnotationExportScope.filters:
      return filtersExportable.value ? `Exports ${plural(props.total, 'matching annotation')}.` : ''
    default: {
      const c = counts.value
      if (!c) return 'Exports every annotation of the chosen statuses.'
      const n = options.value.types.reduce((sum, t) => sum + (t === SpanType.pos ? c.approved : t === SpanType.auto ? c.suggestions : c.rejected), 0)
      return `Exports ${plural(n, 'annotation')}.`
    }
  }
})

/** Opens on the selection when there is one, else on the filter matches when exportable. */
function opened () {
  const scope = selectedCount.value
    ? AnnotationExportScope.selection
    : filtersExportable.value ? AnnotationExportScope.filters : AnnotationExportScope.collection
  options.value = { ...options.value, scope }
  error.value = null
  result.value = null
  counts.value = null
  const id = props.collectionId
  countAnnotations(id).then(c => { if (props.collectionId === id) counts.value = c }).catch(() => {
    // Counts only label the statuses; the export does not need them.
  })
}

watch(() => props.modelValue, isOpen => { if (isOpen) opened() }, { immediate: true })

function close (value: boolean) {
  if (running.value) return
  emit('update:modelValue', value)
}

async function download () {
  if (!canExport.value) return
  running.value = true
  error.value = null
  result.value = null
  controller = new AbortController()
  try {
    result.value = await downloadExport(props.collectionId,
      exportRequest(options.value, props.filters, props.selectedIds), controller.signal)
  } catch (e) {
    if (controller?.signal.aborted) return
    error.value = await exportFailure(e)
  } finally {
    running.value = false
    controller = null
  }
}

onBeforeUnmount(() => controller?.abort())
</script>

<style scoped>
.annotation-export {
  width: 600px;
  max-width: 95vw;
}

.annotation-export__head {
  display: flex;
  align-items: center;
  padding-bottom: 0;
}

.annotation-export__body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 65vh;
  overflow-y: auto;
}

.annotation-export__group {
  border: 0;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.annotation-export__group legend {
  padding: 0;
  margin-bottom: 4px;
}

.annotation-export__caption {
  margin-left: 40px;
}

.annotation-export__statuses {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin: 4px 0 0 40px;
}

.annotation-export__result {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  overflow-wrap: anywhere;
}
</style>
