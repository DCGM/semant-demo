<template>
  <q-page class="q-px-lg doc-page">
    <ReaderToolbar
      v-model:chunk-gutter-visible="chunkGutterVisible"
      v-model:preserve-whitespace="preserveWhitespace"
      :collection-only="chunkWindow.displayedPreviewCount.value === 0"
      :all-chunks="chunkWindow.allChunksShown.value"
      :loading-all="chunkWindow.loadingAllChunks.value"
      @show-collection-only="chunkWindow.hideAllPreviews"
      @show-all-chunks="chunkWindow.loadAllChunks"
    />
    <div class="page-shell">
      <ChunkMembershipGutter
        v-show="chunkGutterVisible"
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

          <div class="document-text" :class="{ 'document-text--preserve-whitespace': preserveWhitespace }" ref="documentTextRef" @mouseup="handleDocumentMouseUp($event)" @pointermove="onDocumentPointerMove" @pointerleave="hoveredPreviewChunkId = null">
            <template v-for="(group, gIndex) in paragraphs" :key="gIndex">
              <p>
                <ChunkAnnotator
                  v-for="chunk in group.chunks"
                  :key="chunk.id"
                  :chunk-id="chunk.id"
                  :text="chunk.text"
                  :spans="getVisibleSpans(chunk.id)"
                  :selection="annotations.getLocalSelection(chunk.id)"
                  :available-tags="tags"
                  :highlight-span-id="hoveredSpanId || highlightedAutoSpanId"
                  :class="{ 'chunk-preview': !chunk.inCollection, 'chunk-preview--active': !chunk.inCollection && hoveredPreviewChunkId === chunk.id, 'chunk-gutter-hovered': gutterHoveredChunkId === chunk.id }"
                  @boundary-drag="onBoundaryDrag"
                />
              </p>
              <!-- Gap buttons between non-consecutive chunks -->
              <div v-if="group.gapAfter !== null" class="gap-row">
                <q-btn
                  flat dense
                  icon="keyboard_arrow_down"
                  :loading="chunkWindow.gapLoadingKey.value === `${group.gapAfter}:next`"
                  class="gap-btn"
                  label="Load next"
                  title="Load the chunk just after this gap"
                  @click="chunkWindow.loadGap(group.gapAfter)"
                />
                <q-btn
                  flat dense
                  icon="unfold_more"
                  :loading="chunkWindow.gapLoadingKey.value === `${group.gapAfter}:all`"
                  class="gap-btn gap-btn--all"
                  label="Load all missing"
                  title="Load all chunks in this gap"
                  @click="chunkWindow.loadGapAll(group.gapAfter, group.gapBefore!)"
                />
                <q-btn
                  flat dense
                  icon="keyboard_arrow_up"
                  :loading="chunkWindow.gapLoadingKey.value === `${group.gapBefore}:prev`"
                  class="gap-btn"
                  label="Load previous"
                  title="Load the chunk just before this gap"
                  @click="chunkWindow.loadGapPrev(group.gapBefore!)"
                />
              </div>
            </template>
          </div>

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

      <AnnotationGutter
        v-if="gutters.spanMarkers.value.length"
        :markers="gutters.spanMarkers.value"
        :tags="tags"
        :hovered-span-id="hoveredSpanId"
        :highlighted-span-id="highlightedAutoSpanId"
        @hover="hoveredSpanId = $event"
        @select="onMarkerClick"
      />

      <AnnotationPopover
        ref="popoverRef"
        :visible="annotations.hasSelection.value && !quickTagging"
        :tags="tags"
        :selection="annotations.selection.value"
        :selected-text="selectedSpanText"
        :selected-tag-id="annotations.selection.value?.tagId ?? null"
        :is-editing="annotations.isEditing.value"
        :position-changed="annotations.positionChanged.value"
        :editing-auto="!!editingAutoSpan"
        :approve-reject-busy="approveRejectBusy"
        :ai-selection-running="aiAssist.isSelectionRunning.value"
        @close="endQuickTagging"
        @pick-tag="onTagClick"
        @create-tag="onCreateTagClick"
        @run-ai="onRunAiOnSelection"
        @save-position="annotations.updateSpanPosition()"
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
  </q-page>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { computed, ref, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useQuasar } from 'quasar'
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'
import { SpanType } from 'src/generated/api'
import ErrorDisplay from 'src/shared/ui/ErrorDisplay.vue'
import AnnotationGutter from 'src/features/annotations/AnnotationGutter.vue'
import type { SpanMarker } from 'src/features/annotations/AnnotationGutterTypes'
import AnnotationPopover from 'src/features/annotations/AnnotationPopover.vue'
import ChunkAnnotator from 'src/features/annotations/ChunkAnnotator.vue'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import useAiAssistance from 'src/features/annotations/useAiAssistance'
import { useAnnotations, type ProjectedSpan } from 'src/features/annotations/useAnnotations'
import useSpanDiscussionDialog from 'src/features/annotations/useSpanDiscussionDialog'
import { useTagEditing } from 'src/features/annotations/useTagEditing'
import { useTagNavigation } from 'src/features/annotations/useTagNavigation'
import useTagSpans from 'src/features/annotations/useTagSpans'
import { useUserCollectionsStore } from 'src/features/user_collections/userCollectionsStore'
import { collectionRights } from 'src/features/user_collections/permissions'
import useDocumentSummary from 'src/features/documents/useDocumentSummary'
import useChunks from '../useChunks'
import ChunkMembershipGutter from './ChunkMembershipGutter.vue'
import ChunkSelectionBar from './ChunkSelectionBar.vue'
import { DOCUMENT_SIDEBAR_PANELS } from './documentSidebar'
import ReaderToolbar from './ReaderToolbar.vue'
import { groupParagraphs, resolveSelectionEndpoint, selectionInDisplayedChunks, selectionText } from './readerOffsets'
import { useChunkMembership } from './useChunkMembership'
import { useChunkWindow } from './useChunkWindow'
import { useReaderGutters } from './useReaderGutters'

// The document reader: the text of the displayed chunks with their annotations, the
// chunk and span gutters, and annotation editing through the selection popover. The
// enclosing DocumentViewLayout loads the document, collection and tags.
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
const documentSummary = useDocumentSummary()
const rightSidebar = useRightSidebarStore()
const aiPanelActive = computed(() => aiAssist.aiPanelActive.value)
const highlightedAutoSpanId = computed(() => aiAssist.highlightedAutoSpanId.value)

const documentTextRef = ref<HTMLElement | null>(null)
const totalDocumentChunks = ref<number | null>(null)
const chunkGutterVisible = ref(true)
// Toggle between original-text whitespace (default) and HTML's collapsed
// whitespace. Original-mode preserves consecutive spaces and line breaks
// inside chunk text via CSS `white-space: pre-wrap`.
const preserveWhitespace = ref(true)

// ── Displayed chunks, membership and gutters ──
const chunkWindow = useChunkWindow(() => props.collectionId, () => props.documentId, () => relayout())
const { displayChunks, hiddenPreviewChunks } = chunkWindow
const membership = useChunkMembership(() => props.collectionId, chunkWindow, () => relayout())
const annotations = useAnnotations(() => displayChunks.value, () => hiddenPreviewChunks.value)
const paragraphs = computed(() => groupParagraphs(displayChunks.value))

// Approved spans of visible tags; AI suggestions only while the AI assist panel is active.
const gutters = useReaderGutters(
  documentTextRef, displayChunks, hiddenPreviewChunks,
  () => annotations.spansByChunkId.value,
  (span) => span.type !== SpanType.neg &&
    (aiPanelActive.value || span.type !== SpanType.auto) &&
    tagNav.isTagVisible(span.tagId)
)
const relayout = () => gutters.relayout()

// ── Hover state shared by the text and the gutters ──
const hoveredSpanId = ref<string | null>(null)
const hoveredPreviewChunkId = ref<string | null>(null)
const hoveredChunkId = ref<string | null>(null)
const gutterHoveredChunkId = ref<string | null>(null)

function onDocumentPointerMove(e: PointerEvent) {
  const el = (e.target as HTMLElement).closest<HTMLElement>('[data-chunk-id]')
  const chunkId = el?.dataset.chunkId ?? null
  hoveredChunkId.value = chunkId

  const chunk = chunkId ? chunkWindow.findChunk(chunkId) : null
  hoveredPreviewChunkId.value = chunk && !chunk.inCollection ? chunk.id : null
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
const visibleSpansByChunkId = computed<Record<string, ProjectedSpan[]>>(() => {
  const map: Record<string, ProjectedSpan[]> = {}
  for (const chunk of displayChunks.value) {
    map[chunk.id] = annotations.getProjectedSpans(chunk.id).filter(
      (s) => tagNav.isTagVisible(s.tagId) && (aiPanelActive.value || s.type !== SpanType.auto)
    )
  }
  return map
})

function getVisibleSpans(chunkId: string): ProjectedSpan[] {
  return visibleSpansByChunkId.value[chunkId] ?? []
}

// ── Scrolling the text to a span ──
function scrollToSpan(chunkId: string, start: number, end: number) {
  const chunkEl = documentTextRef.value?.querySelector<HTMLElement>(`[data-chunk-id="${chunkId}"]`)
  if (!chunkEl) return
  for (const seg of Array.from(chunkEl.querySelectorAll<HTMLElement>('.text-segment'))) {
    const s = parseInt(seg.dataset.start || '0')
    if (s >= start && s < end) {
      seg.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }
  }
}

// A document-summary citation (#249) is whole-chunk granularity, with no offset within the
// chunk to find a text segment for, so this scrolls to the chunk itself rather than reusing
// scrollToSpan's per-segment lookup.
function scrollToChunk(chunkId: string) {
  documentTextRef.value?.querySelector<HTMLElement>(`[data-chunk-id="${chunkId}"]`)
    ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
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
tagNav.onHighlight((spanId) => { hoveredSpanId.value = spanId })

// Re-render gutter (and re-filter auto spans in text) when the AI assist panel
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

// A clicked citation in the document summary panel (a sibling of this route inside
// DocumentViewLayout) scrolls the reader to the cited chunk, loading it into the displayed
// window first (chunkWindow.loadUntil, #249 review) if it isn't shown yet — the summary
// covers the whole document, but the reader only displays a bounded window by default. This
// is otherwise an orthogonal, read-only navigation action: it must not touch
// annotations/tagEditing/quickTagId state (no selection clearing, no popover changes, no span
// highlight changes) or navigate, only scroll/load — so tag-editing state in progress is left
// exactly as it was.
watch(() => documentSummary.requestedCitation.value, async (citation) => {
  if (!citation) return
  if (!chunkWindow.findChunk(citation.chunkId) && citation.order != null) {
    // A citation always refers to a chunk that exists (it came from the document's own
    // chunks); if its order can't be resolved into the window either, there is nothing more
    // to try and scrollToChunk below silently finds nothing (a narrow, documented fallback).
    await chunkWindow.loadUntil(citation.order)
  }
  scrollToChunk(citation.chunkId)
})

// ── Annotation editing ──
const popoverRef = ref<InstanceType<typeof AnnotationPopover> | null>(null)
// The tag of the span whose marker was last clicked. While set, drag-selecting
// new text quick-tags it with this same tag (see handleDocumentMouseUp) —
// stays active across multiple selections until explicitly ended.
const quickTagId = ref<string | null>(null)
// True for the brief window between a quick-tag selection and its span
// being created — suppresses the popover entirely so "Add tag" never flashes.
const quickTagging = ref(false)

const endQuickTagging = () => {
  quickTagId.value = null
  annotations.clearSelection()
}

// The span being edited when it is an AI suggestion: the popover offers approve/reject.
const approveRejectBusy = ref(false)
const editingAutoSpan = computed(() => {
  const sel = annotations.selection.value
  if (!sel?.editingSpanId) return null
  const spans = tagSpans.spansByChunkId.value[sel.chunkId] || []
  const span = spans.find((s) => s.id === sel.editingSpanId)
  return span && span.type === SpanType.auto ? span : null
})

async function changeEditingSpanType(type: SpanType) {
  const span = editingAutoSpan.value
  if (!span || !span.id) return
  approveRejectBusy.value = true
  try {
    await aiAssist.resolveAutoSpan(span, type)
  } finally {
    approveRejectBusy.value = false
    endQuickTagging()
  }
}

// When the user selects an auto span (from its gutter marker), mirror that into the
// AI panel highlight so the matching suggestion card lights up.
watch(editingAutoSpan, (span) => {
  if (span?.id) aiAssist.highlightedAutoSpanId.value = span.id
})

const onMarkerClick = (item: SpanMarker, e: MouseEvent) => {
  annotations.editSpan({
    id: item.spanId,
    chunkId: item.chunkId,
    tagId: item.tagId,
    start: item.start,
    end: item.end
  })
  quickTagId.value = item.tagId
  popoverRef.value?.moveTo(e)
  popoverRef.value?.showMode('actions')

  // Sync nav index
  tagNav.syncIndex(item.tagId, item.spanId)

  // Two-way highlight with the AI panel: clicking an auto span in the gutter
  // should make its corresponding suggestion card light up (and scroll into
  // view inside the panel).
  if (item.isAuto) {
    aiAssist.highlightedAutoSpanId.value = item.spanId
  }
}

const handleDocumentMouseUp = (e: MouseEvent) => {
  const domSelection = window.getSelection()
  if (!domSelection || domSelection.isCollapsed) return

  const range = domSelection.getRangeAt(0)
  const startPoint = resolveSelectionEndpoint(range.startContainer, range.startOffset)
  const endPoint = resolveSelectionEndpoint(range.endContainer, range.endOffset)

  if (!startPoint || !endPoint) return

  if (startPoint.chunkId === endPoint.chunkId) {
    const start = Math.min(startPoint.charOffset, endPoint.charOffset)
    const end = Math.max(startPoint.charOffset, endPoint.charOffset)
    if (end > start) {
      annotations.setSelection(startPoint.chunkId, start, end)
    }
  } else {
    annotations.setCrossChunkSelection(
      startPoint.chunkId, startPoint.charOffset,
      endPoint.chunkId, endPoint.charOffset
    )
  }

  popoverRef.value?.moveTo(e)
  domSelection.removeAllRanges()

  // A marker's tag stays "active" (see quickTagId) until explicitly ended,
  // so every subsequent selection here quick-tags that new text with it
  // instead of opening the picker — repositioning the original span is
  // still done via its drag handles.
  if (quickTagId.value) {
    quickTagging.value = true
    void annotations.createSpan(quickTagId.value).finally(() => {
      quickTagging.value = false
    })
    return
  }

  // Fresh selections open straight into the tag picker, as if "Add tag" had
  // already been clicked.
  popoverRef.value?.showMode('picker')
}

const onTagClick = async (tagId: string) => {
  if (annotations.isEditing.value) {
    quickTagId.value = null
    await annotations.updateSpanTag(tagId)
  } else {
    await annotations.createSpan(tagId)
  }
}

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

const onDeleteSpan = async () => {
  quickTagId.value = null
  await annotations.deleteSpan()
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

  // Show the AI assist panel right away so the user sees the spinner and any
  // incoming suggestions in context, then close the popover.
  rightSidebar.activate(DOCUMENT_SIDEBAR_PANELS.ai)
  annotations.clearSelection()

  const created = await aiAssist.runOnSelection({
    collectionId: props.collectionId,
    documentId: props.documentId,
    chunkIds: target.chunkIds,
    selectionStart: target.start,
    selectionEnd: target.end,
    tagIds
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
    }
  }
)

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

// While quick-tagging is active, keep the tag highlighted in the right-hand
// panel regardless of the selection briefly clearing between instances.
watch(
  [() => annotations.selection.value?.tagId, quickTagId],
  ([selectionTagId, activeQuickTagId]) => tagNav.setActiveTagId(activeQuickTagId ?? selectionTagId ?? null)
)

// ── Dismiss on click-outside / Escape ──

const onClickOutside = (e: MouseEvent) => {
  // quickTagId can stay active with no current selection — createSpan()
  // clears the selection right after each quick-tag, but fast-labeling
  // mode itself keeps going until explicitly ended.
  if (!annotations.hasSelection.value && !quickTagId.value) return
  const target = e.target as HTMLElement
  // Don't dismiss if clicking inside the popover, the document text area,
  // a Quasar dialog opened from the popover (e.g. the create/edit-tag
  // dialog) — those are teleported outside both containers, so without this
  // check the selection would be cleared out from under the dialog's own
  // onOk handler while the user is still filling it in — or the right
  // sidebar (#249): switching tools there (checking tags, AI suggestions,
  // document metadata, or the document summary and its citations) is a
  // normal part of annotating and must not silently discard an open
  // popover or an in-progress quick-tag selection either.
  const popover = document.querySelector('.annotation-popover')
  if (popover?.contains(target)) return
  if (documentTextRef.value?.contains(target)) return
  if (target.closest('.q-dialog')) return
  if (target.closest('.q-drawer--right')) return
  endQuickTagging()
}

const onEscape = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && (annotations.hasSelection.value || quickTagId.value)) {
    endQuickTagging()
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
  resizeObserver?.disconnect()
  document.removeEventListener('mousedown', onClickOutside)
  document.removeEventListener('keydown', onEscape)
})
</script>

<style scoped>
.doc-page {
  min-height: 100%;
  background: #eef2f7;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.page-shell {
  display: flex;
  flex-direction: row;
  gap: 0;
  align-items: stretch;
  border-radius: 16px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
  overflow: hidden;
}

.paper-card {
  flex: 4;
  min-width: 0;
  min-height: calc(100vh - 160px);
  border-radius: 0;
  background: #ffffff;
  box-shadow: none;
}

.paper-card.has-gutter {
  border-radius: 0;
}

.paper-body {
  padding: 32px 32px 40px;
}

.document-text {
  max-width: none;
  margin: 0;
  font-size: 1.08rem;
  line-height: 2;
  color: rgba(15, 23, 42, 0.95);
}

.document-text p {
  margin: 0 0 18px;
}

/* When the toolbar toggle is on, render text exactly as stored (preserve
   consecutive spaces and line breaks inside each chunk). Wrapping is still
   allowed so long lines don't overflow the column. */
.document-text--preserve-whitespace :deep(.text-segment) {
  white-space: pre-wrap;
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
  margin-top: -32px;
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

/* ── Gap row (missing chunks between two displayed chunks) ── */

.gap-row {
  display: flex;
  flex-direction: column;
  margin: 4px 0;
  border-top: 1px dashed #e2e8f0;
  border-bottom: 1px dashed #e2e8f0;
}

.gap-btn {
  flex: 1;
  color: #94a3b8;
  font-size: 0.78rem;
  letter-spacing: 0.02em;
  transition: background 0.15s, color 0.15s;
  border-radius: 0;
}

.gap-btn + .gap-btn {
  border-left: none;
  border-top: 1px solid #e2e8f0;
}

.gap-btn--all {
  color: #64748b;
  font-weight: 500;
}

.gap-btn:hover {
  background: #f8fafc;
  color: #475569;
}

@media (max-width: 1023px) {
  .paper-card {
    min-height: auto;
  }

  .paper-body {
    padding: 24px;
  }
}

@media (max-width: 599px) {
  .paper-body {
    padding: 20px 16px 24px;
  }

  .document-text {
    font-size: 1rem;
    line-height: 1.9;
  }
}
</style>
