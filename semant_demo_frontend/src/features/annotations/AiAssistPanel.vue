<template>
  <div class="ai-assist-panel" :class="{ 'has-pending': pendingAutoSpans.length > 0 }">
    <!-- The run options fold away while the suggestions are reviewed (#770). -->
    <div class="ai-options-header">
      <span class="ai-section-label q-mb-none">Run options</span>
      <span v-if="!optionsShown" class="ai-options-summary" data-testid="ai-options-summary">
        {{ optionsSummary }}
      </span>
      <q-space />
      <q-btn
        flat dense round size="sm"
        :icon="optionsShown ? 'expand_less' : 'expand_more'"
        :aria-label="optionsShown ? 'Hide run options' : 'Show run options'"
        :aria-expanded="optionsShown ? 'true' : 'false'"
        aria-controls="ai-run-options"
        data-testid="ai-options-toggle"
        @click="toggleOptions"
      >
        <q-tooltip>{{ optionsShown ? 'Hide run options' : 'Show run options' }}</q-tooltip>
      </q-btn>
    </div>

    <!-- Folded: only the per-tag suggestion navigation of the tags that have suggestions. -->
    <div v-if="!optionsShown && tagsWithSuggestions.length" class="ai-tag-list q-mb-sm" data-testid="ai-folded-nav">
      <div v-for="tag in tagsWithSuggestions" :key="tag.id" class="ai-tag-list-row">
        <span class="ai-tag-row ai-tag-checkbox">
          <q-icon
            :name="tag.pictogram || 'label'"
            :style="{ color: tag.color || '#64748b' }"
            size="16px"
            class="q-mr-xs"
          />
          <span class="ai-tag-name">{{ tag.name }}</span>
        </span>
        <AiTagNav
          :count="autoSpansByTag[tag.id].length"
          :index="autoSpanNavIndex(tag.id)"
          @prev="navigateAutoSpan(tag.id, 'prev')"
          @next="navigateAutoSpan(tag.id, 'next')"
        />
      </div>
    </div>

    <!-- display: contents keeps the tag list a flex item of the panel, so its height cap holds. -->
    <div v-show="optionsShown" id="ai-run-options" class="ai-run-options">
      <div class="text-caption text-grey-7 q-mb-xs">
        Pick the tags the AI should look for in this document and choose a mode.
      </div>

      <div class="ai-section-label">Mode</div>
      <q-option-group
        v-model="aiMode"
        :options="aiModeOptions"
        type="radio"
        dense
        class="q-mb-xs"
        :disable="aiAssist.isRunning.value"
      />

      <template v-if="topicerModel.loaded && topicerModel.options.length">
        <div class="ai-section-label">Model</div>
        <q-select
          v-model="topicerModel.selected"
          :options="topicerConfigOptions"
          emit-value
          map-options
          dense
          outlined
          options-dense
          class="q-mb-sm"
          data-testid="ai-model-select"
          :disable="aiAssist.isRunning.value || isPreparingRun"
        />
      </template>
      <div v-else-if="topicerModel.failed" class="text-caption text-grey-7 q-mb-sm" data-testid="ai-model-unavailable">
        The AI models could not be listed; the default model is used.
      </div>

      <div class="ai-section-label">
        Tags
        <span class="text-caption text-grey-6 q-ml-xs">({{ selectedAiTagIds.length }}/{{ tags.length }})</span>
        <q-space />
        <q-btn flat dense no-caps size="sm" label="All" @click="selectAllAiTags" :disable="aiAssist.isRunning.value" />
        <q-btn flat dense no-caps size="sm" label="None" @click="clearAiTags" :disable="aiAssist.isRunning.value" />
      </div>
      <div v-if="!tags.length" class="text-body2 text-grey-6 q-mb-sm">
        No tags in this collection yet.
      </div>
      <div v-else class="ai-tag-list q-mb-sm">
        <div
          v-for="tag in tags"
          :key="tag.id"
          class="ai-tag-list-row"
        >
          <q-checkbox
            :model-value="selectedAiTagIds.includes(tag.id)"
            @update:model-value="(v: unknown) => toggleAiTag(tag.id, !!v)"
            dense
            size="sm"
            :disable="aiAssist.isRunning.value"
            class="ai-tag-checkbox"
          >
            <template v-slot:default>
              <span class="ai-tag-row">
                <q-icon
                  :name="tag.pictogram || 'label'"
                  :style="{ color: tag.color || '#64748b' }"
                  size="16px"
                  class="q-mr-xs"
                />
                <span class="ai-tag-name">{{ tag.name }}</span>
              </span>
            </template>
          </q-checkbox>
          <AiTagNav
            v-if="autoSpansByTag[tag.id]?.length"
            :count="autoSpansByTag[tag.id].length"
            :index="autoSpanNavIndex(tag.id)"
            @prev="navigateAutoSpan(tag.id, 'prev')"
            @next="navigateAutoSpan(tag.id, 'next')"
          />
        </div>
      </div>

    </div>

    <div class="ai-actions q-mb-xs">
      <q-btn
        v-if="!aiAssist.isRunning.value"
        color="primary"
        icon="auto_awesome"
        label="Run AI"
        no-caps
        :loading="isPreparingRun"
        :disable="!selectedAiTagIds.length"
        @click="onRunAi"
      />
      <q-btn
        v-else
        color="negative"
        icon="stop"
        label="Cancel"
        no-caps
        @click="aiAssist.cancel"
      />
      <!-- Acts on the selected tags, so only offered while they are in view. -->
      <q-btn
        v-if="optionsShown"
        outline
        color="negative"
        icon="delete_sweep"
        label="Clear unresolved"
        no-caps
        :loading="isBulkDeleting"
        :disable="!selectedAiTagIds.length || aiAssist.isRunning.value"
        @click="onBulkDelete"
      >
        <q-tooltip>
          Delete every unresolved AI suggestion (auto spans) for the selected tags in this document.
        </q-tooltip>
      </q-btn>
    </div>
    <div
      v-if="lastStatusKind === 'deleted' && lastDeletedCount != null"
      class="text-caption text-grey-7"
    >
      Removed {{ lastDeletedCount }} unresolved suggestion(s).
    </div>

    <div
      v-else-if="lastStatusKind === 'processed' && (aiAssist.isRunning.value || aiAssist.processedChunkCount.value > 0)"
      class="ai-progress"
    >
      <q-spinner v-if="aiAssist.isRunning.value" color="primary" size="1.2em" class="q-mr-xs" />
      <span class="text-body2">
        Processed {{ aiAssist.processedChunkCount.value }} chunks,
        {{ aiAssist.totalSpansAdded.value }} suggestions.
        <template v-if="aiAssist.lastStatus.value === 'cancelled'">Cancelled; saved suggestions are kept.</template>
      </span>
    </div>

    <!-- Selection-scoped run (triggered from the in-text "Suggest tags"
         popover button). Lives next to the document-wide progress so
         the user can see something is happening even after the
         popover closes. -->
    <div v-if="aiAssist.isSelectionRunning.value" class="ai-progress q-mb-xs">
      <q-spinner color="primary" size="1.2em" class="q-mr-xs" />
      <span class="text-body2">Generating annotation suggestions for the selected passage…</span>
      <q-space />
      <q-btn
        flat dense no-caps
        size="sm"
        color="negative"
        icon="stop"
        label="Cancel"
        @click="aiAssist.cancelSelection"
      />
    </div>

    <div v-if="aiAssist.lastSelectionError.value" class="ai-error q-mb-xs">
      {{ aiAssist.lastSelectionError.value }}
    </div>

    <div v-if="aiAssist.lastError.value" class="ai-error q-mb-xs">
      {{ aiAssist.lastError.value }}
    </div>

    <div
      v-for="notice in aiAssist.lastNotices.value"
      :key="notice"
      class="ai-notice q-mb-xs"
      data-testid="ai-run-notice"
    >
      <q-icon name="info" size="16px" class="q-mr-xs" />
      <span>{{ notice }}</span>
    </div>

    <q-separator class="q-my-xs" />

    <div class="ai-section-label">
      Pending suggestions
      <span class="text-caption text-grey-6 q-ml-xs">({{ pendingAutoSpans.length }})</span>
    </div>
    <div v-if="!pendingAutoSpans.length" class="text-body2 text-grey-6">
      No unresolved AI suggestions in the displayed chunks.
    </div>
    <template v-else>
      <div class="auto-span-bulk-bar">
        <q-checkbox
          :model-value="allSuggestionsSelected"
          :indeterminate-value="'mixed'"
          :toggle-indeterminate="false"
          dense
          size="sm"
          :disable="isBulkResolving"
          @update:model-value="(v: unknown) => toggleSelectAllSuggestions(!!v)"
        >
          <span v-if="bulkProgress" class="text-caption text-grey-7" data-testid="bulk-resolve-progress">
            Saving {{ bulkProgress.processed }} / {{ bulkProgress.total }}<template v-if="bulkProgress.notSaved">, {{ bulkProgress.notSaved }} not saved</template>…
          </span>
          <span v-else class="text-caption text-grey-7">
            {{ selectedSuggestionIds.size }} / {{ pendingAutoSpans.length }} selected
          </span>
        </q-checkbox>
        <q-space />
        <q-btn
          flat dense no-caps size="sm"
          icon="check"
          color="positive"
          label="Confirm"
          :loading="isBulkResolving"
          :disable="!selectedSuggestionIds.size || isBulkResolving"
          @click="bulkResolveSelected(SpanType.pos)"
        >
          <template #loading><span class="bulk-spinner" aria-label="Saving" /></template>
          <q-tooltip>Confirm all selected suggestions</q-tooltip>
        </q-btn>
        <q-btn
          flat dense no-caps size="sm"
          icon="close"
          color="negative"
          label="Reject"
          :loading="isBulkResolving"
          :disable="!selectedSuggestionIds.size || isBulkResolving"
          @click="bulkResolveSelected(SpanType.neg)"
        >
          <template #loading><span class="bulk-spinner" aria-label="Saving" /></template>
          <q-tooltip>Reject all selected suggestions</q-tooltip>
        </q-btn>
      </div>
      <q-linear-progress
        v-if="bulkProgress"
        :value="bulkProgress.total ? bulkProgress.processed / bulkProgress.total : 0"
        color="primary"
        size="3px"
        class="q-mb-xs"
      />
      <div class="auto-span-list" @scroll.passive="onSuggestionListScroll">
        <div
          v-for="entry in renderedAutoSpans"
          :key="entry.span.id || `${entry.span.chunkId}:${entry.span.start}:${entry.span.end}:${entry.span.tagId}`"
          class="auto-span-card"
          :class="{
            'is-busy': busyAutoSpanIds.has(entry.span.id || ''),
            'is-highlighted': aiAssist.highlightedAutoSpanId.value && entry.span.id === aiAssist.highlightedAutoSpanId.value,
            'is-selected': entry.span.id ? selectedSuggestionIds.has(entry.span.id) : false
          }"
          :ref="(el) => { if (entry.span.id) suggestionCardRefs[entry.span.id] = el as HTMLElement | null }"
          @click="onSuggestionClick(entry.span)"
        >
          <div class="auto-span-header">
            <q-checkbox
              :model-value="entry.span.id ? selectedSuggestionIds.has(entry.span.id) : false"
              @update:model-value="(v: unknown) => toggleSuggestionSelection(entry.span, !!v)"
              @click.stop
              dense
              size="xs"
              :disable="isBulkResolving || busyAutoSpanIds.has(entry.span.id || '')"
              class="q-mr-xs"
            />
            <q-icon
              :name="entry.tag?.pictogram || 'label'"
              :style="{ color: entry.tag?.color || '#64748b' }"
              size="16px"
              class="q-mr-xs"
            />
            <span class="auto-span-tag-name">{{ entry.tag?.name || 'Unknown tag' }}</span>
            <q-badge
              v-if="entry.span.confidence != null"
              outline
              :label="`${Math.round((entry.span.confidence as number) * 100)}%`"
              class="auto-span-confidence q-ml-xs"
            />
            <q-space />
            <q-btn
              flat dense round size="xs"
              icon="settings"
              :disable="!entry.tag || busyAutoSpanIds.has(entry.span.id || '')"
              @click.stop="onEditEntryTag(entry)"
            >
              <q-tooltip>Tag details</q-tooltip>
            </q-btn>
            <q-btn
              flat dense round size="xs"
              icon="check"
              color="positive"
              :disable="busyAutoSpanIds.has(entry.span.id || '')"
              @click.stop="approveAutoSpan(entry.span)"
            >
              <q-tooltip>Confirm</q-tooltip>
            </q-btn>
            <q-btn
              flat dense round size="xs"
              icon="close"
              color="negative"
              :disable="busyAutoSpanIds.has(entry.span.id || '')"
              @click.stop="rejectAutoSpan(entry.span)"
            >
              <q-tooltip>Reject</q-tooltip>
            </q-btn>
          </div>
          <div
            v-if="entry.span.reason"
            class="auto-span-reason"
          >
            {{ entry.span.reason }}
            <q-tooltip
              anchor="top middle"
              self="bottom middle"
              :delay="150"
              max-width="320px"
              class="auto-span-reason-tooltip"
            >
              {{ entry.span.reason }}
            </q-tooltip>
          </div>
        </div>
        <div
          v-if="renderedAutoSpans.length < pendingAutoSpans.length"
          class="text-caption text-grey-6 q-pa-xs text-center"
          data-testid="suggestions-more"
        >
          Showing {{ renderedAutoSpans.length }} of {{ pendingAutoSpans.length }}; scroll for more
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { SpanType, Tag, TagSpan, WriteOutcome } from 'src/generated/api'
import { apiErrorMessage, createContextGuard, isAbortError, useApi } from 'src/shared/api'
import { errorNotification } from 'src/shared/notification'
import { describeIncomplete } from 'src/shared/writeOutcome'
import { readStored, writeStored } from 'src/shared/browserStorage'
import { plural } from 'src/shared/plural'
import { useTagsStore } from './tagsStore'
import useAiAssistance, {
  largeRunWarning, resolveAutoSpanFailure, UNKNOWN_RUN_SIZE_WARNING, type AiAssistanceMode
} from './useAiAssistance'
import { useTagEditing } from './useTagEditing'
import AiTagNav from './AiTagNav.vue'
import { useTopicerModelStore } from './topicerModelStore'
import useTagSpans from './useTagSpans'
import { describeBulkResolve, runBulkResolve, type BulkResolveProgress, type BulkResolveSummary } from './bulkResolve'

// AI annotation suggestions for a document: runs over the selected tags, the pending
// suggestions with approve/reject, and two-way highlighting with the spans in the text
// (through useAiAssistance().highlightedAutoSpanId).
const props = defineProps<{
  collectionId: string
  documentId: string
}>()

const OPTIONS_COLLAPSED_KEY = 'semant.aiRunOptionsCollapsed'
const RUN_TAGS_KEY_PREFIX = 'semant.aiRunTags.'

const $q = useQuasar()
const { default: api } = useApi()
const { tags } = storeToRefs(useTagsStore())
const tagEditing = useTagEditing(() => props.collectionId)
const aiAssist = useAiAssistance()
const tagSpans = useTagSpans()
const aiMode = ref<AiAssistanceMode>('optimized')
const aiModeOptions = [
  { label: 'Optimized (vector pre-filtering)', value: 'optimized' },
  { label: 'Thorough (every chunk in collection)', value: 'thorough' }
]
const topicerModel = useTopicerModelStore()
const topicerConfigOptions = computed(() => topicerModel.options.map((name) => ({
  label: name === topicerModel.defaultConfig ? `${name} (default)` : name,
  value: name
})))
onMounted(() => { void topicerModel.load() })
// The tags chosen for runs, as remembered (#770); `selectedAiTagIds` keeps those of the
// collection's current tags, so a deleted tag, or tags not loaded yet, never count.
const chosenAiTagIds = ref<string[]>([])
const selectedAiTagIds = computed(() => {
  const known = new Set(tags.value.map((t) => t.id))
  return chosenAiTagIds.value.filter((id) => known.has(id))
})

// Folded run options (#770): remembered per browser when the user folds or opens them; a run
// folds them too, without changing what is remembered.
const optionsCollapsed = ref(readStored(OPTIONS_COLLAPSED_KEY) === 'true')
const optionsShown = computed(() => !optionsCollapsed.value)
function toggleOptions () {
  optionsCollapsed.value = !optionsCollapsed.value
  writeStored(OPTIONS_COLLAPSED_KEY, String(optionsCollapsed.value))
}
const optionsSummary = computed(() => {
  const mode = aiMode.value === 'thorough' ? 'Thorough' : 'Optimized'
  return `${plural(selectedAiTagIds.value.length, 'tag')} · ${mode}`
})

const isPreparingRun = ref(false)
const busyAutoSpanIds = ref<Set<string>>(new Set())
const isBulkDeleting = ref(false)
const lastDeletedCount = ref<number | null>(null)
// Tracks which of the two mutually-exclusive status messages should be
// visible — whichever event happened most recently wins.
const lastStatusKind = ref<'deleted' | 'processed' | null>(null)

watch(
  () => aiAssist.processedChunkCount.value,
  (n, prev) => {
    if (n !== prev) lastStatusKind.value = 'processed'
  }
)
watch(
  () => aiAssist.isRunning.value,
  (v) => {
    if (!v) return
    lastStatusKind.value = 'processed'
    optionsCollapsed.value = true
  }
)

function onSuggestionClick(span: TagSpan) {
  if (!span.id) return
  aiAssist.highlightedAutoSpanId.value =
    aiAssist.highlightedAutoSpanId.value === span.id ? null : span.id
}

// Track card DOM nodes so we can scroll to whichever one is highlighted from
// the document side (i.e. the user clicked an auto span in the text).
const suggestionCardRefs = ref<Record<string, HTMLElement | null>>({})

// Only the first cards are rendered and more as the list is scrolled (#464): with every
// card rendered, each change of a long list (a bulk approval batch) re-rendered over a
// thousand cards and blocked the page for hundreds of milliseconds.
const SUGGESTION_RENDER_STEP = 60
const suggestionRenderLimit = ref(SUGGESTION_RENDER_STEP)
const renderedAutoSpans = computed(() => pendingAutoSpans.value.slice(0, suggestionRenderLimit.value))
function onSuggestionListScroll(e: Event) {
  const el = e.target as HTMLElement
  if (suggestionRenderLimit.value >= pendingAutoSpans.value.length) return
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 300) suggestionRenderLimit.value += SUGGESTION_RENDER_STEP
}

watch(
  () => aiAssist.highlightedAutoSpanId.value,
  (id) => {
    if (!id) return
    // A suggestion highlighted from the text may be past the rendered cards.
    const index = pendingAutoSpans.value.findIndex((e) => e.span.id === id)
    if (index >= suggestionRenderLimit.value) suggestionRenderLimit.value = index + SUGGESTION_RENDER_STEP
    void nextTick(() => {
      const el = suggestionCardRefs.value[id]
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }
)

function toggleAiTag(tagId: string, on: boolean) {
  if (on) {
    if (!chosenAiTagIds.value.includes(tagId)) chosenAiTagIds.value = [...chosenAiTagIds.value, tagId]
  } else {
    chosenAiTagIds.value = chosenAiTagIds.value.filter((id) => id !== tagId)
  }
}
function selectAllAiTags() {
  chosenAiTagIds.value = tags.value.map((t) => t.id)
}
function clearAiTags() {
  chosenAiTagIds.value = []
}

function confirmDialog(title: string, message: string): Promise<boolean> {
  return new Promise((resolve) => {
    $q.dialog({
      title,
      message,
      persistent: true,
      cancel: { label: 'Cancel', flat: true, noCaps: true },
      ok: { label: 'Start tagging', color: 'primary', noCaps: true }
    }).onOk(() => resolve(true)).onCancel(() => resolve(false))
  })
}

// Asks before a run that would evaluate more than LARGE_RUN_CHUNKS chunks (a confirmation,
// not a cap). The size comes from the document's stats: its chunks in the collection and
// the backend's per-tag limit of optimized mode. Without them (a failed lookup, missing
// values) the size is unknown and the run also asks first.
async function confirmLargeRun(collectionId: string, documentId: string, tagCount: number,
  mode: AiAssistanceMode): Promise<boolean> {
  let chunks: number | null = null
  let perTag: number | null = null
  try {
    const stats = await api.getDocumentStatsApiUserCollectionsCollectionIdDocumentsDocumentIdStatsGet({
      collectionId, documentId
    })
    chunks = typeof stats.chunksInCollection === 'number' ? stats.chunksInCollection : null
    perTag = typeof stats.aiMaxChunksPerTag === 'number' && stats.aiMaxChunksPerTag > 0 ? stats.aiMaxChunksPerTag : null
  } catch (e) {
    console.warn('Could not read the document size before an AI run', e)
  }
  if (mode === 'thorough' ? chunks === null : perTag === null) {
    return await confirmDialog('AI run of unknown size', UNKNOWN_RUN_SIZE_WARNING)
  }
  const warning = largeRunWarning(mode, chunks ?? 0, tagCount, perTag ?? 0)
  return !warning || await confirmDialog('Large AI run', warning)
}

async function onRunAi() {
  if (!selectedAiTagIds.value.length || isPreparingRun.value) return
  // Not awaited: an outdated or failed list is read again for the next run.
  void topicerModel.load()
  const req = {
    collectionId: props.collectionId,
    documentId: props.documentId,
    tagIds: [...selectedAiTagIds.value],
    mode: aiMode.value,
    configName: topicerModel.chosenConfigName()
  }
  isPreparingRun.value = true
  let confirmed = false
  try {
    confirmed = await confirmLargeRun(req.collectionId, req.documentId, req.tagIds.length, req.mode)
  } finally {
    isPreparingRun.value = false
  }
  // Not for another document opened meanwhile.
  if (!confirmed || req.collectionId !== props.collectionId || req.documentId !== props.documentId) return
  await aiAssist.run(req)
}

interface AutoSpanEntry {
  span: TagSpan
  tag: Tag | undefined
}

const tagsById = computed(() => {
  const m: Record<string, Tag> = {}
  for (const t of tags.value) m[t.id] = t
  return m
})

// Canonical pending auto spans (ordered by confidence desc) come from the
// composable; we just join in the tag for display.
const pendingAutoSpans = computed<AutoSpanEntry[]>(() =>
  aiAssist.pendingAutoSpans.value.map((span) => ({
    span,
    tag: tagsById.value[span.tagId]
  }))
)

// Group pending suggestions by tag id so each tag in the AI tag list can show
// per-tag navigation arrows and a counter.
const autoSpansByTag = computed<Record<string, TagSpan[]>>(() => {
  const out: Record<string, TagSpan[]> = {}
  for (const entry of pendingAutoSpans.value) {
    const list = out[entry.span.tagId] ?? (out[entry.span.tagId] = [])
    list.push(entry.span)
  }
  return out
})

const tagsWithSuggestions = computed(() => tags.value.filter((t) => autoSpansByTag.value[t.id]?.length))

function autoSpanNavIndex(tagId: string): number | null {
  const list = autoSpansByTag.value[tagId]
  if (!list?.length) return null
  const highlightedId = aiAssist.highlightedAutoSpanId.value
  if (!highlightedId) return null
  const idx = list.findIndex((s) => s.id === highlightedId)
  return idx === -1 ? null : idx
}

function navigateAutoSpan(tagId: string, direction: 'prev' | 'next') {
  const list = autoSpansByTag.value[tagId]
  if (!list?.length) return
  const current = autoSpanNavIndex(tagId)
  let nextIdx: number
  if (current == null) {
    nextIdx = direction === 'next' ? 0 : list.length - 1
  } else {
    nextIdx = direction === 'next' ? (current + 1) % list.length : (current - 1 + list.length) % list.length
  }
  const target = list[nextIdx]
  if (target.id) aiAssist.highlightedAutoSpanId.value = target.id
}

// Approve/reject requests of this panel's document: entered when the panel moves to another
// document or collection, or closes, so a failure that arrives later is not reported here.
const resolveRequests = createContextGuard()
onBeforeUnmount(() => resolveRequests.enter())

async function resolveSuggestion(span: TagSpan, type: SpanType) {
  if (!span.id) return
  busyAutoSpanIds.value.add(span.id)
  const isCurrent = resolveRequests.capture()
  try {
    await aiAssist.resolveAutoSpan(span, type)
  } catch (e: unknown) {
    if (isCurrent() && !isAbortError(e)) errorNotification(await apiErrorMessage(e, resolveAutoSpanFailure(type)))
  } finally {
    busyAutoSpanIds.value.delete(span.id)
  }
}

const approveAutoSpan = (span: TagSpan) => resolveSuggestion(span, SpanType.pos)
const rejectAutoSpan = (span: TagSpan) => resolveSuggestion(span, SpanType.neg)

// ── Bulk approve / reject of selected suggestions ──
const selectedSuggestionIds = ref<Set<string>>(new Set())
const isBulkResolving = ref(false)
const bulkProgress = ref<BulkResolveProgress | null>(null)

const allSuggestionsSelected = computed(() => {
  const ids = pendingAutoSpans.value
    .map((e) => e.span.id)
    .filter((id): id is string => !!id)
  if (!ids.length) return false
  return ids.every((id) => selectedSuggestionIds.value.has(id))
})

function toggleSuggestionSelection(span: TagSpan, on: boolean) {
  if (!span.id) return
  const next = new Set(selectedSuggestionIds.value)
  if (on) next.add(span.id)
  else next.delete(span.id)
  selectedSuggestionIds.value = next
}

function toggleSelectAllSuggestions(on: boolean) {
  if (on) {
    const ids = pendingAutoSpans.value
      .map((e) => e.span.id)
      .filter((id): id is string => !!id)
    selectedSuggestionIds.value = new Set(ids)
  } else {
    selectedSuggestionIds.value = new Set()
  }
}

// Drop ids from the selection once their spans disappear from the pending list
// (i.e. they got approved / rejected / deleted somewhere else).
watch(pendingAutoSpans, (entries) => {
  if (!selectedSuggestionIds.value.size) return
  const present = new Set(
    entries.map((e) => e.span.id).filter((id): id is string => !!id)
  )
  const next = new Set<string>()
  for (const id of selectedSuggestionIds.value) {
    if (present.has(id)) next.add(id)
  }
  if (next.size !== selectedSuggestionIds.value.size) {
    selectedSuggestionIds.value = next
  }
})

async function bulkResolveSelected(type: SpanType) {
  if (!selectedSuggestionIds.value.size || isBulkResolving.value) return
  // Snapshot the spans we want to act on before any mutations start removing them from
  // the pending list.
  const idSet = selectedSuggestionIds.value
  const targets = pendingAutoSpans.value.flatMap((e) => e.span.id && idSet.has(e.span.id) ? [e.span.id] : [])
  if (!targets.length) return

  // Pre-compute which suggestion should be highlighted once these resolve.
  const targetIds = new Set(targets)
  const nextHighlight =
    pendingAutoSpans.value.find((e) => e.span.id && !targetIds.has(e.span.id))?.span.id ?? null

  const isCurrent = resolveRequests.capture()
  isBulkResolving.value = true
  bulkProgress.value = { total: targets.length, processed: 0, saved: 0, notSaved: 0 }
  for (const id of targets) busyAutoSpanIds.value.add(id)
  let summary: BulkResolveSummary | null = null
  try {
    summary = await runBulkResolve(
      targets,
      async (ids) => {
        if (!isCurrent()) return null
        try {
          return await tagSpans.applyBulkUpdate(ids, { type })
        } finally {
          for (const id of ids) busyAutoSpanIds.value.delete(id)
        }
      },
      (progress) => { if (isCurrent()) bulkProgress.value = progress }
    )
  } finally {
    for (const id of targets) busyAutoSpanIds.value.delete(id)
    isBulkResolving.value = false
    bulkProgress.value = null
  }
  if (!isCurrent() || summary.abandoned) return
  // Keep the suggestions that were not saved selected, so they can be retried.
  const unresolved = new Set(summary.unresolved)
  selectedSuggestionIds.value = new Set([...selectedSuggestionIds.value].filter((id) => unresolved.has(id)))
  if (summary.saved) aiAssist.highlightedAutoSpanId.value = nextHighlight
  if (summary.error) console.error('Bulk resolve failed', summary.error)
  const message = describeBulkResolve(summary, type === SpanType.pos ? 'Confirmed' : 'Rejected')
  if (message) {
    $q.notify({ type: summary.saved === summary.total ? 'warning' : 'negative', message, timeout: 10000 })
  } else {
    const n = summary.saved
    $q.notify({ type: 'positive', message: `${type === SpanType.pos ? 'Confirmed' : 'Rejected'} ${n} ${n === 1 ? 'suggestion' : 'suggestions'}.` })
  }
}

async function onBulkDelete() {
  if (!selectedAiTagIds.value.length) return
  isBulkDeleting.value = true
  lastDeletedCount.value = null
  try {
    const result = await api.deleteAutoSpansApiAiAutoSpansDeletePost({
      deleteAutoSpansRequest: {
        collectionId: props.collectionId,
        documentId: props.documentId,
        tagIds: [...selectedAiTagIds.value]
      }
    })
    lastDeletedCount.value = result.deleted
    lastStatusKind.value = 'deleted'
    // Drop exactly the spans the backend deleted; failed ones stay visible.
    const deletedIds = new Set(result.succeeded ?? [])
    tagSpans.removeSpansLocally((s) => !!s.id && deletedIds.has(s.id))
    if (result.outcome !== WriteOutcome.complete) {
      $q.notify({ type: 'negative', message: describeIncomplete(result, 'Removing suggestions') })
    }
  } catch (e) {
    console.error('Bulk delete of auto spans failed', e)
    $q.notify({ type: 'negative', message: 'Failed to remove suggestions.' })
  } finally {
    isBulkDeleting.value = false
  }
}

function onEditEntryTag(entry: AutoSpanEntry) {
  if (!entry.tag) return
  tagEditing.editTag(entry.tag)
}

// The panel stays alive while another sidebar panel is shown and keeps its state. The
// run state itself is reset by the document view; the panel drops its own selection and
// status when the document or collection changes, and the chosen tags (a collection's
// tags) when the collection changes.
watch(
  () => [props.collectionId, props.documentId],
  () => {
    resolveRequests.enter()
    selectedSuggestionIds.value = new Set()
    suggestionRenderLimit.value = SUGGESTION_RENDER_STEP
    lastDeletedCount.value = null
    lastStatusKind.value = null
  }
)
// The tags chosen for runs are remembered per collection and browser (#770), so folded run
// options are ready to run after a reload.
const runTagsKey = (collectionId: string) => `${RUN_TAGS_KEY_PREFIX}${collectionId}`
function readRunTags (collectionId: string): string[] {
  try {
    const stored: unknown = JSON.parse(readStored(runTagsKey(collectionId)) ?? '[]')
    return Array.isArray(stored) ? stored.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}
watch(
  () => props.collectionId,
  (collectionId) => {
    chosenAiTagIds.value = readRunTags(collectionId)
  },
  { immediate: true }
)
watch(chosenAiTagIds, (ids) => {
  writeStored(runTagsKey(props.collectionId), JSON.stringify(ids))
})
</script>

<style scoped>
/* Only the suggestions list scrolls; the panel fills the height it is given. */
.ai-assist-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.ai-assist-panel .ai-tag-list {
  flex: 0 1 auto;
  min-height: 0;
}

.ai-assist-panel .auto-span-list {
  flex: 1 1 0;
  min-height: 0;
  max-height: none;
}

.ai-assist-panel.has-pending .ai-tag-list {
  flex: 0 1 auto;
}

.ai-assist-panel.has-pending .auto-span-list {
  flex: 4 1 0;
}

.ai-run-options {
  display: contents;
}

.ai-options-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.ai-options-summary {
  font-size: 0.78rem;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.ai-section-label {
  display: flex;
  align-items: center;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(71, 85, 105, 0.85);
  margin-bottom: 6px;
}

.ai-tag-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 15%;
  overflow-y: auto;
  padding: 4px 6px;
  background: rgba(15, 23, 42, 0.03);
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 6px;
}

.ai-tag-row {
  display: inline-flex;
  align-items: center;
  font-size: 0.9rem;
}

.ai-tag-list-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ai-tag-checkbox {
  flex: 1 1 auto;
  min-width: 0;
}

.ai-tag-name {
  color: rgba(15, 23, 42, 0.9);
}

.ai-actions {
  display: flex;
  gap: 8px;
}

.ai-progress {
  display: flex;
  align-items: center;
  color: #475569;
}

.ai-notice {
  display: flex;
  align-items: flex-start;
  color: #1e3a8a;
  font-size: 0.85rem;
  background: rgba(37, 99, 235, 0.08);
  border-radius: 6px;
  padding: 6px 8px;
}

.ai-error {
  color: #b91c1c;
  font-size: 0.85rem;
  background: rgba(185, 28, 28, 0.08);
  border-radius: 6px;
  padding: 6px 8px;
}

.auto-span-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}

/* The bulk buttons' spinner animates only its transform, which the browser runs off the
   main thread: Quasar's default spinner also animates its stroke on the main thread and
   so stuttered whenever a bulk batch's result was rendered (#464). */
.bulk-spinner {
  display: inline-block;
  width: 1em;
  height: 1em;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  will-change: transform;
  animation: bulk-spin 0.75s linear infinite;
}

@keyframes bulk-spin {
  to { transform: rotate(360deg); }
}

.auto-span-bulk-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 4px 6px 4px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  margin-bottom: 6px;
}

.auto-span-card.is-selected {
  border-style: solid;
  border-color: rgba(37, 99, 235, 0.5);
  background: rgba(37, 99, 235, 0.06);
}

.auto-span-card.is-selected.is-highlighted {
  border-color: rgba(37, 99, 235, 0.7);
  background: rgba(37, 99, 235, 0.12);
}

.auto-span-card {
  border: 1px dashed rgba(15, 23, 42, 0.18);
  background: rgba(255, 255, 255, 0.6);
  border-radius: 6px;
  padding: 6px 8px;
  transition: opacity 0.15s, box-shadow 0.15s, border-color 0.15s, background 0.15s;
  cursor: pointer;
}

.auto-span-card:hover {
  border-color: rgba(15, 23, 42, 0.32);
  background: rgba(255, 255, 255, 0.85);
}

.auto-span-card.is-highlighted {
  border-style: solid;
  border-color: rgba(15, 23, 42, 0.4);
  background: rgba(15, 23, 42, 0.06);
}

.auto-span-card.is-busy {
  opacity: 0.5;
  pointer-events: none;
}

.auto-span-header {
  display: flex;
  align-items: center;
}

.auto-span-tag-name {
  font-size: 0.9rem;
  font-weight: 500;
  color: rgba(15, 23, 42, 0.9);
}

.auto-span-reason {
  margin-top: 4px;
  padding-left: 22px;
  font-size: 0.82rem;
  font-style: italic;
  color: rgba(71, 85, 105, 0.85);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.auto-span-confidence {
  font-size: 0.7rem;
  font-weight: 600;
  color: #64748b;
  border-color: #94a3b8;
}

.auto-span-reason-tooltip {
  font-size: 0.85rem;
  line-height: 1.4;
  white-space: pre-wrap;
  background: rgba(15, 23, 42, 0.92);
}
</style>
