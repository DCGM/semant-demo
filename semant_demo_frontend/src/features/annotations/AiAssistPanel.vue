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
        data-testid="ai-options-toggle"
        @click="toggleOptions"
      >
        <q-tooltip>{{ optionsShown ? 'Hide run options' : 'Show run options' }}</q-tooltip>
      </q-btn>
    </div>

    <!-- Folded: only the per-tag suggestion navigation of the tags that have suggestions. -->
    <div v-if="!optionsShown && tagsWithSuggestions.length" class="ai-tag-list q-mb-sm" data-testid="ai-folded-nav">
      <div v-for="tag in tagsWithSuggestions" :key="tag.id" class="ai-tag-list-row">
        <AiTagLabel :tag="tag" class="ai-tag-checkbox" />
        <AiTagNav
          :count="autoSpansByTag[tag.id].length"
          :index="autoSpanNavIndex(tag.id)"
          @prev="navigateAutoSpan(tag.id, 'prev')"
          @next="navigateAutoSpan(tag.id, 'next')"
        />
      </div>
    </div>

    <!-- display: contents keeps the tag list a flex item of the panel, so its height cap holds.
         The toggle has no aria-controls: such a wrapper may be missing from the accessibility tree. -->
    <div v-show="optionsShown" class="ai-run-options" data-testid="ai-run-options">
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
              <AiTagLabel :tag="tag" />
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
      <q-space />
      <q-btn
        flat dense round size="sm"
        :icon="pendingSuggestionsOpen ? 'expand_less' : 'expand_more'"
        :aria-label="pendingSuggestionsOpen ? 'Hide pending suggestions' : 'Show pending suggestions'"
        :aria-expanded="pendingSuggestionsOpen ? 'true' : 'false'"
        data-testid="pending-suggestions-toggle"
        @click="pendingSuggestionsOpen = !pendingSuggestionsOpen"
      >
        <q-tooltip>{{ pendingSuggestionsOpen ? 'Hide pending suggestions' : 'Show pending suggestions' }}</q-tooltip>
      </q-btn>
    </div>
    <div v-if="pendingSuggestionsOpen && !pendingAutoSpans.length" class="text-body2 text-grey-6">
      No unresolved AI suggestions in the displayed chunks.
    </div>
    <template v-else-if="pendingSuggestionsOpen">
      <!-- Sorting is always available; only optional filters are folded away. -->
      <div class="proposal-toolbar" role="group" aria-label="Sort and filter suggestions">
        <q-select
          v-model="proposalSort"
          :options="proposalSortOptions"
          emit-value map-options dense outlined options-dense
          label="Sort by" class="proposal-sort" data-testid="proposal-sort"
        />
        <q-btn
          flat dense round size="sm"
          :icon="proposalDescending ? 'south' : 'north'"
          :aria-label="proposalDescending ? 'Sort descending' : 'Sort ascending'"
          @click="proposalDescending = !proposalDescending"
        >
          <q-tooltip>Reverse sort direction</q-tooltip>
        </q-btn>
        <q-btn
          flat dense no-caps size="sm" color="primary" icon="filter_list"
          :label="activeProposalFilterCount ? `Filters (${activeProposalFilterCount})` : 'Filters'"
          :aria-expanded="proposalFiltersOpen ? 'true' : 'false'"
          data-testid="proposal-filters-toggle"
          @click="proposalFiltersOpen = !proposalFiltersOpen"
        >
          <q-tooltip>{{ proposalFiltersOpen ? 'Hide filters' : 'Show filters' }}</q-tooltip>
        </q-btn>
      </div>
      <div v-if="!proposalFiltersOpen && hasActiveProposalFilters" class="proposal-active-filters"
        role="group" aria-label="Active suggestion filters" data-testid="proposal-active-filters">
        <q-chip v-if="proposalTagId !== null" dense removable color="grey-2" text-color="grey-9" class="proposal-filter-chip"
          data-testid="proposal-filter-tag-chip" remove-aria-label="Remove tag filter"
          @remove="proposalTagId = null">
          <span class="proposal-chip-text">Tag: {{ selectedProposalTag?.name || 'Unknown tag' }}</span>
        </q-chip>
        <q-chip v-if="minimumConfidencePercent !== null" dense removable color="grey-2" text-color="grey-9" class="proposal-filter-chip"
          data-testid="proposal-filter-confidence-chip" remove-aria-label="Remove confidence filter"
          @remove="minimumConfidencePercent = null">
          ≥{{ minimumConfidencePercent }}%
        </q-chip>
        <q-chip v-if="proposalReasonQuery.trim()" dense removable color="grey-2" text-color="grey-9" class="proposal-filter-chip"
          data-testid="proposal-filter-reason-chip" remove-aria-label="Remove explanation filter"
          @remove="proposalReasonQuery = ''">
          <span class="proposal-chip-text">Explanation: {{ proposalReasonQuery.trim() }}</span>
        </q-chip>
      </div>
      <!-- Filters only change the presentation of proposals, not the AI-run tag choices. -->
      <div v-if="proposalFiltersOpen" class="proposal-controls">
        <div class="proposal-controls-header">
          <span class="text-caption text-grey-7" data-testid="proposal-filter-count">
            {{ activeProposalFilterCount }} active {{ activeProposalFilterCount === 1 ? 'filter' : 'filters' }}
          </span>
          <q-btn flat dense no-caps color="primary" label="Reset filters" size="sm" icon="refresh"
            :disable="!hasActiveProposalFilters" data-testid="proposal-reset-filters"
            @click="resetProposalFilters" />
        </div>
        <div class="proposal-control-row">
          <q-select
            v-model="proposalTagId" :options="proposalTagOptions"
            emit-value map-options dense outlined options-dense
            label="Filter by tag" class="proposal-control" data-testid="proposal-tag-filter"
          >
            <template #prepend>
              <q-icon v-if="selectedProposalTag"
                :name="selectedProposalTag.pictogram || 'label'"
                :style="{ color: selectedProposalTag.color }" size="18px" />
            </template>
            <template #option="{ opt, itemProps }">
              <q-item v-bind="itemProps">
                <q-item-section v-if="opt.icon" avatar>
                  <q-icon :name="opt.icon" :style="{ color: opt.color }" size="18px" />
                </q-item-section>
                <q-item-section><q-item-label>{{ opt.label }}</q-item-label></q-item-section>
              </q-item>
            </template>
          </q-select>
          <q-input
            :model-value="minimumConfidencePercent"
            @update:model-value="setMinimumConfidence"
            type="number" min="0" max="100" step="1"
            dense outlined clearable label="Min. confidence(%)"
            class="proposal-control" data-testid="proposal-confidence-filter"
          />
        </div>
        <div class="proposal-control-row">
          <q-input
            :model-value="proposalReasonQuery" @update:model-value="setProposalReason"
            dense outlined clearable
            label="Explanation contains" class="proposal-control proposal-control--full"
            data-testid="proposal-reason-filter"
          />
        </div>
      </div>
      <div v-if="documentOrderUnavailable"
        class="text-caption text-warning" role="status">
        Document order is unavailable until the reader has loaded the canonical chunk positions.
      </div>
      <div v-if="revealedSuggestion" class="text-caption text-grey-7" role="status">
        Filters were reset to reveal the suggestion selected in the text.
      </div>
      <div v-if="!visibleSuggestions.length && !documentOrderUnavailable" class="text-body2 text-grey-6 q-my-xs"
        data-testid="no-matching-proposals">
        No matching suggestions. Reset the filters to see all pending proposals.
      </div>
      <div class="auto-span-bulk-bar">
        <div class="auto-span-bulk-status">
          <q-checkbox
            :model-value="visibleSelectionState"
            :indeterminate-value="'mixed'"
            :toggle-indeterminate="false"
            dense
            size="sm"
            :disable="isBulkResolving || !visibleSuggestions.length"
            @update:model-value="(v: unknown) => toggleSelectAllSuggestions(!!v)"
          >
            <span v-if="bulkProgress" class="text-caption text-grey-7" data-testid="bulk-resolve-progress">
              {{ bulkAction === 'delete' ? 'Deleting' : 'Saving' }} {{ bulkProgress.processed }} / {{ bulkProgress.total }}<template v-if="bulkProgress.notSaved">, {{ bulkProgress.notSaved }} {{ bulkAction === 'delete' ? 'not deleted' : 'not saved' }}</template>…
            </span>
            <span v-else class="text-caption text-grey-7" data-testid="proposal-selection-count">
              {{ selectedVisibleCount }} / {{ visibleSuggestions.length }} visible selected
              <template v-if="hiddenSelectedCount">({{ hiddenSelectedCount }} hidden)</template>
            </span>
          </q-checkbox>
          <span class="text-caption text-grey-7" data-testid="proposal-match-count">
            {{ visibleSuggestions.length }} of {{ pendingAutoSpans.length }} matching
          </span>
        </div>
        <q-btn
          stack flat dense no-caps size="sm"
          icon="playlist_remove"
          label="Clear"
          color="grey-8"
          aria-label="Clear selection"
          :disable="!selectedSuggestionIds.size || isBulkResolving"
          @click="clearSuggestionSelection"
        />
        <q-space />
        <q-btn
          stack flat dense no-caps size="sm"
          icon="check"
          color="positive"
          label="Confirm"
          aria-label="Confirm"
          :loading="isBulkResolving"
          :disable="!selectedSuggestionIds.size || isBulkResolving"
          @click="bulkResolveSelected(SpanType.pos)"
        >
          <template #loading><span class="bulk-spinner" aria-label="Saving" /></template>
          <q-tooltip>Confirm selected suggestions (keeps an approved annotation)</q-tooltip>
        </q-btn>
        <q-btn
          stack flat dense no-caps size="sm"
          icon="close"
          color="negative"
          label="Reject"
          aria-label="Reject"
          :loading="isBulkResolving"
          :disable="!selectedSuggestionIds.size || isBulkResolving"
          @click="bulkResolveSelected(SpanType.neg)"
        >
          <template #loading><span class="bulk-spinner" aria-label="Saving" /></template>
          <q-tooltip>Reject selected suggestions (keeps rejected annotations)</q-tooltip>
        </q-btn>
        <q-btn
          stack flat dense no-caps size="sm"
          icon="delete"
          color="grey-8"
          label="Delete"
          aria-label="Delete"
          data-testid="bulk-delete-selected"
          :loading="isBulkResolving"
          :disable="!selectedSuggestionIds.size || isBulkResolving"
          @click="bulkResolveSelected('delete')"
        >
          <template #loading><span class="bulk-spinner" aria-label="Deleting" /></template>
          <q-tooltip>Delete selected suggestions (no rejection recorded)</q-tooltip>
        </q-btn>
      </div>
      <q-linear-progress
        v-if="bulkProgress"
        :value="bulkProgress.total ? bulkProgress.processed / bulkProgress.total : 0"
        color="primary"
        size="3px"
        class="q-mb-xs"
      />
      <q-virtual-scroll
        v-if="visibleSuggestions.length && !documentOrderUnavailable"
        ref="suggestionVirtualScroll"
        class="auto-span-list"
        :items="visibleSuggestions"
        :virtual-scroll-item-size="76"
        :virtual-scroll-slice-size="20"
        v-slot="{ item: entry }"
        data-testid="ai-suggestion-list"
      >
        <div
          :key="entry.span.id || `${entry.span.chunkId}:${entry.span.start}:${entry.span.end}:${entry.span.tagId}`"
          class="auto-span-card q-mb-xs"
          :class="{
            'is-busy': busyAutoSpanIds.has(entry.span.id || ''),
            'is-highlighted': aiAssist.highlightedAutoSpanId.value && entry.span.id === aiAssist.highlightedAutoSpanId.value,
            'is-selected': entry.span.id ? selectedSuggestionIds.has(entry.span.id) : false
          }"
          @click="onSuggestionClick(entry.span)"
          :data-suggestion-id="entry.span.id"
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
            <button type="button" class="auto-span-highlight" data-testid="proposal-highlight"
              :aria-label="`Highlight suggestion for ${entry.tag?.name || 'unknown tag'}`"
              :aria-pressed="entry.span.id === aiAssist.highlightedAutoSpanId.value"
              @click.stop="onSuggestionClick(entry.span)">
              <span class="auto-span-tag-name">{{ entry.tag?.name || 'Unknown tag' }}</span>
            </button>
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
      </q-virtual-scroll>
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
import { useChunksStore } from 'src/features/documents/chunksStore'
import {
  filterAndSortSuggestions, toggleVisibleSuggestions, type ProposalSort
} from './aiSuggestionPresentation'
import { readStored, writeStored } from 'src/shared/browserStorage'
import { plural } from 'src/shared/plural'
import { useTagsStore } from './tagsStore'
import useAiAssistance, {
  largeRunWarning, resolveAutoSpanFailure, UNKNOWN_RUN_SIZE_WARNING, type AiAssistanceMode
} from './useAiAssistance'
import { useTagEditing } from './useTagEditing'
import AiTagNav from './AiTagNav.vue'
import AiTagLabel from './AiTagLabel.vue'
import { readRunTags, writeRunTags } from './aiRunTags'
import { useUserStore } from 'src/features/auth/userStore'
import { useTopicerModelStore } from './topicerModelStore'
import useTagSpans from './useTagSpans'
import { confirmBulkDeletion, describeBulkResolve, runBulkResolve, type BulkResolveProgress, type BulkResolveSummary } from './bulkResolve'

// AI annotation suggestions for a document: runs over the selected tags, the pending
// suggestions with approve/reject, and two-way highlighting with the spans in the text
// (through useAiAssistance().highlightedAutoSpanId).
const props = defineProps<{
  collectionId: string
  documentId: string
}>()

const OPTIONS_COLLAPSED_KEY = 'semant.aiRunOptionsCollapsed'

const $q = useQuasar()
const { default: api } = useApi()
const { tags } = storeToRefs(useTagsStore())
const chunksStore = useChunksStore()
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

// QVirtualScroll mounts only the cards in its viewport. Its scrollTo(index)
// can reach a suggestion which has never been mounted as a DOM element.
const suggestionVirtualScroll = ref<{ $el: HTMLElement; scrollTo:(index: number, edge?: 'start' | 'center' | 'end') => void } | null>(null)
const revealedSuggestion = ref(false)
let suggestionFocusRequest = 0

// The list and the right sidebar are independent scrollers. Bring the selected
// card towards the top third of the sidebar even if it was just barely visible
// at the bottom; otherwise repeated text clicks can appear to do nothing.
function scrollCardIntoSidebar(card: HTMLElement) {
  const scroller = card.closest<HTMLElement>('.sidebar-panel')?.parentElement
  if (!scroller) return
  const cardRect = card.getBoundingClientRect()
  const sidebarRect = scroller.getBoundingClientRect()
  const preferredTop = sidebarRect.top + Math.min(140, Math.max(8, (sidebarRect.height - cardRect.height) / 3))
  scroller.scrollTop += cardRect.top - preferredTop
}

function cardVisibleInBothScrollers(card: HTMLElement): boolean {
  const scroller = card.closest<HTMLElement>('.sidebar-panel')?.parentElement
  const list = card.closest<HTMLElement>('.auto-span-list')
  if (!scroller || !list || !card.isConnected) return false
  const cardRect = card.getBoundingClientRect()
  const outerRect = scroller.getBoundingClientRect()
  const listRect = list.getBoundingClientRect()
  return cardRect.top >= Math.max(outerRect.top, listRect.top, 0) - 1 &&
    cardRect.bottom <= Math.min(outerRect.bottom, listRect.bottom, window.innerHeight) + 1
}

async function focusSuggestionById(id: string) {
  const request = ++suggestionFocusRequest
  const collectionId = props.collectionId
  const documentId = props.documentId
  let index = visibleSuggestions.value.findIndex((e) => e.span.id === id)
  if (index === -1 && pendingAutoSpans.value.some((e) => e.span.id === id)) {
    // A text/gutter click always wins over presentation filters; do not silently
    // ignore the annotation or mutate the user's selected proposal IDs.
    resetProposalFilters()
    revealedSuggestion.value = true
    await nextTick()
    if (request !== suggestionFocusRequest || collectionId !== props.collectionId ||
        documentId !== props.documentId || aiAssist.highlightedAutoSpanId.value !== id) return
    index = visibleSuggestions.value.findIndex((e) => e.span.id === id)
  }
  if (index < 0) return // already resolved or removed in a stream
  // Text/gutter navigation can reveal a proposal even after the list was folded.
  pendingSuggestionsOpen.value = true
  await nextTick()
  if (request !== suggestionFocusRequest ||
    collectionId !== props.collectionId || documentId !== props.documentId ||
    visibleSuggestions.value[index]?.span.id !== id) return
  suggestionVirtualScroll.value?.scrollTo(index, 'center')
  // With variable-height cards QVirtualScroll may refine the destination over
  // several frames. Focus is not enough: verify both scroll viewports too.
  await nextTick()
  for (let frame = 0; frame < 24; frame++) {
    if (request !== suggestionFocusRequest || collectionId !== props.collectionId ||
        documentId !== props.documentId || aiAssist.highlightedAutoSpanId.value !== id ||
        visibleSuggestions.value[index]?.span.id !== id) return
    const viewport = suggestionVirtualScroll.value?.$el
    const card = Array.from(viewport?.querySelectorAll<HTMLElement>('.auto-span-card') ?? [])
      .find((el) => el.dataset.suggestionId === id)
    if (!card || !viewport) {
      // Retry the index jump when the destination is not mounted yet.
      if (frame > 0 && frame % 5 === 0) suggestionVirtualScroll.value?.scrollTo(index, 'center')
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      continue
    }
    const cardRect = card.getBoundingClientRect()
    const listRect = viewport.getBoundingClientRect()
    // Correct the approximate virtual offset using the real row height.
    if (cardRect.top < listRect.top) viewport.scrollTop += cardRect.top - listRect.top - 4
    else if (cardRect.bottom > listRect.bottom) viewport.scrollTop += cardRect.bottom - listRect.bottom + 4
    scrollCardIntoSidebar(card)
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    if (!cardVisibleInBothScrollers(card)) continue
    const action = card.querySelector<HTMLButtonElement>('.auto-span-highlight')
    action?.focus({ preventScroll: true })
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    if (action && document.activeElement === action && cardVisibleInBothScrollers(card)) return
  }
}

// Watch both the highlighted ID and explicit navigation requests. Vue batches
// updates in the same click, but re-clicking the same ID still reruns scrolling.
watch(
  [() => aiAssist.highlightedAutoSpanId.value, () => aiAssist.highlightedAutoSpanNavigationRequest.value],
  ([id]) => { if (id) void focusSuggestionById(id) }
)
watch(() => aiAssist.aiPanelActive.value, (active) => {
  const id = aiAssist.highlightedAutoSpanId.value
  if (active && id) void focusSuggestionById(id)
})

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

// The shared composable keeps its original confidence order for text/gutter
// consumers. Only this panel applies the independent presentation order.
const pendingAutoSpans = computed<AutoSpanEntry[]>(() =>
  aiAssist.pendingAutoSpans.value.map((span) => ({
    span,
    tag: tagsById.value[span.tagId]
  }))
)

// UI-only sections; collapsing must not change filters or the selected IDs.
const pendingSuggestionsOpen = ref(true)
const proposalFiltersOpen = ref(false)

const proposalSort = ref<ProposalSort>('confidence')
const proposalDescending = ref(true)
// Natural defaults per mode: confidence/newest first, document/alphabetical first.
watch(proposalSort, (mode) => {
  proposalDescending.value = mode === 'confidence' || mode === 'created'
})
const proposalTagId = ref<string | null>(null)
const proposalReasonQuery = ref('')
const minimumConfidencePercent = ref<number | null>(null)
watch([proposalTagId, proposalReasonQuery, minimumConfidencePercent], () => {
  revealedSuggestion.value = false
}, { flush: 'sync' })

const chunkOrder = computed(() => new Map(chunksStore.chunks.map((c) => [c.id, c.order])))
const documentOrderAvailable = computed(() => !chunksStore.loading && !chunksStore.error &&
  chunksStore.chunks.length > 0 &&
  pendingAutoSpans.value.every((e) => chunkOrder.value.has(e.span.chunkId)))
const documentOrderUnavailable = computed(() =>
  proposalSort.value === 'document' && !documentOrderAvailable.value)
const proposalSortOptions = computed(() => [
  { label: 'Confidence', value: 'confidence' },
  { label: 'Document order', value: 'document', disable: !documentOrderAvailable.value },
  { label: 'Explanation (alphabetical)', value: 'explanation' },
  { label: 'Creation time', value: 'created' }
])
const selectedProposalTag = computed(() =>
  tags.value.find((tag) => tag.id === proposalTagId.value))
const proposalTagOptions = computed(() => [
  { label: 'All tags', value: null, icon: null, color: null },
  ...tags.value.map((tag) => ({
    label: tag.name, value: tag.id, icon: tag.pictogram || 'label', color: tag.color
  }))
])
const activeProposalFilterCount = computed(() => Number(proposalTagId.value !== null) +
  Number(minimumConfidencePercent.value !== null) + Number(!!proposalReasonQuery.value.trim()))
const hasActiveProposalFilters = computed(() => activeProposalFilterCount.value > 0)

function setMinimumConfidence(value: string | number | null) {
  if (value === '' || value === null) {
    minimumConfidencePercent.value = null
    return
  }
  const numeric = Number(value)
  if (Number.isFinite(numeric)) minimumConfidencePercent.value = Math.max(0, Math.min(100, numeric))
}

function setProposalReason(value: string | number | null) {
  proposalReasonQuery.value = String(value ?? '')
}

function resetProposalFilters() {
  revealedSuggestion.value = false
  proposalTagId.value = null
  proposalReasonQuery.value = ''
  minimumConfidencePercent.value = null
}

// Computed only from pending annotations, metadata and controls, not checkbox
// selection or highlighted ID, so card actions don't re-run the whole sort.
const visibleSuggestions = computed<AutoSpanEntry[]>(() => {
  if (documentOrderUnavailable.value) return []
  return filterAndSortSuggestions(pendingAutoSpans.value,
    {
      tagId: proposalTagId.value,
      reason: proposalReasonQuery.value,
      minimumConfidence: minimumConfidencePercent.value === null
        ? null : minimumConfidencePercent.value / 100
    },
    proposalSort.value, proposalDescending.value, chunkOrder.value)
})

// The AI-run tag selection and the per-tag navigation are independent. Navigation
// follows the filtered, presented suggestions; the gutter still uses its own order.
const autoSpansByTag = computed<Record<string, TagSpan[]>>(() => {
  const out: Record<string, TagSpan[]> = {}
  for (const entry of visibleSuggestions.value) {
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
    if (isCurrent()) busyAutoSpanIds.value.delete(span.id)
  }
}

const approveAutoSpan = (span: TagSpan) => resolveSuggestion(span, SpanType.pos)
const rejectAutoSpan = (span: TagSpan) => resolveSuggestion(span, SpanType.neg)

// ── Bulk confirm / reject / delete of selected suggestions ──
const selectedSuggestionIds = ref<Set<string>>(new Set())
const isBulkResolving = ref(false)
const bulkAction = ref<'confirm' | 'reject' | 'delete' | null>(null)
const bulkProgress = ref<BulkResolveProgress | null>(null)
const selectedVisibleCount = computed(() => visibleSuggestions.value.reduce((n, e) =>
  n + (e.span.id && selectedSuggestionIds.value.has(e.span.id) ? 1 : 0), 0))
const hiddenSelectedCount = computed(() => selectedSuggestionIds.value.size - selectedVisibleCount.value)
const visibleSelectionState = computed(() => {
  if (!selectedVisibleCount.value) return false
  if (selectedVisibleCount.value === visibleSuggestions.value.filter((e) => !!e.span.id).length) return true
  return 'mixed'
})

function toggleSuggestionSelection(span: TagSpan, on: boolean) {
  if (!span.id) return
  const next = new Set(selectedSuggestionIds.value)
  if (on) next.add(span.id)
  else next.delete(span.id)
  selectedSuggestionIds.value = next
}

function toggleSelectAllSuggestions(on: boolean) {
  selectedSuggestionIds.value = toggleVisibleSuggestions(
    selectedSuggestionIds.value, visibleSuggestions.value, on)
}

function clearSuggestionSelection() {
  selectedSuggestionIds.value = new Set()
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

async function bulkResolveSelected(type: 'pos' | 'neg' | 'delete') {
  if (!selectedSuggestionIds.value.size || isBulkResolving.value) return
  // Snapshot the exact ID set including selections hidden by filters (#806).
  const idSet = new Set(selectedSuggestionIds.value)
  const selected = pendingAutoSpans.value.filter((e) => e.span.id && idSet.has(e.span.id))
  const targets = selected.flatMap((e) => e.span.id ? [e.span.id] : [])
  if (!targets.length) return
  const isCurrent = resolveRequests.capture()
  const collectionId = props.collectionId
  const documentId = props.documentId
  const knownVersions = new Map(selected.flatMap((e) => e.span.id && e.span.editVersion !== undefined
    ? [[e.span.id, e.span.editVersion] as const] : []))
  if (type === 'delete' && confirmBulkDeletion(targets.length, pendingAutoSpans.value.length)) {
    const confirmed = await new Promise<boolean>((resolve) => {
      $q.dialog({
        title: `Delete ${targets.length} ${targets.length === 1 ? 'suggestion' : 'suggestions'}?`,
        message: 'Permanently remove these AI suggestions without recording rejections. This cannot be undone; rerunning AI may produce different results.',
        persistent: true,
        cancel: { label: 'Cancel', flat: true, noCaps: true },
        ok: { label: 'Delete suggestions', color: 'negative', noCaps: true }
      }).onOk(() => resolve(true)).onCancel(() => resolve(false)).onDismiss(() => resolve(false))
    })
    if (!confirmed || !isCurrent()) return
  }

  const targetIds = new Set(targets)
  const nextHighlight =
    pendingAutoSpans.value.find((e) => e.span.id && !targetIds.has(e.span.id))?.span.id ?? null

  isBulkResolving.value = true
  bulkAction.value = type === 'delete' ? 'delete' : type === SpanType.pos ? 'confirm' : 'reject'
  bulkProgress.value = { total: targets.length, processed: 0, saved: 0, notSaved: 0 }
  for (const id of targets) busyAutoSpanIds.value.add(id)
  let summary: BulkResolveSummary | null = null
  try {
    summary = await runBulkResolve(
      targets,
      async (ids) => {
        if (!isCurrent()) return null
        try {
          if (type !== 'delete') return await tagSpans.applyBulkUpdate(ids, { type })
          const expectedVersions = Object.fromEntries(ids.flatMap((id) => {
            const version = knownVersions.get(id)
            return version === undefined ? [] : [[id, version]]
          }))
          const result = await api.deleteAutoSpansApiAiAutoSpansDeletePost({
            deleteAutoSpansRequest: { collectionId, documentId, spanIds: ids, expectedVersions }
          })
          if (!isCurrent()) return null
          const deletedIds = new Set(result.succeeded ?? [])
          if (deletedIds.size) tagSpans.removeSpansLocally((s) => !!s.id && deletedIds.has(s.id))
          return result
        } finally {
          if (isCurrent()) for (const id of ids) busyAutoSpanIds.value.delete(id)
        }
      },
      (progress) => { if (isCurrent()) bulkProgress.value = progress }
    )
  } finally {
    if (isCurrent()) {
      for (const id of targets) busyAutoSpanIds.value.delete(id)
      isBulkResolving.value = false
      bulkAction.value = null
      bulkProgress.value = null
    }
  }
  if (!isCurrent() || !summary || summary.abandoned) return
  const unresolved = new Set(summary.unresolved)
  selectedSuggestionIds.value = new Set([...selectedSuggestionIds.value].filter((id) => unresolved.has(id)))
  if (summary.saved) aiAssist.highlightedAutoSpanId.value = nextHighlight
  if (summary.error) console.error('Bulk resolve failed', summary.error)
  const verb = type === 'delete' ? 'Deleted' : type === SpanType.pos ? 'Confirmed' : 'Rejected'
  const message = describeBulkResolve(summary, verb)
  if (message) {
    $q.notify({ type: 'negative', message, timeout: 10000 })
  } else {
    const n = summary.saved
    $q.notify({ type: 'positive', message: `${verb} ${n} ${n === 1 ? 'suggestion' : 'suggestions'}.` })
  }
}

async function onBulkDelete() {
  if (!selectedAiTagIds.value.length) return
  const isCurrent = resolveRequests.capture()
  const request = {
    collectionId: props.collectionId,
    documentId: props.documentId,
    tagIds: [...selectedAiTagIds.value]
  }
  isBulkDeleting.value = true
  lastDeletedCount.value = null
  try {
    const result = await api.deleteAutoSpansApiAiAutoSpansDeletePost({
      deleteAutoSpansRequest: request
    })
    if (!isCurrent()) return
    lastDeletedCount.value = result.deleted
    lastStatusKind.value = 'deleted'
    // Drop exactly the spans the backend deleted; failed ones stay visible.
    const deletedIds = new Set(result.succeeded ?? [])
    tagSpans.removeSpansLocally((s) => !!s.id && deletedIds.has(s.id))
    if (result.outcome !== WriteOutcome.complete) {
      $q.notify({ type: 'negative', message: describeIncomplete(result, 'Removing suggestions') })
    }
  } catch (e) {
    if (!isCurrent()) return
    console.error('Bulk delete of auto spans failed', e)
    $q.notify({ type: 'negative', message: 'Failed to remove suggestions.' })
  } finally {
    if (isCurrent()) isBulkDeleting.value = false
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
    suggestionFocusRequest++
    selectedSuggestionIds.value = new Set()
    isBulkDeleting.value = false
    isBulkResolving.value = false
    bulkAction.value = null
    bulkProgress.value = null
    busyAutoSpanIds.value = new Set()
    proposalSort.value = 'confidence'
    proposalDescending.value = true
    resetProposalFilters()
    pendingSuggestionsOpen.value = true
    proposalFiltersOpen.value = false
    revealedSuggestion.value = false
    lastDeletedCount.value = null
    lastStatusKind.value = null
  }
)
// The tags chosen for runs are remembered per user and collection (#770, `aiRunTags`), so
// folded run options are ready to run after a reload.
const userStore = useUserStore()
watch(
  [() => props.collectionId, () => userStore.getUserId],
  ([collectionId, userId]) => {
    chosenAiTagIds.value = readRunTags(userId, collectionId)
  },
  { immediate: true }
)
watch(chosenAiTagIds, (ids) => {
  writeRunTags(userStore.getUserId, props.collectionId, ids)
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

/* The AI panel is not `fill`: the parent right sidebar scrolls over run options,
   filters and actions. The virtualized list keeps a bounded inner viewport. */
.ai-assist-panel {
  min-height: 0;
  height: auto;
}
.ai-assist-panel .ai-tag-list,
.ai-assist-panel.has-pending .ai-tag-list {
  flex: none;
}
.ai-assist-panel .auto-span-list,
.ai-assist-panel.has-pending .auto-span-list {
  flex: none;
  min-height: 0;
  max-height: 360px;
}

.proposal-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  min-width: 0;
  gap: 4px;
  margin: 4px 0 5px;
}
.proposal-sort {
  flex: 1 1 150px;
  min-width: 0;
}
.proposal-toolbar > .q-btn {
  flex: 0 0 auto;
}
.proposal-active-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  min-width: 0;
  margin-bottom: 6px;
}
.proposal-active-filters .q-chip {
  margin: 2px;
  max-width: 100%;
}
.proposal-active-filters .proposal-filter-chip {
  border: 1px solid #dadce0;
}
.proposal-active-filters .proposal-filter-chip :deep(.q-chip__icon--remove) {
  opacity: 0.65;
  font-size: 18px;
}
.proposal-chip-text {
  display: inline-block;
  max-width: 210px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
.proposal-controls {
  flex: 0 0 auto;
  padding: 4px 0 6px;
}
.proposal-control--full {
  flex-basis: 100%;
}
.proposal-controls-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.proposal-control-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  margin-bottom: 5px;
  min-width: 0;
}

/* The tag label is the only keyboard-operated highlight action in a card.
   It is a sibling of the checkbox and action buttons, not their ancestor. */
.auto-span-highlight {
  border: 0;
  padding: 0;
  background: transparent;
  font: inherit;
  color: inherit;
  cursor: pointer;
  min-width: 0;
  text-align: left;
}
.auto-span-highlight:focus-visible {
  outline: 2px solid var(--q-primary);
  outline-offset: 2px;
  border-radius: 2px;
}
/* Preserve numeric validation but hide the native stepper arrows. */
.proposal-controls :deep(input[type="number"]) {
  appearance: textfield;
  -moz-appearance: textfield;
}
.proposal-controls :deep(input[type="number"]::-webkit-outer-spin-button),
.proposal-controls :deep(input[type="number"]::-webkit-inner-spin-button) {
  -webkit-appearance: none;
  margin: 0;
}

.proposal-control {
  flex: 1 1 140px;
  min-width: 0;
}

.ai-tag-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: min(260px, 40vh);
  overflow-y: auto;
  padding: 4px 6px;
  background: rgba(15, 23, 42, 0.03);
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 6px;
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
  display: block;
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
/* Keep the selection count above four evenly sized icon + label actions (#801). */
.auto-span-bulk-bar {
  min-width: 0;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 2px;
}
.auto-span-bulk-status {
  display: flex;
  flex: 1 1 100%;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 2px 8px;
  min-width: 0;
}
.auto-span-bulk-status > .q-checkbox {
  min-width: 0;
}
.auto-span-bulk-status > [data-testid="proposal-match-count"] {
  margin-left: auto;
  white-space: nowrap;
}
.auto-span-bulk-bar > .q-space {
  display: none;
}
.auto-span-bulk-bar > .q-btn {
  flex: 1 1 calc(25% - 2px);
  min-width: 0;
  padding: 3px 0;
  font-size: 11px;
  line-height: 1.2;
}
</style>
