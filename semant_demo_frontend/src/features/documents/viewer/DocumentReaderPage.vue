<template>
  <!-- The reader fills the document view under its header; only its panes scroll (#600). -->
  <q-page class="doc-page" :style-fn="fillHeight">
    <!-- Fixed above the panes: the reader's view options, a notice (in the row: it never
         moves the text) and, for a document with scans, the view toggle. -->
    <WorkspaceControls
      :mode="workspace.shown.value"
      :narrow="workspace.narrow.value"
      :has-scan="workspace.hasScan.value"
      :notice="scanSync.sync.notice.value"
      @update:mode="chooseMode"
    >
      <ReaderToolbar
        v-model:chunk-gutter-visible="chunkGutterVisible"
        v-model:preserve-whitespace="preserveWhitespace"
        :collection-only="chunkWindow.displayedPreviewCount.value === 0"
        :all-chunks="chunkWindow.allChunksShown.value"
        :loading-all="chunkWindow.loadingAllChunks.value"
        :focused-tag="focusedTag"
        @show-collection-only="chunkWindow.hideAllPreviews"
        @show-all-chunks="chunkWindow.loadAllChunks"
        @clear-focused-tag="tagNav.setFocusedTagId(null)"
      />
    </WorkspaceControls>
    <!-- The text (gutters, annotated text) and, for a document with scans, the page scan
         beside it (#545). -->
    <DocumentWorkspace
      ref="workspacePane"
      v-model:narrow="workspace.narrow.value"
      :document-id="documentId"
      :mode="workspace.shown.value"
      :page-id="scanPageId"
      :highlights="scanSync.sync.scanHighlights.value"
      :layout-cache="scanSync.layouts.value"
      @navigate="onScanNavigate"
      @page-change="onScanPage"
      @loaded="onScanLoaded"
      @line-select="scanSync.sync.showLineInText"
      @line-focus="scanSync.sync.showLineInText"
    >
    <div class="page-shell">
      <ChunkMembershipGutter
        v-if="chunkGutterVisible"
        :rows="gutters.chunkRows.value"
        :chunks="displayChunks"
        :selected-ids="membership.selectedChunkIds.value"
        :text-hovered-chunk-id="hoveredChunkId"
        :can-edit-membership="rights.editMembership"
        :loading-chunk-id="membership.chunkLoadingId.value"
        :total-chunks="totalDocumentChunks"
        @hover="onChunkGutterHover"
        @toggle-select="membership.toggleChunkSelection"
        @add="membership.addChunk"
        @remove="membership.removeChunk"
        @hide="chunkWindow.hideChunk"
      />

      <AnnotationGutter
        v-if="gutters.spanMarkers.value.length"
        :markers="gutters.spanMarkers.value"
        :tags="tags"
        :hovered-span-id="hoveredSpanId || navHighlightedSpanId"
        :highlighted-span-id="highlightedAutoSpanId"
        :focused-tag-id="tagNav.focusedTagId.value"
        @hover="hoveredSpanId = $event"
        @select="onMarkerClick"
      />

      <q-card class="paper-card" :class="{ 'has-gutter': gutters.spanMarkers.value.length > 0 }">
        <q-card-section class="paper-body">
          <!-- Expand previous — right above the text -->
          <div v-if="chunkWindow.hasPrev.value" class="expand-row expand-row--top expand-row--col">
            <q-btn
              flat dense
              icon="vertical_align_top"
              :loading="chunkWindow.loadingAllPrev.value"
              class="expand-btn"
              label="Load all previous"
              @click="chunkWindow.loadAllNeighbours('prev')"
            />
            <q-btn
              flat dense
              icon="keyboard_arrow_up"
              :loading="chunkWindow.loadingPrev.value"
              class="expand-btn"
              label="Load previous"
              @click="chunkWindow.loadNeighbour('prev')"
            />
          </div>

          <DocumentTextPane
            ref="textPane"
            :chunks="displayChunks"
            :preserve-whitespace="preserveWhitespace"
            :annotation="textAnnotation"
            :chunk-class="chunkClass"
            :active-range="scanSync.sync.textFocus.value?.range ?? null"
            :active-approximate="!!scanSync.sync.textFocus.value?.approximate"
            :page-marks="scanSync.sync.pageMarks.value"
            :reveal-inset="READER_COVERED_TOP"
            @pointerdown="onDocumentPointerDown"
            @pointermove="onDocumentPointerMove"
            @pointerleave="onDocumentPointerLeave"
            @select="onTextSelect"
            @text-click="onTextClick"
            @boundary-drag="onBoundaryDrag"
          >
            <!-- Divider at a gap between non-consecutive chunks -->
            <template #gap="{ paragraph: group }">
              <div class="gap-row">
                <span class="gap-label">
                  <q-icon name="warning_amber" size="16px" />
                  {{ missingChunksText(gapSize(group)) }}
                </span>
                <span v-if="annotationCutAt(group)" class="gap-label gap-label--cut" data-testid="gap-annotation-cut">
                  An annotation continues in the missing text; load it to see all of it.
                </span>
                <q-btn
                  flat dense no-caps
                  icon="keyboard_arrow_down"
                  :loading="chunkWindow.gapLoadingKey.value === `${group.gapAfter}:next`"
                  class="gap-btn"
                  label="Load next"
                  title="Load the chunk just after this gap"
                  @click="chunkWindow.loadGap(group.gapAfter!)"
                />
                <q-btn
                  flat dense no-caps
                  icon="unfold_more"
                  :loading="chunkWindow.gapLoadingKey.value === `${group.gapAfter}:all`"
                  class="gap-btn gap-btn--all"
                  label="Load all missing"
                  title="Load all chunks in this gap"
                  @click="chunkWindow.loadGapAll(group.gapAfter!, group.gapBefore!)"
                />
                <q-btn
                  flat dense no-caps
                  icon="keyboard_arrow_up"
                  :loading="chunkWindow.gapLoadingKey.value === `${group.gapBefore}:prev`"
                  class="gap-btn"
                  label="Load previous"
                  title="Load the chunk just before this gap"
                  @click="chunkWindow.loadGapPrev(group.gapBefore!)"
                />
              </div>
            </template>
          </DocumentTextPane>

          <!-- Expand next — right below the text -->
          <div v-if="chunkWindow.hasNext.value" class="expand-row expand-row--bottom expand-row--col">
            <q-btn
              flat dense
              icon="keyboard_arrow_down"
              :loading="chunkWindow.loadingNext.value"
              class="expand-btn"
              label="Load next"
              @click="chunkWindow.loadNeighbour('next')"
            />
            <q-btn
              flat dense
              icon="vertical_align_bottom"
              :loading="chunkWindow.loadingAllNext.value"
              class="expand-btn"
              label="Load all next"
              @click="chunkWindow.loadAllNeighbours('next')"
            />
          </div>
        </q-card-section>
        <q-inner-loading :showing="loading" />
        <error-display v-if="error" :error="error" />
      </q-card>

      <AnnotationPopover
        ref="popoverRef"
        :visible="annotations.hasSelection.value && annotations.selection.value !== focusTaggedSelection"
        :tags="tags"
        :selection="annotations.selection.value"
        :selected-text="selectedSpanText"
        :last-used-tag-id="lastUsedTagId"
        :selected-tag-id="annotations.selection.value?.tagId ?? null"
        :is-editing="annotations.isEditing.value"
        :position-changed="annotations.positionChanged.value"
        :editing-auto="!!editingAutoSpan"
        :busy="annotations.saving.value"
        :ai-selection-running="aiAssist.isSelectionRunning.value"
        @close="annotations.clearSelection()"
        @pick-tag="onTagClick"
        @create-tag="onCreateTagClick"
        @run-ai="onRunAiOnSelection"
        @save-position="onSavePosition"
        @approve="changeEditingSpanType(SpanType.pos)"
        @reject="changeEditingSpanType(SpanType.neg)"
        @tag-details="onOpenTagDetails"
        @discuss="onDiscussSpan"
        @delete="onDeleteSpan"
      />

      <ChunkSelectionBar
        :count="membership.selectedChunkIds.value.length"
        :can-add="membership.hasSelectedNotInCollection.value && rights.editMembership"
        :can-remove="membership.hasSelectedInCollection.value && rights.editMembership"
        :loading="membership.bulkLoading.value"
        @select-visible="membership.selectAllVisible"
        @select-not-in-collection="membership.selectAllNotInCollection"
        @add="membership.addSelected"
        @remove="membership.removeSelected"
        @clear="membership.clearChunkSelection"
      />
    </div>
    </DocumentWorkspace>
  </q-page>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, ref, shallowRef, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import { SpanType, type CollectionChunk, type DocumentPage } from 'src/generated/api'
import { apiErrorMessage, createContextGuard, isAbortError } from 'src/shared/api'
import { errorNotification } from 'src/shared/notification'
import { overlayOpen } from 'src/shared/overlays'
import ErrorDisplay from 'src/shared/ui/ErrorDisplay.vue'
import AnnotationGutter from 'src/features/annotations/AnnotationGutter.vue'
import type { SpanMarker } from 'src/features/annotations/AnnotationGutterTypes'
import AnnotationPopover from 'src/features/annotations/AnnotationPopover.vue'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import useAiAssistance, { resolveAutoSpanFailure } from 'src/features/annotations/useAiAssistance'
import { useTopicerModelStore } from 'src/features/annotations/topicerModelStore'
import { useAnnotations, type ProjectedSpan } from 'src/features/annotations/useAnnotations'
import useSpanDiscussionDialog from 'src/features/annotations/useSpanDiscussionDialog'
import { useTagEditing } from 'src/features/annotations/useTagEditing'
import { useTagNavigation } from 'src/features/annotations/useTagNavigation'
import useTagSpans from 'src/features/annotations/useTagSpans'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import { collectionRights } from 'src/features/user_collections/permissions'
import { requestedCitation } from 'src/features/documents/readerCitation'
import useChunks from '../useChunks'
import ChunkMembershipGutter from './ChunkMembershipGutter.vue'
import ChunkSelectionBar from './ChunkSelectionBar.vue'
import { DOCUMENT_SIDEBAR_PANELS } from './documentSidebar'
import DocumentTextPane from './DocumentTextPane.vue'
import type { DocumentTextPaneApi, TextPaneAnnotation, TextSelection } from './documentTextPane'
import type { TextPoint } from './readerOffsets'
import ReaderToolbar from './ReaderToolbar.vue'
import { getLastUsedTagId, setLastUsedTagId } from 'src/features/annotations/lastUsedTag'
import {
  gapSize, missingChunksText, selectionInDisplayedChunks, selectionText,
  shortestMarker, memoizeVisibleSpansByChunkId
} from './readerOffsets'
import { useChunkMembership } from './useChunkMembership'
import { useChunkWindow } from './useChunkWindow'
import { useChunksRepository } from '../useChunksRepository'
import { useReaderGutters } from './useReaderGutters'
import { useReaderScanSync } from './useReaderScanSync'
import { selectionRange } from '../correspondence/layoutMap'
import DocumentWorkspace from '../workspace/DocumentWorkspace.vue'
import WorkspaceControls from '../workspace/WorkspaceControls.vue'
import { fillHeight } from '../workspace/fillHeight'
import { useWorkspaceMode } from '../workspace/useWorkspaceMode'
import { parseMode, targetKey, withMode, withScanPage, type WorkspaceMode } from '../workspace/workspaceMode'

// The collection's document reader: the text of the displayed chunks (DocumentTextPane)
// with their annotations, the chunk and span gutters, chunk membership, and annotation
// editing through the selection popover. The enclosing DocumentViewLayout loads the
// document, collection and tags.
const props = defineProps<{
  collectionId: string
  documentId: string
}>()

const $q = useQuasar()

// Shared users annotate but do not add or remove chunks (ADR 0007).
const { activeCollection } = storeToRefs(useUserCollectionsStore())
const rights = computed(() =>
  collectionRights(activeCollection.value?.id === props.collectionId ? activeCollection.value : null)
)

const { chunks, loading, error, loadChunksInCollectionDocument, countDocumentChunks } = useChunks()
const tagsStore = useTagsStore()
const { tags } = storeToRefs(tagsStore)
const tagEditing = useTagEditing(() => props.collectionId)
const tagNav = useTagNavigation()
const tagSpans = useTagSpans()
const aiAssist = useAiAssistance()
const topicerModel = useTopicerModelStore()
const rightSidebar = useRightSidebarStore()
const aiPanelActive = computed(() => aiAssist.aiPanelActive.value)
const highlightedAutoSpanId = computed(() => aiAssist.highlightedAutoSpanId.value)

const textPane = ref<DocumentTextPaneApi | null>(null)
const documentTextRef = computed(() => textPane.value?.root ?? null)
const totalDocumentChunks = ref<number | null>(null)
// Hidden on every visit; the toolbar toggle shows it.
const chunkGutterVisible = ref(false)
// Toggle between original-text whitespace (default) and HTML's collapsed
// whitespace. Original-mode preserves consecutive spaces and line breaks
// inside chunk text via CSS `white-space: pre-wrap`.
const preserveWhitespace = ref(true)

// ── Displayed chunks, membership and gutters ──
const chunkWindow = useChunkWindow(() => props.collectionId, () => props.documentId, () => relayout())
const { displayChunks, hiddenPreviewChunks } = chunkWindow
const membership = useChunkMembership(() => props.collectionId, chunkWindow, () => relayout())
const annotations = useAnnotations(() => displayChunks.value, () => hiddenPreviewChunks.value)

// The annotation a workspace link points to (#329); shown whatever its tag or type.
const linkedSpanId = ref<string | null>(null)

// Approved spans of visible tags; AI suggestions only while the AI Tagging panel is active.
const gutters = useReaderGutters(
  documentTextRef,
  displayChunks,
  (chunkId) => annotations.getAllProjectedSpans(chunkId),
  (span) => span.id === linkedSpanId.value || (
    span.type !== SpanType.neg &&
    (aiPanelActive.value || span.type !== SpanType.auto) &&
    tagNav.isTagVisible(span.tagId)
  ),
  () => chunkGutterVisible.value
)

watch(chunkGutterVisible, () => {
  void nextTick(() => gutters.relayoutChunkRows())
})

const relayout = () => gutters.relayout()

// ── Hover state shared by the text and the gutters ──
const hoveredSpanId = ref<string | null>(null)
// The span the tags panel's next/prev went to. Separate from hoveredSpanId so moving the
// pointer over the text doesn't clear it; hover only takes precedence while it lasts.
const navHighlightedSpanId = ref<string | null>(null)
const hoveredPreviewChunkId = ref<string | null>(null)
const hoveredChunkId = ref<string | null>(null)
const gutterHoveredChunkId = ref<string | null>(null)

function onDocumentPointerMove(e: PointerEvent) {
  const el = (e.target as HTMLElement).closest<HTMLElement>('[data-chunk-id]')
  const chunkId = el?.dataset.chunkId ?? null
  hoveredChunkId.value = chunkId

  const chunk = chunkId ? chunkWindow.findChunk(chunkId) : null
  hoveredPreviewChunkId.value = chunk && !chunk.inCollection ? chunk.id : null

  // Tagged text under the pointer highlights the span a click would open.
  const spanId = shortestMarker(markersAtSegment(e.target))?.spanId ?? null
  if (hoveredSpanId.value !== spanId) hoveredSpanId.value = spanId
}

function onDocumentPointerLeave() {
  hoveredPreviewChunkId.value = null
  hoveredSpanId.value = null
}

/** The markers of the shown spans covering the tagged text segment at `target`. */
function markersAtSegment(target: EventTarget | null): SpanMarker[] {
  const segment = (target as HTMLElement | null)?.closest?.<HTMLElement>('.text-segment.is-tagged')
  const chunkId = segment?.closest<HTMLElement>('[data-chunk-id]')?.dataset.chunkId
  if (!segment || !chunkId) return []
  const start = Number(segment.dataset.start)
  const end = Number(segment.dataset.end)
  const ids = new Set(getVisibleSpans(chunkId).filter((s) => s.start <= start && s.end >= end).map((s) => s.id))
  return gutters.spanMarkers.value.filter((m) => ids.has(m.spanId))
}

function onChunkGutterHover(chunkId: string | null, controls: boolean) {
  gutterHoveredChunkId.value = chunkId
  if (!controls) return
  hoveredChunkId.value = chunkId
  if (chunkId === null) hoveredPreviewChunkId.value = null
  else if (!chunkWindow.findChunk(chunkId)?.inCollection) hoveredPreviewChunkId.value = chunkId
}

// Memoized per-chunk visible-span lists for ChunkAnnotator's `:spans` prop.
// Must NOT depend on `annotations.selection` (which changes on every
// boundary-drag pointermove) — otherwise every visible chunk gets a new
// array identity each drag tick, forcing a full re-render/flicker across
// the whole document instead of just the chunk being dragged.
let previousVisibleSpansByChunkId: Record<string, ProjectedSpan[]> = {}

const visibleSpansByChunkId = computed<Record<string, ProjectedSpan[]>>(() => {
  const next = memoizeVisibleSpansByChunkId(
    displayChunks.value,
    (chunkId) => annotations.getProjectedSpans(chunkId),
    (span) => span.id === linkedSpanId.value || (
      tagNav.isTagVisible(span.tagId) &&
      (aiPanelActive.value || span.type !== SpanType.auto)
    ),
    previousVisibleSpansByChunkId
  )

  previousVisibleSpansByChunkId = next
  return next
})

function getVisibleSpans(chunkId: string): ProjectedSpan[] {
  return visibleSpansByChunkId.value[chunkId] ?? []
}

// What the text pane shows of the annotations.
const textAnnotation = computed<TextPaneAnnotation>(() => ({
  tags: tags.value,
  spansFor: getVisibleSpans,
  selectionFor: (chunkId) => annotations.getLocalSelection(chunkId),
  highlightSpanId: hoveredSpanId.value || navHighlightedSpanId.value || highlightedAutoSpanId.value,
  focusTagId: tagNav.focusedTagId.value
}))

const chunkClass = (chunk: CollectionChunk) => ({
  'chunk-preview': !chunk.inCollection,
  'chunk-preview--active': !chunk.inCollection && hoveredPreviewChunkId.value === chunk.id,
  'chunk-gutter-hovered': gutterHoveredChunkId.value === chunk.id
})

// ── Scrolling the text to a span ──
function scrollToSpan(chunkId: string, start: number, end: number) {
  textPane.value?.scrollToRange({ chunkId, start, end })
}

// A document-summary citation (#249) is whole-chunk granularity, with no offset within the
// chunk to find a text segment for, so this scrolls to the chunk itself.
function scrollToChunk(chunkId: string) {
  textPane.value?.scrollToChunk(chunkId)
}

// ── Per-tag navigation (shared with the tags panel via composable) ──
watch(gutters.spanMarkers, (markers) => {
  tagNav.setItems(markers.map(i => ({
    spanId: i.spanId,
    chunkId: i.chunkId,
    tagId: i.tagId,
    start: i.start,
    end: i.end
  })))
})
tagNav.onScroll((item) => scrollToSpan(item.chunkId, item.start, item.end))
tagNav.onHighlight((spanId) => { navHighlightedSpanId.value = spanId })

// Re-render gutter (and re-filter auto spans in text) when the AI Tagging panel
// becomes active or inactive in the sidebar.
watch(aiPanelActive, () => {
  void nextTick(() => relayout())
})

// When the AI panel highlights a suggestion, scroll the document text to it.
watch(highlightedAutoSpanId, (spanId) => {
  if (!spanId || !documentTextRef.value) return
  for (const chunkId of Object.keys(tagSpans.spansByChunkId.value)) {
    const span = (tagSpans.spansByChunkId.value[chunkId] || []).find(s => s.id === spanId)
    if (!span) continue
    scrollToSpan(chunkId, span.start, span.end)
    return
  }
})

// A clicked citation in the document Summary or Chat panel (siblings of this route inside
// DocumentViewLayout) scrolls the reader to the cited chunk, loading it into the displayed
// window first (chunkWindow.loadUntil, #249 review) if it isn't shown yet — a citation can
// point anywhere in the document, but the reader only displays a bounded window by default. This
// is otherwise an orthogonal, read-only navigation action: it must not touch
// annotations/tagEditing state (no selection clearing, no popover changes, no span
// highlight changes) or navigate, only scroll/load — so tag-editing state in progress is left
// exactly as it was.
watch(requestedCitation, async (citation) => {
  if (!citation) return
  if (!chunkWindow.findChunk(citation.chunkId) && citation.order != null) {
    // A citation always refers to a chunk that exists (it came from the document's own
    // chunks); if its order can't be resolved into the window either, there is nothing more
    // to try and scrollToChunk below silently finds nothing (a narrow, documented fallback).
    await chunkWindow.loadUntil(citation.order)
  }
  scrollToChunk(citation.chunkId)
  if (chunkWindow.findChunk(citation.chunkId)) showOnScan(citation.chunkId, 0, 0)
})

// A link from the annotation workspace (#329): `?annotation=&chunk=&order=` brings that
// annotation into view and marks it, also when its tag is hidden or it is a proposal
// outside AI Tagging, loading the chunks up to it first (`order` is resolved from the
// chunk when the link has none). Once per link.
const route = useRoute()
const chunksRepository = useChunksRepository()
let linkedAnnotationShown: string | null = null
async function linkedChunkOrder(chunk: string, order: unknown): Promise<number | null> {
  const given = typeof order === 'string' ? Number(order) : Number.NaN
  if (Number.isInteger(given)) return given
  try {
    return await chunksRepository.getChunkOrder(props.documentId, chunk)
  } catch (e) {
    console.error('Resolving the linked annotation\'s chunk failed', e)
    return null
  }
}
async function showLinkedAnnotation() {
  const { annotation, chunk, order } = route.query
  if (typeof annotation !== 'string' || typeof chunk !== 'string' || linkedAnnotationShown === annotation) return
  linkedAnnotationShown = annotation
  if (!chunkWindow.findChunk(chunk)) {
    const chunkOrder = await linkedChunkOrder(chunk, order)
    if (chunkOrder != null) await chunkWindow.loadUntil(chunkOrder)
  }
  let span = (tagSpans.spansByChunkId.value[chunk] || []).find(s => s.id === annotation)
  if (!span && chunkWindow.findChunk(chunk)) {
    await annotations.refreshChunkSpans(chunk, props.collectionId)
    span = (tagSpans.spansByChunkId.value[chunk] || []).find(s => s.id === annotation)
  }
  if (!span) return
  linkedSpanId.value = annotation
  await nextTick()
  relayout()
  navHighlightedSpanId.value = annotation
  scrollToSpan(chunk, span.start, span.end)
  showOnScan(chunk, span.start, span.end)
}

// ── The page scan beside the text (#545) ──
const router = useRouter()
const workspacePane = ref<InstanceType<typeof DocumentWorkspace> | null>(null)
const workspace = useWorkspaceMode(parseMode(route.query.view))
const scanSync = useReaderScanSync({
  documentId: () => props.documentId,
  chunkWindow,
  loadSpans: (chunkIds) => tagSpans.loadSpansForChunksInCollection(chunkIds, props.collectionId),
  focusScan: (request) => workspacePane.value?.focus(request) ?? Promise.resolve(false),
  revealText: (at) => { textPane.value?.revealRange(at) }
})
/** The top of the text's scroller covered by the span gutter's scrollbar (sticky at its top). */
const READER_COVERED_TOP = 20
const scanPageId = computed(() => typeof route.query.page === 'string' ? route.query.page : null)
/** The page the link opened (`?page=`): its text is shown once the reader's text is loaded. */
const linkedPageId = scanPageId.value
let textReady: () => void = () => undefined
const textLoaded = new Promise<void>(resolve => { textReady = resolve })
let scanReady: () => void = () => undefined
const scanLoaded = new Promise<void>(resolve => { scanReady = resolve })
let firstScanPage = true
/** Incremented by every page shown in the scan: an older page still waiting for the text gives up. */
let scanPageGeneration = 0
/** The link's targets: an annotation or a chunk, or a page. */
const LINK_TARGETS = ['annotation', 'chunk', 'order', 'page'] as const
/** The targets a page the reader moved to replaces. */
const TEXT_TARGETS = ['annotation', 'chunk', 'order'] as const
/** The targets of the URL this page wrote itself (the reader's page change): not a new link. */
let ownTarget: string | null = null

function chooseMode (mode: WorkspaceMode) {
  workspace.chosen.value = mode
  void router.replace({ query: withMode(route.query, mode) })
}

/** The reader moved to another page in the scan: the URL opens it again, not the link's annotation or chunk. */
function onScanNavigate (page: DocumentPage) {
  const query = withScanPage(route.query, page.pageId, TEXT_TARGETS)
  ownTarget = targetKey(query, LINK_TARGETS)
  void router.replace({ query })
}

function onScanLoaded (info: { available: boolean, pages: DocumentPage[] }) {
  workspace.hasScan.value = info.available
  scanSync.pages.value = info.pages
  scanReady()
}

/**
 * A page shown in the scan: the text goes to it when the reader opened it there, once the text
 * is loaded. The first page shown is followed only when the link named it; a page replaced
 * while the text was still loading is not followed at all.
 */
async function onScanPage (page: DocumentPage, index: number) {
  const generation = ++scanPageGeneration
  const first = firstScanPage
  firstScanPage = false
  await textLoaded
  if (generation !== scanPageGeneration) return
  void scanSync.sync.onScanPage(page, index, { follow: !first || linkedPageId === page.pageId })
}

/** An annotation runs into this gap: its chunks are not known (a distant page shown, a large gap). */
function annotationCutAt (group: { gapAfter: number | null, gapBefore: number | null }): boolean {
  const { gapAfter, gapBefore } = group
  if (gapAfter === null || gapBefore === null) return false
  for (const order of annotations.cutAtGapOrders.value) if (order >= gapAfter && order < gapBefore) return true
  return false
}

/** Text to scan once the manifest is known: the lines of a range (a linked annotation, a citation). */
function showOnScan (chunkId: string, start: number, end: number) {
  void scanLoaded.then(() => scanSync.sync.showTextOnScan({ chunkId, start, end }))
}

// The text shown again after the scan alone: the passage focused from the scan comes into view.
watch(workspace.shown, async (mode, before) => {
  const at = scanSync.sync.textFocus.value?.range
  if (before !== 'scan' || mode === 'scan' || !at) return
  await nextTick()
  textPane.value?.revealRange(at)
})

// Another link to this document (a query-only navigation: Vue Router reuses the reader): its
// annotation or chunk once the text is loaded; a page alone is opened by the scan viewer
// (`pageId`), whose text follows it. The view follows `?view=`.
watch(() => targetKey(route.query, LINK_TARGETS), async (key, before) => {
  if (route.name !== 'documentDetailV1' || route.params.documentId !== props.documentId) return
  if (key === before || key === ownTarget) return
  ownTarget = null
  await textLoaded
  linkedAnnotationShown = null
  linkedChunkShown = null
  if (navHighlightedSpanId.value === linkedSpanId.value) navHighlightedSpanId.value = null
  const { annotation, chunk } = route.query
  if (typeof annotation === 'string' || typeof chunk === 'string') {
    await showLinkedAnnotation()
    await showLinkedChunk()
    return
  }
  // The scan shows the linked page already: its text is shown as for a page change.
  const shown = workspacePane.value?.currentPage()
  const index = shown ? scanSync.pages.value.findIndex(p => p.pageId === shown.pageId) : -1
  if (shown && index >= 0 && shown.pageId === scanPageId.value) void scanSync.sync.onScanPage(shown, index)
})
watch(() => route.query.view, (view) => {
  if (route.name !== 'documentDetailV1') return
  workspace.chosen.value = parseMode(view) ?? 'split'
})

/** A link to a chunk without an annotation (`?chunk=&order=`): the chunk in view and on the scan. */
let linkedChunkShown: string | null = null
async function showLinkedChunk () {
  const { annotation, chunk, order } = route.query
  if (typeof annotation === 'string' || typeof chunk !== 'string' || linkedChunkShown === chunk) return
  linkedChunkShown = chunk
  if (!chunkWindow.findChunk(chunk)) {
    const chunkOrder = await linkedChunkOrder(chunk, order)
    if (chunkOrder != null) await chunkWindow.loadUntil(chunkOrder)
  }
  if (!chunkWindow.findChunk(chunk)) return
  await nextTick()
  scrollToChunk(chunk)
  showOnScan(chunk, 0, 0)
}

// ── Annotation editing ──
const popoverRef = ref<InstanceType<typeof AnnotationPopover> | null>(null)

// The last tag actually applied to a span in this collection — suggested first in the popover,
// ahead of any text-similarity match. Re-read whenever collectionId changes, like the other
// per-collection state on this page (useChunkWindow, useChunkMembership, useTagEditing), in case
// a future route ever reuses this component instance across collections.
const lastUsedTagId = ref<string | null>(getLastUsedTagId(props.collectionId))
watch(() => props.collectionId, (collectionId) => {
  lastUsedTagId.value = getLastUsedTagId(collectionId)
})
const recordTagUsage = (tagId: string) => {
  lastUsedTagId.value = tagId
  setLastUsedTagId(props.collectionId, tagId)
}

// The span being edited when it is an AI suggestion: the popover offers approve/reject, also
// after its start was dragged into another chunk (it is stored on its own chunk until saved).
const editingAutoSpan = computed(() => {
  const sel = annotations.selection.value
  if (!sel?.editingSpanId) return null
  const spans = tagSpans.spansByChunkId.value[sel.spanChunkId ?? sel.chunkId] || []
  const span = spans.find((s) => s.id === sel.editingSpanId)
  return span && span.type === SpanType.auto ? span : null
})

// Span requests of this reader's document: entered when the reader moves to another document
// or collection, or closes, so a failure that arrives later is not reported here.
const spanRequests = createContextGuard()
watch(() => [props.collectionId, props.documentId], () => spanRequests.enter())

/**
 * Run a span request from the popover. A failed one tells the user it was not saved and leaves
 * its selection open. Returns the request's result, or null when it failed.
 */
async function runSpanRequest<T>(request: () => Promise<T>, failure: string | (() => string)): Promise<T | null> {
  const isCurrent = spanRequests.capture()
  try {
    return await request()
  } catch (err) {
    if (!isCurrent() || isAbortError(err)) return null
    errorNotification(await apiErrorMessage(err, typeof failure === 'function' ? failure() : failure))
    return null
  }
}

async function changeEditingSpanType(type: SpanType) {
  const span = editingAutoSpan.value
  if (!span || !span.id) return
  await runSpanRequest(
    () => annotations.applyToSelection(() => aiAssist.resolveAutoSpan(span, type)),
    resolveAutoSpanFailure(type)
  )
}

// The AI-panel highlight this page set for a selected auto span. A new text selection clears
// the highlight only while it is still this one, so a card the user moved to in the AI panel
// (its prev/next position) is kept.
let highlightFromSelection: string | null = null
const highlightAutoSpan = (spanId: string) => {
  aiAssist.highlightedAutoSpanId.value = spanId
  highlightFromSelection = spanId
}

// When the user selects an auto span (from its gutter marker), mirror that into the
// AI panel highlight so the matching suggestion card lights up.
watch(editingAutoSpan, (span) => {
  if (span?.id) highlightAutoSpan(span.id)
})

const onMarkerClick = (item: SpanMarker, e: MouseEvent) => {
  annotations.editSpan({
    id: item.spanId,
    chunkId: item.chunkId,
    tagId: item.tagId,
    start: item.start,
    end: item.end
  })
  popoverRef.value?.moveTo(e)
  popoverRef.value?.showMode('actions')

  // Sync nav index
  tagNav.syncIndex(item.tagId, item.spanId)

  // Two-way highlight with the AI panel: clicking an auto span in the gutter
  // should make its corresponding suggestion card light up (and scroll into
  // view inside the panel).
  if (item.isAuto) {
    highlightAutoSpan(item.spanId)
  }
}

// Where the primary button went down in the text, to tell a click from a drag. A drag of
// a selection handle is never a click, nor is a right or middle click.
let pointerDown: { x: number, y: number, onHandle: boolean } | null = null
const CLICK_TOLERANCE = 4

// A click opens the span only once no second click has followed, so a double-click
// selects the word without the span's popover opening first; likewise a double-clicked
// word is tagged with a focused tag only then. Kept short: the popover should feel
// immediate (#479). A slower double-click still selects the word; the popover then
// switches from the span to the new selection.
const DOUBLE_CLICK_WAIT = 150
// What a click does once no further click has followed. `onCancel` runs when the next
// click (or a change of the focused tag) cancels it.
let pendingClick: { timer: ReturnType<typeof setTimeout>, onCancel?: () => void } | null = null

function schedulePendingClick(action: () => void, onCancel?: () => void) {
  cancelPendingClick()
  const timer = setTimeout(() => {
    pendingClick = null
    action()
  }, DOUBLE_CLICK_WAIT)
  pendingClick = { timer, onCancel }
}

/** Cancels the pending click action; returns whether there was one. */
function cancelPendingClick(): boolean {
  if (!pendingClick) return false
  const { timer, onCancel } = pendingClick
  pendingClick = null
  clearTimeout(timer)
  onCancel?.()
  return true
}

function onDocumentPointerDown(e: PointerEvent) {
  cancelPendingClick()
  pointerDown = e.button === 0
    ? { x: e.clientX, y: e.clientY, onHandle: !!(e.target as HTMLElement).closest('.selection-handle') }
    : null
}

/** A click (no drag) on tagged text opens the shortest span there, like its gutter label. */
function openSpanAtClick(e: MouseEvent) {
  const down = pointerDown
  if (!down || down.onHandle || e.detail > 1) return
  if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > CLICK_TOLERANCE) return
  const marker = shortestMarker(markersAtSegment(e.target))
  if (!marker) return
  schedulePendingClick(() => onMarkerClick(marker, e))
}

function onTextClick(point: TextPoint | null, e: MouseEvent) {
  openSpanAtClick(e)
  pointerDown = null
  // The line clicked, on the scan (#545).
  if (point) void scanSync.sync.showTextOnScan({ chunkId: point.chunkId, start: point.charOffset, end: point.charOffset })
}

// A text selection becomes the annotation selection; the browser's own selection is cleared.
const onTextSelect = ({ start: startPoint, end: endPoint }: TextSelection, e: MouseEvent) => {
  pointerDown = null
  // The selected lines, on the scan (#545).
  const scanRange = selectionRange(startPoint, endPoint, displayChunks.value)
  if (scanRange) void scanSync.sync.showTextOnScan(scanRange)

  const previousSelection = annotations.selection.value
  let shortened = false
  if (startPoint.chunkId === endPoint.chunkId) {
    const start = Math.min(startPoint.charOffset, endPoint.charOffset)
    const end = Math.max(startPoint.charOffset, endPoint.charOffset)
    if (end > start) {
      annotations.setSelection(startPoint.chunkId, start, end)
    }
  } else {
    shortened = annotations.setCrossChunkSelection(
      startPoint.chunkId, startPoint.charOffset,
      endPoint.chunkId, endPoint.charOffset
    )
  }
  const newSelection = annotations.selection.value !== previousSelection ? annotations.selection.value : null

  popoverRef.value?.moveTo(e)
  window.getSelection()?.removeAllRanges()
  // A new selection is unrelated to an AI suggestion highlighted by selecting it earlier.
  if (highlightFromSelection && aiAssist.highlightedAutoSpanId.value === highlightFromSelection) {
    aiAssist.highlightedAutoSpanId.value = null
  }
  highlightFromSelection = null

  // Fresh selections open straight into the tag picker, as if "Add tag" had
  // already been clicked.
  popoverRef.value?.showMode('picker')

  // With a tag focused in the tags panel, a new selection is tagged with it right away; one
  // cut short at a document gap opens the picker instead, so the user sees what is left.
  const focusedTagId = tagNav.focusedTagId.value
  if (focusedTagId && newSelection && !shortened) tagWithFocusedTag(focusedTagId, newSelection, e.detail >= 2)
}

// ── Tag focus (#479) ──
// A tag focused in the tags panel tags each new selection directly, without the popover.
// The popover appears only when that fails, in the picker, so the user can try again.
const focusedTag = computed(() => tags.value.find((t) => t.id === tagNav.focusedTagId.value) ?? null)
type Selection = NonNullable<typeof annotations.selection.value>
/** The selection the focused tag is going onto: the popover stays closed for it. */
const focusTaggedSelection = shallowRef<Selection | null>(null)

/**
 * Tags `sel` with the focused tag. A double-clicked word waits for the double-click time:
 * a further click, or a change of the focused tag, cancels that and shows the word in the
 * picker instead.
 */
function tagWithFocusedTag(tagId: string, sel: Selection, afterDoubleClick: boolean) {
  focusTaggedSelection.value = sel
  if (!afterDoubleClick) {
    void saveWithFocusedTag(tagId, sel)
    return
  }
  schedulePendingClick(
    () => void saveWithFocusedTag(tagId, sel),
    () => { if (focusTaggedSelection.value === sel) focusTaggedSelection.value = null }
  )
}

async function saveWithFocusedTag(tagId: string, sel: Selection) {
  const failure = () => {
    const text = selectionText(sel, [...displayChunks.value, ...hiddenPreviewChunks.value])
    const quoted = text.length > 40 ? `${text.slice(0, 40).trimEnd()}…` : text
    return `"${quoted}" could not be tagged with ${tags.value.find((t) => t.id === tagId)?.name ?? 'the tag'}.`
  }
  const applied = annotations.selection.value === sel
    ? await runSpanRequest(() => annotations.createSpan(tagId), failure)
    : null
  // Failed and still open: the popover shows it in the picker.
  if (focusTaggedSelection.value === sel) focusTaggedSelection.value = null
  if (applied) recordTagUsage(tagId)
}

// A double-clicked word waiting for its tag is not saved with a tag the user has left.
watch(tagNav.focusedTagId, () => cancelPendingClick())

// The focus ends when its tag is deleted, and in another collection, which has other tags.
watch(tags, (list) => {
  const focused = tagNav.focusedTagId.value
  if (focused && !list.some((t) => t.id === focused)) tagNav.setFocusedTagId(null)
})
watch(() => props.collectionId, () => tagNav.setFocusedTagId(null))

const onTagClick = async (tagId: string) => {
  const applied = annotations.isEditing.value
    ? await runSpanRequest(() => annotations.updateSpanTag(tagId), 'The tag could not be changed.')
    : await runSpanRequest(() => annotations.createSpan(tagId), 'The tag could not be saved.')
  // Only a tag that really went onto a span becomes the last-used suggestion.
  if (applied) recordTagUsage(tagId)
}

const onSavePosition = () =>
  runSpanRequest(() => annotations.updateSpanPosition(), 'The new position could not be saved.')

const onDeleteSpan = () =>
  runSpanRequest(() => annotations.deleteSpan(), 'The tag could not be removed.')

const onCreateTagClick = () => {
  tagEditing.createTag((newTag) => onTagClick(newTag.id))
}

const onOpenTagDetails = () => {
  const tag = tags.value.find((t) => t.id === annotations.selection.value?.tagId)
  if (tag) tagEditing.editTag(tag)
}

const onBoundaryDrag = (payload: { chunkId: string; handle: 'start' | 'end'; charOffset: number }) => {
  annotations.adjustSelectionBoundary(payload.handle, payload.chunkId, payload.charOffset)
}

// The text of the current selection, used by the popover to suggest a likely tag first.
const selectedSpanText = computed(() => {
  const sel = annotations.selection.value
  if (!sel) return ''
  return selectionText(sel, [...displayChunks.value, ...hiddenPreviewChunks.value])
})

// ── Suggest tags via AI for the highlighted selection ──
const onRunAiOnSelection = async (tagIds: string[]) => {
  const sel = annotations.selection.value
  if (!sel) return
  if (!tagIds.length) {
    $q.notify({
      type: 'warning',
      message: 'Select at least one tag.',
      timeout: 2500
    })
    return
  }

  // Topicer gets only the displayed chunks the selection overlaps; hidden gap
  // chunks are skipped and the offsets re-measured without them.
  const target = selectionInDisplayedChunks(sel, displayChunks.value, hiddenPreviewChunks.value)
  if (!target) return

  // Show the AI Tagging panel right away so the user sees the spinner and any
  // incoming suggestions in context, then close the popover.
  rightSidebar.activate(DOCUMENT_SIDEBAR_PANELS.ai)
  annotations.clearSelection()

  // Not awaited: an outdated or failed list is read again for the next run.
  void topicerModel.load()
  const created = await aiAssist.runOnSelection({
    collectionId: props.collectionId,
    documentId: props.documentId,
    chunkIds: target.chunkIds,
    selectionStart: target.start,
    selectionEnd: target.end,
    tagIds,
    // The model chosen in the AI Tagging panel (the default until its list has been read).
    configName: topicerModel.chosenConfigName()
  })
  // Cancelled, or the user moved to another document/collection meanwhile.
  if (created === null) return
  if (!created.length && !aiAssist.lastSelectionError.value) {
    $q.notify({
      type: 'info',
      message: 'AI did not suggest any tag for this selection.',
      timeout: 2500
    })
  } else if (aiAssist.lastSelectionError.value) {
    $q.notify({
      type: 'negative',
      message: aiAssist.lastSelectionError.value,
      timeout: 3500
    })
  }
}

// ── Discuss-with-AI ──
const { openSpanDiscussionDialog } = useSpanDiscussionDialog()

const onDiscussSpan = () => {
  const sel = annotations.selection.value
  if (!sel?.editingSpanId) return
  const tag = sel.tagId ? tags.value.find((t) => t.id === sel.tagId) : undefined
  openSpanDiscussionDialog({
    collectionId: props.collectionId,
    spanId: sel.editingSpanId,
    spanText: selectionText(sel, [...displayChunks.value, ...hiddenPreviewChunks.value]),
    tagName: tag?.name,
    tagColor: tag?.color
  })
}

// ── Loading and re-measuring ──
let resizeObserver: ResizeObserver | null = null

watch(
  () => chunks.value,
  async (newChunks) => {
    if (newChunks.length) {
      chunkWindow.show(newChunks)
      await annotations.loadAllSpans(props.collectionId)
      await chunkWindow.preloadGapChunks()
      await nextTick()
      relayout()
      await chunkWindow.checkNeighbours()
      await showLinkedAnnotation()
      await showLinkedChunk()
    }
    // Not the chunks cleared when the load starts: the text is loaded once the load is done.
    if (!loading.value) textReady()
  }
)
// A load that failed, or found no chunks, without changing them: there is no text to wait for.
watch(loading, (now) => { if (!now && !chunks.value.length) textReady() })

watch(
  () => annotations.spansVersion.value,
  () => nextTick(relayout)
)

watch(
  () => tagNav.hiddenTagIds.size,
  () => nextTick(relayout)
)

// When prev/next expand-rows appear/disappear they shift the text — remeasure
watch([chunkWindow.hasPrev, chunkWindow.hasNext], () => nextTick(() => requestAnimationFrame(relayout)))

// Highlight the selected span's tag in the right-hand panel.
watch(
  () => annotations.selection.value?.tagId,
  (tagId) => tagNav.setActiveTagId(tagId ?? null)
)

// ── Dismiss on click-outside / Escape ──

const onClickOutside = (e: MouseEvent) => {
  if (!annotations.hasSelection.value) return
  const target = e.target as HTMLElement
  // Don't dismiss if clicking inside the popover, the document text area,
  // a Quasar dialog opened from the popover (e.g. the create/edit-tag
  // dialog) — those are teleported outside both containers, so without this
  // check the selection would be cleared out from under the dialog's own
  // onOk handler while the user is still filling it in — or the right
  // sidebar (#249): switching tools there (checking tags, AI suggestions,
  // document metadata, or the document summary and its citations) is a
  // normal part of annotating and must not silently discard an open
  // popover either.
  const popover = document.querySelector('.annotation-popover')
  if (popover?.contains(target)) return
  if (documentTextRef.value?.contains(target)) return
  if (target.closest('.q-dialog')) return
  if (target.closest('.q-drawer--right')) return
  annotations.clearSelection()
}

// Escape in an open dialog belongs to the dialog: the create-tag dialog opened from the
// popover still needs the selection when its tag is created (#379). Escape closes the
// selection first, then ends a tag focus, unless it was typed in a field (the tag search).
const onEscape = (e: KeyboardEvent) => {
  if (e.key !== 'Escape' || overlayOpen()) return
  if (focusTaggedSelection.value && annotations.selection.value === focusTaggedSelection.value && cancelPendingClick()) {
    // A double-clicked word not tagged yet: it is dropped, the focus stays.
    annotations.clearSelection()
  } else if (annotations.hasSelection.value && annotations.selection.value !== focusTaggedSelection.value) {
    annotations.clearSelection()
  } else if (tagNav.focusedTagId.value && !(e.target as HTMLElement | null)?.closest?.('input, textarea, [contenteditable]')) {
    tagNav.setFocusedTagId(null)
  }
}

onMounted(async () => {
  await Promise.all([
    tagsStore.fetchTagsByCollection(props.collectionId),
    loadChunksInCollectionDocument(props.collectionId, props.documentId)
  ])

  void countDocumentChunks(props.documentId).then(n => { totalDocumentChunks.value = n })

  await nextTick()
  if (documentTextRef.value) {
    resizeObserver = new ResizeObserver(() => {
      requestAnimationFrame(() => relayout())
    })
    resizeObserver.observe(documentTextRef.value)
  }

  document.addEventListener('mousedown', onClickOutside)
  document.addEventListener('keydown', onEscape)
})

onBeforeUnmount(() => {
  spanRequests.enter()
  scanSync.sync.cancel()
  resizeObserver?.disconnect()
  if (pendingClick) clearTimeout(pendingClick.timer)
  document.removeEventListener('mousedown', onClickOutside)
  document.removeEventListener('keydown', onEscape)
  // activeTagId and focusedTagId are module-level state in useTagNavigation; don't carry
  // this reader's highlighted or focused tag into the next one.
  tagNav.setActiveTagId(null)
  tagNav.setFocusedTagId(null)
})
</script>

<style scoped>
.doc-page {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}

/* The gutters and the text, one white reading surface at least as tall as the text pane. */
.page-shell {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  min-height: 100%;
  background: #ffffff;
}

.paper-card {
  flex: 4;
  min-width: 0;
  border-radius: 0;
  background: #ffffff;
  box-shadow: none;
}

.paper-body {
  padding: 16px 20px 24px;
}

/* The text starts right next to the span gutter. */
.paper-card.has-gutter .paper-body {
  padding-left: 10px;
}

/* Dim non-collection preview chunks slightly */
:deep(.chunk-preview) {
  opacity: 0.6;
  transition: opacity 0.15s;
}
:deep(.chunk-preview.chunk-preview--active) {
  opacity: 1;
}

/* Highlight the chunk's text background while hovering its left-gutter row. */
:deep(.chunk-gutter-hovered) {
  background: rgba(15, 23, 42, 0.1);
  border-radius: 4px;
  transition: background 0.12s ease;
}

/* ── Full-width expand rows (prev / next) inside paper-body ── */

.expand-row {
  display: flex;
  justify-content: center;
  border-bottom: 1px dashed #e2e8f0;
  margin-bottom: 16px;
}

.expand-row--col {
  flex-direction: column;
}

.expand-row--col .expand-btn + .expand-btn {
  border-top: 1px solid #e2e8f0;
}

.expand-row--top {
  margin-top: -16px;
  margin-bottom: 20px;
}

.expand-row--bottom {
  border-bottom: none;
  border-top: 1px dashed #e2e8f0;
  margin-bottom: 0;
  margin-top: 16px;
}

.expand-btn {
  width: 100%;
  color: #64748b;
  font-size: 0.82rem;
  letter-spacing: 0.02em;
  transition: background 0.15s, color 0.15s;
  border-radius: 0;
}

.expand-btn:hover {
  background: #f1f5f9;
  color: #334155;
}

/* ── Gap divider (missing chunks between two displayed chunks) ── */

.gap-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  margin: 8px 0 18px;
  padding: 4px 10px;
  border-top: 1px dashed #f59e0b;
  border-bottom: 1px dashed #f59e0b;
  background: #fffbeb;
}

.gap-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-right: auto;
  color: #92400e;
  font-size: 0.85rem;
  font-weight: 600;
}

/* Below the buttons, on its own line. */
.gap-label--cut {
  order: 1;
  flex-basis: 100%;
  font-weight: 400;
}

.gap-btn {
  color: #78716c;
  font-size: 0.78rem;
  letter-spacing: 0.02em;
  transition: background 0.15s, color 0.15s;
}

.gap-btn--all {
  color: #57534e;
  font-weight: 500;
}

.gap-btn:hover {
  background: #fef3c7;
  color: #44403c;
}

@media (max-width: 599px) {
  .paper-body {
    padding: 12px 12px 20px;
  }

  .paper-card.has-gutter .paper-body {
    padding-left: 8px;
  }

  .expand-row--top {
    margin-top: -12px;
  }
}
</style>
