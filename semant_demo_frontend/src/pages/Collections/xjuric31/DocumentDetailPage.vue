<template>
  <q-page class="q-px-lg doc-page">
    <!-- View mode toolbar -->
    <div class="paper-toolbar-row">
      <div class="paper-view-toolbar">
        <q-btn
          flat dense round
          icon="view_sidebar"
          size="sm"
          class="view-btn"
          :class="{ 'view-btn--active': leftGutterVisible }"
          title="Show/hide chunk gutter"
          @click="leftGutterVisible = !leftGutterVisible"
          >
          <q-tooltip v-if="leftGutterVisible">Hide chunk gutter</q-tooltip>
          <q-tooltip v-else>Show chunk gutter</q-tooltip>
        </q-btn>
      </div>
      <div class="paper-view-toolbar">
      <q-btn
        flat dense no-caps
        icon="playlist_add_check"
        label="Collection only"
        size="sm"
        :class="{ 'view-btn--active': displayedPreviewCount === 0 }"
        class="view-btn"
        title="Show only chunks already in this collection"
        @click="hideAllPreviews"
      >
        <q-tooltip>
          Show only chunks in the collection (hide preview chunks)
        </q-tooltip>
      </q-btn>
      <q-btn
        flat dense no-caps
        icon="visibility"
        label="All chunks"
        size="sm"
        :loading="loadingAllChunks"
        :class="{ 'view-btn--active': !hasPrev && !hasNext && hiddenPreviewChunks.length === 0 && displayChunks.length > 0 }"
        class="view-btn"
        title="Load and show the entire document"
        @click="loadAllChunks"
      >
        <q-tooltip>
          Load and show all chunks in the document (including previews)
        </q-tooltip>
      </q-btn>
      </div>
    </div>
    <div class="page-shell">

      <!-- Chunk checkbox column -->
      <div
        v-show="leftGutterVisible"
        class="chunk-checkbox-col"
        :class="{ 'is-active': selectedChunkIds.length > 0 }"
      >
        <div
          v-for="item in leftGutterItems"
          :key="item.chunkId"
          class="chunk-checkbox-item"
          :class="{ 'is-checked': selectedChunkIds.includes(item.chunkId), 'is-hovered': hoveredChunkId === item.chunkId }"
          :style="{ top: item.top + 'px', height: item.height + 'px' }"
          :title="selectedChunkIds.includes(item.chunkId) ? 'Deselect chunk' : 'Select chunk'"
          @click.stop="toggleChunkSelection(item.chunkId)"
        >
          <q-icon
            :name="selectedChunkIds.includes(item.chunkId) ? 'check_box' : 'check_box_outline_blank'"
            size="18px"
            :color="selectedChunkIds.includes(item.chunkId) ? 'primary' : 'grey-5'"
          />
        </div>
      </div>

      <!-- Left chunk-control gutter -->
      <div v-show="leftGutterVisible" class="chunk-gutter-wrapper">
        <div class="chunk-gutter">
          <div
            v-for="item in leftGutterItems"
            :key="item.chunkId"
            class="chunk-gutter-item"
            :class="{ 'chunk-gutter-item--text-hover': hoveredChunkId === item.chunkId }"
            :style="{ top: item.top + 'px', height: item.height + 'px' }"
            @mouseenter="hoveredChunkId = item.chunkId; if (!item.inCollection) hoveredPreviewChunkId = item.chunkId"
            @mouseleave="hoveredChunkId = null; hoveredPreviewChunkId = null"
          >
            <div
              class="chunk-bar"
              :class="item.inCollection ? 'chunk-bar--in' : 'chunk-bar--out'"
            />
            <div class="chunk-btn-group">
              <template v-if="item.inCollection">
                <q-btn
                  flat dense round
                  icon="remove_circle_outline"
                  color="negative"
                  size="sm"
                  class="chunk-toggle-btn"
                  :loading="chunkLoadingId === item.chunkId"
                  title="Remove from collection"
                  @click.stop="onRemoveChunkById(item.chunkId)"
                />
              </template>
              <template v-else>
                <q-btn
                  flat dense round
                  icon="add_circle_outline"
                  color="positive"
                  size="sm"
                  class="chunk-toggle-btn"
                  :loading="chunkLoadingId === item.chunkId"
                  title="Add to collection"
                  @click.stop="onAddChunkById(item.chunkId)"
                />
                <q-btn
                  flat dense round
                  icon="visibility_off"
                  color="grey"
                  size="sm"
                  class="chunk-toggle-btn chunk-hide-btn"
                  title="Hide chunk"
                  @click.stop="hideChunkById(item.chunkId)"
                />
              </template>
            </div>
            <span class="chunk-order-label">
              <span class="chunk-order-num">{{ item.order + 1 }}</span>
              <span class="chunk-order-total">/ {{ totalDocumentChunks ?? '?' }}</span>
            </span>
          </div>
        </div>
      </div>

      <q-card class="paper-card" :class="{ 'has-gutter': gutterItems.length > 0 }">
        <q-card-section class="paper-body">
          <!-- Expand previous — right above the text -->
          <div v-if="hasPrev" class="expand-row expand-row--top expand-row--col">
            <q-btn
              flat dense
              icon="vertical_align_top"
              :loading="loadingAllPrev"
              class="expand-btn"
              label="Load all previous"
              @click="loadAllNeighbours('prev')"
            />
            <q-btn
              flat dense
              icon="keyboard_arrow_up"
              :loading="loadingPrev"
              class="expand-btn"
              label="Load previous"
              @click="loadNeighbour('prev')"
            />
          </div>

          <div class="document-text" ref="documentTextRef" @mouseup="handleDocumentMouseUp($event)" @pointermove="onDocumentPointerMove" @pointerleave="hoveredPreviewChunkId = null">
            <template v-for="(group, gIndex) in assembledParagraphs" :key="gIndex">
              <p>
                <ChunkAnnotator
                  v-for="chunk in group.chunks"
                  :key="chunk.id"
                  :chunk-id="chunk.id"
                  :text="chunk.text"
                  :spans="annotations.getProjectedSpans(chunk.id).filter(s => tagNav.isTagVisible(s.tagId) && (aiTabActive || s.type !== SpanType.auto))"
                  :selection="annotations.getLocalSelection(chunk.id)"
                  :available-tags="tags"
                  :highlight-span-id="hoveredSpanId || highlightedAutoSpanId"
                  :class="{ 'chunk-preview': !chunk.inCollection, 'chunk-preview--active': !chunk.inCollection && hoveredPreviewChunkId === chunk.id }"
                  @boundary-drag="onBoundaryDrag"
                />
              </p>
              <!-- Gap buttons between non-consecutive chunks -->
              <div v-if="group.gapAfter !== null" class="gap-row">
                <q-btn
                  flat dense
                  icon="keyboard_arrow_down"
                  :loading="gapLoadingKey === `${group.gapAfter}:next`"
                  class="gap-btn"
                  label="Load next"
                  title="Load the chunk just after this gap"
                  @click="loadGap(group.gapAfter)"
                />
                <q-btn
                  flat dense
                  icon="unfold_more"
                  :loading="gapLoadingKey === `${group.gapAfter}:all`"
                  class="gap-btn gap-btn--all"
                  label="Load all missing"
                  title="Load all chunks in this gap"
                  @click="loadGapAll(group.gapAfter, group.gapBefore!)"
                />
                <q-btn
                  flat dense
                  icon="keyboard_arrow_up"
                  :loading="gapLoadingKey === `${group.gapBefore}:prev`"
                  class="gap-btn"
                  label="Load previous"
                  title="Load the chunk just before this gap"
                  @click="loadGapPrev(group.gapBefore!)"
                />
              </div>
            </template>
          </div>

          <!-- Expand next — right below the text -->
          <div v-if="hasNext" class="expand-row expand-row--bottom expand-row--col">
            <q-btn
              flat dense
              icon="keyboard_arrow_down"
              :loading="loadingNext"
              class="expand-btn"
              label="Load next"
              @click="loadNeighbour('next')"
            />
            <q-btn
              flat dense
              icon="vertical_align_bottom"
              :loading="loadingAllNext"
              class="expand-btn"
              label="Load all next"
              @click="loadAllNeighbours('next')"
            />
          </div>
        </q-card-section>
        <q-inner-loading :showing="loading" />
        <error-display v-if="error" :error="error" />
      </q-card>

      <!-- Span gutter -->
      <div class="span-gutter-wrapper" v-if="gutterItems.length" @wheel.prevent="onGutterWheel">
        <div class="span-gutter" :style="{ width: gutterWidth + 'px', height: gutterHeight + 'px' }">
          <div
            v-for="item in gutterItems"
            :key="item.spanId"
            class="gutter-item"
            :class="{ 'is-active': hoveredSpanId === item.spanId, 'is-auto': item.isAuto, 'is-highlighted': highlightedAutoSpanId === item.spanId }"
            :style="{
              top: item.top + 'px',
              height: item.height + 'px',
              left: item.column * 44 + 8 + 'px',
              '--tag-color': (tagInfoMap[item.tagId] || { color: '#3b82f6' }).color
            }"
            @mouseenter="hoveredSpanId = item.spanId"
            @mouseleave="hoveredSpanId = null"
            @click.stop="onGutterClick(item, $event)"
          >
            <div class="gutter-line" :style="{ backgroundColor: (tagInfoMap[item.tagId] || { color: '#3b82f6' }).color }"></div>
            <div class="gutter-label" :style="{ backgroundColor: (tagInfoMap[item.tagId] || { color: '#3b82f6' }).color }">
              <q-icon :name="(tagInfoMap[item.tagId] || { pictogram: 'label' }).pictogram" size="10px" class="gutter-icon" />
              {{ (tagInfoMap[item.tagId] || { shorthand: '?' }).shorthand }}
            </div>
          </div>
        </div>
      </div>

      <!-- Context popover — shows near the mouse when selection or editing -->
      <Teleport to="body">
        <div
          v-if="annotations.hasSelection.value"
          class="annotation-popover"
          :style="popoverStyle"
          @mousedown.stop
        >
          <!-- Close button -->
          <q-btn
            flat dense round
            icon="close"
            size="sm"
            class="popover-close"
            @click="annotations.clearSelection()"
          />

          <!-- Tag picker mode -->
          <template v-if="showTagPicker">
            <div class="popover-header">
              <span class="popover-title">Select tag</span>
              <q-btn flat dense round icon="arrow_back" size="sm" @click="showTagPicker = false" />
            </div>
            <q-input
              v-model="tagSearch"
              dense
              outlined
              placeholder="Search tags..."
              class="tag-search"
              autofocus
              clearable
            >
              <template #prepend>
                <q-icon name="search" size="xs" />
              </template>
            </q-input>
            <div class="tag-list">
              <div
                v-for="tag in filteredTags"
                :key="tag.id"
                class="tag-row"
                :class="{ 'is-active': annotations.selection.value?.tagId === tag.id }"
                @click="onTagClick(tag.id)"
              >
                <span class="tag-dot" :style="{ backgroundColor: tag.color }"></span>
                <span class="tag-name">{{ tag.name }}</span>
                <span class="tag-shorthand">{{ tag.shorthand }}</span>
              </div>
              <div v-if="filteredTags.length === 0" class="tag-row-empty">No tags found</div>
            </div>
          </template>

          <!-- Default action mode -->
          <template v-else>
            <div class="popover-actions">
              <!-- Approve / reject shortcut for auto spans (AI suggestions) -->
              <template v-if="editingAutoSpan">
                <q-btn
                  no-caps unelevated
                  icon="check"
                  label="Approve"
                  color="positive"
                  class="popover-btn"
                  :disable="approveRejectBusy"
                  @click="onApproveAutoSpan"
                />
                <q-btn
                  no-caps unelevated
                  icon="close"
                  label="Reject"
                  color="negative"
                  class="popover-btn"
                  :disable="approveRejectBusy"
                  @click="onRejectAutoSpan"
                />
              </template>
              <q-btn
                no-caps unelevated
                icon="sell"
                :label="annotations.isEditing.value ? 'Change tag' : 'Add tag'"
                color="primary"
                class="popover-btn"
                @click="showTagPicker = true"
              />
              <q-btn
                v-if="annotations.positionChanged.value"
                no-caps outline
                icon="save"
                label="Save"
                color="primary"
                class="popover-btn"
                @click="onSavePosition"
              />
              <q-btn
                v-if="annotations.isEditing.value"
                no-caps outline
                icon="delete"
                label="Delete"
                color="negative"
                class="popover-btn"
                @click="onDeleteSpan"
              />
              <!-- Cancel removed; close icon is at the top-right of the popover -->
            </div>
          </template>
        </div>
      </Teleport>

      <!-- Bulk selection action bar -->
      <Teleport to="body">
        <div v-if="selectedChunkIds.length > 0" class="bulk-action-bar">
          <span class="bulk-count">{{ selectedChunkIds.length }} selected</span>
          <q-btn
            flat dense no-caps
            label="All visible"
            size="md"
            color="grey-4"
            title="Select all visible chunks"
            @click="selectAllVisible"
          />
          <q-btn
            flat dense no-caps
            label="Not in collection"
            size="md"
            color="grey-4"
            title="Select all chunks not yet in the collection"
            @click="selectAllNotInCollection"
          />
          <div class="bulk-spacer" />
          <q-btn
            v-if="hasSelectedNotInCollection"
            flat dense no-caps
            icon="add_circle_outline"
            label="Add"
            color="positive"
            :loading="bulkLoading"
            title="Add selected chunks to collection"
            @click="onBulkAdd"
          />
          <q-btn
            v-if="hasSelectedInCollection"
            flat dense no-caps
            icon="remove_circle_outline"
            label="Remove"
            color="negative"
            :loading="bulkLoading"
            title="Remove selected chunks from collection"
            @click="onBulkRemove"
          />
          <q-btn
            flat dense round
            icon="close"
            size="md"
            color="grey-4"
            title="Clear selection"
            @click="clearChunkSelection"
          />
        </div>
      </Teleport>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import useChunks from 'src/composables/useChunks'
import useTags from 'src/composables/useTags'
import { useAnnotations } from 'src/composables/useAnnotations'
import useTagSpans from 'src/composables/useTagSpans'
import { SpanType } from 'src/generated/api'
import type { Chunk } from 'src/generated/api'
import { useTagNavigation } from 'src/composables/useTagNavigation'
import useAiAssistance from 'src/composables/useAiAssistance'
import ChunkAnnotator from 'src/components/ChunkAnnotator.vue'
import ErrorDisplay from 'src/components/custom/ErrorDisplay.vue'

/**
 * Resolve a DOM node + offset into { chunkId, charOffset } by walking up
 * to the nearest [data-chunk-id] and [data-start] elements.
 */
function resolveSelectionEndpoint(
  node: Node,
  offset: number
): { chunkId: string; charOffset: number } | null {
  // Find the .text-segment with data-start
  let segmentEl: HTMLElement | null = null
  let current: Node | null = node
  while (current) {
    if (current instanceof HTMLElement && current.dataset.start !== undefined) {
      segmentEl = current
      break
    }
    current = current.parentElement
  }
  if (!segmentEl) return null

  // Find the parent [data-chunk-id]
  let chunkEl: HTMLElement | null = segmentEl
  while (chunkEl && !chunkEl.dataset.chunkId) {
    chunkEl = chunkEl.parentElement
  }
  if (!chunkEl) return null

  const chunkId = chunkEl.dataset.chunkId!
  const segStart = parseInt(segmentEl.dataset.start || '0', 10)
  const charOffset = node.nodeType === Node.TEXT_NODE ? segStart + offset : segStart

  return { chunkId, charOffset }
}

const props = defineProps<{
  collectionId: string
  documentId: string
}>()

const { chunks, loading, error, loadChunksInCollectionDocument, addChunkToCollection, removeChunkFromCollection, getNeighbourChunk, countDocumentChunks, getChunksInRange } = useChunks()
const { tags, loadTagsByCollection } = useTags()

// Local display chunks — a superset of collection chunks plus any expanded previews
const displayChunks = ref<Chunk[]>([])

// Whether neighbour chunks exist in the DB beyond what we're showing
const hasPrev = ref(false)
const hasNext = ref(false)
const loadingPrev = ref(false)
const loadingNext = ref(false)
const loadingAllPrev = ref(false)
const loadingAllNext = ref(false)
const gapLoadingKey = ref<string | null>(null)

// Which chunk is currently being added/removed
const chunkLoadingId = ref<string | null>(null)

// Hidden chunks needed for cross-gap span projection (e.g. a span bridging a removed chunk)
const hiddenPreviewChunks = ref<Chunk[]>([])
// Sync displayChunks from store when initial load completes (handled in watch below)
const annotations = useAnnotations(() => displayChunks.value, () => hiddenPreviewChunks.value)
const tagSpans = useTagSpans()
const aiAssist = useAiAssistance()
const aiTabActive = computed(() => aiAssist.aiTabActive.value)
const highlightedAutoSpanId = computed(() => aiAssist.highlightedAutoSpanId.value)

// ── Approve/reject for AI-suggested (auto) spans ──
// Looks up the span being edited via the popover and exposes whether it has
// ``type === auto`` so the popover can offer Approve/Reject shortcuts.
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
    annotations.clearSelection()
  }
}

function onApproveAutoSpan() {
  void changeEditingSpanType(SpanType.pos)
}

function onRejectAutoSpan() {
  void changeEditingSpanType(SpanType.neg)
}

// ── Gutter state ──

interface GutterItem {
  spanId: string
  chunkId: string
  tagId: string
  start: number
  end: number
  top: number
  height: number
  column: number
  isAuto: boolean
}

const COLUMN_WIDTH = 44
const documentTextRef = ref<HTMLElement | null>(null)
const hoveredSpanId = ref<string | null>(null)
const gutterItems = ref<GutterItem[]>([])
const showTagPicker = ref(false)
const tagSearch = ref('')

// ── Left chunk-control gutter ──
interface LeftGutterItem {
  chunkId: string
  inCollection: boolean
  order: number
  top: number
  height: number
}
const leftGutterItems = ref<LeftGutterItem[]>([])
const totalDocumentChunks = ref<number | null>(null)
const leftGutterVisible = ref(true)

// ── Bulk selection ──
const selectedChunkIds = ref<string[]>([])
const bulkLoading = ref(false)
const loadingAllChunks = ref(false)

const displayedPreviewCount = computed(() => displayChunks.value.filter(c => !c.inCollection).length)

const hasSelectedInCollection = computed(() =>
  selectedChunkIds.value.some(id => displayChunks.value.find(c => c.id === id)?.inCollection)
)
const hasSelectedNotInCollection = computed(() =>
  selectedChunkIds.value.some(id => {
    const c = displayChunks.value.find(ch => ch.id === id)
    return c !== undefined && !c.inCollection
  })
)

function recalculateLeftGutter() {
  const container = documentTextRef.value
  if (!container) { leftGutterItems.value = []; return }
  const cardEl = container.closest('.paper-card') as HTMLElement | null
  if (!cardEl) { leftGutterItems.value = []; return }
  const cardRect = cardEl.getBoundingClientRect()
  const items: LeftGutterItem[] = []

  for (const chunk of displayChunks.value) {
    const chunkEl = container.querySelector(`[data-chunk-id="${chunk.id}"]`) as HTMLElement | null
    if (!chunkEl) continue
    const rect = chunkEl.getBoundingClientRect()
    items.push({
      chunkId: chunk.id,
      inCollection: chunk.inCollection ?? false,
      order: chunk.order,
      top: rect.top - cardRect.top,
      height: Math.max(rect.height, 24)
    })
  }
  leftGutterItems.value = items
}

// Helpers so the left gutter can call add/remove by id without a full Chunk ref
function onAddChunkById(chunkId: string) {
  const chunk = displayChunks.value.find(c => c.id === chunkId)
  if (chunk) onAddChunk(chunk)
}
function onRemoveChunkById(chunkId: string) {
  const chunk = displayChunks.value.find(c => c.id === chunkId)
  if (chunk) onRemoveChunk(chunk)
}

function hideChunkById(chunkId: string) {
  const chunk = displayChunks.value.find(c => c.id === chunkId)
  if (chunk && !chunk.inCollection) hiddenPreviewChunks.value.push(chunk)
  displayChunks.value = displayChunks.value.filter(c => c.id !== chunkId)
  void nextTick().then(() => { recalculateGutter(); void checkNeighbours() })
}

function toggleChunkSelection(chunkId: string) {
  const idx = selectedChunkIds.value.indexOf(chunkId)
  if (idx === -1) selectedChunkIds.value = [...selectedChunkIds.value, chunkId]
  else selectedChunkIds.value = selectedChunkIds.value.filter(id => id !== chunkId)
}

function clearChunkSelection() {
  selectedChunkIds.value = []
}

function hideAllPreviews() {
  const previews = displayChunks.value.filter(c => !c.inCollection)
  hiddenPreviewChunks.value = [...hiddenPreviewChunks.value, ...previews.filter(
    p => !hiddenPreviewChunks.value.find(h => h.id === p.id)
  )]
  displayChunks.value = displayChunks.value.filter(c => c.inCollection)
  void nextTick().then(() => { recalculateGutter(); void checkNeighbours() })
}

async function loadAllChunks() {
  loadingAllChunks.value = true
  try {
    const all = await getChunksInRange(props.collectionId, props.documentId)
    const merged = [...all]
    merged.sort((a, b) => a.order - b.order)
    displayChunks.value = merged.filter((c, i, arr) => arr.findIndex(x => x.id === c.id) === i)
    hiddenPreviewChunks.value = []
    hasPrev.value = false
    hasNext.value = false
    await nextTick()
    recalculateGutter()
  } finally {
    loadingAllChunks.value = false
  }
}

function selectAllVisible() {
  selectedChunkIds.value = displayChunks.value.map(c => c.id)
}

function selectAllNotInCollection() {
  selectedChunkIds.value = displayChunks.value.filter(c => !c.inCollection).map(c => c.id)
}

async function onBulkAdd() {
  bulkLoading.value = true
  try {
    const toAdd = selectedChunkIds.value.filter(id =>
      !displayChunks.value.find(c => c.id === id)?.inCollection
    )
    await Promise.all(toAdd.map(id => addChunkToCollection(id, props.collectionId)))
    displayChunks.value = displayChunks.value.map(c =>
      toAdd.includes(c.id) ? { ...c, inCollection: true } : c
    )
    for (const id of toAdd) {
      const lg = leftGutterItems.value.find(i => i.chunkId === id)
      if (lg) lg.inCollection = true
    }
    selectedChunkIds.value = []
  } finally {
    bulkLoading.value = false
  }
}

async function onBulkRemove() {
  bulkLoading.value = true
  try {
    const toRemove = selectedChunkIds.value.filter(id =>
      displayChunks.value.find(c => c.id === id)?.inCollection
    )
    await Promise.all(toRemove.map(id => removeChunkFromCollection(id, props.collectionId)))
    displayChunks.value = displayChunks.value.map(c =>
      toRemove.includes(c.id) ? { ...c, inCollection: false } : c
    )
    for (const id of toRemove) {
      const lg = leftGutterItems.value.find(i => i.chunkId === id)
      if (lg) lg.inCollection = false
    }
    selectedChunkIds.value = []
    await nextTick()
    recalculateGutter()
    await checkNeighbours()
  } finally {
    bulkLoading.value = false
  }
}

const hoveredPreviewChunkId = ref<string | null>(null)
const hoveredChunkId = ref<string | null>(null)

function onDocumentPointerMove(e: PointerEvent) {
  if (!documentTextRef.value) return
  for (const chunk of displayChunks.value) {
    const el = documentTextRef.value.querySelector(`[data-chunk-id="${chunk.id}"]`) as HTMLElement | null
    if (!el) continue
    const rect = el.getBoundingClientRect()
    if (e.clientX >= rect.left && e.clientX <= rect.right &&
        e.clientY >= rect.top && e.clientY <= rect.bottom) {
      hoveredChunkId.value = chunk.id
      if (!chunk.inCollection) hoveredPreviewChunkId.value = chunk.id
      else hoveredPreviewChunkId.value = null
      return
    }
  }
  hoveredChunkId.value = null
  hoveredPreviewChunkId.value = null
}

const filteredTags = computed(() => {
  const q = tagSearch.value.toLowerCase().trim()
  if (!q) return tags.value
  return tags.value.filter(t =>
    t.name.toLowerCase().includes(q) ||
    (t.shorthand && t.shorthand.toLowerCase().includes(q))
  )
})

// ── Popover positioning ──
const popoverPos = ref({ x: 0, y: 0 })

const popoverStyle = computed(() => ({
  position: 'fixed' as const,
  left: `${popoverPos.value.x}px`,
  top: `${popoverPos.value.y}px`,
  zIndex: 9999
}))

const updatePopoverPos = (e?: MouseEvent) => {
  if (e) {
    popoverPos.value = { x: e.clientX + 12, y: e.clientY - 8 }
  }
}
const tagInfoMap = computed(() => {
  const map: Record<string, { color: string; shorthand: string; pictogram: string }> = {}
  for (const tag of tags.value) {
    map[tag.id] = { color: tag.color, shorthand: tag.shorthand || tag.name.slice(0, 3), pictogram: tag.pictogram || 'label' }
  }
  return map
})

const gutterWidth = computed(() => {
  if (!gutterItems.value.length) return 0
  const maxCol = Math.max(...gutterItems.value.map(i => i.column))
  return (maxCol + 1) * COLUMN_WIDTH
})

const gutterHeight = computed(() => {
  if (!gutterItems.value.length) return 0
  return Math.max(...gutterItems.value.map(i => i.top + i.height))
})

function recalculateGutter() {
  const container = documentTextRef.value
  if (!container) { gutterItems.value = []; return }

  // Gutter wrapper is a flex sibling aligned to top of paper-card, so measure from card top
  const cardEl = container.closest('.paper-card') as HTMLElement | null
  if (!cardEl) { gutterItems.value = []; return }

  const cardRect = cardEl.getBoundingClientRect()
  const items: GutterItem[] = []

  for (const chunk of displayChunks.value) {
    const chunkSpans = annotations.spansByChunkId.value[chunk.id] || []

    for (const span of chunkSpans) {
      if (span.type === SpanType.neg || !span.id) continue
      if (!aiTabActive.value && span.type === SpanType.auto) continue
      if (!tagNav.isTagVisible(span.tagId)) continue

      let minTop = Infinity
      let maxBottom = -Infinity

      // Use all known chunks (display + hidden) so the gutter bar bridges gaps caused by removed chunks
      const allKnown = [...displayChunks.value, ...hiddenPreviewChunks.value]
        .filter((c, i, arr) => arr.findIndex(x => x.id === c.id) === i)
        .sort((a, b) => a.order - b.order)

      const startAllIndex = allKnown.findIndex(c => c.id === chunk.id)
      if (startAllIndex === -1) continue

      let remaining = span.end
      for (let ci = startAllIndex; ci < allKnown.length && remaining > 0; ci++) {
        // Stop only at true document gaps (no known chunk bridges it)
        if (ci > startAllIndex && allKnown[ci].order !== allKnown[ci - 1].order + 1) break
        const c = allKnown[ci]

        const offsetFromSpanChunk = ci === startAllIndex ? 0 : allKnown.slice(startAllIndex, ci).reduce((sum, ch) => sum + ch.text.length, 0)
        const localStart = ci === startAllIndex ? span.start : 0
        const localEnd = Math.min(c.text.length, span.end - offsetFromSpanChunk)

        const cEl = container.querySelector(`[data-chunk-id="${c.id}"]`) as HTMLElement | null
        if (cEl) {
          // Chunk is in the DOM — measure its text segments
          const segEls = cEl.querySelectorAll<HTMLElement>('.text-segment')
          for (const segEl of segEls) {
            const segStart = parseInt(segEl.dataset.start || '0')
            const segEnd = parseInt(segEl.dataset.end || '0')
            if (segStart < localEnd && segEnd > localStart) {
              const rect = segEl.getBoundingClientRect()
              minTop = Math.min(minTop, rect.top - cardRect.top)
              maxBottom = Math.max(maxBottom, rect.bottom - cardRect.top)
            }
          }
        }
        // Hidden gap chunk: no DOM element — subtract its length so remaining decreases correctly

        remaining -= c.text.length
      }

      if (minTop === Infinity) continue

      items.push({
        spanId: span.id,
        chunkId: chunk.id,
        tagId: span.tagId,
        start: span.start,
        end: span.end,
        top: minTop,
        height: Math.max(maxBottom - minTop, 20),
        column: 0,
        isAuto: span.type === SpanType.auto
      })
    }
  }

  // Assign columns (greedy — avoid vertical overlap)
  items.sort((a, b) => a.top - b.top)
  const columnBottoms: number[] = []

  for (const item of items) {
    let assigned = false
    for (let c = 0; c < columnBottoms.length; c++) {
      if (item.top >= columnBottoms[c] + 4) {
        columnBottoms[c] = item.top + item.height
        item.column = c
        assigned = true
        break
      }
    }
    if (!assigned) {
      item.column = columnBottoms.length
      columnBottoms.push(item.top + item.height)
    }
  }

  gutterItems.value = items
  recalculateLeftGutter()
}

const onGutterClick = (item: GutterItem, e: MouseEvent) => {
  annotations.editSpan({
    id: item.spanId,
    chunkId: item.chunkId,
    tagId: item.tagId,
    start: item.start,
    end: item.end
  })
  updatePopoverPos(e)
  showTagPicker.value = false
  tagSearch.value = ''

  // Sync nav index
  tagNav.syncIndex(item.tagId, item.spanId)

  // Two-way highlight with the AI panel: clicking an auto span in the gutter
  // should make its corresponding suggestion card light up (and scroll into
  // view inside the panel).
  if (item.isAuto) {
    aiAssist.highlightedAutoSpanId.value = item.spanId
  }
}

const onGutterWheel = (e: WheelEvent) => {
  const wrapper = (e.currentTarget as HTMLElement)
  wrapper.scrollLeft += e.deltaY
}

// ── Per-tag navigation (shared with drawer via composable) ──

const tagNav = useTagNavigation()

// Keep nav items in sync with gutter items
watch(gutterItems, (items, oldItems) => {
  tagNav.setItems(items.map(i => ({
    spanId: i.spanId,
    chunkId: i.chunkId,
    tagId: i.tagId,
    start: i.start,
    end: i.end
  })))
  // When the span gutter appears or disappears the paper-card width changes,
  // text reflows and chunk heights change → re-measure the left gutter
  if ((items.length > 0) !== (oldItems.length > 0)) {
    requestAnimationFrame(() => recalculateLeftGutter())
  }
})

// Register scroll & highlight callbacks
tagNav.onScroll((item) => {
  if (!documentTextRef.value) return
  const chunkEls = documentTextRef.value.querySelectorAll<HTMLElement>('[data-chunk-id]')
  for (const el of chunkEls) {
    if (el.dataset.chunkId !== item.chunkId) continue
    const segs = el.querySelectorAll<HTMLElement>('.text-segment')
    for (const seg of segs) {
      const s = parseInt(seg.dataset.start || '0')
      if (s >= item.start && s < item.end) {
        seg.scrollIntoView({ behavior: 'smooth', block: 'center' })
        return
      }
    }
  }
})
tagNav.onHighlight((spanId) => { hoveredSpanId.value = spanId })

// Re-render gutter (and re-filter auto spans in text) when the AI tab is
// toggled in the side panel.
watch(aiTabActive, () => {
  void nextTick(() => recalculateGutter())
})

// When the AI panel highlights a suggestion, scroll the document text to it.
watch(highlightedAutoSpanId, (spanId) => {
  if (!spanId || !documentTextRef.value) return
  // Find the span across known chunks.
  for (const chunkId of Object.keys(tagSpans.spansByChunkId.value)) {
    const span = (tagSpans.spansByChunkId.value[chunkId] || []).find(s => s.id === spanId)
    if (!span) continue
    const chunkEl = documentTextRef.value.querySelector(
      `[data-chunk-id="${chunkId}"]`
    ) as HTMLElement | null
    if (!chunkEl) return
    const segs = chunkEl.querySelectorAll<HTMLElement>('.text-segment')
    for (const seg of segs) {
      const s = parseInt(seg.dataset.start || '0')
      if (s >= span.start && s < span.end) {
        seg.scrollIntoView({ behavior: 'smooth', block: 'center' })
        return
      }
    }
    return
  }
})

// When the user clicks an auto span directly in the text (which selects it
// for the popover via `annotations.editSpan` from ChunkAnnotator), mirror that
// into the AI panel highlight so the matching suggestion card lights up.
watch(editingAutoSpan, (span) => {
  if (span?.id) aiAssist.highlightedAutoSpanId.value = span.id
})

/** Group chunks into paragraphs for rendering, but keep individual chunks accessible */
const assembledParagraphs = computed(() => {
  const paragraphs: { chunks: Chunk[]; gapAfter: number | null; gapBefore: number | null }[] = []
  let currentGroup: Chunk[] = []

  for (let i = 0; i < displayChunks.value.length; i++) {
    const chunk = displayChunks.value[i]
    currentGroup.push(chunk)

    const nextChunk = displayChunks.value[i + 1]
    const hasGap = nextChunk != null && nextChunk.order > chunk.order + 1

    // Close the paragraph group on endParagraph OR when there's a gap (so gap buttons can go between <p> tags)
    if (chunk.endParagraph || hasGap || !nextChunk) {
      paragraphs.push({
        chunks: [...currentGroup],
        gapAfter: hasGap ? chunk.order : null,
        gapBefore: hasGap ? nextChunk!.order : null
      })
      currentGroup = []
    }
  }

  if (currentGroup.length) {
    paragraphs.push({ chunks: currentGroup, gapAfter: null, gapBefore: null })
  }

  return paragraphs
})

const handleDocumentMouseUp = (e: MouseEvent) => {
  const domSelection = window.getSelection()
  if (!domSelection || domSelection.isCollapsed) return

  const range = domSelection.getRangeAt(0)
  const startPoint = resolveSelectionEndpoint(range.startContainer, range.startOffset)
  const endPoint = resolveSelectionEndpoint(range.endContainer, range.endOffset)

  if (!startPoint || !endPoint) return

  // Preserve editing context when re-selecting during edit mode
  const editingSpanId = annotations.selection.value?.editingSpanId
  const editingTagId = annotations.selection.value?.tagId

  if (startPoint.chunkId === endPoint.chunkId) {
    const start = Math.min(startPoint.charOffset, endPoint.charOffset)
    const end = Math.max(startPoint.charOffset, endPoint.charOffset)
    if (end > start) {
      annotations.setSelection(startPoint.chunkId, start, end, editingSpanId, editingTagId)
    }
  } else {
    annotations.setCrossChunkSelection(
      startPoint.chunkId, startPoint.charOffset,
      endPoint.chunkId, endPoint.charOffset,
      editingSpanId, editingTagId
    )
  }

  updatePopoverPos(e)
  showTagPicker.value = false
  tagSearch.value = ''
  domSelection.removeAllRanges()
}

const onTagClick = async (tagId: string) => {
  if (annotations.isEditing.value) {
    await annotations.updateSpanTag(tagId)
  } else {
    await annotations.createSpan(tagId)
  }
}

const onSavePosition = async () => {
  await annotations.updateSpanPosition()
}

const onBoundaryDrag = (payload: { chunkId: string; handle: 'start' | 'end'; charOffset: number }) => {
  annotations.adjustSelectionBoundary(payload.handle, payload.chunkId, payload.charOffset)
}

const onDeleteSpan = async () => {
  await annotations.deleteSpan()
}

// Load data + recalculate gutter
let resizeObserver: ResizeObserver | null = null

// ── Check if neighbours exist ──
async function checkNeighbours() {
  if (!displayChunks.value.length) { hasPrev.value = false; hasNext.value = false; return }
  const minOrder = Math.min(...displayChunks.value.map(c => c.order))
  const maxOrder = Math.max(...displayChunks.value.map(c => c.order))
  const [prev, next] = await Promise.all([
    getNeighbourChunk(props.collectionId, props.documentId, 'prev', minOrder),
    getNeighbourChunk(props.collectionId, props.documentId, 'next', maxOrder)
  ])
  hasPrev.value = prev !== null
  hasNext.value = next !== null
}

// ── Pre-load gap chunks for cross-gap span rendering ──
// Fetches chunks that sit in document gaps between displayed chunks and stores
// them in hiddenPreviewChunks so useAnnotations can do correct offset math.
async function preloadGapChunks() {
  const display = displayChunks.value
  const fetches: Promise<void>[] = []
  for (let i = 0; i < display.length - 1; i++) {
    if (display[i + 1].order === display[i].order + 1) continue
    const afterOrder = display[i].order
    const beforeOrder = display[i + 1].order
    fetches.push(
      getChunksInRange(props.collectionId, props.documentId, afterOrder, beforeOrder)
        .then(gaps => {
          for (const g of gaps) {
            if (!hiddenPreviewChunks.value.find(h => h.id === g.id) &&
                !displayChunks.value.find(d => d.id === g.id)) {
              hiddenPreviewChunks.value.push(g)
            }
          }
        })
        .catch(e => console.warn('preloadGapChunks failed:', e))
    )
  }
  await Promise.all(fetches)
}

// ── Load all neighbouring chunks in one direction ──
async function loadAllNeighbours(direction: 'prev' | 'next') {
  if (direction === 'prev') loadingAllPrev.value = true
  else loadingAllNext.value = true
  try {
    const boundary = direction === 'prev'
      ? Math.min(...displayChunks.value.map(c => c.order))
      : Math.max(...displayChunks.value.map(c => c.order))
    const chunks = await getChunksInRange(
      props.collectionId,
      props.documentId,
      direction === 'next' ? boundary : null,
      direction === 'prev' ? boundary : null
    )
    if (chunks.length) {
      if (direction === 'prev') {
        displayChunks.value = [...chunks, ...displayChunks.value]
      } else {
        displayChunks.value = [...displayChunks.value, ...chunks]
      }
    }
    await nextTick()
    recalculateGutter()
    if (direction === 'prev') hasPrev.value = false
    else hasNext.value = false
  } finally {
    if (direction === 'prev') loadingAllPrev.value = false
    else loadingAllNext.value = false
  }
}

// ── Load a neighbouring chunk into the display list ──
async function loadNeighbour(direction: 'prev' | 'next') {
  if (direction === 'prev') loadingPrev.value = true
  else loadingNext.value = true
  try {
    const boundaryOrder = direction === 'prev'
      ? Math.min(...displayChunks.value.map(c => c.order))
      : Math.max(...displayChunks.value.map(c => c.order))
    const chunk = await getNeighbourChunk(props.collectionId, props.documentId, direction, boundaryOrder)
    if (!chunk) {
      if (direction === 'prev') hasPrev.value = false
      else hasNext.value = false
      return
    }
    if (direction === 'prev') {
      displayChunks.value = [chunk, ...displayChunks.value]
    } else {
      displayChunks.value = [...displayChunks.value, chunk]
    }
    await nextTick()
    recalculateGutter()
    // Only re-check the direction we loaded — the other side couldn't have changed
    const newBoundary = direction === 'prev'
      ? Math.min(...displayChunks.value.map(c => c.order))
      : Math.max(...displayChunks.value.map(c => c.order))
    const further = await getNeighbourChunk(props.collectionId, props.documentId, direction, newBoundary)
    if (direction === 'prev') hasPrev.value = further !== null
    else hasNext.value = further !== null
  } finally {
    if (direction === 'prev') loadingPrev.value = false
    else loadingNext.value = false
  }
}

// ── Load a single chunk just after afterOrder (into the gap) ──
async function loadGap(afterOrder: number) {
  gapLoadingKey.value = `${afterOrder}:next`
  try {
    const chunk = await getNeighbourChunk(props.collectionId, props.documentId, 'next', afterOrder)
    if (!chunk) return
    const idx = displayChunks.value.findIndex(c => c.order === afterOrder)
    if (idx === -1) return
    displayChunks.value = [
      ...displayChunks.value.slice(0, idx + 1),
      chunk,
      ...displayChunks.value.slice(idx + 1)
    ]
    await nextTick()
    recalculateGutter()
  } finally {
    gapLoadingKey.value = null
  }
}

// ── Load a single chunk just before beforeOrder (into the gap) ──
async function loadGapPrev(beforeOrder: number) {
  // gapAfter is the order of the last chunk before the gap; we need the boundary
  // We search by the order of the first chunk after the gap
  gapLoadingKey.value = `${beforeOrder}:prev`
  try {
    const chunk = await getNeighbourChunk(props.collectionId, props.documentId, 'prev', beforeOrder)
    if (!chunk) return
    const idx = displayChunks.value.findIndex(c => c.order === beforeOrder)
    if (idx === -1) return
    displayChunks.value = [
      ...displayChunks.value.slice(0, idx),
      chunk,
      ...displayChunks.value.slice(idx)
    ]
    await nextTick()
    recalculateGutter()
  } finally {
    gapLoadingKey.value = null
  }
}

// ── Load all missing chunks between afterOrder and beforeOrder ──
async function loadGapAll(afterOrder: number, beforeOrder: number) {
  gapLoadingKey.value = `${afterOrder}:all`
  try {
    const newChunks = await getChunksInRange(
      props.collectionId,
      props.documentId,
      afterOrder,
      beforeOrder
    )
    if (newChunks.length) {
      const idx = displayChunks.value.findIndex(c => c.order === afterOrder)
      if (idx !== -1) {
        displayChunks.value = [
          ...displayChunks.value.slice(0, idx + 1),
          ...newChunks,
          ...displayChunks.value.slice(idx + 1)
        ]
      }
    }
    await nextTick()
    recalculateGutter()
  } finally {
    gapLoadingKey.value = null
  }
}

// ── Add / remove chunk from collection ──
async function onAddChunk(chunk: Chunk) {
  chunkLoadingId.value = chunk.id
  try {
    await addChunkToCollection(chunk.id, props.collectionId)
    const idx = displayChunks.value.findIndex(c => c.id === chunk.id)
    if (idx !== -1) {
      displayChunks.value = [
        ...displayChunks.value.slice(0, idx),
        { ...displayChunks.value[idx], inCollection: true },
        ...displayChunks.value.slice(idx + 1)
      ]
      // Sync left gutter inCollection flag without full recalculate
      const lg = leftGutterItems.value.find(i => i.chunkId === chunk.id)
      if (lg) lg.inCollection = true
    }
  } finally {
    chunkLoadingId.value = null
  }
}

async function onRemoveChunk(chunk: Chunk) {
  chunkLoadingId.value = chunk.id
  try {
    await removeChunkFromCollection(chunk.id, props.collectionId)
    // Keep chunk visible as a preview (inCollection = false), only hide on explicit hide action
    const idx = displayChunks.value.findIndex(c => c.id === chunk.id)
    if (idx !== -1) {
      displayChunks.value = [
        ...displayChunks.value.slice(0, idx),
        { ...displayChunks.value[idx], inCollection: false },
        ...displayChunks.value.slice(idx + 1)
      ]
      const lg = leftGutterItems.value.find(i => i.chunkId === chunk.id)
      if (lg) lg.inCollection = false
    }
    await nextTick()
    recalculateGutter()
    await checkNeighbours()
  } finally {
    chunkLoadingId.value = null
  }
}

watch(
  () => chunks.value,
  async (newChunks) => {
    if (newChunks.length) {
      displayChunks.value = [...newChunks]
      await annotations.loadAllSpans(props.collectionId)
      await preloadGapChunks()
      await nextTick()
      recalculateGutter()
      await checkNeighbours()
    }
  }
)

watch(
  () => annotations.spansByChunkId.value,
  () => nextTick(recalculateGutter),
  { deep: true }
)

watch(
  () => tagNav.hiddenTagIds.size,
  () => nextTick(recalculateGutter)
)

// When prev/next expand-rows appear/disappear they shift the text — remeasure
watch([hasPrev, hasNext], () => nextTick(() => requestAnimationFrame(recalculateGutter)))

watch(
  () => annotations.selection.value?.tagId,
  (tagId) => tagNav.setActiveTagId(tagId ?? null)
)

// ── Dismiss on click-outside / Escape ──

const onClickOutside = (e: MouseEvent) => {
  if (!annotations.hasSelection.value) return
  const target = e.target as HTMLElement
  // Don't dismiss if clicking inside the popover or document text area
  const popover = document.querySelector('.annotation-popover')
  if (popover?.contains(target)) return
  if (documentTextRef.value?.contains(target)) return
  annotations.clearSelection()
}

const onEscape = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && annotations.hasSelection.value) {
    annotations.clearSelection()
  }
}

onMounted(async () => {
  await Promise.all([
    loadTagsByCollection(props.collectionId),
    loadChunksInCollectionDocument(props.collectionId, props.documentId)
  ])

  void countDocumentChunks(props.documentId).then(n => { totalDocumentChunks.value = n })

  await nextTick()
  if (documentTextRef.value) {
    resizeObserver = new ResizeObserver(() => {
      requestAnimationFrame(() => recalculateGutter())
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

.paper-header {
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
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

/* Dim non-collection preview chunks slightly */
:deep(.chunk-preview) {
  opacity: 0.6;
  transition: opacity 0.15s;
}
:deep(.chunk-preview.chunk-preview--active) {
  opacity: 1;
}

/* ── Left chunk-control gutter ── */

.chunk-gutter-wrapper {
  width: 52px;
  flex-shrink: 0;
  position: relative;
  background: #ffffff;
  min-height: calc(100vh - 160px);
}

.chunk-gutter {
  position: relative;
  width: 100%;
  height: 100%;
}

.chunk-gutter-item {
  position: absolute;
  left: 0;
  right: 0;
  display: flex;
  align-items: flex-start;
  padding-top: 2px;
  gap: 4px;
}

.chunk-btn-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  opacity: 0;
  transition: opacity 0.15s;
  flex-shrink: 0;
  position: absolute;
  left: 5px;
  top: 30px;
  z-index: 1;
}

.chunk-gutter-item:hover .chunk-btn-group,
.chunk-gutter-item--text-hover .chunk-btn-group {
  opacity: 1;
}

.chunk-order-label {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.2;
  color: #64748b;
  white-space: nowrap;
  flex-shrink: 0;
  transition: opacity 0.15s;
  padding-top: 1px;
}

.chunk-order-num {
  font-size: 13px;
  font-weight: 600;
}

.chunk-order-total {
  font-size: 11px;
  color: #94a3b8;
}

.chunk-bar {
  width: 4px;
  border-radius: 2px;
  flex-shrink: 0;
  align-self: stretch;
  min-height: 20px;
  transition: opacity 0.15s;
}

.chunk-bar--in {
  background: #22c55e;
  opacity: 0.7;
}

.chunk-bar--out {
  background: #cbd5e1;
  opacity: 0.5;
}

.chunk-gutter-item:hover .chunk-bar {
  opacity: 1;
}

.chunk-toggle-btn {
  flex-shrink: 0;
}

/* order label stays visible on hover */

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

.annotation-popover {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 8px;
  padding-top: 28px;
  background: #ffffff;
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(15, 23, 42, 0.18);
  border: 1px solid rgba(15, 23, 42, 0.08);
  min-width: 180px;
  max-width: 280px;
}

.popover-close {
  position: absolute;
  top: 4px;
  right: 6px;
  z-index: 1;
  font-size: 1.1em;
}

.popover-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}

.popover-btn {
  width: 100%;
  justify-content: flex-start;
  font-size: 0.85rem;
  font-weight: 500;
  min-height: 36px;
  border-radius: 8px;
  padding: 4px 14px;
}

.popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-bottom: 2px;
}

.popover-title {
  font-size: 0.78rem;
  font-weight: 600;
  color: #64748b;
}

.tag-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 200px;
  overflow-y: auto;
}

.tag-search {
  width: 100%;
  margin-bottom: 4px;
}

.tag-search :deep(.q-field__control) {
  min-height: 32px;
}

.tag-row-empty {
  padding: 8px;
  text-align: center;
  font-size: 0.78rem;
  color: #94a3b8;
}

.tag-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.12s;
}

.tag-row:hover {
  background: #f1f5f9;
}

.tag-row.is-active {
  background: #e0f2fe;
}

.tag-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tag-name {
  font-size: 0.82rem;
  font-weight: 500;
  color: #1e293b;
  flex: 1;
}

.tag-shorthand {
  font-size: 0.72rem;
  color: #94a3b8;
  font-weight: 500;
}

/* ── Span gutter ── */

.span-gutter-wrapper {
  flex: 1;
  min-width: 60px;
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  background: #ffffff;
  border-radius: 0 16px 16px 0;
  box-shadow: none;
}

.span-gutter-wrapper::-webkit-scrollbar {
  height: 6px;
}

.span-gutter-wrapper::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.04);
  border-radius: 3px;
  margin: 0 4px;
}

.span-gutter-wrapper::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.18);
  border-radius: 3px;
}

.span-gutter-wrapper::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.3);
}

.span-gutter {
  position: relative;
  min-width: 100%;
  padding: 0 4px;
}

.gutter-item {
  position: absolute;
  width: 40px;
  cursor: pointer;
}

.gutter-line {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-radius: 2px;
  opacity: 0.7;
  transition: opacity 0.15s;
}

.gutter-item:hover .gutter-line,
.gutter-item.is-active .gutter-line {
  opacity: 1;
}

.gutter-label {
  position: absolute;
  left: 8px;
  top: 0;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  color: #fff;
  white-space: nowrap;
  line-height: 1.4;
  opacity: 0.8;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
  transition: opacity 0.15s;
}

.gutter-icon {
  opacity: 0.9;
}

.gutter-item:hover .gutter-label,
.gutter-item.is-active .gutter-label {
  opacity: 1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}

/* ── Auto (AI-suggested) gutter items: muted, dashed, slightly faded. ── */
.gutter-item.is-auto .gutter-line {
  /* Replace solid colour with a dashed strip so users can spot at a glance
     that this is an unconfirmed AI suggestion. The inline `backgroundColor`
     (tag colour) is intentionally overridden — but we need to use
     `background-image` only (not the `background` shorthand) so the inline
     `background-color` isn't wiped, which would make the bar disappear
     whenever we re-enable it (e.g. on highlight). */
  background-image: repeating-linear-gradient(
    to bottom,
    currentColor 0,
    currentColor 4px,
    transparent 4px,
    transparent 8px
  ) !important;
  background-color: transparent !important;
  color: #94a3b8;
  opacity: 0.55;
  filter: grayscale(0.6);
}

.gutter-item.is-auto .gutter-label {
  background-color: #94a3b8 !important;
  opacity: 0.7;
  filter: grayscale(0.5);
}

.gutter-item.is-auto:hover .gutter-line,
.gutter-item.is-auto.is-active .gutter-line {
  opacity: 0.85;
}

.gutter-item.is-auto:hover .gutter-label,
.gutter-item.is-auto.is-active .gutter-label {
  opacity: 0.95;
}

/* Two-way highlight with the AI suggestions panel: when a card is selected
   in the panel, emphasize the gray dashed marker (darker color, full
   opacity) without restoring the tag's full colour. The same class is
   added when the user clicks an auto span in the text/gutter so the panel
   mirrors the choice. */
.gutter-item.is-auto.is-highlighted .gutter-line {
  color: #475569;
  opacity: 1;
  filter: none;
}

.gutter-item.is-auto.is-highlighted .gutter-label {
  background-color: #475569 !important;
  opacity: 1;
  filter: none;
}

/* ── Chunk selection checkbox column ── */

.chunk-checkbox-col {
  width: 22px;
  flex-shrink: 0;
  position: relative;
  background: #ffffff;
  min-height: calc(100vh - 160px);
}

.chunk-checkbox-item {
  position: absolute;
  left: 0;
  right: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 2px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s;
}

/* Show on direct hover of checkbox column, when something is selected, or when this item is checked */
.chunk-checkbox-col.is-active .chunk-checkbox-item,
.chunk-checkbox-item.is-checked,
.chunk-checkbox-item.is-hovered,
.chunk-checkbox-item:hover {
  opacity: 1;
}

/* ── Bulk action bar ── */

.bulk-action-bar {
  position: fixed;
  bottom: 28px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  background: #1c2636;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.28);
  z-index: 9000;
  white-space: nowrap;
}

.bulk-count {
  font-size: 0.92rem;
  font-weight: 600;
  padding: 0 10px;
  color: #f1f5f9;
}

.bulk-spacer {
  min-width: 12px;
  flex: 1;
}

/* ── Paper view-mode toolbar ── */

.paper-toolbar-row {
  display: flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  position: sticky;
  top: 96px;
  z-index: 200;
  margin-top: 8px;
}

.paper-view-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 6px;
  background: #ffffff;
  border-radius: 10px;
  border: 2px solid rgb(202, 202, 202);
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.14);
}

.view-btn {
  color: #64748b;
  font-size: 0.78rem;
  border-radius: 6px;
}

.view-btn--active {
  color: #1d4ed8;
  background: #eff6ff;
}
</style>
