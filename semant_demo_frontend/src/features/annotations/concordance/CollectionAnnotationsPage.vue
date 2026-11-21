<template>
  <q-page class="collection-annotations q-px-md q-pb-lg" data-testid="collection-annotations">
    <ConcordanceToolbar
      ref="toolbar"
      :filters="store.filters"
      :tags="tags"
      :documents="store.documents"
      :documents-error="store.documentsError"
      :facets="store.facets"
      :attributes="attributesStore.attributes"
      :shown-attribute-ids="store.shownAttributeIds"
      class="q-mb-sm"
      @change="store.setFilters"
      @show-attributes="ids => { store.shownAttributeIds = ids }"
    />

    <ConcordanceFilterChips
      :filters="store.filters"
      :tags="tags"
      :documents="store.documents"
      :attributes="attributesStore.attributes"
      class="q-mb-sm"
      @change="store.setFilters"
      @reset="store.resetFilters"
      @open="openContext"
    />

    <SimilarSourceBar
      :filters="store.filters"
      :has-previous="!!store.previousView"
      @open="openContext"
      @change="store.setFilters"
      @back="store.returnFromSimilar"
    />

    <SelectionBar
      v-if="!statisticsView"
      class="q-mb-xs"
      :selected-count="selection.size"
      :total="store.total"
      :ranked="ranked"
      :hidden-selected="store.hiddenSelected"
      :shown-error="store.shownError"
      :all-selected="allMatchesSelected"
      :resolving="store.resolving"
      :tags="tags"
      :running="review.running"
      :progress="review.progress"
      :running-target="review.target"
      :report="review.report"
      :undoable="review.undoable"
      :undo-note="review.undoNote"
      :assign-busy="assign.running || assign.pending.size > 0"
      :assign-report="assign.report"
      :assign-attribute="assignReportAttribute"
      @select-all="selectAllMatches"
      @clear="clearSelection"
      @deselect-hidden="store.deselectHidden"
      @reload-shown="store.loadShown"
      @review="(action, tagId) => reviewSelection(action, tagId)"
      @retry="retryReview"
      @show-changed="showChanged"
      @dismiss="review.dismiss"
      @undo="undoLast"
      @assign="assignSelection"
      @assign-retry="retryAssign"
      @assign-show-changed="showChangedAssign"
      @assign-dismiss="assign.dismiss"
    />

    <div class="collection-annotations__summary" aria-live="polite">
      <!-- First in the row, so it stays in place whatever each view puts after it. -->
      <q-btn-toggle
        :model-value="statisticsView ? 'statistics' : 'list'"
        dense
        no-caps
        unelevated
        rounded
        toggle-color="primary"
        color="white"
        text-color="primary"
        class="collection-annotations__view"
        aria-label="View"
        data-testid="annotations-view"
        :options="[
          { value: 'list', label: 'List', icon: 'view_list', attrs: { 'data-testid': 'annotations-view-list' } },
          { value: 'statistics', label: 'Statistics', icon: 'bar_chart', attrs: { 'data-testid': 'annotations-view-statistics' } }
        ]"
        @update:model-value="showView"
      />
      <template v-if="!statisticsView">
      <span data-testid="concordance-range">{{ rangeLabel }}</span>
      <span v-if="rankedText" class="collection-annotations__ranked text-grey-8" data-testid="concordance-ranked">{{ rankedText }}</span>
      <span v-if="unsortableText" class="collection-annotations__ranked text-grey-8" data-testid="concordance-unsortable">{{ unsortableText }}</span>
      <span v-if="proximityText" class="collection-annotations__ranked text-grey-8" data-testid="concordance-proximity">{{ proximityText }}</span>
      <q-spinner v-if="store.loading" color="primary" size="1.2em" aria-label="Loading annotations" />
      <!-- Reviewed rows stay in place until the list is read again (#690). -->
      <span v-if="store.unmatched.size" class="collection-annotations__unmatched text-grey-8" data-testid="concordance-unmatched">
        {{ plural(store.unmatched.size, 'reviewed row') }} no longer {{ store.unmatched.size === 1 ? 'matches' : 'match' }} the filters
        <q-btn flat dense no-caps color="primary" label="Refresh" :disable="store.loading" data-testid="concordance-refresh" @click="store.load">
          <q-tooltip>Read the list again: rows that no longer match leave it</q-tooltip>
        </q-btn>
      </span>
      </template>
      <span v-else-if="rankedText" class="collection-annotations__ranked text-grey-8">{{ rankedText }}</span>
      <q-space />
      <q-btn
        v-if="!statisticsView"
        flat
        dense
        no-caps
        color="primary"
        icon="file_download"
        label="Export CSV"
        data-testid="export-csv"
        @click="exportOpen = true"
      >
        <q-tooltip>Download the selected annotations, the filter matches or all annotations as a spreadsheet file</q-tooltip>
      </q-btn>
      <PagerButtons v-if="store.total > PAGE_SIZE && !statisticsView" />
    </div>

    <AnnotationStatisticsPanel
      v-if="statisticsView"
      :filters="store.filters"
      :collection-id="collectionId"
      :tags="tags"
      :documents="store.documents"
      :dimension="statisticsDimension"
      @drill="drillFromStatistics"
      @dimension="showDimension"
    />
    <template v-else>

    <AnnotationExportDialog
      v-model="exportOpen"
      :collection-id="collectionId"
      :filters="store.filters"
      :filter-summary="filterSummary"
      :selected-ids="selection.ids"
      :hidden-selected="store.hiddenSelected"
      :total="store.total"
      :ranked="ranked"
    />

    <div v-if="store.error" class="collection-annotations__state text-negative" role="alert" data-testid="concordance-error">
      {{ store.error }}
      <q-btn flat dense no-caps color="primary" label="Retry" @click="store.load" />
    </div>
    <div
      v-else-if="!store.loading && store.page && !store.rows.length"
      class="collection-annotations__state text-grey-8"
      data-testid="concordance-empty"
    >
      {{ emptyText }}
    </div>
    <div v-else-if="!store.page" class="collection-annotations__state text-grey-7">Loading annotations…</div>

    <ConcordanceTable
      v-if="store.rows.length && !store.error"
      ref="table"
      :rows="store.rows"
      :tags="tags"
      :selected="selection.ids"
      :focused-id="selection.focused?.id ?? null"
      :loading="store.loading"
      :attributes="shownAttributes"
      :pending="assignWaiting"
      :saving="savingIds"
      :unmatched="store.unmatched"
      :query="store.filters.text"
      :query-scope="store.filters.textScope"
      :rank-start="ranked ? store.offset + 1 : null"
      :filters="store.filters"
      similar
      :class="{ 'collection-annotations__stale': store.loading }"
      @open="openContext"
      @open-neighbor="openNeighbor"
      @similar="findSimilar"
      @toggle="toggleRow"
      @select-page="selectPage"
      @sort="(sort, descending, sortAttribute) => store.setFilters({ sort, descending, sortAttribute })"
      @filter="field => toolbar?.openFilter(field)"
      @refine="store.setFilters"
      @assign="(row, attribute, change, done) => assignRow(row, attribute, change).then(done)"
      @review="(row, action, done) => reviewRow(row, action).then(done)"
      @step="(direction, done) => stepPage(direction).then(done)"
    />

    <!-- Says what a review decision or a move did (#690), from the sidebar and from the list. -->
    <div class="sr-only" aria-live="polite" data-testid="annotation-announcement">{{ announcement }}</div>

    <div v-if="store.total > PAGE_SIZE && store.rows.length" class="collection-annotations__summary q-mt-sm">
      <q-space />
      <PagerButtons />
    </div>
    </template>

    <!-- Registered once a row is opened. -->
    <RightSidebarPanel v-if="selection.focused" :id="CONTEXT_PANEL_ID" label="Annotation" icon="format_quote" :order="1" fill v-slot="{ visible }">
      <ChunkContextPanel
        :visible="visible"
        ref="panel"
        :target-chunk-id="chunkContext.target?.chunkId ?? null"
        :document="chunkContext.document"
        :chunks="chunkContext.chunks"
        :has-before="chunkContext.hasBefore"
        :has-after="chunkContext.hasAfter"
        :focus-request="chunkContext.focusRequest"
        :loading="chunkContext.loading"
        :extending="chunkContext.extending"
        :error="chunkContext.error"
        :highlight="highlight"
        target-name="Annotated passage"
        document-heading="In the document"
        scroll-text
        :open-link="selection.focused.documentId ? documentRoute : null"
        link-title
        back-label="Back to annotation"
        @extend="chunkContext.extend"
        @reload="chunkContext.load"
        @focus="chunkContext.focus"
      >
        <template #header>
          <!-- The open annotation (#659): what it is and what can be done with it first, then its
               attributes and origin (scrolled within a capped height), then its document. -->
          <div class="annotation-context" data-testid="annotation-context">
            <section class="annotation-context__main" aria-label="Annotation">
              <!-- Its tag (choosing another one retags it) and its place in the result (#690). -->
              <div class="annotation-context__head">
                <TagChipMenu
                  :tag="focusedTag"
                  :tags="tags"
                  :disable="review.running || selection.focusedGone || editingBoundary"
                  @pick="tagId => reviewFocused(ReviewAction.retag, tagId)"
                />
                <nav class="annotation-context__nav" aria-label="Annotations in the list" data-testid="annotation-nav">
                  <q-btn
                    flat
                    round
                    dense
                    color="primary"
                    icon="chevron_left"
                    aria-label="Previous annotation"
                    aria-keyshortcuts="Alt+ArrowUp"
                    :disable="!canStep(-1)"
                    data-testid="row-prev"
                    @click="stepAndAnnounce(-1)"
                  >
                    <q-tooltip>Previous (Alt+↑)</q-tooltip>
                  </q-btn>
                  <span v-if="position" class="annotation-context__position text-caption" data-testid="annotation-position">{{ position }}</span>
                  <q-btn
                    flat
                    round
                    dense
                    color="primary"
                    icon="chevron_right"
                    aria-label="Next annotation"
                    aria-keyshortcuts="Alt+ArrowDown"
                    :disable="!canStep(1)"
                    data-testid="row-next"
                    @click="stepAndAnnounce(1)"
                  >
                    <q-tooltip>Next (Alt+↓)</q-tooltip>
                  </q-btn>
                </nav>
              </div>
              <BoundaryEditor
                v-if="editingBoundary && boundary"
                ref="boundaryEditor"
                v-model:unit="boundaryUnit"
                :text="boundaryText"
                :changed="boundaryChanged"
                :saving="savingBoundary"
                :note="boundaryNote"
                @step="stepEdited"
                @use-selection="useSelectedText"
                @save="saveBoundary"
                @cancel="cancelBoundary"
              />
              <!-- The review decision as a choice of state (#690): the current one is pressed and named
                   as the state (Confirmed / Rejected), an unpressed one as the action it takes (Confirm /
                   Reject); a proposal has neither pressed. The buttons share the row equally, so a label
                   change does not move them. After a decision the next row opens. -->
              <div
                v-else-if="!selection.focusedGone"
                class="annotation-context__review"
                role="group"
                :aria-label="`Review this annotation, now ${statusText.toLowerCase()}`"
                data-testid="annotation-review"
              >
                <q-btn
                  :unelevated="isConfirmed"
                  :outline="!isConfirmed"
                  no-caps
                  color="positive"
                  icon="check"
                  :label="isConfirmed ? 'Confirmed' : 'Confirm'"
                  class="annotation-context__decision"
                  :aria-pressed="isConfirmed ? 'true' : 'false'"
                  aria-keyshortcuts="Alt+C"
                  :loading="savingAction === ReviewAction.approve"
                  :disable="decisionDisabled"
                  data-testid="row-approve"
                  @click="decide(ReviewAction.approve)"
                >
                  <q-tooltip>{{ isConfirmed ? 'Confirmed (Alt+C)' : 'Confirm (Alt+C)' }}</q-tooltip>
                </q-btn>
                <q-btn
                  :unelevated="isRejected"
                  :outline="!isRejected"
                  no-caps
                  color="deep-orange-9"
                  icon="block"
                  :label="isRejected ? 'Rejected' : 'Reject'"
                  class="annotation-context__decision"
                  :aria-pressed="isRejected ? 'true' : 'false'"
                  aria-keyshortcuts="Alt+R"
                  :loading="savingAction === ReviewAction.reject"
                  :disable="decisionDisabled"
                  data-testid="row-reject"
                  @click="decide(ReviewAction.reject)"
                >
                  <q-tooltip>
                    {{ isRejected ? 'Rejected (Alt+R)' : 'Reject (Alt+R)' }}: kept as a rejected
                    annotation (negative feedback); to remove it for good, use Delete
                  </q-tooltip>
                </q-btn>
              </div>
              <div
                v-if="focusedConflict && !selection.focusedGone"
                class="annotation-context__conflict text-body2"
                role="alert"
                data-testid="annotation-conflict"
              >
                <div>{{ conflictText }}</div>
                <div class="annotation-context__conflict-actions">
                  <q-btn
                    dense
                    unelevated
                    no-caps
                    color="primary"
                    label="Apply to current version"
                    :disable="review.running || store.loading || savingBoundary"
                    data-testid="conflict-apply"
                    @click="applyToCurrent"
                  />
                  <q-btn dense flat no-caps color="primary" label="Keep" data-testid="conflict-keep" @click="keepCurrent" />
                </div>
              </div>
              <div
                v-if="selection.focusedGone"
                class="annotation-context__gone text-body2 text-grey-8"
                role="status"
                data-testid="annotation-context-gone"
              >
                This annotation is no longer on this page: it was deleted, or an edit took it out of
                these filters or moved it to another page.
              </div>
              <!-- A long text shows its first lines, ending in "…"; the text or the arrow
                   unfolds it (the whole span is also marked in the passage below). -->
              <div
                v-else
                class="annotation-context__quote"
                :class="{ 'annotation-context__quote--foldable': textClamped || textExpanded }"
                @click="toggleTextFromClick"
              >
                <blockquote
                  ref="focusedTextEl"
                  class="annotation-context__text text-body2"
                  :class="{ 'annotation-context__text--expanded': textExpanded }"
                  :style="textStyle"
                  data-testid="annotation-context-text"
                >{{ selection.focused.text ?? 'The annotated text is not available yet.' }}</blockquote>
                <span v-if="textClamped && !textExpanded" class="annotation-context__ellipsis" aria-hidden="true">…</span>
                <q-btn
                  v-if="textClamped || textExpanded"
                  flat
                  round
                  dense
                  size="sm"
                  color="primary"
                  icon="expand_more"
                  class="annotation-context__fold"
                  :class="{ 'annotation-context__fold--open': textExpanded }"
                  :aria-label="textExpanded ? 'Show less text' : 'Show all text'"
                  :aria-expanded="textExpanded"
                  data-testid="annotation-context-text-toggle"
                  @click.stop="textExpanded = !textExpanded"
                />
              </div>
              <!-- Corrections, and annotations like this one. -->
              <div
                v-if="!selection.focusedGone && !editingBoundary"
                class="annotation-context__actions"
                data-testid="annotation-secondary-actions"
              >
                <q-btn
                  ref="editBoundaryButton"
                  dense
                  flat
                  no-caps
                  color="primary"
                  icon="straighten"
                  label="Edit boundaries"
                  :disable="review.running || !canEditBoundary"
                  data-testid="row-edit-boundaries"
                  @click="editBoundary"
                >
                  <q-tooltip>{{ canEditBoundary ? 'Change where this annotation starts or ends' : 'Wait until its passage is loaded' }}</q-tooltip>
                </q-btn>
                <q-btn
                  dense
                  flat
                  no-caps
                  color="primary"
                  icon="join_inner"
                  label="Find similar"
                  :disable="selection.focused.textStatus !== TextStatus.ready"
                  data-testid="row-find-similar"
                  @click="findSimilar(selection.focused)"
                >
                  <q-tooltip>
                    {{ selection.focused.textStatus === TextStatus.ready
                      ? 'List the annotations closest in meaning to this one, within the current filters'
                      : 'Its text and vector are not derived yet' }}
                  </q-tooltip>
                </q-btn>
                <!-- Kept apart from the review decision and less prominent; it asks before deleting. -->
                <q-btn
                  dense
                  flat
                  round
                  color="grey-7"
                  icon="delete_outline"
                  aria-label="Delete…"
                  class="annotation-context__delete"
                  :disable="review.running"
                  data-testid="row-delete"
                  @click="reviewFocused(ReviewAction.delete)"
                >
                  <q-tooltip>Delete: remove the annotation permanently; it cannot be restored. To keep it as negative feedback, use Reject</q-tooltip>
                </q-btn>
              </div>
            </section>
            <div v-if="!selection.focusedGone" class="annotation-context__details" data-testid="annotation-context-details">
              <AnnotationAttributes
                :row="selection.focused"
                :attributes="attributesStore.attributes"
                :loading="attributesStore.loading"
                :error="attributesStore.error"
                :busy="assign.running || assign.pending.has(selection.focused.id)"
                :definitions-route="{ name: 'collectionAttributes', params: { collectionId } }"
                @assign="(attribute, change, done) => selection.focused && assignRow(selection.focused, attribute, change).then(done)"
              />
            </div>
            <section v-if="!selection.focusedGone && selection.focused.provenance" class="annotation-context__origin" aria-label="Origin">
              <div class="annotation-context__title text-caption">Origin</div>
              <ProvenanceSummary
                :provenance="selection.focused.provenance"
                :type="selection.focused.type"
                :people="store.people"
                :me="userStore.getUserId"
              />
            </section>
          </div>
        </template>
      </ChunkContextPanel>
    </RightSidebarPanel>
  </q-page>
</template>

<script setup lang="ts">
import { plural } from 'src/shared/plural'
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { QBtn, QBtnToggle, QPage, QSpace, QSpinner, QTooltip, useQuasar } from 'quasar'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import {
  RetrievalMode, ReviewAction, SpanType, TextStatus, type AnnotationListRow, type Attribute, type AttributeAssignResult
} from 'src/generated/api'
import { apiErrorMessage, captureSession, errorStatus } from 'src/shared/api'
import { spanWriteWarning } from 'src/shared/writeOutcome'
import { warningNotification } from 'src/shared/notification'
import { useTagSpansRepository } from 'src/features/annotations/useTagSpansRepository'
import RightSidebarPanel from 'src/app/sidebar/RightSidebarPanel.vue'
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import ChunkContextPanel from 'src/features/documents/ChunkContextPanel.vue'
import { useChunkContext } from 'src/features/documents/useChunkContext'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import { MAX_SELECTION, useAnnotationSelectionStore } from 'src/features/annotations/annotationSelectionStore'
import ConcordanceFilterChips from './ConcordanceFilterChips.vue'
import AnnotationStatisticsPanel from '../statistics/AnnotationStatisticsPanel.vue'
import { DIMENSIONS, type Dimension } from '../statistics/statistics'
import type { ConcordanceFilters } from './concordanceStore'
import SimilarSourceBar from './SimilarSourceBar.vue'
import ConcordanceTable, { type RowDecision } from './ConcordanceTable.vue'
import ConcordanceToolbar from './ConcordanceToolbar.vue'
import SelectionBar from './SelectionBar.vue'
import TagChipMenu from './TagChipMenu.vue'
import ProvenanceSummary from './ProvenanceSummary.vue'
import BoundaryEditor from './BoundaryEditor.vue'
import AnnotationAttributes from './AnnotationAttributes.vue'
import AnnotationExportDialog from './AnnotationExportDialog.vue'
import { exportFilterSummary } from './annotationExport'
import { useAttributesStore } from 'src/features/attributes/attributesStore'
import { assignMayHaveChanged, useAttributeAssignStore } from 'src/features/attributes/attributeAssignStore'
import AssignAttributeDialog from 'src/features/attributes/AssignAttributeDialog.vue'
import type { AssignChange } from 'src/features/attributes/assignment'
import {
  rangeBetween, rangeText, sameRange, stepBoundary, type BoundaryHandle, type BoundaryRange, type BoundaryUnit
} from './boundaryEdit'
import { useAnnotationReviewStore, type ReviewReport } from './annotationReviewStore'
import { PAGE_SIZE, defaultFilters, useConcordanceStore } from './concordanceStore'
import { concordanceChips, proximityLabel, rankedLabel, unsortableLabel } from './filterChips'
import { formatWhen, personName } from './provenance'
import { useUserStore } from 'src/features/auth/userStore'
import type { SelectionEntry } from 'src/features/annotations/annotationSelectionStore'

const CONTEXT_PANEL_ID = 'annotation-context'

const route = useRoute()
const $q = useQuasar()
const store = reactive(useConcordanceStore())
const selection = reactive(useAnnotationSelectionStore())
const review = reactive(useAnnotationReviewStore())
const assign = reactive(useAttributeAssignStore())
const attributesStore = reactive(useAttributesStore())
const userStore = useUserStore()
const tagsStore = useTagsStore()
const { tags } = storeToRefs(tagsStore)
const rightSidebar = useRightSidebarStore()
const chunkContext = reactive(useChunkContext())
const table = ref<InstanceType<typeof ConcordanceTable> | null>(null)
const toolbar = ref<InstanceType<typeof ConcordanceToolbar> | null>(null)
const panel = ref<InstanceType<typeof ChunkContextPanel> | null>(null)
const spansRepo = useTagSpansRepository()

const collectionId = computed(() => typeof route.params.collectionId === 'string' ? route.params.collectionId : '')

// ── Statistics view (#818): the same query, counted instead of listed (`?view=statistics`, one
// distribution in full with `&dimension=`). ──
const router = useRouter()
const statisticsView = computed(() => route.query.view === 'statistics')
const statisticsDimension = computed<Dimension | null>(() => {
  const d = route.query.dimension
  return typeof d === 'string' && (DIMENSIONS as readonly string[]).includes(d) ? d as Dimension : null
})
function showView (view: 'list' | 'statistics') {
  void router.push({ query: view === 'statistics' ? { view } : {} })
}
function showDimension (dimension: Dimension | null) {
  void router.push({ query: dimension ? { view: 'statistics', dimension } : { view: 'statistics' } })
}
/** Lists exactly a category's annotations: the query narrowed to it, then the list. */
function drillFromStatistics (change: Partial<ConcordanceFilters>) {
  void store.setFilters(change)
  void router.push({ query: {} })
}

const ranked = computed(() => store.filters.mode !== RetrievalMode.lexical)

const rangeLabel = computed(() => {
  if (!store.page) return ''
  if (!store.total) return ranked.value ? 'No ranked annotations' : 'No matching annotations'
  const first = store.offset + 1
  const last = store.offset + store.rows.length
  return `Rows ${first}–${last} of ${store.total} ${ranked.value ? 'ranked' : 'matching'} annotations`
})

// ── CSV export (#719) ──
const exportOpen = ref(false)
/** The active filters in words, for the export's filter scope. */
const filterSummary = computed(() => exportFilterSummary(store.filters,
  concordanceChips(store.filters, tags.value, store.documents, attributesStore.attributes)))

/** A ranked page's description (#664): top k, truncation and vector coverage. */
const rankedText = computed(() => rankedLabel(store.page?.result, store.total))

/** Text and context sorts (#666): how many rows have no current sort key, and where they are. */
const unsortableText = computed(() => unsortableLabel(store.page?.unsortable, store.filters.descending))

/** Proximity (#333): what could not be compared for lack of current positions. */
const proximityText = computed(() => proximityLabel(store.page?.proximity))

const emptyText = computed(() => {
  if (ranked.value) return 'No annotation matching these filters has a current vector to rank by.'
  return JSON.stringify(store.filters) === JSON.stringify(defaultFilters())
    ? 'This collection has no confirmed or proposed annotations yet.'
    : 'No annotations match these filters.'
})

// Previous/next page; rendered above and below the rows.
const PagerButtons = defineComponent(() => () => h('div', { class: 'row no-wrap q-gutter-x-xs' }, [
  h(QBtn, {
    dense: true,
    outline: true,
    noCaps: true,
    color: 'primary',
    icon: 'chevron_left',
    label: 'Previous',
    disable: store.offset === 0 || store.loading,
    onClick: () => store.goTo(Math.max(0, store.offset - PAGE_SIZE))
  }),
  h(QBtn, {
    dense: true,
    outline: true,
    noCaps: true,
    color: 'primary',
    iconRight: 'chevron_right',
    label: 'Next',
    disable: !store.hasNextPage || store.loading,
    onClick: () => store.goTo(store.nextOffset)
  })
]))

// ── Source context (shared right sidebar) ──
const highlight = computed(() => {
  if (editingBoundary.value && boundary.value) return { ...boundary.value.range, pending: true }
  const row = selection.focusedGone ? null : selection.focused
  return row?.chunkId && row.start != null && row.end != null
    ? { chunkId: row.chunkId, start: row.start, end: row.end }
    : null
})

// The decision is a choice of state (#690): the state in effect is pressed, not disabled.
const isConfirmed = computed(() => selection.focused?.type === SpanType.pos)
const isRejected = computed(() => selection.focused?.type === SpanType.neg)
const decisionDisabled = computed(() => review.running || savingBoundary.value)
const focusedTag = computed(() => tags.value.find(t => t.id === selection.focused?.tagId) ?? null)

// A long annotated text shows its first lines; the whole span is also marked in the passage.
// Its height is animated between those lines and the whole text (capped, then scrolled).
const TEXT_LINES = 3
const focusedTextEl = ref<HTMLElement | null>(null)
const textExpanded = ref(false)
const textClamped = ref(false)
const textHeights = ref<{ folded: number, full: number } | null>(null)

/** Measures the text's folded and whole heights (again when the panel's width changes). */
function measureText () {
  const el = focusedTextEl.value
  if (!el) { textClamped.value = false; textHeights.value = null; return }
  const style = getComputedStyle(el)
  const line = parseFloat(style.lineHeight) || 20
  const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom)
  const folded = Math.ceil(line * TEXT_LINES + padding)
  textHeights.value = { folded, full: el.scrollHeight }
  textClamped.value = el.scrollHeight > folded + 1
}
const textObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => measureText())
watch(focusedTextEl, (el, old) => {
  if (old) textObserver?.unobserve(old)
  if (el) textObserver?.observe(el)
})
onBeforeUnmount(() => textObserver?.disconnect())
watch(() => [selection.focused?.id, selection.focused?.text, selection.focusedGone] as const, async ([id], old) => {
  if (id !== old?.[0]) textExpanded.value = false
  await nextTick()
  measureText()
}, { immediate: true })
watch(textExpanded, measureText)
const textStyle = computed(() => {
  const h = textHeights.value
  if (!h || !textClamped.value) return undefined
  const full = Math.min(h.full, Math.round(window.innerHeight / 3))
  return { maxHeight: `${textExpanded.value ? full : h.folded}px` }
})

/** A click on a foldable text unfolds or folds it, unless it ended a text selection. */
function toggleTextFromClick () {
  if (!textClamped.value && !textExpanded.value) return
  if (window.getSelection()?.isCollapsed === false) return
  textExpanded.value = !textExpanded.value
}
const statusText = computed(() => ({
  [SpanType.pos]: 'Confirmed',
  [SpanType.auto]: 'Proposal',
  [SpanType.neg]: 'Rejected'
} as Record<string, string>)[selection.focused?.type ?? ''] ?? 'Unknown status')

const documentRoute = computed(() => {
  const row = selection.focused
  const order = chunkContext.chunks.find(c => c.id === row?.chunkId)?.order
  return {
    name: 'documentDetailV1',
    params: { collectionId: collectionId.value, documentId: row?.documentId ?? '' },
    query: {
      from: 'annotations',
      annotation: row?.id,
      chunk: row?.chunkId ?? undefined,
      order: order != null ? String(order) : undefined
    }
  }
})

function showContext (row: AnnotationListRow) {
  if (!row.documentId || !row.chunkId) return null
  return chunkContext.open({ documentId: row.documentId, chunkId: row.chunkId })
}

/** Opens the row in the sidebar; viewing context never changes the selection. */
async function openContext (row: AnnotationListRow) {
  if (row.id !== selection.focused?.id) {
    focusedConflict.value = null
    boundary.value = null
  }
  selection.focus(row)
  const opening = showContext(row)
  await nextTick() // the panel registers when the first row is opened
  rightSidebar.activate(CONTEXT_PANEL_ID)
  await opening
}

/** Opens a neighbor that made a row match the proximity filter (#333), read as it is now; it need
 * not be listed. */
async function openNeighbor (id: string) {
  try {
    const row = await store.readRow(id)
    if (row) await openContext(row)
    else $q.notify({ type: 'warning', message: 'This annotation no longer exists.' })
  } catch (e) {
    console.error('Reading the neighbor annotation failed', e)
    $q.notify({ type: 'negative', message: 'The annotation could not be read.' })
  }
}

/** Lists the annotations most similar to `row` within the current filters (#664); the row stays
 * open. On narrow screens the sidebar covering the list closes, so the result is seen. */
function findSimilar (row: AnnotationListRow) {
  if ($q.screen.lt.md) rightSidebar.open = false
  void store.findSimilar(row)
}

/** Escape closes the sidebar where it covers the list (narrow screens) and gives the keyboard back
 * to the open row. Not while a menu or dialog is open (Escape closes that) or when something
 * else handled the key (e.g. the boundary editor's cancel). */
function closeSidebarOnEscape (event: KeyboardEvent) {
  if (event.key !== 'Escape' || event.defaultPrevented || !$q.screen.lt.md) return
  if (!rightSidebar.open || !rightSidebar.hasPanels || !selection.focused) return
  // A field, select or menu takes Escape for itself (closing its list).
  const target = event.target as HTMLElement | null
  if (target?.closest('input, textarea, select, [role="listbox"], [role="menu"], .q-field, .q-menu, .q-dialog')) return
  if (document.querySelector('.q-menu, .q-dialog')) return
  // Closing returns to the open row (watch below).
  rightSidebar.open = false
}
onMounted(() => window.addEventListener('keydown', closeSidebarOnEscape))
onBeforeUnmount(() => window.removeEventListener('keydown', closeSidebarOnEscape))

// On a narrow screen the sidebar covers the list: closing it returns to the open row
// (focused and in view), or to the first row when it left this page (#669 review).
watch(() => rightSidebar.open, (open, was) => {
  if (open || !was || !$q.screen.lt.md || !selection.focused) return
  const id = selection.focused.id
  void nextTick(() => {
    const back = store.rows.some(r => r.id === id) ? id : store.rows[0]?.id
    if (back) table.value?.reveal(back)
  })
})

// ── Selection (#459) ──
const allMatchesSelected = computed(() =>
  store.hiddenSelected !== null && selection.size - store.hiddenSelected >= store.total)

function tooMany () {
  $q.notify({ type: 'warning', message: `The selection can hold at most ${MAX_SELECTION} annotations.` })
}

function toggleRow (id: string, value: boolean) {
  const row = store.rows.find(r => r.id === id)
  if (!selection.toggle(id, row?.editVersion ?? 0, value, row?.attributeVersion ?? 0)) tooMany()
}

function selectPage (value: boolean) {
  if (!store.setPageSelected(value)) tooMany()
}

function clearSelection () {
  selection.clearSelection()
  void store.loadShown()
}

async function selectAllMatches () {
  const problem = await store.selectAllMatches()
  if (problem) $q.notify({ type: 'warning', message: problem })
}

// ── Review (#459) ──
const VERB: Record<ReviewAction, string> = {
  [ReviewAction.approve]: 'Confirm',
  [ReviewAction.reject]: 'Reject',
  [ReviewAction.retag]: 'Change the tag of',
  [ReviewAction.delete]: 'Delete'
}

// ── Moving through the result in the sidebar (#690) ──
/** The open row's index on this page; -1 when it is not listed here. */
const focusedIndex = computed(() =>
  selection.focusedGone ? -1 : store.rows.findIndex(r => r.id === selection.focused?.id))
/** "3 / 50": its place in the result as read (the total changes only when the list is read again). */
const position = computed(() =>
  focusedIndex.value < 0 ? '' : `${store.offset + focusedIndex.value + 1} / ${store.total}`)

function canStep (direction: 1 | -1): boolean {
  const index = focusedIndex.value
  if (index < 0 || store.loading) return false
  if (store.rows[index + direction]) return true
  return direction > 0 ? store.hasNextPage : store.offset > 0
}

/** Opens the next or previous row of the result, reading the adjacent page at the end of this
 * one; the row opened, or null when there is none. Keyboard focus stays where it is. */
async function step (direction: 1 | -1): Promise<AnnotationListRow | null> {
  if (!canStep(direction)) return null
  let row = store.rows[focusedIndex.value + direction] ?? null
  if (!row) {
    await store.goTo(direction > 0 ? store.nextOffset : Math.max(0, store.offset - PAGE_SIZE))
    row = (direction > 0 ? store.rows[0] : store.rows[store.rows.length - 1]) ?? null
    if (!row) return null
  }
  void openContext(row)
  return row
}

/** What the polite live region says after a move or decision (#690). */
const announcement = ref('')
const ANNOUNCED_TEXT = 60

/** Says `prefix`, then the row's place in the result and its text, and whether it is the last one. */
function announce (prefix: string, row: AnnotationListRow | null) {
  const text = (row?.text ?? '').replace(/\s+/g, ' ').trim()
  const clipped = text.length > ANNOUNCED_TEXT ? `${text.slice(0, ANNOUNCED_TEXT - 1)}…` : text
  const index = row ? store.rows.findIndex(r => r.id === row.id) : -1
  const parts = [prefix]
  if (index >= 0) parts.push(`${store.offset + index + 1} / ${store.total}${clipped ? `: ${clipped}` : ''}.`)
  const last = index >= 0 ? !store.rows[index + 1] && !store.hasNextPage : !canStep(1)
  if (last) parts.push('Last annotation.')
  announcement.value = parts.filter(Boolean).join(' ')
}

async function stepAndAnnounce (direction: 1 | -1) {
  announce('', await step(direction))
}

/** Asks before deleting, and before a change to annotations not on this page. */
function confirmed (action: ReviewAction, ids: string[], tagId?: string): Promise<boolean> {
  const offPage = ids.filter(id => !store.rows.some(r => r.id === id)).length
  if (action !== ReviewAction.delete && !offPage) return Promise.resolve(true)
  const tag = tagId ? tags.value.find(t => t.id === tagId)?.name : null
  const lines = [`${VERB[action]} ${plural(ids.length, 'annotation')}${tag ? ` to "${tag}"` : ''}?`]
  if (offPage) lines.push(`${offPage} of them ${offPage === 1 ? 'is' : 'are'} not on this page.`)
  if (action === ReviewAction.delete) {
    lines.push('Deleted annotations cannot be restored. To keep a proposal as negative feedback, reject it instead.')
  }
  return new Promise(resolve => {
    $q.dialog({
      title: action === ReviewAction.delete ? 'Delete annotations' : 'Review annotations',
      message: lines.join(' '),
      cancel: true,
      persistent: true,
      ok: { label: `${VERB[action].split(' ')[0]} ${ids.length}`, color: action === ReviewAction.delete ? 'negative' : 'primary', flat: false }
    }).onOk(() => resolve(true)).onCancel(() => resolve(false)).onDismiss(() => resolve(false))
  })
}

/** Shows the review's effect: the listed rows it touched are read again where they are (#690),
 * at their current state, also those out of the filters now; deleted and missing ones leave the
 * page and the selection. Resolves when the rows have been read. */
function afterReview (report: ReviewReport) {
  const gone = report.action === ReviewAction.delete ? [...report.saved, ...report.missing] : report.missing
  if (gone.length) selection.remove(gone)
  const loading = store.refreshRows([
    ...report.saved, ...report.missing, ...report.failed.map(f => f.id), ...report.conflicts.map(c => c.id)
  ])
  void store.loadShown()
  if (report.action !== ReviewAction.approve) void store.loadDocuments()
  // The counts of the filter menus follow a review that changed (or may have changed) annotations,
  // once per review, whether or not they are on this page (#667).
  if (report.saved.length || report.missing.length || report.failed.length) void store.loadFacets()
  return loading
}

/** Annotations whose review is being saved; their rows show a spinner (#690). */
const savingIds = ref<Set<string>>(new Set())

async function saving<T> (ids: Iterable<string>, write: () => Promise<T>): Promise<T> {
  savingIds.value = new Set(ids)
  try {
    return await write()
  } finally {
    savingIds.value = new Set()
  }
}

async function runReview (action: ReviewAction, items: SelectionEntry[], tagId?: string) {
  const id = collectionId.value
  if (!id || !items.length || !await confirmed(action, items.map(([i]) => i), tagId)) return null
  assign.dismiss()
  const report = await saving(items.map(([i]) => i), () => review.review(id, action, items, tagId ?? null))
  return report ? { report, loaded: afterReview(report) } : null
}

async function reviewSelection (action: ReviewAction, tagId?: string) {
  await runReview(action, [...selection.ids].map(i => [i, selection.versionOf(i)] as const), tagId)
}

/** Selects the annotations someone else changed meanwhile, at their current versions, to
 * look at them and review them again (#460). */
function showChanged () {
  const conflicts = review.report?.conflicts ?? []
  if (!conflicts.length) return
  selection.replace(conflicts.map(c => [c.id, c.version] as const))
  review.dismiss()
  void store.loadShown()
}

async function retryReview () {
  const id = collectionId.value
  if (!id) return
  const report = await saving(review.report?.failed.map(f => f.id) ?? [], () => review.retry(id))
  if (report) void afterReview(report)
}

/** A review or boundary edit of the open annotation refused because someone else changed it
 * meanwhile (#460). */
const focusedConflict = ref<{ id: string, action: ReviewAction | 'boundary', tagId?: string } | null>(null)

const conflictText = computed(() => {
  const row = selection.focused
  const conflict = focusedConflict.value
  if (!row || !conflict || row.id !== conflict.id) return ''
  const p = row.provenance
  const who = personName(p?.lastEditedBy, store.people, userStore.getUserId)
  const when = formatWhen(p?.lastEditedAt)
  const by = who === 'you' ? 'Changed in another window' : `Changed by ${who}`
  const now = `now ${statusText.value.toLowerCase()}, tag "${focusedTag.value?.name ?? 'unknown'}"`
  const away = !store.rows.some(r => r.id === row.id)
    ? ' It is no longer on this page.'
    : store.unmatched.has(row.id) ? ' It no longer matches the filters.' : ''
  const yours = conflict.action === 'boundary' ? 'boundary change' : VERB[conflict.action].toLowerCase()
  return `${by}${when ? ` at ${when}` : ''}: ${now}. Your ${yours} was not saved.${away}`
})

/** The sidebar control whose review is being saved; it shows a spinner (#690). */
const savingAction = ref<ReviewAction | null>(null)

/** Confirms or rejects the open annotation. Choosing the state it has writes nothing and only
 * goes on to the next row (#690). */
async function decide (action: typeof ReviewAction.approve | typeof ReviewAction.reject) {
  const row = selection.focused
  if (!row || selection.focusedGone || decisionDisabled.value || editingBoundary.value) return
  if (row.type === (action === ReviewAction.approve ? SpanType.pos : SpanType.neg)) {
    await advance(action === ReviewAction.approve ? 'Already confirmed.' : 'Already rejected.')
    return
  }
  savingAction.value = action
  try {
    await reviewFocused(action)
  } finally {
    savingAction.value = null
  }
}

/** Reviews the open annotation; approving or rejecting it moves on to the next row, also on
 * the next page. A conflict or failure does not move on. */
async function reviewFocused (action: ReviewAction, tagId?: string) {
  const row = selection.focused
  if (!row) return
  focusedConflict.value = null
  const reviewed = await runReview(action, [[row.id, row.editVersion ?? 0]], tagId)
  if (!reviewed) return
  const { report } = reviewed
  if (report.conflicts.length) {
    // The page is read again (afterReview): the sidebar shows the current annotation and
    // says what happened; the selection's result line has nothing to add.
    focusedConflict.value = { id: row.id, action, tagId }
    review.dismiss()
    await reviewed.loaded
    // A change that took it out of the filters must not hide the conflict: read it as it is now.
    if (selection.focusedGone && focusedConflict.value?.id === row.id && await store.readFocused()) {
      const current = selection.focused
      if (current && current.chunkId !== chunkContext.target?.chunkId) void showContext(current)
    }
    return
  }
  const ok = report.saved.length === 1
  if (!ok) {
    $q.notify({ type: 'warning', message: report.missing.length ? 'This annotation no longer exists.' : 'The change was not saved; see the result above the list.' })
    return
  }
  if ((action !== ReviewAction.approve && action !== ReviewAction.reject) || selection.focused?.id !== row.id) return
  // The next page starts after the rows that left the result: known once they are read again.
  if (!store.rows[focusedIndex.value + 1]) await reviewed.loaded
  if (selection.focused?.id !== row.id) return
  quietDecision()
  await advance(action === ReviewAction.approve ? 'Confirmed.' : 'Rejected.')
}

/**
 * A saved decision of one annotation (sidebar or row, #690) adds no lines above the list, which
 * would move it: the row shows its new state and the live region says it. It is changed back by
 * choosing the other state, so it leaves no Undo either. Batch reviews, failures and conflicts
 * still report there.
 */
function quietDecision () {
  review.dismiss()
  review.noteChange(null)
}

/**
 * After a decision: opens the next row when it is a proposal still to review (#690 review). A
 * next row already confirmed or rejected means the user is going back over decided ones: the
 * sidebar stays, instead of jumping to an annotation already settled. At the end of a page the
 * next page is read and its first row opened (its state is not known before).
 */
async function advance (said: string) {
  const next = store.rows[focusedIndex.value + 1]
  if (next && next.type !== SpanType.auto) {
    announcement.value = `${said} The next annotation is already reviewed; staying here.`
    return
  }
  announce(said, await step(1))
}

/**
 * A decision made in a row of the list (#690 phase B): its buttons or Alt+C / Alt+R on the
 * focused row. It acts on that row only, at the version the row shows, through the same review
 * as the sidebar; the sidebar does not move. Resolves whether the row is now in that state (the
 * state in effect writes nothing). A conflict opens the row in the sidebar with its conflict; a
 * failure shows the result line with Retry.
 */
async function reviewRow (row: AnnotationListRow, action: RowDecision): Promise<boolean> {
  if (review.running || savingBoundary.value || (editingBoundary.value && selection.focused?.id === row.id)) return false
  const reviewAction = action === 'approve' ? ReviewAction.approve : ReviewAction.reject
  const done = action === 'approve' ? 'Confirmed.' : 'Rejected.'
  if (row.type === (action === 'approve' ? SpanType.pos : SpanType.neg)) {
    announce(action === 'approve' ? 'Already confirmed.' : 'Already rejected.', row)
    return true
  }
  if (selection.focused?.id === row.id) focusedConflict.value = null
  const reviewed = await runReview(reviewAction, [[row.id, row.editVersion ?? 0]])
  if (!reviewed) return false
  const { report } = reviewed
  if (report.conflicts.length) {
    review.dismiss()
    await reviewed.loaded
    await openContext(store.rows.find(r => r.id === row.id) ?? row)
    focusedConflict.value = { id: row.id, action: reviewAction }
    return false
  }
  if (report.saved.length !== 1) return false
  quietDecision()
  await reviewed.loaded
  announce(done, store.rows.find(r => r.id === row.id) ?? row)
  return true
}

/** Opens the first row of the next page or the last one of the previous page, from the list's
 * keys at the page's end (#690); the row opened, or null. */
async function stepPage (direction: 1 | -1): Promise<AnnotationListRow | null> {
  if (store.loading || (direction > 0 ? !store.hasNextPage : store.offset <= 0)) {
    if (direction > 0) announcement.value = 'Last annotation.'
    return null
  }
  await store.goTo(direction > 0 ? store.nextOffset : Math.max(0, store.offset - PAGE_SIZE))
  const row = (direction > 0 ? store.rows[0] : store.rows[store.rows.length - 1]) ?? null
  if (row) void openContext(row)
  announce('', row)
  return row
}

/** Repeats the refused review or boundary edit against the version the sidebar shows now. */
async function applyToCurrent () {
  const conflict = focusedConflict.value
  if (!conflict || selection.focused?.id !== conflict.id) return
  if (conflict.action === 'boundary') await saveBoundary()
  else await reviewFocused(conflict.action, conflict.tagId)
}

/** Keeps the annotation as someone else changed it, dropping the refused change. */
function keepCurrent () {
  if (focusedConflict.value?.action === 'boundary') cancelBoundary()
  focusedConflict.value = null
}

// ── Boundary editing (#461) ──
/** The range being edited for the annotation `id`; `range` is not saved yet. */
const boundary = ref<{ id: string, range: BoundaryRange } | null>(null)
const boundaryUnit = ref<BoundaryUnit>('word')
const boundaryNote = ref<string | null>(null)
const savingBoundary = ref(false)
const boundaryEditor = ref<InstanceType<typeof BoundaryEditor> | null>(null)
const editBoundaryButton = ref<InstanceType<typeof QBtn> | null>(null)

/** The range of the open annotation as saved. */
const focusedRange = computed<BoundaryRange | null>(() => {
  const row = selection.focusedGone ? null : selection.focused
  return row?.chunkId && row.start != null && row.end != null
    ? { chunkId: row.chunkId, start: row.start, end: row.end }
    : null
})
const editingBoundary = computed(() => !!boundary.value && boundary.value.id === selection.focused?.id &&
  !selection.focusedGone)
// Its anchor chunk must be loaded, to edit it in the passage shown.
const canEditBoundary = computed(() => {
  const range = focusedRange.value
  return !!range && chunkContext.chunks.some(c => c.id === range.chunkId)
})
const boundaryText = computed(() => boundary.value ? rangeText(chunkContext.chunks, boundary.value.range) : '')
const boundaryChanged = computed(() => !!boundary.value && !!focusedRange.value &&
  !sameRange(boundary.value.range, focusedRange.value))

async function editBoundary () {
  const row = selection.focused
  const range = focusedRange.value
  if (!row || !range || !canEditBoundary.value) return
  boundary.value = { id: row.id, range }
  boundaryNote.value = null
  await nextTick()
  boundaryEditor.value?.$el?.querySelector?.('button')?.focus()
}

async function cancelBoundary () {
  boundary.value = null
  boundaryNote.value = null
  await nextTick()
  editBoundaryButton.value?.$el?.focus?.()
}

function stepEdited (handle: BoundaryHandle, direction: -1 | 1) {
  const b = boundary.value
  if (!b) return
  const next = stepBoundary(chunkContext.chunks, b.range, handle, direction, boundaryUnit.value)
  if (!next) {
    boundaryNote.value = `The ${handle} cannot move further: the start stays before the end, within the text ` +
      'shown (show earlier or later text to go further).'
    return
  }
  b.range = next
  boundaryNote.value = null
}

function useSelectedText () {
  const b = boundary.value
  if (!b) return
  const selected = panel.value?.textSelection() ?? null
  const range = selected ? rangeBetween(chunkContext.chunks, selected[0], selected[1]) : null
  if (!range) {
    boundaryNote.value = selected
      ? 'The selection must be within one continuous part of the document.'
      : 'Select the new text in the passage first.'
    return
  }
  b.range = range
  boundaryNote.value = null
}

/** The page read again after a change of the open annotation; it stays open, also when the
 * change took it out of the filters, and its passage follows it to another chunk. */
async function followFocused () {
  const loading = store.load()
  void store.loadShown()
  await loading
  if (selection.focusedGone) await store.readFocused()
  const current = selection.focusedGone ? null : selection.focused
  if (current?.chunkId && !chunkContext.chunks.some(c => c.id === current.chunkId)) void showContext(current)
}

/**
 * Saves the edited range of the open annotation at the version shown (#460): a start in
 * another chunk moves the annotation there (#436). The edit becomes the change to undo,
 * from the range the annotation had at that version. A conflict keeps the editor open
 * with the current annotation shown, to save against it or keep it.
 */
async function saveBoundary () {
  const row = selection.focused
  const b = boundary.value
  const saved = focusedRange.value
  const id = collectionId.value
  if (!row || !b || !saved || b.id !== row.id || !id || savingBoundary.value || sameRange(b.range, saved)) return
  const inScope = selection.captureScope()
  const inSession = captureSession()
  const applies = () => inScope() && inSession() && selection.focused?.id === row.id
  savingBoundary.value = true
  focusedConflict.value = null
  try {
    const result = await spansRepo.update(row.id, id, {
      start: b.range.start,
      end: b.range.end,
      ...(b.range.chunkId !== saved.chunkId ? { chunkId: b.range.chunkId } : {})
    }, row.editVersion ?? 0)
    const warning = spanWriteWarning(result, 'saved')
    if (warning) warningNotification(warning)
    if (!inScope() || !inSession()) return
    const version = result.editVersion ?? 0
    selection.noteVersions({ [row.id]: version })
    review.noteChange({
      kind: 'boundary',
      items: [{
        id: row.id,
        version,
        values: { start: saved.start, end: saved.end, ...(result.chunkId !== saved.chunkId ? { chunkId: saved.chunkId } : {}) }
      }]
    })
    void store.loadFacets() // the text, and so the words filter's counts, may have changed
    if (boundary.value === b) boundary.value = null
    await followFocused()
    if (applies() && !boundary.value) await cancelBoundary()
  } catch (e) {
    if (!applies()) return
    const status = errorStatus(e)
    if (status === 409) {
      focusedConflict.value = { id: row.id, action: 'boundary' }
      await followFocused()
    } else if (status === 404) {
      boundary.value = null
      $q.notify({ type: 'warning', message: 'This annotation no longer exists.' })
      await followFocused()
    } else {
      $q.notify({ type: 'negative', message: await apiErrorMessage(e, 'The boundaries could not be saved.') })
    }
  } finally {
    savingBoundary.value = false
  }
}

// ── Undo (#461) ──
async function undoLast () {
  const id = collectionId.value
  if (!id) return
  focusedConflict.value = null
  const report = await saving(review.undoable?.items.map(i => i.id) ?? [], () => review.undo(id))
  if (!report) return
  await afterReview(report)
  const current = selection.focusedGone ? null : selection.focused
  if (current?.chunkId && !chunkContext.chunks.some(c => c.id === current.chunkId)) void showContext(current)
}

// ── Attribute assignment (#331) ──
/** The attributes shown in columns of their own, in the collection's order (#537). */
const shownAttributes = computed(() => {
  const ids = new Set(store.shownAttributeIds)
  return attributesStore.attributes.filter(a => ids.has(a.id))
})
const assignReportAttribute = computed(() =>
  attributesStore.attributes.find(a => a.id === assign.report?.attributeId) ?? null)
// While a selection's assignment runs, rows wait too: its later parts expect the versions the
// selection had when it started.
const assignWaiting = computed(() => assign.running ? new Set(store.rows.map(r => r.id)) : assign.pending)
const filtersByAttribute = computed(() =>
  store.filters.attributeValues.length > 0 || store.filters.attributeUnassigned.length > 0)

/** Rows and the open annotation take what the server answered, never their own copy. */
const answered = (attributeId: string) => (result: AttributeAssignResult) => store.applyAssignment(attributeId, result)

/** An assignment that changed something, or may have (a lost write), is the last change,
 * which cannot be undone (yet): the undo line no longer offers the change before it. One that
 * found every annotation already as asked changed nothing and keeps it (#569). */
function noteAssigned (changed: number) {
  if (changed && (review.undoable || review.undoNote)) review.noteChange(null, 'Attribute assignments cannot be undone.')
  // The attribute menu's counts follow an assignment that changed something, once per assignment (#667).
  if (changed) void store.loadFacets()
}

/** Assigns values to one annotation (a row's column or the sidebar), at the attribute version
 * it shows; at most one at a time per annotation. True when it was saved (its picker may close). */
async function assignRow (row: AnnotationListRow, attribute: Attribute, change: AssignChange): Promise<boolean> {
  const id = collectionId.value
  if (!id) return false
  const report = await assign.assignOne(id, attribute.id, change, [row.id, row.attributeVersion ?? 0], answered(attribute.id))
  if (!report) return false
  noteAssigned(assignMayHaveChanged(report))
  if (report.missing.length) selection.remove(report.missing)
  const problem = report.conflicts.length
    ? 'Someone else changed this annotation\'s attributes meanwhile; it now shows them. Your change was not saved.'
    : report.refused[0]?.message ?? report.failed[0]?.message ??
      (report.missing.length ? 'This annotation no longer exists.' : null)
  if (problem) $q.notify({ type: 'warning', message: problem })
  else if (report.unrecorded.length) $q.notify({ type: 'warning', message: 'Saved, but the change history could not be recorded.' })
  // Its values decide whether it still matches attribute filters.
  if (filtersByAttribute.value || report.missing.length) await followFocused()
  return report.saved.includes(row.id)
}

/** Reads the page again after a selection's assignment; missing members leave the selection. */
function afterAssign (report: { missing: string[] }) {
  if (report.missing.length) selection.remove(report.missing)
  if (filtersByAttribute.value || report.missing.length) {
    void store.load()
    void store.loadShown()
  }
}

function assignSelection () {
  const id = collectionId.value
  if (!id || !selection.size) return
  const targets = [...selection.ids].map(i => [i, selection.attributeVersionOf(i)] as const)
  const offPage = targets.filter(([i]) => !store.rows.some(r => r.id === i)).length
  $q.dialog({
    component: AssignAttributeDialog,
    componentProps: {
      attributes: attributesStore.attributes.filter(a => !a.retired),
      tags: tags.value,
      count: targets.length,
      offPage,
      progress: () => assign.progress,
      save: async (attributeId: string, change: AssignChange) => {
        review.dismiss()
        const report = await assign.assign(id, attributeId, change, targets, answered(attributeId))
        if (report) {
          noteAssigned(assignMayHaveChanged(report))
          afterAssign(report)
        }
        return report
      }
    }
  })
}

async function retryAssign () {
  const id = collectionId.value
  const attributeId = assign.report?.attributeId
  if (!id || !attributeId) return
  const report = await assign.retry(id, answered(attributeId))
  if (report) {
    noteAssigned(assignMayHaveChanged(report))
    afterAssign(report)
  }
}

/** Selects the annotations someone else changed meanwhile, at their current attribute
 * versions, to look at them and assign again. */
function showChangedAssign () {
  const conflicts = assign.report?.conflicts ?? []
  if (!conflicts.length) return
  selection.replace(conflicts.map(([i]) => [i, selection.versionOf(i)] as const), Object.fromEntries(conflicts))
  assign.dismiss()
  void store.loadShown()
}

/**
 * Review shortcuts of the sidebar (#690): Alt+C confirms, Alt+R rejects the open annotation,
 * Alt+↓ / Alt+↑ open the next / previous one. Matched by `event.code` (macOS Option+C types
 * "ç"). Tab stays native. Ignored in fields, menus and dialogs, in the list's grid (which has
 * the same keys for its focused row), while a write is saved and while boundaries are edited.
 */
const SHORTCUTS: Record<string, 'approve' | 'reject' | 'next' | 'previous'> = {
  KeyC: 'approve', KeyR: 'reject', ArrowDown: 'next', ArrowUp: 'previous'
}

function onReviewShortcut (event: KeyboardEvent) {
  if (statisticsView.value) return
  if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.defaultPrevented) return
  const shortcut = SHORTCUTS[event.code]
  if (!shortcut || !selection.focused || !rightSidebar.open || rightSidebar.activePanelId !== CONTEXT_PANEL_ID) return
  const target = event.target as HTMLElement | null
  if (target?.closest('input, textarea, select, [contenteditable="true"], [role="listbox"], [role="menu"], [role="grid"], .q-field, .q-menu, .q-dialog')) return
  if (document.querySelector('.q-menu, .q-dialog')) return
  event.preventDefault()
  if (event.repeat && (shortcut === 'approve' || shortcut === 'reject')) return
  if (review.running || savingBoundary.value || editingBoundary.value) return
  if (shortcut === 'approve') void decide(ReviewAction.approve)
  else if (shortcut === 'reject') void decide(ReviewAction.reject)
  else void stepAndAnnounce(shortcut === 'next' ? 1 : -1)
}
onMounted(() => window.addEventListener('keydown', onReviewShortcut))
onBeforeUnmount(() => window.removeEventListener('keydown', onReviewShortcut))

// ── Workspace state across navigation ──
onBeforeRouteLeave(() => {
  store.scrollY = window.scrollY
})

// The attribute facets follow the collection's attributes (#667); read again when they arrive.
watch(() => attributesStore.attributes.map(a => a.id).join(','), () => {
  store.facetAttributeIds = attributesStore.attributes.map(a => a.id)
  if (store.collectionId) void store.loadFacets()
})

watch(collectionId, async (id) => {
  if (!id) return
  chunkContext.clear()
  const returning = store.collectionId === id && !!store.page
  void tagsStore.fetchTagsByCollection(id)
  void attributesStore.load(id)
  const loading = store.open(id)
  if (returning) {
    // Back from a document: the same place, then the rows as they are now.
    await nextTick()
    window.scrollTo(0, store.scrollY)
    if (selection.focused) void showContext(selection.focused)
  }
  await loading
  // A boundary edit may have moved the annotation to another chunk.
  const row = selection.focused
  if (returning && row && !selection.focusedGone && row.chunkId && row.chunkId !== chunkContext.target?.chunkId) {
    void showContext(row)
  }
}, { immediate: true })
</script>

<style scoped>
.collection-annotations__view {
  border: 1px solid var(--q-primary);
}

.collection-annotations__view :deep(.q-btn) {
  padding: 0 12px;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.collection-annotations__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  min-height: 36px;
  font-size: 0.85rem;
  color: rgba(0, 0, 0, 0.72);
}

.collection-annotations__unmatched {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.collection-annotations__state {
  padding: 24px 0;
}

.collection-annotations__stale {
  opacity: 0.55;
  transition: opacity 0.2s;
}

.annotation-context {
  margin-bottom: 4px;
}

.annotation-context__main {
  padding-bottom: 6px;
}

.annotation-context__head {
  display: flex;
  align-items: center;
  gap: 4px 8px;
  margin-bottom: 8px;
}

.annotation-context__head > :first-child {
  min-width: 0;
}

.annotation-context__nav {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 2px;
  margin-left: auto;
}

.annotation-context__position {
  min-width: 4.5em;
  text-align: center;
  font-variant-numeric: tabular-nums;
  color: rgba(0, 0, 0, 0.72);
}

.annotation-context__delete {
  margin-left: auto;
}

.annotation-context__quote {
  position: relative;
  margin-top: 6px;
}

.annotation-context__quote--foldable {
  cursor: pointer;
}

.annotation-context__text {
  margin: 0;
  padding: 4px 28px 4px 8px;
  border-left: 3px solid #ffd54f;
  background: #fffbe6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  overflow: hidden;
  transition: max-height 0.2s ease;
}

/* Unfolded, a very long text scrolls (its height is capped in `textStyle`). */
.annotation-context__text--expanded {
  overflow-y: auto;
}

.annotation-context__ellipsis {
  position: absolute;
  right: 28px;
  bottom: 4px;
  padding-left: 24px;
  background: linear-gradient(to right, rgba(255, 251, 230, 0), #fffbe6 18px);
  color: var(--q-primary);
  font-weight: 700;
  line-height: 1.25rem;
}

.annotation-context__fold {
  position: absolute;
  top: 2px;
  right: 2px;
  transition: transform 0.2s ease;
}

.annotation-context__fold--open {
  transform: rotate(180deg);
}

@media (prefers-reduced-motion: reduce) {
  .annotation-context__text,
  .annotation-context__fold {
    transition: none;
  }
}

.annotation-context__gone {
  margin: 6px 0 0;
  padding: 4px 8px;
  border-left: 3px solid #bdbdbd;
}

.annotation-context__review {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.annotation-context__decision {
  flex: 1 1 0;
  min-width: 0;
  min-height: 40px;
  padding: 0 6px;
}

.annotation-context__decision :deep(.q-btn__content) {
  flex-wrap: nowrap;
  white-space: nowrap;
}

.annotation-context__decision :deep(.q-icon.on-left) {
  margin-right: 6px;
}

.annotation-context__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin: 4px 0 0 -6px;
}

/* Attributes and origin can be long: capped, so the passage keeps room on short screens. */
.annotation-context__details {
  max-height: 18vh;
  overflow-y: auto;
  padding-top: 6px;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
}

.annotation-context__origin {
  margin-top: 6px;
}

.annotation-context__title {
  font-weight: 600;
  color: rgba(0, 0, 0, 0.7);
  margin-bottom: 2px;
}

.annotation-context__conflict {
  margin: 6px 0;
  padding: 4px 8px;
  border-left: 3px solid var(--q-warning);
  background: rgba(242, 192, 55, 0.12);
}

.annotation-context__conflict-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 6px;
  margin-top: 4px;
}
</style>
